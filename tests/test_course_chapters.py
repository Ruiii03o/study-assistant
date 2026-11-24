import json
import sqlite3

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from backend import ai
from backend.app import create_app, Credentials, CourseInput, OutlineInput


@pytest.fixture
def course_setup(tmp_path, monkeypatch):
    path = tmp_path / 'chapters.db'
    app = create_app(path)
    routes = {(r.path, m): r.endpoint for r in app.routes if hasattr(r, 'methods') for m in r.methods}
    def call(route, method='GET', user=None, **kwargs):
        return routes[route, method](user=user or {'id': 1}, **kwargs)
    for username in ('alice', 'bobby'):
        routes['/api/auth/register', 'POST'](body=Credentials(username=username, password='testing-12345'))
    course = call('/api/courses', 'POST', body=CourseInput(name='Networks'))['id']
    chapters = [dict(title='Shared', unit_index=0, end_unit_index=1, included=True),
                dict(title='Shared', unit_index=1, end_unit_index=2, included=True),
                dict(title='Other', unit_index=3, end_unit_index=3, included=True),
                dict(title='Excluded', unit_index=0, end_unit_index=0, included=False)]
    units = [dict(location=f'Slide {i}', text=f'Content {i}') for i in range(4)]
    with sqlite3.connect(path) as conn:
        for mid, confirmed in [('a', 1), ('b', 1), ('unconfirmed', 0)]:
            conn.execute('INSERT INTO materials(id,owner_id,course_id,name,suffix,size,status,units,chapters,confirmed) VALUES(?,?,?,?,?,?,?,?,?,?)',
                         (mid, 1, course, mid+'.pptx', '.pptx', 10, 'ready', json.dumps(units), json.dumps(chapters), confirmed))
    received = []
    monkeypatch.setattr(ai, 'settings', lambda: {'model':'test'})
    def generate(config, name, goal, detail, sources):
        received.extend(sources)
        return {'title':'Test', 'sections':[{'title':'Section', 'points':[{'text':'Content', 'source_ids':['S1']}]}]}
    monkeypatch.setattr(ai, 'generate_outline', generate)
    return path, course, call, received


def test_grouping_access_and_exclusions(course_setup):
    path, course, call, _ = course_setup
    groups = call('/api/courses/{course_id}/chapters', course_id=course)
    assert [g['title'] for g in groups] == ['Shared', 'Other']
    assert len(groups[0]['ranges']) == 4
    assert {r['material_id'] for r in groups[0]['ranges']} == {'a', 'b'}
    assert len({r['key'] for g in groups for r in g['ranges']}) == 6
    with pytest.raises(HTTPException) as error:
        call('/api/courses/{course_id}/chapters', course_id=course, user={'id':2})
    assert error.value.status_code == 404


def test_independent_selection_deduplication_and_history(course_setup):
    path, course, call, received = course_setup
    ranges = call('/api/courses/{course_id}/chapters', course_id=course)[0]['ranges']
    with sqlite3.connect(path) as conn:
        before = conn.execute('SELECT id,chapters FROM materials ORDER BY id').fetchall()
    saved = call('/api/courses/{course_id}/outlines', 'POST', course_id=course,
                 body=OutlineInput(material_ids=['a','b'], chapter_keys=[r['key'] for r in ranges]))
    assert saved['status'] == 'ready'
    assert [(s['material_id'], s['unit_index']) for s in received] == [(m,i) for m in ['a','b'] for i in range(3)]
    record = call('/api/outlines/{outline_id}', outline_id=saved['id'])
    assert len(record['selected_chapters']) == 4
    with sqlite3.connect(path) as conn:
        assert conn.execute('SELECT id,chapters FROM materials ORDER BY id').fetchall() == before
        conn.execute("UPDATE materials SET name='changed' WHERE id='a'")
    record = call('/api/outlines/{outline_id}', outline_id=saved['id'])
    assert record['stale'] and record['selected_chapters'][0]['name'] == 'a.pptx'
    endpoint = next(r.endpoint for r in create_app(path).routes if r.path == '/api/outlines/{outline_id}')
    assert endpoint(outline_id=saved['id'], user={'id':1})['selected_chapters'] == record['selected_chapters']


def test_stale_foreign_and_empty_selections_rejected_before_ai(course_setup):
    path, course, call, received = course_setup
    ranges = call('/api/courses/{course_id}/chapters', course_id=course)[0]['ranges']
    key_a = next(r['key'] for r in ranges if r['material_id'] == 'a')
    key_b = next(r['key'] for r in ranges if r['material_id'] == 'b')
    with pytest.raises(ValidationError):
        OutlineInput(material_ids=['a'], chapter_keys=[])
    for key in ['invented', key_b]:
        with pytest.raises(HTTPException) as error:
            call('/api/courses/{course_id}/outlines', 'POST', course_id=course,
                 body=OutlineInput(material_ids=['a'], chapter_keys=[key]))
        assert error.value.status_code == 409
    with sqlite3.connect(path) as conn:
        conn.execute("UPDATE materials SET chapters='[]' WHERE id='a'")
    with pytest.raises(HTTPException) as error:
        call('/api/courses/{course_id}/outlines', 'POST', course_id=course,
             body=OutlineInput(material_ids=['a'], chapter_keys=[key_a]))
    assert error.value.status_code == 409
    assert received == []


def test_single_subrange_does_not_include_other_file(course_setup):
    _, course, call, received = course_setup
    ranges = call('/api/courses/{course_id}/chapters', course_id=course)[0]['ranges']
    chosen = next(r for r in ranges if r['material_id'] == 'a' and r['unit_index'] == 1)
    result = call('/api/courses/{course_id}/outlines', 'POST', course_id=course,
                  body=OutlineInput(material_ids=['a','b'], chapter_keys=[chosen['key'],chosen['key']]))
    assert result['status'] == 'ready'
    assert [(s['material_id'],s['unit_index']) for s in received] == [('a',1),('a',2)]
