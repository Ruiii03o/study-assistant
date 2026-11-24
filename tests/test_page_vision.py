import base64
import json
import sqlite3
import httpx
import pytest
from fastapi import HTTPException
from backend import ai
from backend.page_vision import ImageInput,AnalyzeInput,ApplyInput,image_bytes
from test_practice import setup_practice,create

BASE='/api/materials/{material_id}/pages/{unit_index}'
PNG='data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aX1sAAAAASUVORK5CYII='


def page(call,suffix='/analysis',method='GET',**kwargs):
    return call(BASE+suffix,method,material_id='m1',unit_index=0,**kwargs)


def ready(call):
    state=page(call)
    page(call,'/image','PUT',body=ImageInput(data=PNG,revision=state['revision']))
    return state


def mock_analysis(monkeypatch,action=None):
    def request(*args,**kwargs):
        assert kwargs['image_data']==PNG
        if action:action()
        return json.dumps({'text':'完整句子','diagram':'图中有两个节点','uncertain':['边沿看不清']})
    monkeypatch.setattr(ai,'request_content',request)


def test_draft_does_not_modify_source_and_apply_preserves_snapshot(setup_practice,monkeypatch):
    path,_,call,*_=setup_practice
    pid=create(setup_practice)
    before=call('/api/practices/{practice_id}',practice_id=pid)
    state=ready(call);mock_analysis(monkeypatch)
    draft=page(call,'/analyze','POST',body=AnalyzeInput(revision=state['revision']))
    assert page(call)['text']==state['text']
    page(call,'/analysis','PUT',body=ApplyInput(revision=state['revision'],draft_id=draft['id'],text='经校对的完整句子'))
    assert page(call)['text']=='经校对的完整句子'
    assert page(call)['raw_text']==state['text']
    after=call('/api/practices/{practice_id}',practice_id=pid)
    assert after.pop('stale') is True
    before.pop('stale')
    assert after==before
    with sqlite3.connect(path) as conn:
        units,chapters,confirmed=conn.execute("SELECT units,chapters,confirmed FROM materials WHERE id='m1'").fetchone()
        assert json.loads(units)[1]['text']=='Excluded data'
        assert json.loads(chapters)[0]['end_unit_index']==0 and confirmed==1


def test_ownership_and_non_image_rejection(setup_practice):
    _,_,call,*_=setup_practice
    ready(call)
    for suffix in ['/image','/analysis']:
        with pytest.raises(HTTPException) as e:page(call,suffix,user={'id':2})
        assert e.value.status_code==404
    for data in ['data:image/svg+xml;base64,PHN2Zz4=', 'data:image/png;base64,AAAA','data:image/jpeg;base64,bm90LWEtcGhvdG8=']:
        with pytest.raises(HTTPException):image_bytes(data)


def test_changes_during_analysis_reject_stale_result(setup_practice,monkeypatch):
    path,_,call,*_=setup_practice;state=ready(call)
    def change():
        with sqlite3.connect(path) as conn:conn.execute("UPDATE materials SET confirmed=0 WHERE id='m1'")
    mock_analysis(monkeypatch,change)
    with pytest.raises(HTTPException) as e:page(call,'/analyze','POST',body=AnalyzeInput(revision=state['revision']))
    assert e.value.status_code==409
    assert not page(call)['busy'] and not page(call)['draft']


def test_image_replacement_invalidates_draft(setup_practice,monkeypatch):
    _,_,call,*_=setup_practice;state=ready(call);mock_analysis(monkeypatch)
    draft=page(call,'/analyze','POST',body=AnalyzeInput(revision=state['revision']))
    ready(call)
    with pytest.raises(HTTPException) as e:page(call,'/analysis','PUT',body=ApplyInput(revision=state['revision'],draft_id=draft['id'],text='bad'))
    assert e.value.status_code==409 and page(call)['text']==state['text']


def test_failure_unlocks_without_modifying_source(setup_practice,monkeypatch):
    _,_,call,*_=setup_practice;state=ready(call)
    monkeypatch.setattr(ai,'request_content',lambda *a,**kw:'not-json')
    with pytest.raises(HTTPException) as e:page(call,'/analyze','POST',body=AnalyzeInput(revision=state['revision']))
    assert e.value.status_code==422
    assert page(call)['text']==state['text'] and not page(call)['busy']


def test_multimodal_adapter_sends_image_and_text():
    def handle(request):
        payload=json.loads(request.content)
        content=payload['messages'][1]['content']
        assert content[0]['type']=='text' and content[1]['image_url']['url']==PNG
        return httpx.Response(200,json={'choices':[{'finish_reason':'stop','message':{'content':'{}'}}]})
    assert ai.request_content({'url':'https://example.test/chat/completions','api_key':'fake','model':'test'},'system',{'text':'test'},transport=httpx.MockTransport(handle),image_data=PNG)=='{}'


def test_reextract_keeps_reviewed_page_and_refreshes_other_pages(setup_practice,monkeypatch):
    path,_,call,*_=setup_practice;state=ready(call);mock_analysis(monkeypatch)
    draft=page(call,'/analyze','POST',body=AnalyzeInput(revision=state['revision']))
    page(call,'/analysis','PUT',body=ApplyInput(revision=state['revision'],draft_id=draft['id'],text='已核对图示'))
    monkeypatch.setattr('backend.app.extract',lambda *a:[{'location':'Slide 1','text':'new raw 1','raw_text':'new raw 1'},{'location':'Slide 2','text':'new raw 2'}])
    call('/api/materials/{material_id}/refresh-text','POST',material_id='m1')
    assert page(call)['text']=='已核对图示'
    with sqlite3.connect(path) as conn:
        units=json.loads(conn.execute("SELECT units FROM materials WHERE id='m1'").fetchone()[0])
        assert units[1]['text']=='new raw 2' and units[0]['vision_review']
