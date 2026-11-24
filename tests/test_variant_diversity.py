import json
import sqlite3
from backend import ai
from backend.diversity import near_duplicate, ensure_plan, semantic_filter
from backend.paper_tools import VariantInput
from backend.practice import AnswersInput
from test_practice import setup_practice, RAW
from test_mistakes import submitted


def test_near_duplicates_ignore_punctuation_numbers_but_allow_new_task():
    original='某网络中有100个节点，请按照给出的网络结构计算链路的数量。'
    assert near_duplicate('某网络中有200个节点，请按照给出的网络结构计算链路的数量！',[original])
    assert not near_duplicate('比较电路交换与分组交换在突发流量下的优缺点。',[original])


def test_plan_balanced_persistent_and_legacy_outputs_untouched():
    jobs=[{'kind':'generate','count':3,'output':[{'prompt':'saved'}]}, {'kind':'generate','count':2}]
    ensure_plan(jobs,[{'source_id':'S1'},{'source_id':'S2'}])
    assert [p['source_id'] for j in jobs for p in j['question_plan']]==['S1','S2','S1','S2','S1']
    before=json.dumps(jobs)
    ensure_plan(jobs,[{'source_id':'changed'}])
    assert json.dumps(jobs)==before
    assert jobs[0]['output']==[{'prompt':'saved'}]


def test_semantic_pairs_reject_only_duplicate(monkeypatch):
    qs=[{'prompt':'召回率如何计算','answer':['TP/(TP+FN)'],'kind':'short'}, {'prompt':'解释精确率的含义','answer':['预测正例中真正例的比例'],'kind':'short'}]
    seen=[]
    def request(*args,**kwargs):
        seen.append((args,kwargs))
        return json.dumps({'duplicates':[{'candidate':0,'against':'previous','index':0,'reason':'同样要求写出召回率公式'}]})
    monkeypatch.setattr(ai,'request_content',request)
    accepted,issues=semantic_filter({},qs,['给出Recall的公式'])
    assert accepted==[qs[1]] and issues
    assert seen[0][1]['timeout_seconds']==45


def test_semantic_outage_or_bad_index_keeps_valid_candidates_with_warning(monkeypatch):
    qs=[{'prompt':'x','answer':['a'],'kind':'single'}]
    def fail(*a,**k):raise ai.AIError('timeout')
    monkeypatch.setattr(ai,'request_content',fail)
    assert semantic_filter({},qs,['y'])[0]==qs
    monkeypatch.setattr(ai,'request_content',lambda *a,**k:json.dumps({'duplicates':[{'candidate':9,'against':'previous','index':0,'reason':'bad'}]}))
    accepted,issues=semantic_filter({},qs,['y'])
    assert accepted==qs and '复核未完成' in issues[0]


def test_variant_schema_no_exam_fields_and_correct_rate_not_weighted(setup_practice,monkeypatch):
    pid=submitted(setup_practice);path,course,call,*_=setup_practice
    with sqlite3.connect(path) as c:
        questions=json.loads(c.execute('SELECT questions FROM practices WHERE id=?',(pid,)).fetchone()[0])
        for q in questions:q.update(max_score=1.1,scoring_version=2,section_index=0,section_title='sample')
        c.execute('UPDATE practices SET questions=? WHERE id=?',(json.dumps(questions),pid))
    captures=[]
    def request(config,prompt,payload):
        captures.append(payload)
        return json.dumps({'title':'variant','questions':[dict(RAW['questions'][1],prompt='A different task',max_score=1.1,section_title='sample')]})
    monkeypatch.setattr(ai,'request_content',request)
    result=call('/api/practices/{practice_id}/variant','POST',practice_id=pid,body=VariantInput(question_id='Q4',request_id='variant-schema-1234'))
    assert result['status']=='ready'
    assert not {'id','max_score','section_title','scoring_version'} & captures[0]['original'].keys()
    call('/api/practices/{practice_id}/submit','POST',practice_id=result['id'],body=AnswersInput(revision=0,answers={'Q1':['A']}))
    report=call('/api/courses/{course_id}/report',course_id=course)['variants']
    assert report['evaluation_mode']=='correctness'
    assert report['totals']['partial']==1 and report['totals']['correct_rate']==0
    assert report['totals']['score_rate']==50  # legacy internal weights never become correctness


def test_batch_supplies_whole_exam_and_only_keeps_semantically_new_question(monkeypatch):
    from backend.blueprints import question_batch
    captured=[]
    def request(config,prompt,payload,**kwargs):
        captured.append(payload)
        if 'candidate' in payload:
            return json.dumps({'duplicates':[{'candidate':0,'against':'previous','index':0,'reason':'same conclusion'}]})
        return json.dumps({'title':'exam','questions':[dict(RAW['questions'][0],prompt='First candidate'),dict(RAW['questions'][0],prompt='Other candidate')]})
    monkeypatch.setattr(ai,'request_content',request)
    section={'kind':'single','basis_mode':'sample','question_plan':[{'slot':1,'source_id':'S1','angle':'应用'}]}
    old=['Existing question '+str(i) for i in range(45)]
    questions=question_batch({},section,2,[{'source_id':'S1','text':'AI识别知识点：网络'}],old)
    assert len(captured[0]['previous'])==45
    assert [q['prompt'] for q in questions]==['Other candidate']
    assert section['_validation_feedback']
