import json
import sqlite3

from backend import app as app_module
from backend.app import create_app, Credentials, CourseInput, ChaptersInput


def test_extraction_requires_explicit_ranges_and_preserves_confirmed(tmp_path, monkeypatch):
    path = tmp_path / 'ranges.db'
    app = create_app(path)
    routes = {(r.path, m): r.endpoint for r in app.routes if hasattr(r, 'methods') for m in r.methods}
    def call(route, method='GET', **kwargs):
        return routes[route, method](user={'id': 1}, **kwargs)
    routes['/api/auth/register', 'POST'](body=Credentials(username='alice', password='testing-12345'))
    course = call('/api/courses', 'POST', body=CourseInput(name='Course'))['id']
    chapters = [{'title': 'Old suggestion', 'unit_index': 0, 'end_unit_index': 0, 'included': True}]
    with sqlite3.connect(path) as conn:
        conn.execute('INSERT INTO materials(id,owner_id,course_id,name,suffix,size,status,chapters) VALUES(?,?,?,?,?,?,?,?)',
                     ('m1', 1, course, 'notes.pptx', '.pptx', 10, 'uploaded', json.dumps(chapters)))
    monkeypatch.setattr(app_module, 'extract', lambda *args: [{'location': 'Slide 1', 'text': 'Chapter 1 Intro'}])
    assert call('/api/materials/{material_id}', material_id='m1')['chapters'] == []
    call('/api/materials/{material_id}/parse', 'POST', material_id='m1')
    item = call('/api/materials/{material_id}', material_id='m1')
    assert item['status'] == 'ready' and item['units']
    assert item['chapters'] == [] and not item['confirmed']
    call('/api/materials/{material_id}/chapters', 'PUT', material_id='m1', body=ChaptersInput(chapters=chapters))
    call('/api/materials/{material_id}/refresh-text', 'POST', material_id='m1')
    assert call('/api/materials/{material_id}', material_id='m1')['chapters'] == chapters
    assert call('/api/courses/{course_id}/materials', course_id=course)[0]['confirmed']
    assert len(call('/api/materials/{material_id}/selected-content', material_id='m1')['units']) == 1
