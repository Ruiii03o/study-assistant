import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from backend.outline_sessions import ArchiveName
from test_practice import setup_practice, create
from test_batching import long_setup, sessions

def test_named_archive_persists_and_is_owned(setup_practice, monkeypatch):
    create(setup_practice)
    body, _ = long_setup(setup_practice, monkeypatch)
    _, course, call, *_ = setup_practice
    record = sessions(setup_practice, body)
    sid = record['id']
    route = '/api/outline-sessions/{session_id}'
    with pytest.raises(HTTPException) as error:
        call(route+'/name', 'PATCH', session_id=sid, body=ArchiveName(title='Test'))
    assert error.value.status_code == 409
    call(route+'/archive', 'POST', session_id=sid, body=ArchiveName(title='  期末第一章  '))
    saved = call(route, 'GET', session_id=sid)
    assert saved['title'] == saved['result']['title'] == '期末第一章'
    assert saved['goal'] == record['goal']
    with pytest.raises(HTTPException) as error:
        call(route+'/name', 'PATCH', session_id=sid, body=ArchiveName(title='Other'), user={'id':2})
    assert error.value.status_code == 404
    call(route+'/name', 'PATCH', session_id=sid, body=ArchiveName(title='期末重点'))
    assert call(route, 'GET', session_id=sid)['result']['title'] == '期末重点'

@pytest.mark.parametrize('value', ['', '   ', 'a'*101])
def test_archive_name_validation(value):
    with pytest.raises(ValidationError):
        ArchiveName(title=value)
