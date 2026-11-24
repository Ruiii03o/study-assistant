import json
import sqlite3
import zipfile
from pathlib import Path

import pytest
from fastapi import HTTPException, Response
from pydantic import ValidationError
from backend.learning_tools import NoteInput, ResourceInput, PasswordInput, ActiveInput, ConfidenceInput
from backend.paper_tools import ManualInput, VariantInput
from backend.practice_ai import Paper
from backend.practice import AnswersInput
from backend import ai
from backend.maintenance import backup, restore
from backend.material_tools import TextInput, Unit, SuggestInput
from test_practice import setup_practice, create, RAW
from test_mistakes import submitted


def test_notes_edit_preserves_ai_and_conflicts(setup_practice):
    path,course,call,*_=setup_practice
    result={'sections':[{'title':'Chapter','points':[{'text':'AI original','source_ids':['S1']}]}]}
    with sqlite3.connect(path) as conn:
        conn.execute("INSERT INTO outlines(id,owner_id,course_id,status,goal,detail,model,sources,versions,result,created_at) VALUES('outline',1,?,'ready','','','test','[]','{}',?,1)",(course,json.dumps(result)))
    body=NoteInput(revision=0,text='My correction',note='Teacher emphasized',important=True)
    saved=call('/api/learning-notes/{record_id}/{point_index}','PUT',record_id='outline',point_index=0,body=body)
    assert saved['revision']==1
    assert call('/api/learning-notes/{record_id}',record_id='outline')[0]['important']==1
    with pytest.raises(HTTPException) as e: call('/api/learning-notes/{record_id}/{point_index}','PUT',record_id='outline',point_index=0,body=body)
    assert e.value.status_code==409
    with pytest.raises(HTTPException) as e: call('/api/learning-notes/{record_id}',record_id='outline',user={'id':2})
    assert e.value.status_code==404
    with sqlite3.connect(path) as conn: assert json.loads(conn.execute("SELECT result FROM outlines WHERE id='outline'").fetchone()[0])==result


def test_resource_isolation_and_url_validation(setup_practice):
    _,course,call,*_=setup_practice
    for url in ['javascript:alert(1)','data:text/html,x','https://user:pass@example.com','/local']:
        with pytest.raises(ValidationError): ResourceInput(title='X',url=url)
    item=call('/api/courses/{course_id}/resources','POST',course_id=course,body=ResourceInput(title='Book',url='https://example.com',note='Private'))
    assert len(call('/api/courses/{course_id}/resources',course_id=course))==1
    with pytest.raises(HTTPException) as e: call('/api/resources/{resource_id}','DELETE',resource_id=item['id'],user={'id':2})
    assert e.value.status_code==404
    call('/api/resources/{resource_id}','DELETE',resource_id=item['id'])
    assert call('/api/courses/{course_id}/resources',course_id=course)==[]


def test_admin_rechecks_database_and_revokes_sessions(setup_practice):
    path,_,call,*_=setup_practice
    with pytest.raises(HTTPException) as e: call('/api/admin/users',user={'id':2,'role':'admin'})
    assert e.value.status_code==403
    with sqlite3.connect(path) as conn:
        conn.execute("UPDATE users SET role='admin' WHERE id=1")
        conn.execute("INSERT INTO sessions VALUES('fake',2,9999999999)")
    rows=call('/api/admin/users')
    assert all(set(r)=={'id','username','role','active'} for r in rows)
    call('/api/admin/users/{user_id}/active','PUT',user_id=2,body=ActiveInput(active=False))
    with sqlite3.connect(path) as conn:
        assert conn.execute('SELECT count(*) FROM sessions WHERE user_id=2').fetchone()[0]==0
        assert conn.execute('SELECT count(*) FROM admin_audit').fetchone()[0]==1
    with pytest.raises(HTTPException): call('/api/admin/users/{user_id}/active','PUT',user_id=1,body=ActiveInput(active=False))


def test_password_change_requires_old_and_revokes_sessions(setup_practice):
    path,_,call,*_=setup_practice
    with sqlite3.connect(path) as conn: conn.execute("INSERT INTO sessions VALUES('old-token',1,9999999999)")
    with pytest.raises(HTTPException): call('/api/auth/password','POST',body=PasswordInput(old_password='wrong',new_password='new-password123'),response=Response())
    response=Response()
    call('/api/auth/password','POST',body=PasswordInput(old_password='test-password-123',new_password='new-password123'),response=response)
    assert 'Max-Age=0' in response.headers['set-cookie']
    with sqlite3.connect(path) as conn: assert conn.execute('SELECT count(*) FROM sessions WHERE user_id=1').fetchone()[0]==0


def test_manual_paper_validated_redacted_idempotent_and_exam(setup_practice):
    _,course,call,*_=setup_practice
    body=ManualInput(paper=Paper.model_validate(RAW),request_id='manual-paper-request',exam_minutes=30)
    result=call('/api/courses/{course_id}/manual-papers','POST',course_id=course,body=body)
    assert call('/api/courses/{course_id}/manual-papers','POST',course_id=course,body=body)==result
    record=call('/api/practices/{practice_id}',practice_id=result['id'])
    assert record['questions']==[] and record['attempt_kind']=='exam' and record['duration_seconds']==1800
    assert 'sources' not in record
    body=ManualInput(paper=Paper.model_validate(RAW),request_id='manual-practice-request')
    result=call('/api/courses/{course_id}/manual-papers','POST',course_id=course,body=body)
    record=call('/api/practices/{practice_id}',practice_id=result['id'])
    assert len(record['questions'])==5 and all('answer' not in q for q in record['questions'])
    assert [q['kind'] for q in record['questions']]==[q['kind'] for q in RAW['questions']]
    call('/api/practices/{practice_id}/submit','POST',practice_id=result['id'],body=AnswersInput(revision=0,answers={}))
    record=call('/api/practices/{practice_id}',practice_id=result['id'])
    assert record['result']['total_score']==0 and record['sources'][0]['source_id']=='MANUAL'


def test_confidence_is_private_versioned_and_locks_on_submit(setup_practice):
    pid=create(setup_practice);call=setup_practice[2]
    body=ConfidenceInput(revision=0,values={'Q1':3})
    assert call('/api/practices/{practice_id}/confidence','PUT',practice_id=pid,body=body)['revision']==1
    with pytest.raises(HTTPException) as e: call('/api/practices/{practice_id}/confidence','PUT',practice_id=pid,body=body)
    assert e.value.status_code==409
    with pytest.raises(HTTPException): call('/api/practices/{practice_id}/confidence',practice_id=pid,user={'id':2})
    call('/api/practices/{practice_id}/submit','POST',practice_id=pid,body=AnswersInput(revision=0,answers={}))
    with pytest.raises(HTTPException): call('/api/practices/{practice_id}/confidence','PUT',practice_id=pid,body=ConfidenceInput(revision=1,values={'Q1':1}))
    assert call('/api/practices/{practice_id}/confidence',practice_id=pid)['values']=={'Q1':3}


def test_variant_new_questions_independent_report_and_request_retry(setup_practice,monkeypatch):
    pid=submitted(setup_practice);call=setup_practice[2];calls=[]
    raw={'title':'Variant','questions':[dict(RAW['questions'][1],prompt='A different situation')]}
    def request(*args): calls.append(args);return json.dumps(raw)
    monkeypatch.setattr(ai,'request_content',request)
    body=VariantInput(question_id='Q4',request_id='variant-request-123')
    result=call('/api/practices/{practice_id}/variant','POST',practice_id=pid,body=body)
    assert result['status']=='ready'
    assert call('/api/practices/{practice_id}/variant','POST',practice_id=pid,body=body)['id']==result['id'] and len(calls)==1
    record=call('/api/practices/{practice_id}',practice_id=result['id'])
    assert record['parent_id'] is None and record['variant_of']==pid+':Q4' and 'answer' not in record['questions'][0]
    call('/api/practices/{practice_id}/submit','POST',practice_id=result['id'],body=AnswersInput(revision=0,answers={'Q1':['A','B']}))
    report=call('/api/courses/{course_id}/report',course_id=setup_practice[1])
    assert report['variants']['totals']['questions']==1 and report['first_attempts']['totals']['questions']==5
    with pytest.raises(HTTPException): call('/api/practices/{practice_id}/variant','POST',practice_id=pid,body=body,user={'id':2})


def test_variant_duplicate_model_output_fails_without_question(setup_practice,monkeypatch):
    pid=submitted(setup_practice);call=setup_practice[2]
    monkeypatch.setattr(ai,'request_content',lambda *args:json.dumps({'title':'Duplicate','questions':[RAW['questions'][1]]}))
    result=call('/api/practices/{practice_id}/variant','POST',practice_id=pid,body=VariantInput(question_id='Q4',request_id='duplicate-request-123'))
    assert result['status']=='failed'
    assert call('/api/practices/{practice_id}',practice_id=result['id'])['questions']==[]


def test_backup_roundtrip_no_sessions_or_keys_and_no_overwrite(setup_practice,tmp_path):
    path,_,_,*_=setup_practice
    uploads=Path(path).parent/'uploads';uploads.mkdir(exist_ok=True);(uploads/'m1.pptx').write_bytes(b'original material')
    (Path(path).parent/'ai-config.json').write_text('{"secret":"do not copy"}')
    with sqlite3.connect(path) as conn: conn.execute("INSERT INTO sessions VALUES('old',1,9999999999)")
    archive=backup(path,tmp_path/'backup.zip')
    with zipfile.ZipFile(archive) as z: assert set(z.namelist())=={'app.db','uploads/m1.pptx','manifest.json'}
    dest=restore(archive,tmp_path/'recovered')
    assert (dest/'uploads/m1.pptx').read_bytes()==b'original material'
    with sqlite3.connect(dest/'app.db') as conn:
        assert conn.execute('SELECT count(*) FROM users').fetchone()[0]==2
        assert conn.execute('SELECT count(*) FROM sessions').fetchone()[0]==0
    with pytest.raises(ValueError): restore(archive,dest)
    with pytest.raises(ValueError): backup(path,archive)
    with sqlite3.connect(path) as conn: assert conn.execute('SELECT count(*) FROM sessions').fetchone()[0]==1


def test_restore_rejects_corruption_and_traversal(tmp_path):
    archive=tmp_path/'bad.zip'
    for name in ['../app.db','uploads/../../evil','uploads/file:stream','app.db']:
        with zipfile.ZipFile(archive,'w') as z:
            z.writestr(name,b'tampered');z.writestr('manifest.json',json.dumps({'format':1,'files':{name:'wrong'}}))
        with pytest.raises(ValueError): restore(archive,tmp_path/'output')
        assert not (tmp_path/'output').exists()


def test_text_correction_versions_positions_and_existing_practice(setup_practice):
    _,_,call,*_=setup_practice;pid=create(setup_practice)
    before=call('/api/practices/{practice_id}',practice_id=pid)
    state=call('/api/materials/{material_id}/text-editor',material_id='m1')
    units=[Unit(**u) for u in state['units']];units[0].text='Corrected text'
    body=TextInput(revision=state['revision'],units=units)
    call('/api/materials/{material_id}/text-editor','PUT',material_id='m1',body=body)
    after=call('/api/practices/{practice_id}',practice_id=pid)
    assert after['questions']==before['questions'] and after['stale']
    with pytest.raises(HTTPException) as e: call('/api/materials/{material_id}/text-editor','PUT',material_id='m1',body=body)
    assert e.value.status_code==409
    state=call('/api/materials/{material_id}/text-editor',material_id='m1')
    with pytest.raises(HTTPException): call('/api/materials/{material_id}/text-editor','PUT',material_id='m1',body=TextInput(revision=state['revision'],units=units[:1]))
    with pytest.raises(HTTPException): call('/api/materials/{material_id}/text-editor',material_id='m1',user={'id':2})


def test_chapter_suggestions_never_save_and_reject_invalid_model_ranges(setup_practice,monkeypatch):
    path,_,call,*_=setup_practice
    with sqlite3.connect(path) as conn: original=conn.execute("SELECT chapters FROM materials WHERE id='m1'").fetchone()[0]
    monkeypatch.setattr(ai,'request_content',lambda *args:json.dumps({'chapters':[{'title':'Proposed','unit_index':0,'end_unit_index':1}]}))
    result=call('/api/materials/{material_id}/suggest-chapters','POST',material_id='m1',body=SuggestInput(start=0,end=1))
    assert result['chapters'][0]['title']=='Proposed'
    with sqlite3.connect(path) as conn: assert conn.execute("SELECT chapters FROM materials WHERE id='m1'").fetchone()[0]==original
    with pytest.raises(HTTPException): call('/api/materials/{material_id}/suggest-chapters','POST',material_id='m1',body=SuggestInput(start=1,end=1))
    with pytest.raises(HTTPException): call('/api/materials/{material_id}/suggest-chapters','POST',material_id='m1',body=SuggestInput(start=0,end=2))


def test_manual_text_bootstraps_empty_scan_without_confirming_range(setup_practice):
    path,_,call,*_=setup_practice
    with sqlite3.connect(path) as conn: conn.execute("UPDATE materials SET units='[]',chapters='[]',confirmed=0,status='needs_ocr' WHERE id='m1'")
    state=call('/api/materials/{material_id}/text-editor',material_id='m1')
    call('/api/materials/{material_id}/text-editor','PUT',material_id='m1',body=TextInput(revision=state['revision'],units=[Unit(location='Page 1',text='Checked scan text')]))
    with sqlite3.connect(path) as conn:
        status,confirmed,chapters=conn.execute("SELECT status,confirmed,chapters FROM materials WHERE id='m1'").fetchone()
    assert status=='ready' and confirmed==0 and chapters=='[]'
