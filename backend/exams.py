"""Server-authoritative deadlines; expired exams use only saved answers."""
import json
import time
from fastapi import Depends, HTTPException
from backend import practice_ai


def now():
    return time.time()


def migrate(conn):
    fields={r['name'] for r in conn.execute('PRAGMA table_info(practices)')}
    for name,definition in {
        'attempt_kind':"TEXT NOT NULL DEFAULT 'practice'",'duration_seconds':'INTEGER',
        'started_at':'REAL','deadline':'REAL','submission_reason':"TEXT NOT NULL DEFAULT 'manual'"
    }.items():
        if name not in fields:conn.execute(f'ALTER TABLE practices ADD COLUMN {name} {definition}')


def due(row):
    return row['attempt_kind']=='exam' and row['status']=='ready' and row['deadline'] is not None and row['deadline']<=now()


def finish(conn,row):
    result=practice_ai.grade(json.loads(row['questions']),json.loads(row['answers']))
    conn.execute("UPDATE practices SET status='submitted',result=?,revision=revision+1,submitted_at=deadline,submission_reason='timeout' WHERE id=? AND status='ready'",
                 (json.dumps(result),row['id']))


def expire(conn,user_id=None):
    sql="SELECT * FROM practices WHERE attempt_kind='exam' AND status='ready' AND deadline IS NOT NULL AND deadline<=?"
    params=[now()]
    if user_id is not None:sql+=' AND owner_id=?';params.append(user_id)
    for row in conn.execute(sql,params).fetchall():finish(conn,row)


def require_started(row):
    if row['attempt_kind']=='exam' and row['started_at'] is None:
        raise HTTPException(409,'请先点击开始考试，计时开始后才能作答或交卷')


def register_exams(app,db,current_user,owned,public_record):
    @app.post('/api/practices/{practice_id}/start-exam')
    def start(practice_id:str,user=Depends(current_user)):
        with db() as conn:
            conn.execute('BEGIN IMMEDIATE');expire(conn,user['id']);row=owned(conn,practice_id,user)
            if row['attempt_kind']!='exam':raise HTTPException(409,'这是一份普通练习，不需要开始考试')
            if row['status']=='submitted' or row['started_at'] is not None:return public_record(row,conn)
            if row['status']!='ready':raise HTTPException(409,'试卷尚未生成完成')
            started=now()
            conn.execute('UPDATE practices SET started_at=?,deadline=?,revision=revision+1 WHERE id=?',(started,started+row['duration_seconds'],practice_id))
            return public_record(owned(conn,practice_id,user),conn)
