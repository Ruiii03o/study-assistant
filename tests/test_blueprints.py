import asyncio
import io
import json
import sqlite3
import zipfile
import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from backend import blueprints,ai
from backend.blueprints import Blueprint,ConfirmInput,StartInput,read_sample
from backend.practice import AnswersInput,ReviewInput
from test_practice import setup_practice


def template():
    return Blueprint(title='网络模拟',minutes=60,total=15,sections=[{'title':'选择题','kind':'single','count':2,'points':2.5,'skill':'辨析概念'},{'title':'简答','kind':'short','count':1,'points':10}])


def setup_blueprint(setup,monkeypatch):
    path,course,call,body,_=setup
    with sqlite3.connect(path) as c:c.execute("INSERT INTO exam_blueprints(id,owner_id,course_id,name,suffix,original) VALUES('b1',1,?,'sample.docx','.docx',?)",(course,b'fake'))
    confirmed=call('/api/blueprints/{blueprint_id}','PUT',blueprint_id='b1',body=ConfirmInput(revision=0,blueprint=template()))
    n=[0]
    def generate(config,section,count,sources,previous):
        questions=[]
        for i in range(count):
            n[0]+=1
            questions.append({'id':'temporary','kind':section['kind'],'prompt':f'问题{n[0]}','options':['a','b'] if section['kind']=='single' else [],'answer':['A'] if section['kind']=='single' else ['定义'], 'explanation':'原文定义','key_points':[] if section['kind']=='single' else ['第一点','第二点'],'source_ids':[sources[0]['source_id']]})
        return questions
    monkeypatch.setattr(blueprints,'question_batch',generate)
    start=StartInput(revision=confirmed['revision'],material_ids=body.material_ids,chapter_keys=body.chapter_keys,request_id='blueprint-test-1234')
    run=call('/api/blueprints/{blueprint_id}/runs','POST',blueprint_id='b1',body=start)
    return path,course,call,start,run


def finish(call,run):
    for _ in range(10):
        run=call('/api/blueprint-runs/{run_id}/next','POST',run_id=run['id'])
        if run['status']=='ready':return run
        assert run['status']!='failed',run
    raise AssertionError('Not finished')


def test_blueprint_total_and_unsupported_types():
    template()
    for change in [{'total':16},{'sections':[{'title':'图','kind':'drawing','count':1,'points':15}]},{'sections':[{'title':'A','kind':'single','count':101,'points':1}],'total':101}]:
        with pytest.raises(ValidationError):Blueprint.model_validate({**template().model_dump(),**change})


def test_resumable_assembly_scores_redaction_and_grading(setup_practice,monkeypatch):
    path,course,call,start,run=setup_blueprint(setup_practice,monkeypatch)
    again=call('/api/blueprints/{blueprint_id}/runs','POST',blueprint_id='b1',body=start)
    assert again['id']==run['id']
    run=finish(call,run);pid=run['practice_id']
    assert call('/api/blueprint-runs/{run_id}/next','POST',run_id=run['id'])==run
    record=call('/api/practices/{practice_id}',practice_id=pid)
    assert record['questions']==[] and 'sources' not in record
    record=call('/api/practices/{practice_id}/start-exam','POST',practice_id=pid)
    assert [q['max_score'] for q in record['questions']]==[2.5,2.5,10]
    assert all('answer' not in q for q in record['questions'])
    answers={'Q1':['A'],'Q2':['B'],'Q3':['定义']}
    record=call('/api/practices/{practice_id}/submit','POST',practice_id=pid,body=AnswersInput(revision=record['revision'],answers=answers))
    record=call('/api/practices/{practice_id}/self-review','PUT',practice_id=pid,body=ReviewInput(revision=record['revision'],point_verdicts={'Q3':['met','partial']}))
    assert record['result']['max_score']==15 and record['result']['total_score']==10
    compared=call('/api/courses/{course_id}/exam-comparisons',course_id=course)
    assert compared[0]['score']==10
    assert all(s['expected']==s['actual'] and s['expected_count']==s['actual_count'] for s in compared[0]['sections'])


def test_failed_batch_retry_preserves_completed_jobs(setup_practice,monkeypatch):
    path,course,call,start,run=setup_blueprint(setup_practice,monkeypatch)
    run=call('/api/blueprint-runs/{run_id}/next','POST',run_id=run['id']);assert run['done']==1
    original=blueprints.question_batch
    def fail(*a):raise ai.AIError('模拟失败')
    monkeypatch.setattr(blueprints,'question_batch',fail)
    failed=call('/api/blueprint-runs/{run_id}/next','POST',run_id=run['id'])
    assert failed['done']==1 and failed['status']=='failed'
    monkeypatch.setattr(blueprints,'question_batch',original)
    assert finish(call,run)['done']==2


def test_owner_isolation_and_confirmed_snapshot(setup_practice,monkeypatch):
    path,course,call,start,run=setup_blueprint(setup_practice,monkeypatch)
    for endpoint,args in [('/api/blueprints/{blueprint_id}/original',{'blueprint_id':'b1'}),('/api/courses/{course_id}/exam-comparisons',{'course_id':course})]:
        with pytest.raises(HTTPException) as e:call(endpoint,user={'id':2},**args)
        assert e.value.status_code==404
    with pytest.raises(HTTPException):call('/api/blueprint-runs/{run_id}/next','POST',run_id=run['id'],user={'id':2})
    changed=template().model_dump();changed.update(minutes=90)
    call('/api/blueprints/{blueprint_id}','PUT',blueprint_id='b1',body=ConfirmInput(revision=1,blueprint=Blueprint.model_validate(changed)))
    record=call('/api/practices/{practice_id}',practice_id=finish(call,run)['practice_id'])
    assert record['duration_seconds']==3600


def test_docx_and_upload_are_not_ai_calls(setup_practice,monkeypatch):
    blob=io.BytesIO()
    with zipfile.ZipFile(blob,'w') as z:z.writestr('word/document.xml','<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:p><w:r><w:t>选择题 共20分</w:t></w:r></w:p></w:document>')
    text,images=read_sample(blob.getvalue(),'.docx');assert '20' in text and not images
    _,course,call,*_=setup_practice
    class Request:
        async def stream(self):yield blob.getvalue()
    result=asyncio.run(call('/api/courses/{course_id}/blueprints','POST',course_id=course,name='sample.docx',request=Request()))
    assert result['confirmed'] is None
    assert call('/api/blueprints/{blueprint_id}/original',blueprint_id=result['id']).body==blob.getvalue()


def test_scanned_pdf_without_renderer_is_not_silently_empty(monkeypatch):
    from pypdf import PdfWriter
    writer=PdfWriter();writer.add_blank_page(width=200,height=200);blob=io.BytesIO();writer.write(blob)
    monkeypatch.setattr(blueprints.shutil,'which',lambda _:None)
    with pytest.raises(ValueError,match='扫描页'):read_sample(blob.getvalue(),'.pdf')


def test_more_than_twenty_answers_supported():
    AnswersInput(revision=0,answers={f'Q{i}':['A'] for i in range(100)})
    with pytest.raises(ValidationError):AnswersInput(revision=0,answers={f'Q{i}':['A'] for i in range(101)})


def test_large_source_summary_keeps_valid_original_references(setup_practice,monkeypatch):
    path,course,call,start,run=setup_blueprint(setup_practice,monkeypatch)
    with sqlite3.connect(path) as c:
        units=json.loads(c.execute("SELECT units FROM materials WHERE id='m1'").fetchone()[0]);units[0]['text']='资料内容'*18000
        c.execute("UPDATE materials SET units=? WHERE id='m1'",(json.dumps(units),))
    start.chapter_keys=[r['key'] for g in call('/api/courses/{course_id}/chapters',course_id=course) for r in g['ranges']]
    start.request_id='second-large-run-1234'
    run=call('/api/blueprints/{blueprint_id}/runs','POST',blueprint_id='b1',body=start)
    monkeypatch.setattr(blueprints,'summary',lambda config,course,inputs:[{'text':'知识摘要','refs':[s['source_id'] for s in inputs]}])
    record=finish(call,run)
    with sqlite3.connect(path) as c:
        sources,questions=c.execute('SELECT sources,questions FROM practices WHERE id=?',(record['practice_id'],)).fetchone()
    refs={s['source_id'] for s in json.loads(sources)}
    assert len(refs)>1 and all(set(q['source_ids'])<=refs for q in json.loads(questions))


def test_twenty_five_question_exam(setup_practice,monkeypatch):
    path,course,call,start,run=setup_blueprint(setup_practice,monkeypatch)
    b=Blueprint(title='25题',minutes=90,total=100,sections=[{'title':'单选','kind':'single','count':25,'points':4}])
    result=call('/api/blueprints/{blueprint_id}','PUT',blueprint_id='b1',body=ConfirmInput(revision=1,blueprint=b))
    start.revision=result['revision'];start.request_id='twenty-five-test-1234'
    run=call('/api/blueprints/{blueprint_id}/runs','POST',blueprint_id='b1',body=start)
    assert run['total']==5
    pid=finish(call,run)['practice_id'];record=call('/api/practices/{practice_id}/start-exam','POST',practice_id=pid)
    assert len(record['questions'])==25
    graded=call('/api/practices/{practice_id}/submit','POST',practice_id=pid,body=AnswersInput(revision=record['revision'],answers={q['id']:['A'] for q in record['questions']}))
    assert graded['result']['total_score']==100


def test_recognition_is_unconfirmed_and_missing_numbers_remain_missing(setup_practice,monkeypatch):
    path,course,call,start,run=setup_blueprint(setup_practice,monkeypatch)
    monkeypatch.setattr(blueprints,'read_sample',lambda *a:('单项选择题',[]))
    monkeypatch.setattr(ai,'request_content',lambda *a,**k:json.dumps({'title':'新草稿','minutes':None,'total':None,'sections':[{'title':'单选','kind':'single','count':None,'points':None}],'uncertain':['分值不清晰']}))
    result=call('/api/blueprints/{blueprint_id}/analyze','POST',blueprint_id='b1')
    assert result['draft']['total'] is None and result['confirmed'] is None
    with pytest.raises(ValidationError):Blueprint.model_validate(result['draft'])


@pytest.mark.parametrize('count,total,evidence,expected',[
    (35,38.5,'单选题（共35题，38.5分）',1.1),
    (10,12,'第5页起“五、计算题（共10题，12分）”，第80–89题',1.2),
    (10,20,'每小题2分，共20分',2),
    (3,10,'共3题，10分',None),
    (10,12,'共10题，12分，各题分值不等',None),
    (10,12,'每题2分，共12分',None),
    (9,12,'共10题，12分',None),
])
def test_section_total_is_not_per_question(count,total,evidence,expected):
    rows=[{'title':'测试','count':count,'points':total,'evidence':evidence}]
    blueprints.normalize_section_scores(rows)
    assert rows[0]['points']==expected


def test_recognition_normalizes_section_total(monkeypatch):
    monkeypatch.setattr(blueprints,'read_sample',lambda *a:('试卷',[]))
    monkeypatch.setattr(ai,'request_content',lambda *a,**k:json.dumps({'total':12,'sections':[{'count':10,'points':12,'section_total':12,'evidence':'共10题，12分'}]}))
    result=blueprints.analyze_sample(b'x','.docx',{})
    assert result['sections'][0]['points']==1.2
    assert result['total']==12 and result['uncertain']


def test_multiple_photos_preserve_order_and_original_bundle(setup_practice):
    from backend.blueprints import PhotosInput
    from test_page_vision import PNG
    _,course,call,*_=setup_practice
    record=call('/api/courses/{course_id}/blueprint-photos','POST',course_id=course,body=PhotosInput(pages=[PNG,PNG]))
    original=call('/api/blueprints/{blueprint_id}/original',blueprint_id=record['id'])
    text,images=read_sample(original.body,'.zip')
    assert images==[PNG,PNG]
    assert not text and record['confirmed'] is None


def test_sample_only_without_course_materials_and_retry(setup_practice,monkeypatch):
    path,course,call,start,_=setup_blueprint(setup_practice,monkeypatch)
    with sqlite3.connect(path) as c:c.execute('DELETE FROM materials WHERE course_id=?',(course,))
    body=StartInput(revision=start.revision,mode='sample',request_id='sample-only-request-1234')
    run=call('/api/blueprints/{blueprint_id}/runs','POST',blueprint_id='b1',body=body)
    assert run['mode']=='sample' and run['steps'][0]['kind']=='sample'
    monkeypatch.setattr(blueprints,'read_sample',lambda *a:('1. IP地址属于哪一层？',[]))
    attempts=[]
    def recognize(*a,**k):
        attempts.append(1)
        if len(attempts)==1:raise ai.AIError('temporary failure')
        return json.dumps({'items':[{'location':'第1题','excerpt':'IP地址属于哪一层？','knowledge':'网络层寻址','skill':'辨别层次'}]})
    monkeypatch.setattr(ai,'request_content',recognize)
    failed=call('/api/blueprint-runs/{run_id}/next','POST',run_id=run['id'])
    assert failed['status']=='failed' and failed['done']==0
    result=finish(call,run)
    assert len(attempts)==2
    with sqlite3.connect(path) as c:
        record=c.execute('SELECT sources,versions,selected_chapters,title FROM practices WHERE id=?',(result['practice_id'],)).fetchone()
    assert json.loads(record[1])=={} and json.loads(record[2])==[]
    assert json.loads(record[0])[0]['source_type']=='sample_analysis'
    assert '样卷同类卷' in record[3]
    before=call('/api/practices/{practice_id}',practice_id=result['practice_id'])
    assert before['questions']==[] and 'sources' not in before
    started=call('/api/practices/{practice_id}/start-exam','POST',practice_id=result['practice_id'])
    assert len(started['questions'])==3


def test_modes_validate_scopes():
    with pytest.raises(ValidationError):StartInput(revision=1,request_id='empty-course-123456')
    with pytest.raises(ValidationError):StartInput(revision=1,mode='sample',material_ids=['m1'],request_id='invalid-mode-12345')
    with pytest.raises(ValidationError):StartInput(revision=1,mode='unknown',request_id='invalid-mode-12345')


def test_timeout_reduces_next_call_to_one_question(setup_practice,monkeypatch):
    path,course,call,start,run=setup_blueprint(setup_practice,monkeypatch)
    original=blueprints.question_batch;counts=[]
    def generate(config,section,n,sources,previous):
        counts.append(n)
        if len(counts)==1:raise ai.AIError('AI 请求超时')
        return original(config,section,n,sources,previous)
    monkeypatch.setattr(blueprints,'question_batch',generate)
    failed=call('/api/blueprint-runs/{run_id}/next','POST',run_id=run['id'])
    assert failed['status']=='failed'
    with sqlite3.connect(path) as c:
        jobs=json.loads(c.execute('SELECT jobs FROM blueprint_runs WHERE id=?',(run['id'],)).fetchone()[0])
    assert jobs[0]['request_limit']==1
    finish(call,failed)
    assert counts==[2,1,1,1]


def test_duplicates_keep_valid_questions_and_only_refill_missing(setup_practice,monkeypatch):
    path,course,call,start,run=setup_blueprint(setup_practice,monkeypatch)
    original=blueprints.question_batch;calls=[]
    def generate(config,section,count,sources,previous):
        calls.append(count)
        qs=original(config,section,count,sources,previous)
        if len(calls)==1:qs[1]=dict(qs[0])
        return qs
    monkeypatch.setattr(blueprints,'question_batch',generate)
    first=call('/api/blueprint-runs/{run_id}/next','POST',run_id=run['id'])
    assert first['done']==0 and first['status']=='pending'
    with sqlite3.connect(path) as c:jobs=json.loads(c.execute('SELECT jobs FROM blueprint_runs WHERE id=?',(run['id'],)).fetchone()[0])
    assert len(jobs[0]['output'])==1
    finish(call,first)
    assert calls==[2,1,1]


def test_duplicate_refill_stops_after_three_calls(setup_practice,monkeypatch):
    path,course,call,start,run=setup_blueprint(setup_practice,monkeypatch)
    original=blueprints.question_batch
    fixed=original({},template().sections[0].model_dump(),1,[{'source_id':'S1'}],[])[0]
    monkeypatch.setattr(blueprints,'question_batch',lambda config,section,n,sources,previous:[dict(fixed) for _ in range(n)])
    for _ in range(4):run=call('/api/blueprint-runs/{run_id}/next','POST',run_id=run['id'])
    assert run['status']=='failed' and run['done']==0
    with sqlite3.connect(path) as c:jobs=json.loads(c.execute('SELECT jobs FROM blueprint_runs WHERE id=?',(run['id'],)).fetchone()[0])
    assert len(jobs[0]['output'])==1 and jobs[0]['attempts']==3


def test_sample_basis_rejects_empty_recognition(monkeypatch):
    monkeypatch.setattr(blueprints,'read_sample',lambda *a:('', ['data:image/png;base64,test']))
    def response(*a,**k):
        assert k['image_data']==['data:image/png;base64,test']
        return '{"items":[]}'
    monkeypatch.setattr(ai,'request_content',response)
    with pytest.raises(ai.AIError):blueprints.extract_sample_basis(b'x','.png',{},'sample','b1')
