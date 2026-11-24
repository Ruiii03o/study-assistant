import copy
import json
import sqlite3
import time

import httpx
import pytest
from fastapi import HTTPException
from backend import ai, review_ai
from backend.practice import AIReviewInput, AnswersInput, ReviewInput
from test_practice import setup_practice, create, paper


def raw_feedback(verdict='met'):
    return {'summary':'Test feedback','points':[{'point_index':0,'verdict':verdict,'reason':'Test reason','basis':'material','source_ids':['S1']}]}


@pytest.mark.parametrize('verdict,score',[('met',2),('partial',1),('missed',0)])
def test_score_computed_from_points(verdict,score):
    q=paper()['questions'][1]
    assert review_ai.validate_feedback(json.dumps(raw_feedback(verdict)),q)['score'] == score


@pytest.mark.parametrize('change',['index','citation','general_citation','material_no_citation','empty','extra_score','duplicate'])
def test_invalid_feedback_rejected(change):
    data=raw_feedback(); point=data['points'][0]
    if change=='index': point['point_index']=1
    if change=='citation': point['source_ids']=['S404']
    if change=='general_citation': point['basis']='general'
    if change=='material_no_citation': point['source_ids']=[]
    if change=='empty': point['reason']=' '
    if change=='extra_score': data['score']=2
    if change=='duplicate': data['points'].append(copy.deepcopy(point))
    with pytest.raises(ai.AIError): review_ai.validate_feedback(json.dumps(data),paper()['questions'][1])


def test_general_knowledge_and_only_relevant_sources_sent():
    q=paper()['questions'][1]
    data=raw_feedback();data['points'][0].update(basis='general',source_ids=[])
    def handle(request):
        payload=json.loads(json.loads(request.content)['messages'][1]['content'])
        assert [s['source_id'] for s in payload['sources']]==['S1']
        assert payload['student_answer']=='My answer'
        return httpx.Response(200,json={'choices':[{'finish_reason':'stop','message':{'content':json.dumps(data)}}]})
    config={'url':'https://example.com/chat/completions','model':'test','api_key':'test'}
    result=review_ai.review_answer(config,q,'My answer',[{'source_id':'S1','text':'Relevant'},{'source_id':'S2','text':'Other'}],transport=httpx.MockTransport(handle))
    assert result['points'][0]['basis']=='general' and result['points'][0]['source_ids']==[]


def submit(setup):
    pid=create(setup);call=setup[2]
    call('/api/practices/{practice_id}/submit','POST',practice_id=pid,body=AnswersInput(revision=0,answers={'Q2':['One'],'Q3':['Idea']}))
    return pid


def review(call,pid,qid='Q2',user=None):
    return call('/api/practices/{practice_id}/ai-review','POST',practice_id=pid,body=AIReviewInput(question_id=qid),user=user)


def test_ai_score_persistence_idempotency_manual_correction(setup_practice,monkeypatch):
    path,_,call,_,_=setup_practice; pid=submit(setup_practice); calls=[]
    def mocked(config,q,answer,sources):
        calls.append(q['id']);return review_ai.validate_feedback(json.dumps(raw_feedback()),q)
    monkeypatch.setattr(review_ai,'review_answer',mocked)
    result=review(call,pid)
    assert result['result']['questions'][1]['mode']=='ai'
    assert result['result']['questions'][1]['score']==2
    assert result['result']['pending_self_review']==1
    assert review(call,pid)['revision']==result['revision'] and calls==['Q2']
    changed=call('/api/practices/{practice_id}/self-review','PUT',practice_id=pid,body=ReviewInput(revision=result['revision'],scores={'Q2':1}))
    assert changed['result']['questions'][1]['mode']=='self'
    assert changed['ai_reviews']['Q2']['feedback']['score']==2
    assert review(call,pid)['result']['questions'][1]['score']==1
    from backend.app import create_app
    endpoint=next(r.endpoint for r in create_app(path).routes if r.path=='/api/practices/{practice_id}')
    assert endpoint(practice_id=pid,user={'id':1})['ai_reviews']['Q2']['status']=='ready'


def test_failure_retry_keeps_other_feedback(setup_practice,monkeypatch):
    _,_,call,_,_=setup_practice;pid=submit(setup_practice)
    def mocked(config,q,*args):
        if q['id']=='Q3': raise RuntimeError('private secret')
        return review_ai.validate_feedback(json.dumps(raw_feedback()),q)
    monkeypatch.setattr(review_ai,'review_answer',mocked)
    review(call,pid);failed=review(call,pid,'Q3')
    assert failed['ai_reviews']['Q3']['status']=='failed'
    assert 'secret' not in failed['ai_reviews']['Q3']['message']
    assert failed['ai_reviews']['Q2']['status']=='ready'
    monkeypatch.setattr(review_ai,'review_answer',lambda config,q,*args:review_ai.validate_feedback(json.dumps(raw_feedback('partial')),q))
    fixed=review(call,pid,'Q3')
    assert fixed['result']['total_score']==3
    assert fixed['result']['questions'][1]['score']==2


def test_manual_update_during_ai_request_is_preserved(setup_practice,monkeypatch):
    _,_,call,_,_=setup_practice;pid=submit(setup_practice)
    def mocked(config,q,*args):
        call('/api/practices/{practice_id}/self-review','PUT',practice_id=pid,body=ReviewInput(revision=1,scores={'Q2':0}))
        return review_ai.validate_feedback(json.dumps(raw_feedback()),q)
    monkeypatch.setattr(review_ai,'review_answer',mocked)
    result=review(call,pid)
    assert result['result']['questions'][1]['score']==0 and result['result']['questions'][1]['mode']=='self'
    assert result['ai_reviews']['Q2']['feedback']['score']==2


def test_permissions_and_ineligible_questions_never_call_ai(setup_practice,monkeypatch):
    _,_,call,_,_=setup_practice;pid=create(setup_practice)
    monkeypatch.setattr(review_ai,'review_answer',lambda *args:pytest.fail('Must not call AI'))
    with pytest.raises(HTTPException) as error: review(call,pid)
    assert error.value.status_code==409
    with pytest.raises(HTTPException) as error: review(call,pid,user={'id':2})
    assert error.value.status_code==404
    call('/api/practices/{practice_id}/submit','POST',practice_id=pid,body=AnswersInput(revision=0,answers={}))
    for qid in ['Q1','Q2','unknown']:
        with pytest.raises(HTTPException) as error: review(call,pid,qid)
        assert error.value.status_code==422


def test_late_result_does_not_restore_expired_job(setup_practice,monkeypatch):
    path,_,call,_,_=setup_practice;pid=submit(setup_practice)
    def mocked(config,q,*args):
        with sqlite3.connect(path) as conn:
            conn.execute('UPDATE practice_reviews SET started_at=? WHERE practice_id=?',(time.time()-400,pid))
        return review_ai.validate_feedback(json.dumps(raw_feedback()),q)
    monkeypatch.setattr(review_ai,'review_answer',mocked)
    result=review(call,pid)
    assert result['ai_reviews']['Q2']['status']=='failed'
    assert result['result']['questions'][1]['score'] is None
