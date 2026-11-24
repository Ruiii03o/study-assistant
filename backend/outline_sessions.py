import json
import secrets
import time
from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field, field_validator

class ArchiveName(BaseModel):
    title: str = Field(min_length=1, max_length=100)

    @field_validator("title")
    @classmethod
    def clean_title(cls, value):
        value = value.strip()
        if not value: raise ValueError("请输入存档名称")
        return value

from backend import ai
from backend.batching import encode, split_sources, pack_sources, source_key, ranges


def register_outline_sessions(app,db,current_user,get_course,collect_sources,Input,material_version):
    with db() as conn:
        conn.executescript('''CREATE TABLE IF NOT EXISTS outline_sessions(
          id TEXT PRIMARY KEY,owner_id INTEGER NOT NULL REFERENCES users(id),course_id INTEGER NOT NULL REFERENCES courses(id),
          status TEXT NOT NULL DEFAULT 'active',goal TEXT NOT NULL,detail TEXT NOT NULL,created_at REAL NOT NULL,archived_at REAL);
          CREATE UNIQUE INDEX IF NOT EXISTS one_active_outline ON outline_sessions(owner_id,course_id) WHERE status='active';
          CREATE TABLE IF NOT EXISTS outline_parts(
          id INTEGER PRIMARY KEY,session_id TEXT NOT NULL REFERENCES outline_sessions(id),seq INTEGER NOT NULL,
          status TEXT NOT NULL DEFAULT 'pending',sources TEXT NOT NULL,result TEXT,model TEXT NOT NULL DEFAULT '',
          token TEXT,started_at REAL,message TEXT NOT NULL DEFAULT '',UNIQUE(session_id,seq));''')

    with db() as conn:
        if 'title' not in {r['name'] for r in conn.execute('PRAGMA table_info(outline_sessions)')}:
            conn.execute("ALTER TABLE outline_sessions ADD COLUMN title TEXT NOT NULL DEFAULT ''")

    def owned(conn,sid,user):
        row=conn.execute('SELECT * FROM outline_sessions WHERE id=? AND owner_id=?',(sid,user['id'])).fetchone()
        if not row:raise HTTPException(404,'复习大纲不存在')
        return dict(row)

    def expire(conn):
        conn.execute("UPDATE outline_parts SET status='failed',message='本批处理超时或中断，可重试；已完成批次保留' WHERE status='running' AND started_at<?",(time.time()-240,))

    def detail(conn,sid,user):
        row=owned(conn,sid,user);parts=[];sections=[];completed=[];all_sources=[]
        for part in conn.execute('SELECT * FROM outline_parts WHERE session_id=? ORDER BY seq',(sid,)):
            sources=json.loads(part['sources']);all_sources.extend(sources)
            parts.append({'seq':part['seq'],'status':part['status'],'ranges':ranges(sources),'message':part['message'],'model':part['model']})
            if part['status']=='done':
                sections.extend(json.loads(part['result'])['sections']);completed.extend(sources)
        row.update(parts=parts,completed_batches=sum(p['status']=='done' for p in parts),total_batches=len(parts),
                   result={'title':row.get('title') or '复习大纲','sections':sections},sources=completed,
                   selected_chapters=[],model='分批生成（各批次模型见进度）',stale=False)
        versions={}
        for source in all_sources:
            versions.setdefault(source['material_id'],set()).add(source['version'])
        for mid,expected in versions.items():
            material=conn.execute('SELECT * FROM materials WHERE id=? AND owner_id=?',(mid,user['id'])).fetchone()
            if not material or expected!={material_version(material)}:row['stale']=True
        row['pending_stale']=False
        for part in conn.execute("SELECT sources FROM outline_parts WHERE session_id=? AND status!='done'",(sid,)):
            for source in json.loads(part['sources']):
                material=conn.execute('SELECT * FROM materials WHERE id=? AND owner_id=?',(source['material_id'],user['id'])).fetchone()
                if not material or source['version']!=material_version(material):row['pending_stale']=True
        return row

    @app.get('/api/courses/{course_id}/outline-sessions')
    def listing(course_id:int,user=Depends(current_user)):
        get_course(course_id,user)
        with db() as conn:
            expire(conn)
            return [dict(r) for r in conn.execute('SELECT * FROM outline_sessions WHERE course_id=? AND owner_id=? ORDER BY created_at DESC',(course_id,user['id']))]

    @app.post('/api/courses/{course_id}/outline-sessions',status_code=201)
    def append(course_id:int,body:Input,user=Depends(current_user)):
        get_course(course_id,user)
        sources,versions,chapters=collect_sources(course_id,body,user)
        fragments=split_sources(sources)
        with db() as conn:
            conn.execute('BEGIN IMMEDIATE');expire(conn)
            active=conn.execute("SELECT * FROM outline_sessions WHERE course_id=? AND owner_id=? AND status='active'",(course_id,user['id'])).fetchone()
            sid=active['id'] if active else secrets.token_hex(16)
            if not active:
                conn.execute('INSERT INTO outline_sessions(id,owner_id,course_id,goal,detail,created_at) VALUES(?,?,?,?,?,?)',(sid,user['id'],course_id,body.goal,body.detail,time.time()))
            previous=[];seq=0
            for part in conn.execute('SELECT sources,seq FROM outline_parts WHERE session_id=? ORDER BY seq',(sid,)):
                previous.extend(json.loads(part['sources']));seq=part['seq']
            known={source_key(s) for s in previous};fresh=[]
            for source in fragments:
                key=source_key(source)
                if key in known:continue
                known.add(key);source['source_id']=f'S{len(previous)+len(fresh)+1}'
                source['version']=versions[source['material_id']];fresh.append(source)
            for batch in pack_sources(fresh):
                seq+=1;conn.execute('INSERT INTO outline_parts(session_id,seq,sources) VALUES(?,?,?)',(sid,seq,encode(batch)))
            result=detail(conn,sid,user)
            result['message']='已追加新范围；已完成内容保留。' if fresh else '所选内容已在当前大纲中，无需重复追加。可继续处理待完成批次。'
            return result

    @app.get('/api/outline-sessions/{session_id}')
    def get(session_id:str,user=Depends(current_user)):
        with db() as conn:
            expire(conn);return detail(conn,session_id,user)

    @app.post('/api/outline-sessions/{session_id}/next')
    def process(session_id:str,user=Depends(current_user)):
        with db() as conn:
            session=owned(conn,session_id,user)
            if session['status']!='active':raise HTTPException(409,'大纲已存档，不能继续追加或处理')
        try:config=ai.settings()
        except ai.AIError as error:raise HTTPException(503,str(error))
        with db() as conn:
            conn.execute('BEGIN IMMEDIATE');expire(conn);session=owned(conn,session_id,user)
            if session['status']!='active':raise HTTPException(409,'大纲已存档')
            if conn.execute("SELECT 1 FROM outline_parts p JOIN outline_sessions s ON s.id=p.session_id WHERE s.owner_id=? AND p.status='running'",(user['id'],)).fetchone():
                raise HTTPException(409,'已有大纲批次处理中，请稍后刷新进度')
            part=conn.execute("SELECT * FROM outline_parts WHERE session_id=? AND status!='done' ORDER BY seq LIMIT 1",(session_id,)).fetchone()
            if not part:return detail(conn,session_id,user)
            if detail(conn,session_id,user)['pending_stale']:raise HTTPException(409,'资料已更新，请先更新未完成批次')
            token=secrets.token_hex(16)
            conn.execute("UPDATE outline_parts SET status='running',token=?,started_at=?,message='',model=? WHERE id=?",(token,time.time(),config['model'],part['id']))
            course=get_course(session['course_id'],user)
        try:
            result=ai.generate_outline(config,course['name'],session['goal'],session['detail'],json.loads(part['sources']))
        except Exception as error:
            message=str(error) if isinstance(error,ai.AIError) else '本批处理失败，已完成内容保留，可重试本批'
            with db() as conn:
                conn.execute("UPDATE outline_parts SET status='failed',message=? WHERE id=? AND token=? AND status='running'",(message,part['id'],token))
                return detail(conn,session_id,user)
        with db() as conn:
            expire(conn)
            conn.execute("UPDATE outline_parts SET status='done',result=? WHERE id=? AND token=? AND status='running'",(encode(result),part['id'],token))
            return detail(conn,session_id,user)

    @app.post('/api/outline-sessions/{session_id}/refresh-pending')
    def refresh_pending(session_id:str,user=Depends(current_user)):
        with db() as conn:
            conn.execute('BEGIN IMMEDIATE');expire(conn);session=owned(conn,session_id,user)
            if session['status']!='active':raise HTTPException(409,'大纲已存档')
            parts=list(conn.execute('SELECT * FROM outline_parts WHERE session_id=? ORDER BY seq',(session_id,)))
            if any(p['status']=='running' for p in parts):raise HTTPException(409,'请等待当前批次结束')
            sources=[];seen=set();seq=0;offset=0
            for part in parts:
                if part['status']=='done':
                    seq=max(seq,part['seq'])
                    offset=max([offset]+[int(s['source_id'][1:]) for s in json.loads(part['sources'])])
                    continue
                for old in json.loads(part['sources']):
                    key=(old['material_id'],old['unit_index'])
                    if key in seen:continue
                    seen.add(key)
                    material=conn.execute('SELECT * FROM materials WHERE id=? AND owner_id=?',(key[0],user['id'])).fetchone()
                    if not material:raise HTTPException(409,'部分资料已删除，请重新选择范围')
                    units=json.loads(material['units'])
                    if key[1]>=len(units) or not units[key[1]]['text'].strip():raise HTTPException(409,'部分页面没有文字，请先完成校对')
                    unit=units[key[1]]
                    sources.append({'material_id':key[0],'unit_index':key[1],'name':material['name'],'location':unit['location'],'text':unit['text'],'version':material_version(material)})
            fragments=split_sources(sources)
            for i,source in enumerate(fragments):source['source_id']=f'S{offset+i+1}'
            batches=pack_sources(fragments)
            conn.execute("DELETE FROM outline_parts WHERE session_id=? AND status!='done'",(session_id,))
            for batch in batches:
                seq+=1;conn.execute('INSERT INTO outline_parts(session_id,seq,sources) VALUES(?,?,?)',(session_id,seq,encode(batch)))
            return detail(conn,session_id,user)

    @app.post('/api/outline-sessions/{session_id}/archive')
    def archive(session_id:str,body:ArchiveName=None,user=Depends(current_user)):
        with db() as conn:
            conn.execute('BEGIN IMMEDIATE');expire(conn);owned(conn,session_id,user)
            if conn.execute("SELECT 1 FROM outline_parts WHERE session_id=? AND status='running'",(session_id,)).fetchone():
                raise HTTPException(409,'请等待当前批次结束后存档')
            if body is not None:
                conn.execute('UPDATE outline_sessions SET title=? WHERE id=?',(body.title,session_id))
            conn.execute("UPDATE outline_sessions SET status='archived',archived_at=COALESCE(archived_at,?) WHERE id=?",(time.time(),session_id))
            return detail(conn,session_id,user)

    @app.patch('/api/outline-sessions/{session_id}/name')
    def rename_archive(session_id:str,body:ArchiveName,user=Depends(current_user)):
        with db() as conn:
            conn.execute('BEGIN IMMEDIATE')
            row=owned(conn,session_id,user)
            if row['status']!='archived':raise HTTPException(409,'仅能重命名已存档的大纲')
            conn.execute('UPDATE outline_sessions SET title=? WHERE id=?',(body.title,session_id))
            return detail(conn,session_id,user)

    @app.delete('/api/outline-sessions/{session_id}')
    def delete_archive(session_id:str,user=Depends(current_user)):
        with db() as conn:
            conn.execute('BEGIN IMMEDIATE')
            session=owned(conn,session_id,user)
            if session['status']!='archived':raise HTTPException(409,'仅可删除已存档的大纲')
            if conn.execute("SELECT 1 FROM outline_parts WHERE session_id=? AND status='running'",(session_id,)).fetchone():
                raise HTTPException(409,'大纲仍在处理中，请稍后重试')
            conn.execute('DELETE FROM learning_notes WHERE owner_id=? AND record_id=?',(user['id'],session_id))
            conn.execute('DELETE FROM outline_parts WHERE session_id=?',(session_id,))
            conn.execute('DELETE FROM outline_sessions WHERE id=?',(session_id,))
        return {'message':'大纲存档已删除'}
