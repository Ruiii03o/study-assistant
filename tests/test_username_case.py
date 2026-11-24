import sqlite3
import sys
import pytest
from fastapi import HTTPException,Response
from backend.app import create_app,Credentials
from backend.maintenance import main


def routes(path):
    return {r.path:r.endpoint for r in create_app(path).routes if hasattr(r,'methods')}


def test_case_sensitive_registration_login_and_duplicate(tmp_path):
    path=tmp_path/'case.db';r=routes(path)
    first=Credentials(username='Rui',password='first-password-123')
    second=Credentials(username='rui',password='second-password-123')
    for body in [first,second]:r['/api/auth/register'](body)
    with pytest.raises(HTTPException) as e:r['/api/auth/register'](first)
    assert e.value.status_code==409
    a=r['/api/auth/login'](first,Response());b=r['/api/auth/login'](second,Response())
    assert a['username']=='Rui' and b['username']=='rui' and a['id']!=b['id']
    for name in ['RUI','rui']:
        with pytest.raises(HTTPException) as e:r['/api/auth/login'](Credentials(username=name,password=first.password),Response())
        assert e.value.status_code==401


def test_old_lowercase_account_retained_and_cli_exact_match(tmp_path,monkeypatch):
    path=tmp_path/'old.db';r=routes(path)
    for name in ['rui','Rui']:r['/api/auth/register'](Credentials(username=name,password='test-password-123'))
    routes(path)
    monkeypatch.setattr(sys,'argv',['maintenance','grant-admin','--db',str(path),'--username','Rui'])
    main()
    with sqlite3.connect(path) as conn:
        assert dict(conn.execute('SELECT username,role FROM users'))=={'rui':'user','Rui':'admin'}
