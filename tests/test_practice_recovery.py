import json
import sqlite3
import pytest
from backend import ai,practice_ai
from backend.practice_candidates import complete
from test_practice import setup_practice,create,RAW


def test_normalizes_fill_and_ignores_unrelated_score_without_retry(monkeypatch):
    q={'kind':'fill','prompt':'两个空____与____','options':[],'answer':['甲','乙'],'key_points':['甲','乙'],'source_ids':'S1','explanation':'解释','points':2}
    calls=[]
    def request(*a,**k):calls.append(a);return json.dumps({'questions':[q]})
    monkeypatch.setattr(ai,'request_content',request)
    paper=complete({},'system','course',{'fill':1},[{'source_id':'S1'}])
    assert len(calls)==1 and len(paper['questions'][0]['answer'])==1


def test_repairs_only_missing_retains_valid_and_reports_specific_failure(monkeypatch):
    good=dict(RAW['questions'][0],prompt='Valid question')
    bad=dict(good,prompt='Bad question',source_ids=['UNKNOWN'])
    calls=[]
    def request(config,prompt,payload,*args,**kwargs):
        calls.append(payload)
        return json.dumps({'questions':[good,bad]}) if len(calls)==1 else json.dumps({'questions':[bad]})
    monkeypatch.setattr(ai,'request_content',request)
    with pytest.raises(ai.AIError) as e:complete({},'system','course',{'single':2},[{'source_id':'S1'}])
    assert calls[1]['counts']=={'single':1}
    assert calls[1]['accepted_prompts']==['Valid question']
    assert len(e.value.partial_questions)==1 and '引用不在' in str(e.value)
    monkeypatch.setattr(ai,'request_content',lambda *a,**k:json.dumps({'questions':[dict(good,prompt='New task')]}))
    done=complete({},'system','course',{'single':2},[{'source_id':'S1'}],initial=e.value.partial_questions)
    assert [q['prompt'] for q in done['questions']]==['Valid question','New task']


def test_transport_failure_never_automatically_retries(monkeypatch):
    calls=[]
    def request(*a,**k):calls.append(1);raise ai.AIError('AI 请求超时')
    monkeypatch.setattr(ai,'request_content',request)
    with pytest.raises(ai.AIError,match='请求超时'):complete({},'system','course',{'single':1},[{'source_id':'S1'}])
    assert len(calls)==1


def test_failure_persists_valid_questions_and_retry_uses_snapshot(setup_practice,monkeypatch):
    path,course,call,*_=setup_practice
    good={'id':'Q1',**RAW['questions'][0]}
    def fail(*a,**k):
        error=ai.AIError('missing fill');error.partial_questions=[good];raise error
    monkeypatch.setattr(practice_ai,'generate_practice',fail)
    failed={'id':create(setup_practice)}
    with sqlite3.connect(path) as c:
        row=c.execute('SELECT questions,created_at FROM practices WHERE id=?',(failed['id'],)).fetchone()
    assert len(json.loads(row[0]))==1
    detail=call('/api/practices/{practice_id}',practice_id=failed['id'])
    assert detail['retained_questions']==1 and 'answer' not in detail['questions'][0]
    from fastapi import HTTPException
    with pytest.raises(HTTPException):call('/api/practices/{practice_id}/retry-generation','POST',practice_id=failed['id'],user={'id':2})
    def resume(config,course,counts,sources,**kw):
        assert kw['initial']==[good]
        return practice_ai.validate_paper(json.dumps(RAW),sources,counts)
    monkeypatch.setattr(practice_ai,'generate_practice',resume)
    ready=call('/api/practices/{practice_id}/retry-generation','POST',practice_id=failed['id'])
    assert ready['status']=='ready' and ready['created_at']==row[1]
    with pytest.raises(HTTPException):call('/api/practices/{practice_id}/retry-generation','POST',practice_id=failed['id'])


def test_pipeline_keeps_partial_with_summary_refs_and_reuses_it(setup_practice,monkeypatch):
    from test_batching import long_setup
    body,_=long_setup(setup_practice,monkeypatch)
    path,course,call,*_=setup_practice
    run=call('/api/courses/{course_id}/practices','POST',course_id=course,body=body)
    record=call('/api/practices/{practice_id}',practice_id=run['id'])
    for _ in range(record['pipeline']['total']):call('/api/practices/{practice_id}/next','POST',practice_id=run['id'])
    def fail(config,name,counts,sources):
        error=ai.AIError('missing');error.partial_questions=[{'id':'Q1',**dict(RAW['questions'][0],source_ids=[sources[0]['source_id']])}];raise error
    monkeypatch.setattr(practice_ai,'generate_practice',fail)
    failed=call('/api/practices/{practice_id}/next','POST',practice_id=run['id'])
    assert failed['status']=='processing'
    with sqlite3.connect(path) as c:
        saved=json.loads(c.execute("SELECT result FROM practice_jobs WHERE practice_id=? AND kind='generate'",(run['id'],)).fetchone()[0])
    assert len(saved)==1 and saved[0]['source_ids'][0].startswith('K')
    def resume(config,name,counts,sources,**kw):
        assert kw['initial']==saved
        raw=json.loads(json.dumps(RAW))
        for q in raw['questions']:q['source_ids']=[sources[0]['source_id']]
        return practice_ai.validate_paper(json.dumps(raw),sources,counts)
    monkeypatch.setattr(practice_ai,'generate_practice',resume)
    done=call('/api/practices/{practice_id}/next','POST',practice_id=run['id'])
    assert done['status']=='ready'
