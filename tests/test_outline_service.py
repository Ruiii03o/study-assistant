"""Exercise DB-backed route services without the sandbox's blocked ASGI loop.

These tests do not replace HTTP authentication/integration tests.
"""
import json
import sqlite3

import pytest
from fastapi import HTTPException

from backend import ai
from backend.app import create_app, Credentials, CourseInput, OutlineInput, ChaptersInput


def test_outline_snapshot_ownership_failure_and_range(tmp_path,monkeypatch):
    path = tmp_path/'app.db'
    app = create_app(path)
    routes = {(r.path,method):r.endpoint for r in app.routes if hasattr(r,'methods') for method in r.methods}
    def call(url,method='GET',**kwargs):
        return routes[url,method](**kwargs)
    for username in ['alice','bobby']:
        call('/api/auth/register','POST',body=Credentials(username=username,password='test-password-123'))
    alice,bob = {'id':1},{'id':2}
    course = call('/api/courses','POST',body=CourseInput(name='网络'),user=alice)['id']
    units = [{'location':f'幻灯片 {i+1}','text':f'内容{i}'} for i in range(3)]
    chapters = [{'title':'概述','unit_index':1,'end_unit_index':2,'included':True}]
    with sqlite3.connect(path) as conn:
        conn.execute('INSERT INTO materials(id,owner_id,course_id,name,suffix,size,status,units,chapters,confirmed) VALUES(?,?,?,?,?,?,?,?,?,?)',
                     ('m1',1,course,'第一章.pptx','.pptx',100,'ready',json.dumps(units),json.dumps(chapters),1))
    monkeypatch.setattr(ai,'settings',lambda: {'model':'test-model'})
    received = []
    def generate(config,course,goal,detail,sources):
        received.extend(sources)
        return {'title':'测试大纲','sections':[{'title':'知识','points':[{'text':'内容1','source_ids':['S1']}]}]}
    monkeypatch.setattr(ai,'generate_outline',generate)
    body = OutlineInput(material_ids=['m1','m1'])
    saved = call('/api/courses/{course_id}/outlines','POST',course_id=course,body=body,user=alice)
    assert saved['status'] == 'ready'
    assert [s['unit_index'] for s in received] == [1,2]
    record = call('/api/outlines/{outline_id}',outline_id=saved['id'],user=alice)
    assert record['stale'] is False
    assert record['sources'] == received
    with pytest.raises(HTTPException) as denied:
        call('/api/outlines/{outline_id}',outline_id=saved['id'],user=bob)
    assert denied.value.status_code == 404
    with pytest.raises(HTTPException):
        call('/api/courses/{course_id}/outlines','POST',course_id=course,body=body,user=bob)
    chapters[0]['end_unit_index'] = 1
    call('/api/materials/{material_id}/chapters','PUT',material_id='m1',body=ChaptersInput(chapters=chapters),user=alice)
    record = call('/api/outlines/{outline_id}',outline_id=saved['id'],user=alice)
    assert record['stale'] is True
    assert len(record['sources']) == 2
    def fail(*args):
        raise ai.AIError('模拟测试超时')
    monkeypatch.setattr(ai,'generate_outline',fail)
    failed = call('/api/courses/{course_id}/outlines','POST',course_id=course,body=body,user=alice)
    assert failed['status'] == 'failed'
    assert len(call('/api/courses/{course_id}/outlines',course_id=course,user=alice)) == 2
    restarted = create_app(path)
    endpoint = next(r.endpoint for r in restarted.routes if r.path == '/api/outlines/{outline_id}')
    assert endpoint(outline_id=saved['id'],user=alice)['sources'] == received
