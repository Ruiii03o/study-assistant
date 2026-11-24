import json
import sqlite3

import pytest
from fastapi import HTTPException
from backend import ai, practice_ai
from backend.app import create_app, CourseInput
from backend.mistakes import RetryInput
from backend.practice import AnswersInput, ReviewInput
from test_practice import setup_practice, create


def submitted(setup):
    pid=create(setup);call=setup[2]
    call('/api/practices/{practice_id}/submit','POST',practice_id=pid,
         body=AnswersInput(revision=0,answers={'Q1':['A'],'Q2':['One'],'Q4':['A'],'Q5':['错误']}))
    return pid


def book(setup):
    return setup[2]('/api/courses/{course_id}/mistakes',course_id=setup[1])


def retry(setup,pid,qids=None,request_id='retry-request-123456'):
    return setup[2]('/api/practices/{practice_id}/retry','POST',practice_id=pid,
                    body=RetryInput(question_ids=qids or ['Q4'],request_id=request_id))


def test_only_scored_mistakes_including_partial_and_blank(setup_practice):
    submitted(setup_practice)
    result=book(setup_practice)
    assert {item['question']['id'] for item in result['items']}=={'Q3','Q4','Q5'}
    assert result['summary']=={'total':3,'ungraded_excluded':1,'needs_practice':3,'full_score':0,'pending_review':0}
    assert next(i for i in result['items'] if i['question']['id']=='Q4')['first_score']==1


def test_retry_is_independent_redacted_and_never_calls_ai(setup_practice,monkeypatch):
    _,_,call,_,_=setup_practice;pid=submitted(setup_practice)
    original=call('/api/practices/{practice_id}',practice_id=pid)
    monkeypatch.setattr(ai,'settings',lambda:pytest.fail('Retry should not need configuration'))
    monkeypatch.setattr(practice_ai,'generate_practice',lambda *args:pytest.fail('Retry must not generate new questions'))
    rid=retry(setup_practice,pid)['id']
    record=call('/api/practices/{practice_id}',practice_id=rid)
    assert record['parent_id']==pid and record['answers']=={} and record['revision']==0
    assert record['questions']==[{k:original['questions'][3][k] for k in ['id','kind','prompt','options']}]
    assert 'sources' not in record and 'result' not in record
    assert retry(setup_practice,pid)['id']==rid
    assert retry(setup_practice,pid,request_id='another-retry-123456')['id']==rid
    assert next(i for i in book(setup_practice)['items'] if i['question']['id']=='Q4')['pending_retry_id']==rid
    call('/api/practices/{practice_id}/submit','POST',practice_id=rid,body=AnswersInput(revision=0,answers={'Q4':['A','B']}))
    assert call('/api/practices/{practice_id}',practice_id=pid)==original
    item=next(i for i in book(setup_practice)['items'] if i['question']['id']=='Q4')
    assert item['state']=='full_score' and item['first_score']==1 and item['latest_score']==2 and item['retry_count']==1
    assert item['pending_retry_id'] is None


def test_full_score_history_can_be_retried_and_partial_score_returns_to_list(setup_practice):
    call=setup_practice[2];pid=submitted(setup_practice);rid=retry(setup_practice,pid)['id']
    call('/api/practices/{practice_id}/submit','POST',practice_id=rid,body=AnswersInput(revision=0,answers={'Q4':['A','B']}))
    again=retry(setup_practice,rid,request_id='second-retry-123456')['id']
    assert call('/api/practices/{practice_id}',practice_id=again)['parent_id']==pid
    call('/api/practices/{practice_id}/submit','POST',practice_id=again,body=AnswersInput(revision=0,answers={'Q4':['A']}))
    item=next(i for i in book(setup_practice)['items'] if i['question']['id']=='Q4')
    assert item['state']=='needs_practice' and item['retry_count']==2
    assert [a['score'] for a in item['attempts']]==[1,2,1]


def test_pending_subjective_retry_not_counted_as_wrong_score(setup_practice):
    call=setup_practice[2];pid=submitted(setup_practice)
    rid=retry(setup_practice,pid,['Q3'])['id']
    call('/api/practices/{practice_id}/submit','POST',practice_id=rid,body=AnswersInput(revision=0,answers={'Q3':['My answer']}))
    item=next(i for i in book(setup_practice)['items'] if i['question']['id']=='Q3')
    assert item['state']=='pending_review' and item['latest_score'] is None
    call('/api/practices/{practice_id}/self-review','PUT',practice_id=rid,body=ReviewInput(revision=1,scores={'Q3':2}))
    item=next(i for i in book(setup_practice)['items'] if i['question']['id']=='Q3')
    assert item['state']=='full_score' and item['latest_mode']=='self'


def test_permissions_and_invalid_selection(setup_practice):
    _,course,call,_,_=setup_practice;pid=submitted(setup_practice)
    with pytest.raises(HTTPException) as error:
        call('/api/courses/{course_id}/mistakes',course_id=course,user={'id':2})
    assert error.value.status_code==404
    with pytest.raises(HTTPException) as error:
        call('/api/practices/{practice_id}/retry','POST',practice_id=pid,user={'id':2},body=RetryInput(question_ids=['Q4'],request_id='not-my-retry-123456'))
    assert error.value.status_code==404
    for qids in [['Q1'],['Q2'],['unknown'],['Q4','unknown']]:
        with pytest.raises(HTTPException) as error:retry(setup_practice,pid,qids)
        assert error.value.status_code==422
    other=call('/api/courses','POST',body=CourseInput(name='Other'))['id']
    assert call('/api/courses/{course_id}/mistakes',course_id=other)['items']==[]


def test_request_conflict_overlap_and_multiple_question_retry(setup_practice):
    pid=submitted(setup_practice)
    rid=retry(setup_practice,pid,['Q4','Q5','Q4'])['id']
    assert len(setup_practice[2]('/api/practices/{practice_id}',practice_id=rid)['questions'])==2
    with pytest.raises(HTTPException) as error: retry(setup_practice,pid,['Q5'])
    assert error.value.status_code==409
    with pytest.raises(HTTPException) as error: retry(setup_practice,pid,['Q5'],request_id='different-request-1234')
    assert error.value.status_code==409


def test_snapshot_and_restart_persistence(setup_practice):
    path,course,call,_,_=setup_practice;pid=submitted(setup_practice)
    with sqlite3.connect(path) as conn:conn.execute("UPDATE materials SET units='[]',chapters='[]' WHERE id='m1'")
    rid=retry(setup_practice,pid)['id']
    call('/api/practices/{practice_id}/submit','POST',practice_id=rid,body=AnswersInput(revision=0,answers={}))
    record=call('/api/practices/{practice_id}',practice_id=rid)
    assert record['stale'] and record['sources'][0]['text']=='Sample reference data'
    app=create_app(path)
    endpoint=next(r.endpoint for r in app.routes if r.path=='/api/courses/{course_id}/mistakes')
    assert endpoint(course_id=course,user={'id':1})==book(setup_practice)


def test_original_manual_correction_updates_mistake_membership(setup_practice):
    call=setup_practice[2];pid=submitted(setup_practice)
    call('/api/practices/{practice_id}/self-review','PUT',practice_id=pid,body=ReviewInput(revision=1,scores={'Q2':1}))
    assert any(i['question']['id']=='Q2' for i in book(setup_practice)['items'])
    call('/api/practices/{practice_id}/self-review','PUT',practice_id=pid,body=ReviewInput(revision=2,scores={'Q2':2}))
    assert not any(i['question']['id']=='Q2' for i in book(setup_practice)['items'])
