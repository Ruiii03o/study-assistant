import json
import sqlite3
import pytest
from fastapi import HTTPException
from backend import ai, knowledge_guide
from backend.practice import AnswersInput
from test_practice import setup_practice, create

GUIDE={'title':'决策树','overview':'按特征划分样本。','concepts':[{'name':'C4.5','explanation':'使用信息增益率。'}],
       'differences':['CART回归树与分类树指标不同。'],'example':'按特征划分。','takeaway':'区分划分指标。'}
PATH='/api/practices/{practice_id}/knowledge-guide/{question_id}'


def test_generate_validate_and_fenced_json(monkeypatch):
    monkeypatch.setattr(ai,'settings',lambda:{})
    monkeypatch.setattr(ai,'request_content',lambda *a,**k:'```json\n'+json.dumps(GUIDE)+'\n```')
    assert knowledge_guide.generate({}, {})==GUIDE
    monkeypatch.setattr(ai,'request_content',lambda *a,**k:'{}')
    with pytest.raises(ai.AIError):knowledge_guide.generate({}, {})


def test_private_submitted_cached_and_not_called_on_read(setup_practice,monkeypatch):
    pid=create(setup_practice);call=setup_practice[2];calls=[]
    monkeypatch.setattr(knowledge_guide,'generate',lambda *a:calls.append(1) or GUIDE)
    with pytest.raises(HTTPException):call(PATH,practice_id=pid,question_id='Q1')
    call('/api/practices/{practice_id}/submit','POST',practice_id=pid,body=AnswersInput(revision=0,answers={}))
    assert call(PATH,practice_id=pid,question_id='Q1')['guide'] is None
    assert not calls
    for _ in range(2):assert call(PATH,'POST',practice_id=pid,question_id='Q1')['guide']==GUIDE
    assert len(calls)==1
    assert call(PATH,practice_id=pid,question_id='Q1')['guide']==GUIDE
    with pytest.raises(HTTPException) as error:call(PATH,practice_id=pid,question_id='Q1',user={'id':2})
    assert error.value.status_code==404


def test_duplicate_inflight_and_failed_attempt_can_retry(setup_practice,monkeypatch):
    pid=create(setup_practice);call=setup_practice[2]
    call('/api/practices/{practice_id}/submit','POST',practice_id=pid,body=AnswersInput(revision=0,answers={}))
    def fail(*args):
        with pytest.raises(HTTPException) as error:call(PATH,'POST',practice_id=pid,question_id='Q1')
        assert error.value.status_code==409
        raise ai.AIError('timeout')
    monkeypatch.setattr(knowledge_guide,'generate',fail)
    with pytest.raises(HTTPException) as error:call(PATH,'POST',practice_id=pid,question_id='Q1')
    assert error.value.status_code==502
    assert not call(PATH,practice_id=pid,question_id='Q1')['generating']
    monkeypatch.setattr(knowledge_guide,'generate',lambda *a:GUIDE)
    assert call(PATH,'POST',practice_id=pid,question_id='Q1')['guide']==GUIDE
