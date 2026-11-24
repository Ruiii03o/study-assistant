import sqlite3
import time
import pytest
from fastapi import HTTPException
from backend.course_deletion import DeleteCourseInput
from backend.app import CourseInput
from test_practice import setup_practice,create


def test_delete_scope_files_and_children(setup_practice):
    path,course,call,_,_=setup_practice
    pid=create(setup_practice)
    other=call('/api/courses','POST',body=CourseInput(name='Other'))['id']
    file=path.parent/'uploads'/'m1.pptx';file.write_bytes(b'source')
    keep=path.parent/'uploads'/'keep.pdf';keep.write_bytes(b'keep')
    with sqlite3.connect(path) as c:
        c.execute('INSERT INTO confidence(practice_id,values_json) VALUES(?,?)',(pid,'{}'))
        c.execute("INSERT INTO outline_sessions(id,owner_id,course_id,goal,detail,created_at) VALUES('s1',1,?,'g','d',0)",(course,))
        c.execute("INSERT INTO outline_parts(session_id,seq,sources) VALUES('s1',1,'[]')")
        c.execute("INSERT INTO learning_notes VALUES(1,'s1',0,'t','n',0,0,0)")
        c.execute("INSERT INTO material_page_images(material_id,unit_index,image,mime,image_hash) VALUES('m1',0,?,'image/png','hash')",(b'img',))
        c.execute("INSERT INTO resources VALUES('r1',1,?,'t','https://example.com','',0)",(course,))
    preview=call('/api/courses/{course_id}/deletion-preview',course_id=course)
    assert preview['counts']['materials']==1 and preview['counts']['practices']==1
    assert call('/api/courses/{course_id}','DELETE',course_id=course,body=DeleteCourseInput(name='Test'))['deleted']
    assert not file.exists() and keep.exists()
    assert call('/api/courses/{course_id}',course_id=other)['name']=='Other'
    with sqlite3.connect(path) as c:
        for table in ['materials','practices','confidence','outline_parts','outline_sessions','learning_notes','material_page_images','resources']:
            assert c.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]==0
        assert not c.execute('PRAGMA foreign_key_check').fetchall()


def test_delete_requires_owner_and_exact_name(setup_practice):
    _,course,call,_,_=setup_practice
    for user,name,code in [({'id':2},'Test',404),({'id':1},'test',422)]:
        with pytest.raises(HTTPException) as err:
            call('/api/courses/{course_id}','DELETE',course_id=course,user=user,body=DeleteCourseInput(name=name))
        assert err.value.status_code==code
    assert call('/api/courses/{course_id}',course_id=course)


def test_running_generation_blocks_deletion(setup_practice):
    path,course,call,_,_=setup_practice
    pid=create(setup_practice)
    with sqlite3.connect(path) as c:c.execute("UPDATE practices SET status='generating',created_at=? WHERE id=?",(time.time(),pid))
    with pytest.raises(HTTPException) as err:
        call('/api/courses/{course_id}','DELETE',course_id=course,body=DeleteCourseInput(name='Test'))
    assert err.value.status_code==409
    assert call('/api/courses/{course_id}',course_id=course)
