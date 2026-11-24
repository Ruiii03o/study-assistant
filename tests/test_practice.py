import copy
import json
import sqlite3
import time

import httpx
import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from backend import ai, practice_ai
from backend.scoring import stamp
from backend.app import create_app, Credentials, CourseInput
from backend.practice import PracticeInput, AnswersInput, ReviewInput

SOURCES = [{'source_id':'S1','text':'Sample reference data'}]
COUNTS = {k:1 for k in practice_ai.KINDS}
RAW = {'title':'Test practice', 'questions':[
    {'kind':'single','prompt':'Single question','options':['One','Two'],'answer':['A'],'explanation':'Reference one','key_points':[],'source_ids':['S1']},
    {'kind':'multiple','prompt':'Multiple question','options':['One','Two','Three'],'answer':['A','B'],'explanation':'Reference two','key_points':[],'source_ids':['S1']},
    {'kind':'true_false','prompt':'True false question','options':[],'answer':['正确'],'explanation':'Reference three','key_points':[],'source_ids':['S1']},
    {'kind':'fill','prompt':'Fill ____','options':[],'answer':['One'],'explanation':'Reference four','key_points':['One'],'source_ids':['S1']},
    {'kind':'short','prompt':'Explain the idea','options':[],'answer':['Idea'],'explanation':'Reference five','key_points':['Idea'],'source_ids':['S1']},
]}


def paper():
    return practice_ai.validate_paper(json.dumps(RAW), SOURCES, COUNTS)


@pytest.mark.parametrize('mutation', ['count','citation','single','multiple','options','duplicate','empty','key_points'])
def test_invalid_questions_rejected(mutation):
    raw = copy.deepcopy(RAW)
    if mutation == 'count': raw['questions'].pop()
    if mutation == 'citation': raw['questions'][0]['source_ids'] = ['S404']
    if mutation == 'single': raw['questions'][0]['answer'] = ['A','B']
    if mutation == 'multiple': raw['questions'][1]['answer'] = ['A']
    if mutation == 'options': raw['questions'][0]['answer'] = ['F']
    if mutation == 'duplicate': raw['questions'][1]['prompt'] = raw['questions'][0]['prompt']
    if mutation == 'empty': raw['questions'][0]['explanation'] = ' '
    if mutation == 'key_points': raw['questions'][3]['key_points'] = []
    with pytest.raises(ai.AIError):
        practice_ai.validate_paper(json.dumps(raw), SOURCES, COUNTS)


@pytest.mark.parametrize('selected,score', [([],0),(['A'],1),(['A','B'],2),(['A','C'],0),(['A','B','C'],0)])
def test_multiple_choice_scoring(selected, score):
    q = next(q for q in paper()['questions'] if q['kind'] == 'multiple')
    assert practice_ai.grade([q], {q['id']:selected})['total_score'] == score


def test_subjective_pending_and_empty_answers():
    questions = paper()['questions']
    assert [q['kind'] for q in questions] == ['single','fill','short','multiple','true_false']
    result = practice_ai.grade(questions, {'Q2':['One'],'Q3':['   ']})
    assert result['pending_self_review'] == 1 and result['total_score'] is None
    assert result['questions'][2]['mode'] == 'blank'
    assert practice_ai.grade(questions, {})['total_score'] == 0


def test_generation_transport_and_no_credentials_in_return():
    config = {'url':'https://api.deepseek.com/chat/completions','model':'test','api_key':'fake-secret'}
    def handle(request):
        body = json.loads(request.content)
        assert json.loads(body['messages'][1]['content'])['counts'] == COUNTS
        assert body['response_format'] == {'type':'json_object'}
        return httpx.Response(200,json={'choices':[{'finish_reason':'stop','message':{'content':json.dumps(RAW)}}]})
    result = practice_ai.generate_practice(config,'Test',COUNTS,SOURCES,transport=httpx.MockTransport(handle))
    assert result == stamp(paper()) and 'fake-secret' not in json.dumps(result)


@pytest.fixture
def setup_practice(tmp_path, monkeypatch):
    path = tmp_path/'practice.db'
    app = create_app(path)
    routes = {(r.path,m):r.endpoint for r in app.routes if hasattr(r,'methods') for m in r.methods}
    def call(route, method='GET', user=None, **kwargs):
        return routes[route,method](user=user or {'id':1}, **kwargs)
    for name in ['alice','bobby']:
        routes['/api/auth/register','POST'](body=Credentials(username=name,password='test-password-123'))
    course = call('/api/courses','POST',body=CourseInput(name='Test'))['id']
    units = [{'location':'Slide 1','text':'Sample reference data'}, {'location':'Slide 2','text':'Excluded data'}]
    chapters = [dict(title='Selected',unit_index=0,end_unit_index=0,included=True)]
    with sqlite3.connect(path) as conn:
        conn.execute('INSERT INTO materials(id,owner_id,course_id,name,suffix,size,status,units,chapters,confirmed) VALUES(?,?,?,?,?,?,?,?,?,?)',
                     ('m1',1,course,'test.pptx','.pptx',10,'ready',json.dumps(units),json.dumps(chapters),1))
    keys = [r['key'] for g in call('/api/courses/{course_id}/chapters',course_id=course) for r in g['ranges']]
    calls = []
    monkeypatch.setattr(ai,'settings',lambda: {'model':'test-model'})
    def generate(config, name, counts, sources):
        calls.append(sources)
        return paper()
    monkeypatch.setattr(practice_ai,'generate_practice',generate)
    body = PracticeInput(material_ids=['m1'],chapter_keys=keys,counts=COUNTS,request_id='request-1234567890')
    return path,course,call,body,calls


def create(setup):
    _,course,call,body,_ = setup
    return call('/api/courses/{course_id}/practices','POST',course_id=course,body=body)['id']


def test_generation_redaction_isolation_and_idempotency(setup_practice):
    _,course,call,body,calls = setup_practice
    pid = create(setup_practice)
    assert create(setup_practice) == pid and len(calls) == 1
    assert len(calls[0]) == 1 and calls[0][0]['unit_index'] == 0
    detail = call('/api/practices/{practice_id}',practice_id=pid)
    assert detail['status'] == 'ready' and 'sources' not in detail and 'result' not in detail
    assert all(set(q) == {'id','kind','prompt','options'} for q in detail['questions'])
    assert len(call('/api/courses/{course_id}/practices',course_id=course)) == 1
    for route,method,args in [
        ('/api/practices/{practice_id}','GET',dict(practice_id=pid)),
        ('/api/courses/{course_id}/practices','GET',dict(course_id=course)),
        ('/api/practices/{practice_id}/answers','PUT',dict(practice_id=pid,body=AnswersInput(revision=0,answers={}))),
        ('/api/practices/{practice_id}/submit','POST',dict(practice_id=pid,body=AnswersInput(revision=0,answers={}))),
        ('/api/practices/{practice_id}/self-review','PUT',dict(practice_id=pid,body=ReviewInput(revision=0,scores={}))),
    ]:
        with pytest.raises(HTTPException) as error:
            call(route,method,user={'id':2},**args)
        assert error.value.status_code == 404


def test_drafts_revision_submit_lock_and_self_review(setup_practice):
    path,_,call,_,_ = setup_practice
    pid = create(setup_practice)
    answers = {'Q1':['A'],'Q2':['One'],'Q3':['Idea'],'Q4':['A'],'Q5':['错误']}
    save = call('/api/practices/{practice_id}/answers','PUT',practice_id=pid,body=AnswersInput(revision=0,answers=answers))
    assert save['revision'] == 1
    with pytest.raises(HTTPException) as error:
        call('/api/practices/{practice_id}/answers','PUT',practice_id=pid,body=AnswersInput(revision=0,answers={}))
    assert error.value.status_code == 409
    # Persistence across app restart before submission.
    restarted = create_app(path)
    endpoint = next(r.endpoint for r in restarted.routes if r.path == '/api/practices/{practice_id}')
    assert endpoint(practice_id=pid,user={'id':1})['answers'] == answers
    result = call('/api/practices/{practice_id}/submit','POST',practice_id=pid,body=AnswersInput(revision=1,answers=answers))
    assert result['status'] == 'submitted'
    assert result['result']['objective_score'] == 3 and result['result']['objective_max'] == 6
    assert result['result']['pending_self_review'] == 2 and result['result']['total_score'] is None
    repeated = call('/api/practices/{practice_id}/submit','POST',practice_id=pid,body=AnswersInput(revision=1,answers={}))
    assert repeated['answers'] == answers and repeated['revision'] == 2
    with pytest.raises(HTTPException):
        call('/api/practices/{practice_id}/answers','PUT',practice_id=pid,body=AnswersInput(revision=2,answers={}))
    with pytest.raises(HTTPException):
        call('/api/practices/{practice_id}/self-review','PUT',practice_id=pid,body=ReviewInput(revision=2,scores={'Q1':2}))
    review = call('/api/practices/{practice_id}/self-review','PUT',practice_id=pid,body=ReviewInput(revision=2,scores={'Q2':2,'Q3':1}))
    assert review['result']['total_score'] == 6 and review['result']['pending_self_review'] == 0
    assert review['result']['objective_score'] == 3
    assert review['result']['questions'][1]['mode'] == 'self'
    with sqlite3.connect(path) as conn:
        conn.execute("UPDATE materials SET units='[]' WHERE id='m1'")
    historical = call('/api/practices/{practice_id}',practice_id=pid)
    assert historical['stale'] and historical['sources'][0]['text'] == 'Sample reference data'


@pytest.mark.parametrize('answers', [{'Q99':['A']},{'Q1':['A','B']},{'Q4':['F']},{'Q4':['A','A']},{'Q5':['A']},{'Q2':['a','b']}])
def test_invalid_answers_rejected(setup_practice, answers):
    _,_,call,_,_ = setup_practice
    pid = create(setup_practice)
    with pytest.raises(HTTPException) as error:
        call('/api/practices/{practice_id}/answers','PUT',practice_id=pid,body=AnswersInput(revision=0,answers=answers))
    assert error.value.status_code == 422


def test_provider_failure_and_expired_generation(setup_practice, monkeypatch):
    path,course,call,body,_ = setup_practice
    def fail(*args): raise RuntimeError('private secret error')
    monkeypatch.setattr(practice_ai,'generate_practice',fail)
    pid = create(setup_practice)
    detail = call('/api/practices/{practice_id}',practice_id=pid)
    assert detail['status'] == 'failed' and detail['questions'] == []
    assert 'secret' not in detail['message']
    with sqlite3.connect(path) as conn:
        conn.execute("UPDATE practices SET status='generating',created_at=? WHERE id=?",(time.time()-400,pid))
    assert call('/api/practices/{practice_id}',practice_id=pid)['status'] == 'failed'


def test_pending_generation_conflict_and_stale_selection_never_call_ai(setup_practice):
    path,course,call,body,calls = setup_practice
    pid = create(setup_practice)
    fresh = body.model_copy(update={'request_id':'another-1234567890'})
    with sqlite3.connect(path) as conn:
        conn.execute("UPDATE practices SET status='generating' WHERE id=?", (pid,))
    with pytest.raises(HTTPException) as error:
        call('/api/courses/{course_id}/practices','POST',course_id=course,body=fresh)
    assert error.value.status_code == 409 and len(calls) == 1
    with sqlite3.connect(path) as conn:
        conn.execute("UPDATE practices SET status='failed' WHERE id=?", (pid,))
        conn.execute("UPDATE materials SET name='changed' WHERE id='m1'")
    with pytest.raises(HTTPException) as error:
        call('/api/courses/{course_id}/practices','POST',course_id=course,body=fresh)
    assert error.value.status_code == 409 and len(calls) == 1


@pytest.mark.parametrize('counts', [{'single':0},{'single':21},{'single':10,'short':11},{'single':-1},{'single':True}])
def test_invalid_counts_rejected(counts):
    with pytest.raises(ValidationError):
        PracticeInput(material_ids=['m'],chapter_keys=['key'],counts=counts,request_id='request-1234567890')
