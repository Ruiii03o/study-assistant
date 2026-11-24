"""Versioned private practice sessions, draft saves and idempotent submission."""
import json
import secrets
import time
from typing import Annotated, Literal
from backend.scoring import maximum, point_score

from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field, model_validator
from backend import ai, practice_ai, review_ai, practice_pipeline, exams
from backend.batching import split_sources, pack_sources


class PracticeInput(BaseModel):
    exam_minutes: int | None = Field(default=None, strict=True, ge=1, le=180)
    material_ids: list[str] = Field(min_length=1, max_length=20)
    chapter_keys: list[str] = Field(min_length=1, max_length=2000)
    counts: dict[practice_ai.Kind, Annotated[int, Field(strict=True, ge=0, le=20)]]
    request_id: str = Field(min_length=16, max_length=64, pattern=r'^[A-Za-z0-9_-]+$')

    @model_validator(mode='after')
    def count_limit(self):
        if not 1 <= sum(self.counts.values()) <= 20:
            raise ValueError('每次练习总题量须为1至20题')
        return self


class AnswersInput(BaseModel):
    revision: int = Field(ge=0)
    answers: dict[str, Annotated[list[Annotated[str, Field(max_length=4000)]], Field(max_length=6)]] = Field(max_length=100)


class AIReviewInput(BaseModel):
    question_id: str = Field(min_length=1, max_length=20)


class ReviewInput(BaseModel):
    revision: int = Field(ge=0)
    scores: dict[str, Annotated[float, Field(strict=True, ge=0, le=100, allow_inf_nan=False)]] = Field(default_factory=dict, max_length=100)
    point_verdicts: dict[str, list[Literal['met','partial','missed']]] = Field(default_factory=dict,max_length=100)


def validate_answers(questions, answers):
    known = {q['id']:q for q in questions}
    if set(answers) - known.keys():
        raise HTTPException(422, '答案包含不属于本次练习的题目')
    result = {}
    for qid, values in answers.items():
        q = known[qid]
        if len(values) > 6 or len(set(values)) != len(values):
            raise HTTPException(422, '答案重复或数量超限')
        if q['kind'] in ('single', 'multiple', 'true_false'):
            allowed = set(('正确', '错误')) if q['kind'] == 'true_false' else set('ABCDEF'[:len(q['options'])])
            if not set(values) <= allowed or (q['kind'] != 'multiple' and len(values) > 1):
                raise HTTPException(422, '所选答案不符合题型或选项范围')
        elif len(values) > 1:
            raise HTTPException(422, '填空和简答须提交一段文字')
        result[qid] = values
    return result


def register_practice_routes(app, db, current_user, get_course, collect_sources, material_version):
    with db() as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS practices(
            id TEXT PRIMARY KEY, owner_id INTEGER NOT NULL REFERENCES users(id),
            course_id INTEGER NOT NULL REFERENCES courses(id), request_id TEXT NOT NULL,
            status TEXT NOT NULL, title TEXT NOT NULL DEFAULT '', model TEXT NOT NULL,
            counts TEXT NOT NULL, sources TEXT NOT NULL, versions TEXT NOT NULL, selected_chapters TEXT NOT NULL,
            questions TEXT NOT NULL DEFAULT '[]', answers TEXT NOT NULL DEFAULT '{}', result TEXT,
            revision INTEGER NOT NULL DEFAULT 0, message TEXT NOT NULL DEFAULT '',
            created_at REAL NOT NULL, submitted_at REAL, UNIQUE(owner_id,request_id))''')

    with db() as conn:
        if 'generation_started' not in {r['name'] for r in conn.execute('PRAGMA table_info(practices)')}:
            conn.execute('ALTER TABLE practices ADD COLUMN generation_started REAL')
        exams.migrate(conn)
        conn.execute("""CREATE TABLE IF NOT EXISTS practice_reviews(
            practice_id TEXT NOT NULL REFERENCES practices(id), question_id TEXT NOT NULL,
            status TEXT NOT NULL, token TEXT NOT NULL, started_at REAL NOT NULL,
            model TEXT NOT NULL, feedback TEXT, message TEXT NOT NULL DEFAULT '',
            PRIMARY KEY(practice_id,question_id))""")

    def expire(conn):
        exams.expire(conn)
        practice_pipeline.expire(conn)
        conn.execute("UPDATE practice_reviews SET status='failed',message='批改中断或超时，原有分数保留，可重试本题' WHERE status='running' AND started_at<?", (time.time()-300,))
        conn.execute("UPDATE practices SET status='failed',message='生成中断或超时，请刷新记录确认后再创建练习' WHERE status='generating' AND COALESCE(generation_started,created_at)<?", (time.time()-300,))

    def owned(conn, practice_id, user):
        row = conn.execute('SELECT * FROM practices WHERE id=? AND owner_id=?', (practice_id,user['id'])).fetchone()
        if not row:
            raise HTTPException(404, '练习不存在')
        return dict(row)

    def public_record(row, conn):
        result = {k:row[k] for k in ('id','course_id','status','title','model','message','created_at','submitted_at','revision','parent_id','attempt_kind','duration_seconds','started_at','deadline','submission_reason')}
        if row['attempt_kind']=='exam': result['server_time']=exams.now()
        result.update({k:json.loads(row[k]) for k in ('counts','selected_chapters','answers')})
        result['variant_of'] = row.get('variant_of')
        result['retained_questions'] = len(json.loads(row['questions'])) if row['status']=='failed' else 0
        result['pipeline'] = practice_pipeline.progress(conn,row['id'])
        result['stale'] = False
        for mid, version in json.loads(row['versions']).items():
            material = conn.execute('SELECT * FROM materials WHERE id=? AND owner_id=?', (mid,row['owner_id'])).fetchone()
            if not material or material_version(material) != version:
                result['stale'] = True
        questions = json.loads(row['questions'])
        if row['status'] == 'submitted':
            result['questions'] = questions
            result['sources'] = json.loads(row['sources'])
            result['result'] = json.loads(row['result'])
            result['ai_reviews'] = {}
            for review in conn.execute('SELECT question_id,status,model,feedback,message FROM practice_reviews WHERE practice_id=?', (row['id'],)):
                item = dict(review)
                item['feedback'] = json.loads(item['feedback']) if item['feedback'] else None
                result['ai_reviews'][item.pop('question_id')] = item
        else:
            # Never deliver the answer key or explanation before submission.
            result['questions'] = [] if row['attempt_kind']=='exam' and row['started_at'] is None else [{**{k:q[k] for k in ('id','kind','prompt','options')}, **({k:q[k] for k in ('max_score','scoring_version')} if q.get('scoring_version')==2 else {})} for q in questions]
        return result

    @app.get('/api/courses/{course_id}/practices')
    def list_practices(course_id: int, user=Depends(current_user)):
        get_course(course_id, user)
        with db() as conn:
            expire(conn)
            return [dict(r) for r in conn.execute('SELECT id,title,status,message,created_at,parent_id,attempt_kind,started_at,deadline FROM practices WHERE course_id=? AND owner_id=? ORDER BY created_at DESC', (course_id,user['id']))]

    @app.post('/api/courses/{course_id}/practices', status_code=201)
    def create_practice(course_id: int, body: PracticeInput, user=Depends(current_user)):
        course = get_course(course_id, user)
        with db() as conn:
            expire(conn)
            previous = conn.execute('SELECT id,status,course_id,message FROM practices WHERE owner_id=? AND request_id=?', (user['id'],body.request_id)).fetchone()
            if previous:
                if previous['course_id'] != course_id:
                    raise HTTPException(409, '请求编号已用于其他课程')
                return dict(previous)
        sources, versions, chapters = collect_sources(course_id, body, user)
        try:
            config = ai.settings()
        except ai.AIError as error:
            raise HTTPException(503, str(error))
        practice_id = secrets.token_hex(16)
        with db() as conn:
            conn.execute('BEGIN IMMEDIATE')
            expire(conn)
            previous = conn.execute('SELECT id,status,course_id,message FROM practices WHERE owner_id=? AND request_id=?', (user['id'],body.request_id)).fetchone()
            if previous:
                if previous['course_id'] != course_id:
                    raise HTTPException(409, '请求编号已用于其他课程')
                return dict(previous)
            if conn.execute("SELECT 1 FROM practices WHERE owner_id=? AND status IN ('generating','processing')", (user['id'],)).fetchone():
                raise HTTPException(409, '已有练习正在生成，请稍后刷新记录')
            conn.execute('INSERT INTO practices(id,owner_id,course_id,request_id,status,model,counts,sources,versions,selected_chapters,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                         (practice_id,user['id'],course_id,body.request_id,'generating',config['model'],json.dumps(body.counts),json.dumps(sources,ensure_ascii=False),json.dumps(versions),json.dumps(chapters,ensure_ascii=False),time.time()))
            if body.exam_minutes is not None:
                conn.execute("UPDATE practices SET attempt_kind='exam',duration_seconds=? WHERE id=?",(body.exam_minutes*60,practice_id))
        fragments=split_sources(sources)
        if len(pack_sources(fragments))>1 or len(fragments)!=len(sources):
            with db() as conn:
                practice_pipeline.prepare(conn,practice_id,fragments)
            return {'id':practice_id,'status':'processing','message':'已建立分批读取任务，请继续处理；不会跳过剩余资料'}
        try:
            paper = practice_ai.generate_practice(config, course['name'], body.counts, sources)
        except Exception as error:
            message = str(error) if isinstance(error, ai.AIError) else '练习生成失败，请稍后重试'
            with db() as conn:
                conn.execute("UPDATE practices SET status='failed',message=?,questions=? WHERE id=? AND status='generating'", (message,json.dumps(getattr(error,'partial_questions',[]),ensure_ascii=False),practice_id))
            return {'id':practice_id,'status':'failed','message':message}
        with db() as conn:
            cursor = conn.execute("UPDATE practices SET status='ready',title=?,questions=? WHERE id=? AND status='generating'", (paper['title'],json.dumps(paper['questions'],ensure_ascii=False),practice_id))
            if cursor.rowcount != 1:
                return {'id':practice_id,'status':'failed','message':'本次生成已超时，请刷新记录'}
        return {'id':practice_id,'status':'ready'}

    @app.post('/api/practices/{practice_id}/retry-generation')
    def retry_generation(practice_id: str, user=Depends(current_user)):
        with db() as conn:
            conn.execute('BEGIN IMMEDIATE')
            expire(conn)
            row=owned(conn,practice_id,user)
            if row['status']!='failed' or row.get('variant_of') or row.get('parent_id'):
                raise HTTPException(409,'当前记录不支持补题，请刷新记录')
            if conn.execute("SELECT 1 FROM practices WHERE owner_id=? AND status IN ('generating','processing')",(user['id'],)).fetchone():
                raise HTTPException(409,'已有练习正在生成，请等待完成')
            try: config=ai.settings()
            except ai.AIError as error: raise HTTPException(503,str(error))
            conn.execute("UPDATE practices SET status='generating',generation_started=?,message='' WHERE id=?",(time.time(),practice_id))
        course=get_course(row['course_id'],user)
        try:
            paper=practice_ai.generate_practice(config,course['name'],json.loads(row['counts']),json.loads(row['sources']),initial=json.loads(row['questions']))
        except Exception as error:
            message=str(error) if isinstance(error,ai.AIError) else '补题失败，已保留合格题，请稍后重试'
            partial=getattr(error,'partial_questions',json.loads(row['questions']))
            with db() as conn:
                conn.execute("UPDATE practices SET status='failed',message=?,questions=? WHERE id=? AND status='generating'",(message,json.dumps(partial,ensure_ascii=False),practice_id))
                return public_record(owned(conn,practice_id,user),conn)
        with db() as conn:
            conn.execute("UPDATE practices SET status='ready',title=?,questions=?,model=?,message='' WHERE id=? AND status='generating'",(paper['title'],json.dumps(paper['questions'],ensure_ascii=False),config['model'],practice_id))
            return public_record(owned(conn,practice_id,user),conn)

    @app.get('/api/practices/{practice_id}')
    def practice_detail(practice_id: str, user=Depends(current_user)):
        with db() as conn:
            expire(conn)
            return public_record(owned(conn,practice_id,user), conn)

    @app.put('/api/practices/{practice_id}/answers')
    def save_answers(practice_id: str, body: AnswersInput, user=Depends(current_user)):
        with db() as conn:
            conn.execute('BEGIN IMMEDIATE')
            row = owned(conn,practice_id,user)
            if exams.due(row):
                exams.finish(conn,row)
                return {'revision':row['revision']+1,'status':'submitted','message':'考试时间已到，已按最后保存的答案交卷'}
            if row['status'] != 'ready':
                raise HTTPException(409, '仅未交卷的练习可以保存答案')
            exams.require_started(row)
            if row['revision'] != body.revision:
                raise HTTPException(409, '答案已在其他页面更新，请重新打开练习后作答')
            answers = validate_answers(json.loads(row['questions']), body.answers)
            conn.execute('UPDATE practices SET answers=?,revision=revision+1 WHERE id=?', (json.dumps(answers,ensure_ascii=False),practice_id))
            return {'revision':row['revision']+1, 'message':'答案已保存'}

    @app.post('/api/practices/{practice_id}/submit')
    def submit(practice_id: str, body: AnswersInput, user=Depends(current_user)):
        with db() as conn:
            conn.execute('BEGIN IMMEDIATE')
            row = owned(conn,practice_id,user)
            if exams.due(row):
                exams.finish(conn,row)
                return public_record(owned(conn,practice_id,user),conn)
            if row['status'] == 'submitted':
                return public_record(row, conn)
            if row['status'] != 'ready':
                raise HTTPException(409, '练习尚不可交卷')
            exams.require_started(row)
            if row['revision'] != body.revision:
                raise HTTPException(409, '答案已在其他页面更新，请重新打开练习后交卷')
            questions = json.loads(row['questions'])
            answers = validate_answers(questions, body.answers)
            result = practice_ai.grade(questions, answers)
            conn.execute("UPDATE practices SET status='submitted',answers=?,result=?,revision=revision+1,submitted_at=? WHERE id=?",
                         (json.dumps(answers,ensure_ascii=False),json.dumps(result),time.time(),practice_id))
            return public_record(owned(conn,practice_id,user), conn)

    @app.put('/api/practices/{practice_id}/self-review')
    def self_review(practice_id: str, body: ReviewInput, user=Depends(current_user)):
        with db() as conn:
            conn.execute('BEGIN IMMEDIATE')
            row = owned(conn,practice_id,user)
            if row['status'] != 'submitted':
                raise HTTPException(409, '请先交卷再核对参考答案')
            if row['revision'] != body.revision:
                raise HTTPException(409, '自评已在其他页面更新，请重新打开练习')
            result = json.loads(row['result'])
            allowed = {r['id'] for r in result['questions'] if r['mode'] in ('self','ai')}
            if (set(body.scores) | set(body.point_verdicts)) - allowed:
                raise HTTPException(422, '只能为已作答的填空或简答题保存自评分')
            questions = {q['id']:q for q in json.loads(row['questions'])}
            scores = dict(body.scores)
            for qid, score in scores.items():
                q=questions[qid]
                if score > maximum(q) or score not in (0, maximum(q)/2, maximum(q)) or (q['kind']=='short' and q.get('scoring_version')==2):
                    raise HTTPException(422,'分数不符合本题规则；新版简答题请逐项评价评分要点')
            for qid, verdicts in body.point_verdicts.items():
                q=questions[qid]
                if q['kind']!='short' or q.get('scoring_version')!=2 or qid in scores:
                    raise HTTPException(422,'本题不接受重复或不适用的分点评分')
                try: scores[qid]=point_score(q,verdicts)
                except ValueError as e: raise HTTPException(422,str(e))
            for item in result['questions']:
                if item['id'] in scores:
                    if item['id'] in body.point_verdicts:
                        if item.get('point_verdicts') != body.point_verdicts[item['id']]: item['mode']='self'
                        item['point_verdicts']=body.point_verdicts[item['id']]
                    if item['score'] != scores[item['id']] or item['score'] is None:
                        item['mode'] = 'self'
                    item['score'] = scores[item['id']]
            conn.execute('UPDATE practices SET result=?,revision=revision+1 WHERE id=?', (json.dumps(practice_ai.summarize(result['questions'])),practice_id))
            return public_record(owned(conn,practice_id,user), conn)

    @app.post('/api/practices/{practice_id}/ai-review')
    def ai_review(practice_id: str, body: AIReviewInput, user=Depends(current_user)):
        with db() as conn:
            expire(conn)
            row = owned(conn, practice_id, user)
            if row['status'] != 'submitted':
                raise HTTPException(409, '请先交卷，再请求 AI 辅助批改')
            question = next((q for q in json.loads(row['questions']) if q['id'] == body.question_id), None)
            answer = json.loads(row['answers']).get(body.question_id, [])
            if not question or question['kind'] not in ('fill','short') or not answer or not answer[0].strip():
                raise HTTPException(422, '仅支持批改已作答的填空、简答题；空白题按0分计')
            existing = conn.execute('SELECT status FROM practice_reviews WHERE practice_id=? AND question_id=?', (practice_id,body.question_id)).fetchone()
            if existing and existing['status'] in ('running','ready'):
                return public_record(row, conn)
        try:
            config = ai.settings()
        except ai.AIError as error:
            raise HTTPException(503, str(error))
        token = secrets.token_hex(16)
        with db() as conn:
            conn.execute('BEGIN IMMEDIATE')
            expire(conn)
            row = owned(conn,practice_id,user)
            existing = conn.execute('SELECT status FROM practice_reviews WHERE practice_id=? AND question_id=?', (practice_id,body.question_id)).fetchone()
            if existing and existing['status'] in ('running','ready'):
                return public_record(row,conn)
            if conn.execute("SELECT 1 FROM practice_reviews r JOIN practices p ON p.id=r.practice_id WHERE p.owner_id=? AND r.status='running'",(user['id'],)).fetchone():
                raise HTTPException(409, '已有题目正在批改，请稍后重试')
            conn.execute("""INSERT INTO practice_reviews(practice_id,question_id,status,token,started_at,model)
                VALUES(?,?,'running',?,?,?) ON CONFLICT(practice_id,question_id) DO UPDATE SET
                status='running',token=excluded.token,started_at=excluded.started_at,model=excluded.model,feedback=NULL,message=''""",
                (practice_id,body.question_id,token,time.time(),config['model']))
        try:
            feedback = review_ai.review_answer(config,question,answer[0],json.loads(row['sources']))
        except Exception as error:
            message = str(error) if isinstance(error,ai.AIError) else '本题批改失败，原有分数保留，可稍后重试'
            with db() as conn:
                conn.execute("UPDATE practice_reviews SET status='failed',message=? WHERE practice_id=? AND question_id=? AND token=? AND status='running'",(message,practice_id,body.question_id,token))
                return public_record(owned(conn,practice_id,user),conn)
        with db() as conn:
            conn.execute('BEGIN IMMEDIATE')
            expire(conn)
            changed = conn.execute("UPDATE practice_reviews SET status='ready',feedback=? WHERE practice_id=? AND question_id=? AND token=? AND status='running'",(json.dumps(feedback,ensure_ascii=False),practice_id,body.question_id,token))
            if changed.rowcount:
                latest = owned(conn,practice_id,user)
                result = json.loads(latest['result'])
                for item in result['questions']:
                    if item['id'] == body.question_id and item['score'] is None:
                        item['score'] = feedback['score']
                        if question.get('scoring_version')==2 and question['kind']=='short': item['point_verdicts']=[p['verdict'] for p in feedback['points']]
                        item['mode'] = 'ai'
                conn.execute('UPDATE practices SET result=?,revision=revision+1 WHERE id=?', (json.dumps(practice_ai.summarize(result['questions'])),practice_id))
            return public_record(owned(conn,practice_id,user),conn)

    from backend.mistakes import register_mistake_routes
    register_mistake_routes(app, db, current_user, get_course, owned)

    from backend.reports import register_report_routes
    register_report_routes(app, db, current_user, get_course)

    practice_pipeline.register_pipeline(app,db,current_user,owned,public_record,get_course)

    exams.register_exams(app,db,current_user,owned,public_record)
