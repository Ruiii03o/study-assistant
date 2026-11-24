import json
import sqlite3
import time

import pytest
from fastapi import HTTPException
from backend import ai, practice_ai, practice_pipeline
from backend.app import create_app, OutlineInput
from backend.batching import split_sources,pack_sources,ranges,encode,BATCH_CHARS
from test_practice import setup_practice, paper


def long_setup(setup,monkeypatch):
    path,course,call,body,calls=setup
    units=[{'location':f'Slide {i+1}','text':f'Topic {i} '+('内容'*4500)} for i in range(16)]
    chapters=[dict(title='All',unit_index=0,end_unit_index=15,included=True)]
    with sqlite3.connect(path) as conn:
        conn.execute('UPDATE materials SET units=?,chapters=? WHERE id=?',(encode(units),encode(chapters),'m1'))
    keys=[r['key'] for g in call('/api/courses/{course_id}/chapters',course_id=course) for r in g['ranges']]
    body=body.model_copy(update={'chapter_keys':keys})
    seen=[]
    def outline(config,name,goal,detail,sources):
        seen.append([s['source_id'] for s in sources])
        return {'title':'Test','sections':[{'title':f'Batch {len(seen)}','points':[{'text':'Topic summary','source_ids':[sources[0]['source_id']]}]}]}
    monkeypatch.setattr(ai,'generate_outline',outline)
    return body,seen


def sessions(setup,body):
    return setup[2]('/api/courses/{course_id}/outline-sessions','POST',course_id=setup[1],body=OutlineInput(material_ids=body.material_ids,chapter_keys=body.chapter_keys))


def test_split_no_lost_characters_and_exact_gaps():
    raw=[{'source_id':'S1','material_id':'m','unit_index':0,'name':'File','location':'Page 1','text':'汉😀'*25000}]
    pieces=split_sources(raw)
    assert ''.join(p['text'] for p in pieces)==raw[0]['text']
    assert pieces[0]['char_start']==0 and pieces[-1]['char_end']==len(raw[0]['text'])
    assert all(len(encode(batch))<=BATCH_CHARS for batch in pack_sources(pieces))
    assert all('字符' in r['start'] for r in ranges(pieces))
    short=[{**raw[0],'text':'x','unit_index':i,'location':f'Page {i+1}'} for i in [0,1,4]]
    labels=ranges(split_sources(short))
    assert [(r['start'],r['end']) for r in labels]==[('Page 1','Page 2'),('Page 5','Page 5')]


def test_partial_append_dedup_archive_and_new_workspace(setup_practice,monkeypatch):
    body,seen=long_setup(setup_practice,monkeypatch);path,course,call,_,_=setup_practice
    created=sessions(setup_practice,body);sid=created['id']
    assert created['total_batches']>1 and created['completed_batches']==0
    assert created['result']['sections']==[] and created['sources']==[]
    processed=call('/api/outline-sessions/{session_id}/next','POST',session_id=sid)
    assert processed['completed_batches']==1 and len(processed['result']['sections'])==1
    assert processed['parts'][0]['status']=='done' and processed['parts'][1]['status']=='pending'
    duplicate=sessions(setup_practice,body)
    assert duplicate['id']==sid and duplicate['total_batches']==created['total_batches']
    # New upload in the same course is appended behind the old queued range.
    with sqlite3.connect(path) as conn:
        conn.execute("INSERT INTO materials(id,owner_id,course_id,name,suffix,size,status,units,chapters,confirmed) VALUES(?,?,?,?,?,?,?,?,?,?)",('m2',1,course,'new.pptx','.pptx',10,'ready',encode([{'location':'Slide 1','text':'New content'}]),encode([dict(title='New',unit_index=0,end_unit_index=0,included=True)]),1))
    new_keys=[r['key'] for g in call('/api/courses/{course_id}/chapters',course_id=course) for r in g['ranges'] if r['material_id']=='m2']
    appended=call('/api/courses/{course_id}/outline-sessions','POST',course_id=course,body=OutlineInput(material_ids=['m2'],chapter_keys=new_keys))
    assert appended['total_batches']==created['total_batches']+1 and appended['parts'][-1]['ranges'][0]['name']=='new.pptx'
    assert appended['result']==processed['result']
    archived=call('/api/outline-sessions/{session_id}/archive','POST',session_id=sid)
    assert archived['status']=='archived' and archived['completed_batches']==1
    with pytest.raises(HTTPException):call('/api/outline-sessions/{session_id}/next','POST',session_id=sid)
    fresh=sessions(setup_practice,body);assert fresh['id']!=sid and fresh['completed_batches']==0
    restarted=create_app(path)
    endpoint=next(r.endpoint for r in restarted.routes if r.path=='/api/outline-sessions/{session_id}')
    assert endpoint(session_id=sid,user={'id':1})['result']==processed['result']


def test_failed_batch_keeps_completed_sections_and_retry_does_not_repeat_done(setup_practice,monkeypatch):
    body,seen=long_setup(setup_practice,monkeypatch);call=setup_practice[2]
    sid=sessions(setup_practice,body)['id'];first=call('/api/outline-sessions/{session_id}/next','POST',session_id=sid)
    original=ai.generate_outline
    monkeypatch.setattr(ai,'generate_outline',lambda *args:(_ for _ in ()).throw(ai.AIError('test failure')))
    failed=call('/api/outline-sessions/{session_id}/next','POST',session_id=sid)
    assert failed['completed_batches']==1 and failed['result']==first['result']
    assert failed['parts'][1]['status']=='failed'
    monkeypatch.setattr(ai,'generate_outline',original)
    resumed=call('/api/outline-sessions/{session_id}/next','POST',session_id=sid)
    assert resumed['completed_batches']==2 and len(seen)==2
    assert seen[0]!=seen[1] and len(set(s['source_id'] for s in resumed['sources']))==len(resumed['sources'])


def test_session_ownership_and_archive_running_guard(setup_practice,monkeypatch):
    body,_=long_setup(setup_practice,monkeypatch);path,course,call,_,_=setup_practice;sid=sessions(setup_practice,body)['id']
    for route,method,kwargs in [('/api/outline-sessions/{session_id}','GET',{'session_id':sid}),('/api/outline-sessions/{session_id}/next','POST',{'session_id':sid}),('/api/outline-sessions/{session_id}/archive','POST',{'session_id':sid}),('/api/courses/{course_id}/outline-sessions','GET',{'course_id':course})]:
        with pytest.raises(HTTPException) as error:call(route,method,user={'id':2},**kwargs)
        assert error.value.status_code==404
    with sqlite3.connect(path) as conn:conn.execute("UPDATE outline_parts SET status='running',started_at=? WHERE session_id=? AND seq=1",(time.time(),sid))
    with pytest.raises(HTTPException) as error:call('/api/outline-sessions/{session_id}/archive','POST',session_id=sid)
    assert error.value.status_code==409


def test_multi_batch_practice_reads_all_before_generation_and_maps_citations(setup_practice,monkeypatch):
    body,seen=long_setup(setup_practice,monkeypatch);_,course,call,_,_=setup_practice
    calls=[]
    def generate(config,name,counts,sources):
        calls.append(sources)
        result=paper()
        for q in result['questions']:q['source_ids']=[sources[0]['source_id']]
        return result
    monkeypatch.setattr(practice_ai,'generate_practice',generate)
    response=call('/api/courses/{course_id}/practices','POST',course_id=course,body=body);pid=response['id']
    assert response['status']=='processing' and calls==[]
    initial=call('/api/practices/{practice_id}',practice_id=pid);read_count=initial['pipeline']['total']
    for _ in range(read_count):
        record=call('/api/practices/{practice_id}/next','POST',practice_id=pid)
        assert record['status']=='processing' and record['questions']==[]
    assert len(seen)==read_count and calls==[]
    assert len({ref for batch in seen for ref in batch})==16
    final=call('/api/practices/{practice_id}/next','POST',practice_id=pid)
    assert final['status']=='ready' and len(final['questions'])==5
    assert all('answer' not in q for q in final['questions']) and len(calls)==1
    assert final['pipeline']['done']==final['pipeline']['total']
    # Idempotent retry after successful generation returns the persisted paper.
    assert call('/api/practices/{practice_id}/next','POST',practice_id=pid)['status']=='ready'
    assert len(calls)==1
    from backend.practice import AnswersInput
    result=call('/api/practices/{practice_id}/submit','POST',practice_id=pid,body=AnswersInput(revision=0,answers={}))
    source_ids={s['source_id'] for s in result['sources']}
    assert all(set(q['source_ids'])<=source_ids for q in result['questions'])


def test_practice_failure_retry_and_permission(setup_practice,monkeypatch):
    body,seen=long_setup(setup_practice,monkeypatch);_,course,call,_,_=setup_practice
    pid=call('/api/courses/{course_id}/practices','POST',course_id=course,body=body)['id']
    with pytest.raises(HTTPException) as error:call('/api/practices/{practice_id}/next','POST',practice_id=pid,user={'id':2})
    assert error.value.status_code==404
    original=ai.generate_outline
    monkeypatch.setattr(ai,'generate_outline',lambda *args:(_ for _ in ()).throw(RuntimeError('private error')))
    failed=call('/api/practices/{practice_id}/next','POST',practice_id=pid)
    assert failed['pipeline']['parts'][0]['status']=='failed' and failed['pipeline']['done']==0
    assert 'private' not in failed['pipeline']['parts'][0]['message']
    monkeypatch.setattr(ai,'generate_outline',original)
    resumed=call('/api/practices/{practice_id}/next','POST',practice_id=pid)
    assert resumed['pipeline']['done']==1


def test_hierarchical_summary_schedules_reduction_without_dropping_provenance(setup_practice):
    path,_,call,_,_=setup_practice
    from test_practice import create
    pid=create(setup_practice)
    with sqlite3.connect(path) as conn:
        conn.row_factory=sqlite3.Row
        for i in range(12):
            notes=[{'text':'knowledge '*700,'refs':[f'S{i+1}']}]
            conn.execute("INSERT INTO practice_jobs(practice_id,seq,round,kind,status,payload,result) VALUES(?,?,0,'read','done','[]',?)",(pid,i+1,encode(notes)))
        practice_pipeline.advance(conn,pid)
        jobs=conn.execute("SELECT * FROM practice_jobs WHERE practice_id=? AND kind='reduce'",(pid,)).fetchall()
        assert len(jobs)>1
        refs={ref for j in jobs for n in json.loads(j['payload']) for ref in n['refs']}
        assert refs=={f'S{i+1}' for i in range(12)}


def test_more_than_300_positions_are_batched_not_rejected():
    sources=[{'source_id':f'S{i+1}','material_id':'m','unit_index':i,'name':'Slides','location':f'Slide {i+1}','text':'Short text'} for i in range(320)]
    batches=pack_sources(split_sources(sources))
    assert len(batches)>1 and sum(map(len,batches))==320
    assert [s['unit_index'] for batch in batches for s in batch]==list(range(320))


def test_practice_reduction_round_completes_and_resolves_original_sources(setup_practice,monkeypatch):
    body,_=long_setup(setup_practice,monkeypatch);path,course,call,_,_=setup_practice
    pid=call('/api/courses/{course_id}/practices','POST',course_id=course,body=body)['id']
    with sqlite3.connect(path) as conn:
        conn.row_factory=sqlite3.Row
        rows=conn.execute('SELECT * FROM practice_jobs WHERE practice_id=?',(pid,)).fetchall()
        for job in rows:
            first=json.loads(job['payload'])[0]['source_id']
            conn.execute("UPDATE practice_jobs SET status='done',result=? WHERE id=?",(encode([{'text':'knowledge '*900,'refs':[first]}]),job['id']))
    def generate(config,name,counts,sources):
        result=paper()
        for q in result['questions']:q['source_ids']=[sources[0]['source_id']]
        return result
    monkeypatch.setattr(practice_ai,'generate_practice',generate)
    result=call('/api/practices/{practice_id}/next','POST',practice_id=pid)
    assert any(p['kind']=='reduce' for p in result['pipeline']['parts'])
    for _ in range(10):
        if result['status']=='ready':break
        result=call('/api/practices/{practice_id}/next','POST',practice_id=pid)
    assert result['status']=='ready'
    with sqlite3.connect(path) as conn:
        questions,sources=conn.execute('SELECT questions,sources FROM practices WHERE id=?',(pid,)).fetchone()
    known={s['source_id'] for s in json.loads(sources)}
    assert all(set(q['source_ids'])<=known for q in json.loads(questions))
