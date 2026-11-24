import json
import pytest
from fastapi import HTTPException
from backend.study_actions import recommend
from backend.practice import AnswersInput
from backend.learning_tools import ConfidenceInput
from test_practice import setup_practice,create

def record(pid,score=0,confidence=3,**extra):
    q={'id':'Q1','kind':'single','prompt':'Question '+pid,'options':['A','B'],'answer':['A'],'explanation':'explanation','key_points':[],'source_ids':['S1'],'max_score':2}
    return {'id':pid,'title':pid,'status':'submitted','parent_id':None,'variant_of':None,'attempt_kind':'practice','questions':json.dumps([q]),'result':json.dumps({'questions':[{'id':'Q1','score':score,'mode':'automatic','max_score':2}]}),'answers':'{}','sources':'[]','confidence_values':json.dumps({'Q1':confidence}),'submitted_at':1,**extra}

def test_priorities_limit_and_unknown_confidence():
    rows=[record('low',confidence=1),record('unknown',confidence=None),record('middle',confidence=2),record('high'),record('right',score=2),record('pending',score=None)]
    result=recommend(rows)
    assert result['total']==4
    assert [r['item']['practice_id'] for r in result['items']]==['high','middle','low']
    assert recommend([record('unknown',confidence=None)])['items'][0]['confidence'] is None

def test_modes_retry_outcome_and_exact_variant_link():
    root=record('root');retry=record('retry',score=2,parent_id='root')
    assert recommend([root,retry])['items']==[]
    variant=record('v',score=2,variant_of='root:Q1')
    other=record('v2',score=0,variant_of='another:Q1')
    failed=record('v3',variant_of='root:Q1',status='failed')
    pending=record('v4',score=None,variant_of='root:Q1')
    result=recommend([root,variant,other,failed,pending])
    assert result['total']==1
    assert result['items'][0]['progress']=={'correct':1,'partial':0,'incorrect':0,'pending':1,'ready':0}
    assert recommend([record('exam',attempt_kind='exam')],'first')['items']==[]
    assert recommend([record('exam',attempt_kind='exam')],'exam')['total']==1

def test_endpoint_uses_saved_records_and_guards_owner(setup_practice):
    _,course,call,*_=setup_practice;pid=create(setup_practice)
    route='/api/courses/{course_id}/study-actions'
    assert call(route,course_id=course)['items']==[]
    call('/api/practices/{practice_id}/confidence','PUT',practice_id=pid,body=ConfidenceInput(revision=0,values={'Q1':3}))
    call('/api/practices/{practice_id}/submit','POST',practice_id=pid,body=AnswersInput(revision=0,answers={}))
    result=call(route,course_id=course)
    assert len(result['items'])==3
    assert result['items'][0]['item']['question']['id']=='Q1'
    assert result['items'][0]['confidence']==3
    assert 'points' in result['items'][0]
    with pytest.raises(HTTPException) as error:call(route,course_id=course,user={'id':2})
    assert error.value.status_code==404
    with pytest.raises(HTTPException):call(route,course_id=course,mode='invalid')
