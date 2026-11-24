"""Private learning annotations, resource bookmarks and account administration."""
import hmac
import json
import secrets
import time
from urllib.parse import urlsplit
from typing import Annotated

from fastapi import Depends, HTTPException, Response
from pydantic import BaseModel, Field, field_validator


class NoteInput(BaseModel):
    revision: int = Field(ge=0)
    text: str = Field(max_length=12000)
    note: str = Field(default='', max_length=8000)
    important: bool = False


class ResourceInput(BaseModel):
    title: str = Field(min_length=1, max_length=150)
    url: str = Field(max_length=2000)
    note: str = Field(default='', max_length=4000)

    @field_validator('url')
    @classmethod
    def safe_url(cls, value):
        parts = urlsplit(value.strip())
        if parts.scheme not in ('http', 'https') or not parts.hostname or parts.username or parts.password:
            raise ValueError('请填写不含账号密码的 http/https 链接')
        return value.strip()

    @field_validator('title')
    @classmethod
    def nonempty(cls, value):
        if not value.strip(): raise ValueError('标题不能为空')
        return value.strip()


class PasswordInput(BaseModel):
    old_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=10, max_length=128)


class ActiveInput(BaseModel):
    active: bool


class ConfidenceInput(BaseModel):
    revision: int = Field(ge=0)
    values: dict[str, Annotated[int, Field(strict=True, ge=1, le=3)]] = Field(max_length=100)


def register_learning_tools(app, db, current_user, get_course, password_hash):
    with db() as conn:
        conn.executescript('''
        CREATE TABLE IF NOT EXISTS learning_notes(
          owner_id INTEGER NOT NULL REFERENCES users(id), record_id TEXT NOT NULL,
          point_index INTEGER NOT NULL, text TEXT NOT NULL, note TEXT NOT NULL,
          important INTEGER NOT NULL, revision INTEGER NOT NULL, updated_at REAL NOT NULL,
          PRIMARY KEY(owner_id,record_id,point_index));
        CREATE TABLE IF NOT EXISTS resources(
          id TEXT PRIMARY KEY, owner_id INTEGER NOT NULL REFERENCES users(id),
          course_id INTEGER NOT NULL REFERENCES courses(id), title TEXT NOT NULL,
          url TEXT NOT NULL, note TEXT NOT NULL, created_at REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS confidence(
          practice_id TEXT PRIMARY KEY REFERENCES practices(id), values_json TEXT NOT NULL,
          revision INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS admin_audit(
          id INTEGER PRIMARY KEY, actor_id INTEGER NOT NULL, target_id INTEGER NOT NULL,
          action TEXT NOT NULL, created_at REAL NOT NULL);
        ''')

    def points(conn, record_id, user):
        row = conn.execute('SELECT result FROM outlines WHERE id=? AND owner_id=?', (record_id,user['id'])).fetchone()
        if row:
            sections = json.loads(row['result'] or '{"sections":[]}')['sections']
        else:
            session = conn.execute('SELECT status FROM outline_sessions WHERE id=? AND owner_id=?', (record_id,user['id'])).fetchone()
            if not session:
                raise HTTPException(404, '大纲不存在')
            sections = [section for part in conn.execute("SELECT result FROM outline_parts WHERE session_id=? AND status='done' ORDER BY seq", (record_id,)) for section in json.loads(part['result'])['sections']]
            # Incomplete parts can later insert points ahead of an existing point.
            if session['status']=='active' and conn.execute("SELECT 1 FROM outline_parts WHERE session_id=? AND status!='done'", (record_id,)).fetchone():
                raise HTTPException(409, '请先完成本次全部批次，再编辑知识点；已保存笔记仍保留')
        return [point for section in sections for point in section['points']]

    @app.get('/api/learning-notes/{record_id}')
    def notes(record_id: str, user=Depends(current_user)):
        with db() as conn:
            points(conn, record_id, user)
            return [dict(r) for r in conn.execute('SELECT * FROM learning_notes WHERE owner_id=? AND record_id=? ORDER BY point_index', (user['id'],record_id))]

    @app.put('/api/learning-notes/{record_id}/{point_index}')
    def save_note(record_id: str, point_index: int, body: NoteInput, user=Depends(current_user)):
        with db() as conn:
            conn.execute('BEGIN IMMEDIATE')
            entries = points(conn,record_id,user)
            if not 0 <= point_index < len(entries): raise HTTPException(404,'知识点不存在')
            if not body.text.strip(): raise HTTPException(422,'知识点不能为空')
            row = conn.execute('SELECT revision FROM learning_notes WHERE owner_id=? AND record_id=? AND point_index=?', (user['id'],record_id,point_index)).fetchone()
            revision = row['revision'] if row else 0
            if body.revision != revision: raise HTTPException(409,'笔记已在其他页面修改，请重新打开后编辑')
            conn.execute('INSERT OR REPLACE INTO learning_notes VALUES(?,?,?,?,?,?,?,?)', (user['id'],record_id,point_index,body.text.strip(),body.note,body.important,revision+1,time.time()))
            return {'revision':revision+1}

    @app.get('/api/courses/{course_id}/resources')
    def resources(course_id: int, user=Depends(current_user)):
        get_course(course_id,user)
        with db() as conn:
            return [dict(r) for r in conn.execute('SELECT * FROM resources WHERE owner_id=? AND course_id=? ORDER BY created_at DESC', (user['id'],course_id))]

    @app.post('/api/courses/{course_id}/resources', status_code=201)
    def add_resource(course_id: int, body: ResourceInput, user=Depends(current_user)):
        get_course(course_id,user)
        rid=secrets.token_hex(16)
        with db() as conn:
            conn.execute('BEGIN IMMEDIATE')
            existing=conn.execute('SELECT id FROM resources WHERE owner_id=? AND course_id=? AND url=?',(user['id'],course_id,body.url)).fetchone()
            if existing:return {'id':existing['id']}
            if conn.execute('SELECT count(*) FROM resources WHERE owner_id=? AND course_id=?',(user['id'],course_id)).fetchone()[0] >= 500:
                raise HTTPException(409,'每门课程最多收藏500条资源')
            conn.execute('INSERT INTO resources VALUES(?,?,?,?,?,?,?)', (rid,user['id'],course_id,body.title,body.url,body.note,time.time()))
        return {'id':rid}

    @app.delete('/api/resources/{resource_id}')
    def delete_resource(resource_id: str, user=Depends(current_user)):
        with db() as conn:
            if not conn.execute('DELETE FROM resources WHERE id=? AND owner_id=?',(resource_id,user['id'])).rowcount:
                raise HTTPException(404,'资源不存在')
        return {'deleted':True}

    @app.post('/api/auth/password')
    def change_password(body: PasswordInput, response: Response, user=Depends(current_user)):
        with db() as conn:
            conn.execute('BEGIN IMMEDIATE')
            row=conn.execute('SELECT * FROM users WHERE id=?',(user['id'],)).fetchone()
            if not hmac.compare_digest(password_hash(body.old_password,row['salt']),row['password_hash']):
                raise HTTPException(400,'原密码不正确')
            salt=secrets.token_hex(16)
            conn.execute('UPDATE users SET salt=?,password_hash=? WHERE id=?',(salt,password_hash(body.new_password,salt),user['id']))
            conn.execute('DELETE FROM sessions WHERE user_id=?',(user['id'],))
        response.delete_cookie('study_session')
        return {'message':'密码已修改，所有已登录会话已退出，请重新登录'}

    def admin(conn,user):
        row=conn.execute('SELECT role,active FROM users WHERE id=?',(user['id'],)).fetchone()
        if not row or not row['active'] or row['role']!='admin': raise HTTPException(403,'仅管理员可操作')

    @app.get('/api/admin/users')
    def users(user=Depends(current_user)):
        with db() as conn:
            admin(conn,user)
            return [dict(r) for r in conn.execute('SELECT id,username,role,active FROM users ORDER BY id')]

    @app.put('/api/admin/users/{user_id}/active')
    def set_active(user_id: int, body: ActiveInput, user=Depends(current_user)):
        with db() as conn:
            conn.execute('BEGIN IMMEDIATE');admin(conn,user)
            target=conn.execute('SELECT role FROM users WHERE id=?',(user_id,)).fetchone()
            if not target: raise HTTPException(404,'用户不存在')
            if target['role']=='admin': raise HTTPException(409,'网页不允许停用管理员；请使用本地维护工具')
            conn.execute('UPDATE users SET active=? WHERE id=?',(body.active,user_id))
            if not body.active: conn.execute('DELETE FROM sessions WHERE user_id=?',(user_id,))
            conn.execute('INSERT INTO admin_audit(actor_id,target_id,action,created_at) VALUES(?,?,?,?)',(user['id'],user_id,'enable' if body.active else 'disable',time.time()))
        return {'active':body.active}

    def practice(conn,pid,user):
        row=conn.execute('SELECT * FROM practices WHERE id=? AND owner_id=?',(pid,user['id'])).fetchone()
        if not row: raise HTTPException(404,'练习不存在')
        return row

    @app.get('/api/practices/{practice_id}/knowledge/{question_id}')
    def knowledge(practice_id: str, question_id: str, user=Depends(current_user)):
        with db() as conn:
            row=practice(conn,practice_id,user)
            if row['status']!='submitted': raise HTTPException(409,'交卷后才能查看知识点与原文依据')
            question=next((q for q in json.loads(row['questions']) if q['id']==question_id),None)
            if not question: raise HTTPException(404,'题目不存在')
            sources=[s for s in json.loads(row['sources']) if s['source_id'] in question['source_ids']]
            locations={(s.get('material_id'),s.get('unit_index')) for s in sources if s.get('material_id')!='manual'}
            related=[];seen=set()
            active=conn.execute("SELECT id FROM outline_sessions WHERE owner_id=? AND course_id=? AND status='active'",(user['id'],row['course_id'])).fetchone()
            if active:
                records=conn.execute("SELECT sources,result FROM outline_parts WHERE session_id=? AND status='done' ORDER BY seq",(active['id'],)).fetchall()
            else:
                records=conn.execute("SELECT sources,result FROM outlines WHERE owner_id=? AND course_id=? AND status='ready' ORDER BY created_at DESC LIMIT 1",(user['id'],row['course_id'])).fetchall()
            for record in records:
                refs={s['source_id'] for s in json.loads(record['sources']) if (s.get('material_id'),s.get('unit_index')) in locations}
                for section in json.loads(record['result'])['sections']:
                    for point in section['points']:
                        if point['text'] not in seen:
                            related.append({'title':section['title'],'text':point['text'], 'scope':'cited' if refs.intersection(point['source_ids']) else 'course_outline'});seen.add(point['text'])
        from backend.knowledge_focus import focus
        return {'key_points':question['key_points'],'explanation':question['explanation'],'sources':sources, **focus(question,sources,related)}

    from backend.knowledge_guide import register as register_knowledge_guide
    register_knowledge_guide(app,db,current_user,practice,knowledge)

    @app.get('/api/courses/{course_id}/study-actions')
    def study_actions(course_id:int,mode:str='all',user=Depends(current_user)):
        get_course(course_id,user)
        if mode not in ('all','first','exam'):raise HTTPException(422,'无效的记录类型')
        with db() as conn:
            rows=[dict(r) for r in conn.execute("SELECT p.*,c.values_json AS confidence_values FROM practices p LEFT JOIN confidence c ON p.id=c.practice_id WHERE p.owner_id=? AND p.course_id=? AND p.status IN ('submitted','ready') ORDER BY p.created_at DESC",(user['id'],course_id))]
        from backend.study_actions import recommend
        result=recommend(rows,mode)
        for entry in result['items']:
            item=entry['item']
            focused=knowledge(item['practice_id'],item['question']['id'],user)
            entry['points']=[p for p in focused['related_outline_points'] if p.get('scope')=='cited'][:2]
        return result

    @app.get('/api/courses/{course_id}/confidence-report')
    def confidence_report(course_id:int,user=Depends(current_user)):
        get_course(course_id,user)
        with db() as conn:
            rows=[dict(r) for r in conn.execute("SELECT p.*,c.values_json AS confidence_values FROM practices p LEFT JOIN confidence c ON p.id=c.practice_id WHERE p.owner_id=? AND p.course_id=? AND p.status='submitted'",(user['id'],course_id))]
        from backend.confidence_report import analyze
        return analyze(rows)

    @app.get('/api/practices/{practice_id}/confidence')
    def get_confidence(practice_id: str, user=Depends(current_user)):
        with db() as conn:
            practice(conn,practice_id,user)
            row=conn.execute('SELECT * FROM confidence WHERE practice_id=?',(practice_id,)).fetchone()
            return {'values':json.loads(row['values_json']) if row else {},'revision':row['revision'] if row else 0}

    @app.put('/api/practices/{practice_id}/confidence')
    def save_confidence(practice_id: str, body: ConfidenceInput, user=Depends(current_user)):
        with db() as conn:
            conn.execute('BEGIN IMMEDIATE')
            row=practice(conn,practice_id,user)
            if row['parent_id'] or row['variant_of']:
                raise HTTPException(409,'原题重做和变式练习不采集信心')
            if row['status']!='ready' or (row['attempt_kind']=='exam' and (not row['started_at'] or row['deadline']<=time.time())):
                raise HTTPException(409,'只能在作答期间记录信心，交卷后不可修改')
            known={q['id'] for q in json.loads(row['questions'])}
            if not set(body.values)<=known or any(type(v)!=int or v not in (1,2,3) for v in body.values.values()):
                raise HTTPException(422,'信心只能是1（不确定）、2（一般）、3（确定）')
            old=conn.execute('SELECT revision FROM confidence WHERE practice_id=?',(practice_id,)).fetchone()
            revision=old['revision'] if old else 0
            if body.revision!=revision: raise HTTPException(409,'信心记录已更新，请重新打开练习')
            conn.execute('INSERT OR REPLACE INTO confidence VALUES(?,?,?)',(practice_id,json.dumps(body.values),revision+1))
        return {'revision':revision+1}
