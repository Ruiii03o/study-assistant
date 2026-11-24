import sqlite3
import pytest
from fastapi import HTTPException
from test_practice import setup_practice,create
from test_batching import long_setup,sessions

def test_archive_delete_scope_and_permissions(setup_practice,monkeypatch):
    create(setup_practice)
    body,_=long_setup(setup_practice,monkeypatch)
    path,course,call,*_=setup_practice
    sid=sessions(setup_practice,body)['id']
    route='/api/outline-sessions/{session_id}'
    with pytest.raises(HTTPException) as error:call(route,'DELETE',session_id=sid)
    assert error.value.status_code==409
    call(route+'/archive','POST',session_id=sid)
    with pytest.raises(HTTPException) as error:call(route,'DELETE',session_id=sid,user={'id':2})
    assert error.value.status_code==404
    second=sessions(setup_practice,body)['id']
    with sqlite3.connect(path) as c:
        c.execute('INSERT INTO learning_notes VALUES(?,?,?,?,?,?,?,?)',(1,sid,0,'point','note',1,1,0))
        c.execute('INSERT INTO learning_notes VALUES(?,?,?,?,?,?,?,?)',(1,second,0,'other','keep',1,1,0))
        material=c.execute('SELECT * FROM materials').fetchall()
        practices=c.execute('SELECT * FROM practices').fetchall()
    call(route,'DELETE',session_id=sid)
    with sqlite3.connect(path) as c:
        assert not c.execute('SELECT 1 FROM outline_sessions WHERE id=?',(sid,)).fetchone()
        assert not c.execute('SELECT 1 FROM outline_parts WHERE session_id=?',(sid,)).fetchone()
        assert not c.execute('SELECT 1 FROM learning_notes WHERE record_id=?',(sid,)).fetchone()
        assert c.execute('SELECT 1 FROM learning_notes WHERE record_id=?',(second,)).fetchone()
        assert c.execute('SELECT 1 FROM outline_parts WHERE session_id=?',(second,)).fetchone()
        assert c.execute('SELECT * FROM materials').fetchall()==material
        assert c.execute('SELECT * FROM practices').fetchall()==practices
    with pytest.raises(HTTPException) as error:call(route,'DELETE',session_id=sid)
    assert error.value.status_code==404
