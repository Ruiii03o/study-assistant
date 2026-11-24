import json
import sqlite3
import pytest
from fastapi import HTTPException
from backend import exams
from backend.practice import AnswersInput
from test_practice import setup_practice, create


def prepare(setup, monkeypatch):
    monkeypatch.setattr(exams, 'now', lambda: 1000.0)
    setup[3].exam_minutes = 1
    pid = create(setup)
    return pid, setup[2]


def test_start_hides_questions_and_cannot_extend(setup_practice, monkeypatch):
    pid, call = prepare(setup_practice, monkeypatch)
    get = lambda: call('/api/practices/{practice_id}', practice_id=pid)
    assert get()['questions'] == []
    with pytest.raises(HTTPException) as error:
        call('/api/practices/{practice_id}/submit','POST',practice_id=pid,body=AnswersInput(revision=0,answers={}))
    assert error.value.status_code == 409
    record=call('/api/practices/{practice_id}/start-exam','POST',practice_id=pid)
    assert record['deadline']==1060 and len(record['questions'])==5
    assert all('answer' not in q for q in record['questions'])
    monkeypatch.setattr(exams,'now',lambda:1030)
    again=call('/api/practices/{practice_id}/start-exam','POST',practice_id=pid)
    assert again['deadline']==1060 and again['revision']==record['revision']


@pytest.mark.parametrize('entry',['get','submit','save','report','list'])
def test_timeout_uses_saved_answers_once(setup_practice, monkeypatch, entry):
    pid,call=prepare(setup_practice,monkeypatch)
    r=call('/api/practices/{practice_id}/start-exam','POST',practice_id=pid)
    saved=call('/api/practices/{practice_id}/answers','PUT',practice_id=pid,body=AnswersInput(revision=r['revision'],answers={'Q1':['A']}))
    monkeypatch.setattr(exams,'now',lambda:1060)
    late=AnswersInput(revision=saved['revision'],answers={'Q1':['B']})
    if entry=='submit':call('/api/practices/{practice_id}/submit','POST',practice_id=pid,body=late)
    if entry=='save':call('/api/practices/{practice_id}/answers','PUT',practice_id=pid,body=late)
    if entry=='report':call('/api/courses/{course_id}/report',course_id=setup_practice[1])
    if entry=='list':call('/api/courses/{course_id}/practices',course_id=setup_practice[1])
    result=call('/api/practices/{practice_id}',practice_id=pid)
    assert result['status']=='submitted' and result['submission_reason']=='timeout'
    assert result['answers']=={'Q1':['A']} and result['result']['total_score']==2
    assert result['submitted_at']==1060 and result['revision']==saved['revision']+1
    again=call('/api/practices/{practice_id}/start-exam','POST',practice_id=pid)
    assert again['revision']==result['revision']
    report=call('/api/courses/{course_id}/report',course_id=setup_practice[1])
    assert report['exams']['submitted_attempts']==1
    assert report['first_attempts']['submitted_attempts']==0


def test_exam_owner_and_manual_submit(setup_practice,monkeypatch):
    pid,call=prepare(setup_practice,monkeypatch)
    with pytest.raises(HTTPException) as error:
        call('/api/practices/{practice_id}/start-exam','POST',practice_id=pid,user={'id':2})
    assert error.value.status_code==404
    r=call('/api/practices/{practice_id}/start-exam','POST',practice_id=pid)
    result=call('/api/practices/{practice_id}/submit','POST',practice_id=pid,body=AnswersInput(revision=r['revision'],answers={}))
    assert result['submission_reason']=='manual' and result['status']=='submitted'
