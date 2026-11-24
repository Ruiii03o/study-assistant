"""Derive mistake history from scored attempts; retries keep immutable questions."""
import json
import secrets
import time
from collections import Counter, defaultdict

from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field
from backend import exams
from backend.scoring import maximum


class RetryInput(BaseModel):
    question_ids: list[str] = Field(min_length=1, max_length=20)
    request_id: str = Field(min_length=16, max_length=64, pattern=r'^[A-Za-z0-9_-]+$')


def mistake_items(records):
    roots, retries = [], defaultdict(list)
    for record in records:
        if record['parent_id']:
            retries[record['parent_id']].append(record)
        elif record['status'] == 'submitted':
            roots.append(record)
    items, ungraded = [], 0
    for root in roots:
        original_grades = {g['id']:g for g in json.loads(root['result'])['questions']}
        root_answers = json.loads(root['answers'])
        children = retries[root['id']]
        for question in json.loads(root['questions']):
            qid = question['id']
            first = original_grades[qid]
            attempts = [{'practice_id':root['id'], 'score':first['score'], 'mode':first['mode'],
                         'answer':root_answers.get(qid,[]), 'submitted_at':root['submitted_at'], 'is_retry':False}]
            pending = None
            for child in children:
                if not any(q['id'] == qid for q in json.loads(child['questions'])):
                    continue
                if child['status'] == 'ready':
                    pending = child['id']
                elif child['status'] == 'submitted':
                    grade = next(g for g in json.loads(child['result'])['questions'] if g['id'] == qid)
                    attempts.append({'practice_id':child['id'], 'score':grade['score'], 'mode':grade['mode'],
                                     'answer':json.loads(child['answers']).get(qid,[]), 'submitted_at':child['submitted_at'], 'is_retry':True})
            attempts[1:] = sorted(attempts[1:],key=lambda a:(a['submitted_at'],a['practice_id']))
            if not any(a['score'] is not None and a['score'] < maximum(question) for a in attempts):
                if attempts[-1]['score'] is None:
                    ungraded += 1
                continue
            latest = attempts[-1]
            state = 'pending_review' if latest['score'] is None else 'full_score' if latest['score'] == maximum(question) else 'needs_practice'
            source_ids = set(question['source_ids'])
            items.append({'variant_of':root.get('variant_of'), 'practice_id':root['id'], 'practice_title':('模拟考试 · ' if root.get('attempt_kind')=='exam' else '')+root['title'], 'question':question,
                          'first_score':first['score'], 'first_mode':first['mode'], 'latest_score':latest['score'],
                          'latest_mode':latest['mode'], 'latest_practice_id':latest['practice_id'],
                          'state':state, 'pending_retry_id':pending, 'retry_count':len(attempts)-1,
                          'attempts':attempts, 'sources':[s for s in json.loads(root['sources']) if s['source_id'] in source_ids]})
    items.sort(key=lambda item: (item['attempts'][-1]['submitted_at'], item['latest_practice_id']), reverse=True)
    return {'items':items, 'summary':{'total':len(items), 'ungraded_excluded':ungraded,
            **{state:sum(item['state'] == state for item in items) for state in ('needs_practice','full_score','pending_review')}}}


def register_mistake_routes(app, db, current_user, get_course, owned):
    with db() as conn:
        if 'parent_id' not in {r['name'] for r in conn.execute('PRAGMA table_info(practices)')}:
            conn.execute('ALTER TABLE practices ADD COLUMN parent_id TEXT REFERENCES practices(id)')
        conn.execute('CREATE INDEX IF NOT EXISTS practices_parent ON practices(owner_id,course_id,parent_id)')

    @app.get('/api/courses/{course_id}/mistakes')
    def list_mistakes(course_id: int, user=Depends(current_user)):
        get_course(course_id,user)
        with db() as conn:
            exams.expire(conn,user['id'])
            records = [dict(r) for r in conn.execute("SELECT * FROM practices WHERE owner_id=? AND course_id=? AND status IN ('submitted','ready') ORDER BY created_at DESC",(user['id'],course_id))]
        return mistake_items(records)

    @app.post('/api/practices/{practice_id}/retry', status_code=201)
    def retry(practice_id: str, body: RetryInput, user=Depends(current_user)):
        with db() as conn:
            conn.execute('BEGIN IMMEDIATE')
            original = owned(conn,practice_id,user)
            root_id = original['parent_id'] or original['id']
            root = owned(conn,root_id,user)
            if root['status'] != 'submitted':
                raise HTTPException(409,'请先交卷并完成评分，再从错题本重做')
            selected = set(body.question_ids)
            previous = conn.execute('SELECT * FROM practices WHERE owner_id=? AND request_id=?',(user['id'],body.request_id)).fetchone()
            if previous:
                if previous['parent_id'] != root_id or {q['id'] for q in json.loads(previous['questions'])} != selected:
                    raise HTTPException(409,'该请求编号已用于其他练习，请刷新后重试')
                return {'id':previous['id'],'status':previous['status']}
            children = [dict(r) for r in conn.execute('SELECT * FROM practices WHERE parent_id=? AND owner_id=? ORDER BY created_at', (root_id,user['id']))]
            wrong = {item['question']['id'] for item in mistake_items([root,*children])['items']}
            if not selected <= wrong:
                raise HTTPException(422,'只能选择错题本中已评分的题目；满分且无错题记录或尚未评分的题目不能加入')
            for child in children:
                if child['status'] != 'ready':
                    continue
                existing = {q['id'] for q in json.loads(child['questions'])}
                if selected == existing:
                    return {'id':child['id'],'status':'ready'}
                if selected & existing:
                    raise HTTPException(409,'所选题目已有未交卷的重做，请先从错题本继续作答')
            questions = [q for q in json.loads(root['questions']) if q['id'] in selected]
            refs = {ref for q in questions for ref in q['source_ids']}
            sources = [s for s in json.loads(root['sources']) if s['source_id'] in refs]
            material_ids = {s['material_id'] for s in sources}
            versions = {mid:v for mid,v in json.loads(root['versions']).items() if mid in material_ids}
            chapters = [r for r in json.loads(root['selected_chapters']) if any(s['material_id'] == r['material_id'] and r['unit_index'] <= s['unit_index'] <= r['end_unit_index'] for s in sources)]
            retry_id = secrets.token_hex(16)
            conn.execute('''INSERT INTO practices(id,owner_id,course_id,request_id,status,title,model,counts,sources,versions,selected_chapters,questions,created_at,parent_id)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                (retry_id,user['id'],root['course_id'],body.request_id,'ready','原题重做 · '+root['title'],root['model'],
                 json.dumps(dict(Counter(q['kind'] for q in questions))),json.dumps(sources,ensure_ascii=False),json.dumps(versions),
                 json.dumps(chapters,ensure_ascii=False),json.dumps(questions,ensure_ascii=False),time.time(),root_id))
            return {'id':retry_id,'status':'ready'}
