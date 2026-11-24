import json
import sqlite3
from io import BytesIO
from zipfile import ZipFile

from fastapi.testclient import TestClient
from backend.app import create_app


def test_material_flow_isolation_and_persistence(tmp_path):
    path = tmp_path / 'test.db'
    app = create_app(path)
    alice, bob = TestClient(app), TestClient(app)
    for client, name in ((alice,'alice'),(bob,'bobby')):
        credentials = {'username':name,'password':'testing-12345'}
        assert client.post('/api/auth/register',json=credentials).status_code == 201
        assert client.post('/api/auth/login',json=credentials).status_code == 200
    course = alice.post('/api/courses',json={'name':'数据库'}).json()['id']
    endpoint = f'/api/courses/{course}/materials'
    assert bob.get(endpoint).status_code == 404
    assert alice.post(endpoint,params={'name':'a.exe'},content=b'x').status_code == 422
    assert alice.post(endpoint,params={'name':'a.docx'},content=b'').status_code == 422
    buffer = BytesIO()
    with ZipFile(buffer,'w') as archive:
        archive.writestr('word/document.xml','<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>第一章 概述</w:t></w:r></w:p></w:body></w:document>')
    response = alice.post(endpoint,params={'name':'notes.docx'},content=buffer.getvalue())
    assert response.status_code == 201
    item = '/api/materials/' + response.json()['id']
    assert bob.post(endpoint,params={'name':'notes.docx'},content=buffer.getvalue()).status_code == 404
    for suffix in ('','/download'):
        assert bob.get(item+suffix).status_code == 404
    assert bob.post(item+'/parse').status_code == 404
    assert bob.put(item+'/chapters',json={'chapters':[]}).status_code == 404
    assert alice.post(item+'/parse').status_code == 200
    details = alice.get(item).json()
    assert details['status'] == 'ready'
    assert details['units'][0]['text'] == '第一章 概述'
    assert details['chapters'] == []
    assert not details['confirmed']
    assert alice.get(item+'/selected-content').status_code == 409
    chapters = [{'title':'概述','unit_index':0,'end_unit_index':0,'included':True}]
    # Old automatically generated suggestions must not appear as user selections.
    with sqlite3.connect(path) as conn:
        conn.execute('UPDATE materials SET chapters=? WHERE id=?', (json.dumps(chapters), details['id']))
    assert alice.get(item).json()['chapters'] == []
    assert not alice.get(endpoint).json()[0]['confirmed']
    assert alice.put(item+'/chapters',json={'chapters':[{**chapters[0],'unit_index':99}]}).status_code == 422
    chapters[0]['included'] = False
    assert alice.put(item+'/chapters',json={'chapters':chapters}).status_code == 200
    assert alice.post(item+'/parse').status_code == 409
    assert alice.post(item+'/refresh-text').status_code == 200
    assert alice.get(item).json()['chapters'] == chapters
    assert alice.get(item+'/selected-content').json()['units'] == []
    assert bob.post(item+'/refresh-text').status_code == 404
    assert bob.get(item+'/selected-content').status_code == 404
    assert alice.put(item+'/chapters',json={'chapters':[{**chapters[0],'end_unit_index':99}]}).status_code == 422
    resumed = TestClient(create_app(path))
    resumed.cookies.set('study_session',alice.cookies.get('study_session'))
    assert resumed.get(item).json()['chapters'][0]['included'] is False
    assert resumed.get(item+'/download').content == buffer.getvalue()
    assert len(resumed.get(endpoint).json()) == 1
