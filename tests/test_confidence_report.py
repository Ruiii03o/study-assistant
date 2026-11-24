import json
import pytest
from fastapi import HTTPException
from backend.confidence_report import analyze
from backend.learning_tools import ConfidenceInput
from backend.practice import AnswersInput
from test_practice import setup_practice,create


def test_confidence_report_outcomes_are_not_score_weighted():
    questions=[{'id':str(i),'prompt':'Question'} for i in range(5)]
    grades=[{'id':'0','score':2,'max_score':2},{'id':'1','score':1,'max_score':2},{'id':'2','score':0,'max_score':5},{'id':'3','score':None,'max_score':5},{'id':'4','score':2,'max_score':2}]
    record={'id':'p','title':'P','status':'submitted','parent_id':None,'questions':json.dumps(questions),'result':json.dumps({'questions':grades}),'confidence_values':json.dumps({'0':3,'1':3,'2':3,'3':3})}
    group=analyze([record])['groups']['first'];band=group['bands'][2]
    assert band=={'level':3,'correct':1,'partial':1,'incorrect':1,'pending':1,'graded':3,'rate':33.3}
    assert group['unrecorded']==1 and len(group['items'])==4
    assert analyze([{**record,'status':'ready'}])['groups']['first']['items']==[]
    for key,extra in [('retry',{'parent_id':'x'}),('variant',{'variant_of':'x'}),('exam',{'attempt_kind':'exam'})]:
        data=analyze([{**record,**extra}])['groups'];assert len(data[key]['items'])==(4 if key=='exam' else 0) and data['first']['items']==[]
        if key!='exam':assert data[key]['unrecorded']==0


def test_saved_confidence_visible_only_after_submission_and_owner_only(setup_practice):
    _,course,call,*_=setup_practice;pid=create(setup_practice)
    call('/api/practices/{practice_id}/confidence','PUT',practice_id=pid,body=ConfidenceInput(revision=0,values={'Q1':3,'Q2':1}))
    assert call('/api/courses/{course_id}/confidence-report',course_id=course)['groups']['first']['items']==[]
    call('/api/practices/{practice_id}/submit','POST',practice_id=pid,body=AnswersInput(revision=0,answers={}))
    report=call('/api/courses/{course_id}/confidence-report',course_id=course)
    assert len(report['groups']['first']['items'])==2
    with pytest.raises(HTTPException) as error:call('/api/courses/{course_id}/confidence-report',course_id=course,user={'id':2})
    assert error.value.status_code==404
    with pytest.raises(HTTPException):call('/api/practices/{practice_id}/confidence','PUT',practice_id=pid,body=ConfidenceInput(revision=1,values={'Q1':1}))
