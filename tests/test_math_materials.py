import json
import sqlite3
import pytest
from fastapi import HTTPException
from backend.math_text import parse_model_json
from backend.page_vision import AnalyzeInput, ApplyInput, ImageInput
from backend import ai
from test_practice import setup_practice
from test_page_vision import ready, page, PNG
from test_batching import long_setup, sessions


def test_latex_json_preserves_commands_and_valid_json():
    formula=r'\(\lim_{x\to 0}\frac{\sin x}{x}=1\)'
    assert parse_model_json(json.dumps({'text':formula}))['text']==formula
    assert parse_model_json('{"text":"'+formula+'"}')['text']==formula
    assert parse_model_json(r'{"text":"first\nsecond\u4e00"}')['text']=='first\nsecond一'
    with pytest.raises(ValueError):parse_model_json('{"broken":')


def test_math_draft_survives_other_page_save(setup_practice,monkeypatch):
    _,_,call,*_=setup_practice;state=ready(call)
    formula=r'\[\frac{1}{2}x^2\]'
    monkeypatch.setattr(ai,'request_content',lambda *a,**k:json.dumps({'text':formula,'diagram':'','uncertain':[]}))
    draft=page(call,'/analyze','POST',body=AnalyzeInput(revision=state['revision'],mode='math'))
    call('/api/materials/{material_id}/pages/{unit_index}/image','PUT',material_id='m1',unit_index=1,body=ImageInput(data=PNG,revision=state['revision']))
    other=call('/api/materials/{material_id}/pages/{unit_index}/analyze','POST',material_id='m1',unit_index=1,body=AnalyzeInput(revision=state['revision'],mode='math'))
    page(call,'/analysis','PUT',body=ApplyInput(revision=state['revision'],draft_id=draft['id'],text=formula))
    assert page(call)['reviewed_math']
    latest=page(call)['revision']
    call('/api/materials/{material_id}/pages/{unit_index}/analysis','PUT',material_id='m1',unit_index=1,body=ApplyInput(revision=latest,draft_id=other['id'],text=formula))
    assert page(call)['text']==formula


def test_pdf_render_local_and_owner_guard(setup_practice):
    from pypdf import PdfWriter
    path,_,call,*_=setup_practice
    uploads=path.parent/'uploads';uploads.mkdir(exist_ok=True)
    writer=PdfWriter();writer.add_blank_page(width=595,height=842)
    writer.write(str(uploads/'m1.pdf'))
    with sqlite3.connect(path) as conn:conn.execute("UPDATE materials SET suffix='.pdf' WHERE id='m1'")
    state=page(call)
    assert state['can_render_pdf']
    assert page(call,'/render','POST',body=AnalyzeInput(revision=state['revision']))['ready']
    assert page(call,'/image').body.startswith(b'\xff\xd8')
    with pytest.raises(HTTPException) as e:page(call,'/render','POST',user={'id':2},body=AnalyzeInput(revision=state['revision']))
    assert e.value.status_code==404


def test_refresh_pending_preserves_completed(setup_practice,monkeypatch):
    body,_=long_setup(setup_practice,monkeypatch);path,_,call,*_=setup_practice
    sid=sessions(setup_practice,body)['id']
    before=call('/api/outline-sessions/{session_id}/next','POST',session_id=sid)
    with sqlite3.connect(path) as conn:
        units=json.loads(conn.execute("SELECT units FROM materials WHERE id='m1'").fetchone()[0]);units[-1]['text']=r'Corrected \(x^2\)'
        conn.execute("UPDATE materials SET units=? WHERE id='m1'",(json.dumps(units),))
    with pytest.raises(HTTPException) as e:call('/api/outline-sessions/{session_id}/next','POST',session_id=sid)
    assert e.value.status_code==409
    after=call('/api/outline-sessions/{session_id}/refresh-pending','POST',session_id=sid)
    assert after['result']==before['result'] and not after['pending_stale']
    with sqlite3.connect(path) as conn:
        texts=''.join(r[0] for r in conn.execute("SELECT sources FROM outline_parts WHERE session_id=? AND status!='done'",(sid,)))
        assert 'Corrected' in texts
