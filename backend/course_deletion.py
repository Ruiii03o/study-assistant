"""Owner-scoped permanent course removal with retryable file cleanup."""
import time
from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field


class DeleteCourseInput(BaseModel):
    name: str = Field(min_length=1, max_length=200)


def register_course_deletion(app, db, current_user, uploads):
    with db() as c:
        c.execute('CREATE TABLE IF NOT EXISTS deleted_uploads(filename TEXT PRIMARY KEY)')

    def cleanup():
        with db() as c:
            for row in c.execute('SELECT filename FROM deleted_uploads').fetchall():
                target=uploads/row['filename']
                # Never follow a stored path outside the upload directory.
                if target.resolve().parent!=uploads.resolve():continue
                try:target.unlink(missing_ok=True)
                except OSError:continue
                c.execute('DELETE FROM deleted_uploads WHERE filename=?',(row['filename'],))
            return c.execute('SELECT COUNT(*) FROM deleted_uploads').fetchone()[0]
    cleanup()

    def owned(c, course_id, user):
        course=c.execute('SELECT * FROM courses WHERE id=? AND owner_id=?',(course_id,user['id'])).fetchone()
        if not course:raise HTTPException(404,'课程不存在')
        return course

    @app.get('/api/courses/{course_id}/deletion-preview')
    def preview(course_id:int,user=Depends(current_user)):
        with db() as c:
            course=owned(c,course_id,user)
            counts={table:c.execute(f'SELECT COUNT(*) FROM {table} WHERE course_id=?',(course_id,)).fetchone()[0]
                    for table in ('materials','outlines','outline_sessions','practices','exam_blueprints','resources')}
            return {'name':course['name'],'counts':counts}

    @app.delete('/api/courses/{course_id}')
    def delete(course_id:int,body:DeleteCourseInput,user=Depends(current_user)):
        with db() as c:
            c.execute('BEGIN IMMEDIATE')
            course=owned(c,course_id,user)
            if body.name!=course['name']:raise HTTPException(422,'输入的课程名称不一致，未删除')
            cutoff=time.time()-600
            checks=[
                ("SELECT 1 FROM outlines WHERE course_id=? AND status='generating' AND created_at>?",),
                ("SELECT 1 FROM practices WHERE course_id=? AND status='generating' AND created_at>?",),
                ("SELECT 1 FROM outline_parts WHERE session_id IN (SELECT id FROM outline_sessions WHERE course_id=?) AND status='running' AND started_at>?",),
                ("SELECT 1 FROM practice_jobs WHERE practice_id IN (SELECT id FROM practices WHERE course_id=?) AND status='running' AND started_at>?",),
                ("SELECT 1 FROM practice_reviews WHERE practice_id IN (SELECT id FROM practices WHERE course_id=?) AND status='running' AND started_at>?",),
                ("SELECT 1 FROM exam_blueprints WHERE course_id=? AND token!='' AND started>?",),
                ("SELECT 1 FROM blueprint_runs WHERE course_id=? AND token!='' AND started>?",),
                ("SELECT 1 FROM material_page_images WHERE material_id IN (SELECT id FROM materials WHERE course_id=?) AND token!='' AND started>?",),
                ("SELECT 1 FROM resource_searches WHERE course_id=? AND status='running' AND started_at>?",),
            ]
            if any(c.execute(sql,(course_id,cutoff)).fetchone() for (sql,) in checks):
                raise HTTPException(409,'本课程还有任务正在处理，请等待本步完成并暂停后再删除')
            c.execute('INSERT OR IGNORE INTO deleted_uploads SELECT id || suffix FROM materials WHERE course_id=?',(course_id,))
            c.execute('DELETE FROM learning_notes WHERE owner_id=? AND record_id IN (SELECT id FROM outlines WHERE course_id=? UNION SELECT id FROM outline_sessions WHERE course_id=?)',(user['id'],course_id,course_id))
            for table in ('confidence','practice_reviews','practice_jobs','knowledge_guides'):
                c.execute(f'DELETE FROM {table} WHERE practice_id IN (SELECT id FROM practices WHERE course_id=?)',(course_id,))
            c.execute('DELETE FROM outline_parts WHERE session_id IN (SELECT id FROM outline_sessions WHERE course_id=?)',(course_id,))
            for table in ('blueprint_runs','exam_blueprints','resource_searches','resources','practices','outline_sessions','outlines','materials'):
                c.execute(f'DELETE FROM {table} WHERE course_id=?',(course_id,))
            c.execute('DELETE FROM courses WHERE id=? AND owner_id=?',(course_id,user['id']))
        pending=cleanup()
        return {'deleted':True,'message':'课程及关联记录已删除。'+('部分原文件暂被占用，将在服务重启时重试清理。' if pending else '')}
