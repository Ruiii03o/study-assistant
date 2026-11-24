import json
import sqlite3
import pytest
from fastapi import HTTPException
from backend import practice_ai, review_ai, exams
from backend.scoring import stamp, point_score
from backend.practice import AnswersInput, ReviewInput
from backend.mistakes import RetryInput
from test_practice import setup_practice, create, paper


def new_paper():
    result=stamp(paper())
    result['questions'][2]['key_points']=['第一点','第二点','第三点']
    return result


@pytest.mark.parametrize('answer,expected',[([],0),(['A'],1.5),(['A','B'],3),(['A','C'],0),(['A','B','C'],0)])
def test_new_multiple_keeps_half_credit_rule(answer,expected):
    q=new_paper()['questions'][3]
    result=practice_ai.grade([q],{q['id']:answer})
    assert result['total_score']==expected and result['max_score']==3


@pytest.mark.parametrize('verdicts,expected',[
    (['met','met','met'],5),(['met','met','missed'],3.33),(['met','partial','missed'],2.5),(['missed']*3,0)])
def test_short_point_weighting_and_ai_same_rule(verdicts,expected):
    q=new_paper()['questions'][2]
    assert point_score(q,verdicts)==expected
    raw={'summary':'核对完成','points':[{'point_index':i,'verdict':v,'reason':'理由','basis':'material','source_ids':['S1']} for i,v in enumerate(verdicts)]}
    assert review_ai.validate_feedback(json.dumps(raw),q)['score']==expected


def test_new_maxima_and_legacy_snapshot_do_not_change():
    assert [q['max_score'] for q in new_paper()['questions']]==[2,2,5,3,2]
    assert practice_ai.grade(new_paper()['questions'],{})['max_score']==14
    assert practice_ai.grade(paper()['questions'],{})['max_score']==10
    assert point_score(paper()['questions'][2],['partial'])==1


def test_new_scoring_routes_retry_reports_and_manual_points(setup_practice,monkeypatch):
    monkeypatch.setattr(practice_ai,'generate_practice',lambda *args:new_paper())
    pid=create(setup_practice);call=setup_practice[2]
    public=call('/api/practices/{practice_id}',practice_id=pid)
    assert public['questions'][2]['max_score']==5 and 'key_points' not in public['questions'][2]
    result=call('/api/practices/{practice_id}/submit','POST',practice_id=pid,body=AnswersInput(revision=0,answers={'Q3':['answer'],'Q4':['A']}))
    assert result['result']['objective_max']==7 and result['result']['max_score']==14
    assert result['result']['questions'][3]['score']==1.5
    with pytest.raises(HTTPException): call('/api/practices/{practice_id}/self-review','PUT',practice_id=pid,body=ReviewInput(revision=1,scores={'Q3':5}))
    with pytest.raises(HTTPException): call('/api/practices/{practice_id}/self-review','PUT',practice_id=pid,body=ReviewInput(revision=1,point_verdicts={'Q3':['met']}))
    result=call('/api/practices/{practice_id}/self-review','PUT',practice_id=pid,body=ReviewInput(revision=1,point_verdicts={'Q3':['met','met','missed']}))
    assert result['result']['total_score']==4.83
    assert result['result']['questions'][2]['point_verdicts']==['met','met','missed']
    rid=call('/api/practices/{practice_id}/retry','POST',practice_id=pid,body=RetryInput(question_ids=['Q4'],request_id='new-score-retry-123'))['id']
    retry=call('/api/practices/{practice_id}/submit','POST',practice_id=rid,body=AnswersInput(revision=0,answers={'Q4':['A','B']}))
    assert retry['result']['total_score']==3
    item=next(i for i in call('/api/courses/{course_id}/mistakes',course_id=setup_practice[1])['items'] if i['question']['id']=='Q4')
    assert item['state']=='full_score'
    report=call('/api/courses/{course_id}/report',course_id=setup_practice[1])
    assert report['first_attempts']['totals']['graded_max']==14 and report['first_attempts']['totals']['earned']==4.83
    assert report['retries']['totals']['earned']==3


def test_new_exam_timeout_uses_question_snapshot(setup_practice,monkeypatch):
    monkeypatch.setattr(practice_ai,'generate_practice',lambda *args:new_paper())
    monkeypatch.setattr(exams,'now',lambda:1000)
    setup_practice[3].exam_minutes=1;pid=create(setup_practice);call=setup_practice[2]
    started=call('/api/practices/{practice_id}/start-exam','POST',practice_id=pid)
    call('/api/practices/{practice_id}/answers','PUT',practice_id=pid,body=AnswersInput(revision=started['revision'],answers={'Q4':['A','B']}))
    monkeypatch.setattr(exams,'now',lambda:1061)
    result=call('/api/practices/{practice_id}',practice_id=pid)
    assert result['result']['total_score']==3 and result['result']['max_score']==14


def test_knowledge_is_private_locked_before_submission_and_matches_sources(setup_practice):
    path,course,call,*_=setup_practice;pid=create(setup_practice)
    with pytest.raises(HTTPException) as e: call('/api/practices/{practice_id}/knowledge/{question_id}',practice_id=pid,question_id='Q1')
    assert e.value.status_code==409
    call('/api/practices/{practice_id}/submit','POST',practice_id=pid,body=AnswersInput(revision=0,answers={}))
    result={'sections':[{'title':'知识章','points':[{'text':'匹配要点','source_ids':['A']},{'text':'不匹配要点','source_ids':['B']}]}]}
    sources=[{'source_id':'A','material_id':'m1','unit_index':0},{'source_id':'B','material_id':'m1','unit_index':1}]
    with sqlite3.connect(path) as conn:
        conn.execute("INSERT INTO outlines(id,owner_id,course_id,status,goal,detail,model,sources,versions,result,created_at) VALUES('knowledge-outline',1,?,'ready','','','test',?,'{}',?,1)",(course,json.dumps(sources),json.dumps(result)))
    data=call('/api/practices/{practice_id}/knowledge/{question_id}',practice_id=pid,question_id='Q1')
    assert data['related_outline_points']==[]  # Same page alone is insufficient.
    assert data['sources'][0]['text']=='Sample reference data'
    with pytest.raises(HTTPException) as e: call('/api/practices/{practice_id}/knowledge/{question_id}',practice_id=pid,question_id='Q1',user={'id':2})
    assert e.value.status_code==404
