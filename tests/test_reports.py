import json
import sqlite3

import pytest
from fastapi import HTTPException
from backend.app import CourseInput
from backend.practice import AnswersInput, ReviewInput
from backend.mistakes import RetryInput
from backend.reports import metrics
from test_practice import setup_practice, create


def report(setup):
    return setup[2]('/api/courses/{course_id}/report',course_id=setup[1])


def submitted(setup):
    pid=create(setup)
    setup[2]('/api/practices/{practice_id}/submit','POST',practice_id=pid,
             body=AnswersInput(revision=0,answers={'Q1':['A'],'Q2':['One'],'Q4':['A'],'Q5':['错误']}))
    return pid


def test_empty_and_unsubmitted_do_not_become_zero_scores(setup_practice):
    data=report(setup_practice)
    assert data['first_attempts']['totals']['score_rate'] is None
    assert data['first_attempts']['submitted_attempts']==0
    create(setup_practice);data=report(setup_practice)
    assert data['first_attempts']['ready_attempts']==1
    assert data['first_attempts']['totals']['questions']==0
    assert data['retries']['totals']['score_rate'] is None


def test_partial_credit_pending_and_scoring_modes(setup_practice):
    submitted(setup_practice);data=report(setup_practice);first=data['first_attempts']
    assert first['totals']=={'questions':5,'graded':4,'pending':1,'unanswered':1,'earned':3,'graded_max':8,'score_rate':37.5,'full_score':1,'partial':1,'zero':2,'small_sample':True}
    assert first['fully_scored_attempts']==0
    automatic=next(row for row in first['by_mode'] if row['mode']=='automatic')
    assert automatic['graded']==3 and automatic['score_rate']==50
    subjective=next(row for row in first['by_kind'] if row['kind']=='fill')
    assert subjective['score_rate'] is None and subjective['pending']==1
    assert any('待评分' in text for text in data['suggestions'])


def test_retries_never_inflate_first_attempts(setup_practice):
    _,_,call,_,_=setup_practice;pid=submitted(setup_practice)
    rid=call('/api/practices/{practice_id}/retry','POST',practice_id=pid,body=RetryInput(question_ids=['Q4'],request_id='report-retry-12345'))['id']
    before=report(setup_practice)
    assert before['retries']['ready_attempts']==1 and before['retries']['totals']['questions']==0
    call('/api/practices/{practice_id}/submit','POST',practice_id=rid,body=AnswersInput(revision=0,answers={'Q4':['A','B']}))
    after=report(setup_practice)
    assert after['first_attempts']['totals']==before['first_attempts']['totals']
    assert after['retries']['totals']['score_rate']==100 and after['retries']['submitted_attempts']==1
    assert after['mistakes']['full_score']==1


def test_chapter_overlap_deduplicates_within_title(setup_practice):
    path,_,_,_,_=setup_practice;pid=submitted(setup_practice)
    with sqlite3.connect(path) as conn:
        ranges=json.loads(conn.execute('SELECT selected_chapters FROM practices WHERE id=?',(pid,)).fetchone()[0])
        ranges=[ranges[0],dict(ranges[0]),{**ranges[0],'title':'Second chapter'}]
        conn.execute('UPDATE practices SET selected_chapters=? WHERE id=?',(json.dumps(ranges),pid))
    data=report(setup_practice)['first_attempts']
    assert data['totals']['questions']==5
    assert len(data['chapters'])==2 and all(row['questions']==5 for row in data['chapters'])


def test_manual_score_updates_report_and_keeps_source_label(setup_practice):
    call=setup_practice[2];pid=submitted(setup_practice)
    call('/api/practices/{practice_id}/self-review','PUT',practice_id=pid,body=ReviewInput(revision=1,scores={'Q2':2}))
    data=report(setup_practice);first=data['first_attempts']
    assert first['totals']['score_rate']==50 and first['totals']['pending']==0
    assert first['fully_scored_attempts']==1 and not first['totals']['small_sample']
    assert next(row for row in first['by_mode'] if row['mode']=='self')['earned']==2
    assert any('可优先复习' in text for text in data['suggestions'])


def test_course_and_user_isolation_and_no_raw_answers(setup_practice):
    _,course,call,_,_=setup_practice;submitted(setup_practice)
    with pytest.raises(HTTPException) as error:call('/api/courses/{course_id}/report',course_id=course,user={'id':2})
    assert error.value.status_code==404
    other=call('/api/courses','POST',body=CourseInput(name='Other'))['id']
    assert call('/api/courses/{course_id}/report',course_id=other)['first_attempts']['totals']['questions']==0
    data=report(setup_practice)
    assert 'Sample reference data' not in json.dumps(data)
    assert 'student_answer' not in json.dumps(data)


def test_recent_limit_and_failed_requests_excluded(setup_practice):
    path,_,_,_,_=setup_practice;pid=submitted(setup_practice)
    with sqlite3.connect(path) as conn:
        conn.row_factory=sqlite3.Row
        original=dict(conn.execute('SELECT * FROM practices WHERE id=?',(pid,)).fetchone())
        for i in range(12):
            row={**original,'id':f'copy-{i}','request_id':f'copy-request-{i}','submitted_at':100+i,'created_at':100+i}
            conn.execute('INSERT INTO practices('+','.join(row)+') VALUES('+','.join('?' for _ in row)+')',list(row.values()))
        conn.execute("UPDATE practices SET status='failed' WHERE id=?",(pid,))
    data=report(setup_practice)['first_attempts']
    assert data['submitted_attempts']==12 and data['totals']['questions']==60
    assert len(data['recent'])==10 and data['recent'][0]['id']=='copy-11'


def test_pending_and_zero_have_different_denominators():
    rows=[dict(score=None,max_score=2,answered=True),dict(score=0,max_score=2,answered=False)]
    result=metrics(rows)
    assert result['score_rate']==0 and result['graded_max']==2 and result['pending']==1
    assert metrics(rows[:1])['score_rate'] is None
