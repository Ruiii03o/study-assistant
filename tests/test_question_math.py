import json
import pytest
from backend import ai,practice_ai
from backend.practice_candidates import collect,complete
from backend.exam_candidates import parse_candidates

SOURCES=[{'source_id':'S1','text':'limits and fractions'}]
FORMULA=r'\(\lim_{x\to0}\frac{1-\cos x}{x^2}=\frac12\)'

def content(raw=False):
    q={'kind':'single','prompt':FORMULA,'options':[r'\(\frac12\)','2'],'answer':['A'],'explanation':r'\[\alpha_i+\beta^2\]','key_points':[],'source_ids':['S1']}
    text=json.dumps({'title':'Math','questions':[q]},ensure_ascii=False)
    return text.replace('\\\\','\\') if raw else text

@pytest.mark.parametrize('raw',[False,True])
@pytest.mark.parametrize('parser',['practice','exam','strict'])
def test_formulas_survive_all_question_parsers(raw,parser):
    text=content(raw)
    if parser=='practice':questions,issues=collect(text,SOURCES,{'single':1},[]);assert not issues
    elif parser=='exam':questions,issues=parse_candidates(text,SOURCES,'single',1);assert not issues
    else:questions=practice_ai.validate_paper(text,SOURCES,{'single':1})['questions']
    assert questions[0]['prompt']==FORMULA
    assert questions[0]['options'][0]==r'\(\frac12\)'
    assert questions[0]['explanation']==r'\[\alpha_i+\beta^2\]'

def test_raw_frac_not_silently_converted_to_form_feed():
    text=content(True).replace(FORMULA,r'\frac{1}{2}')
    questions,issues=collect(text,SOURCES,{'single':1},[])
    assert questions[0]['prompt']==r'\frac{1}{2}'
    assert '\f' not in questions[0]['prompt']

def test_math_repair_does_not_accept_unknown_citations_or_wrong_answers():
    for text in [content(True).replace('S1','MISSING'),content(True).replace('["A"]','["F"]')]:
        questions,issues=collect(text,SOURCES,{'single':1},[])
        assert not questions and issues

def test_valid_math_needs_no_repair_request(monkeypatch):
    calls=[]
    def request(*args,**kwargs):calls.append(1);return content(True)
    monkeypatch.setattr(ai,'request_content',request)
    paper=complete({},'system','math',{'single':1},SOURCES)
    assert len(calls)==1 and paper['questions'][0]['prompt']==FORMULA

def test_malformed_structure_and_damaged_control_char_rejected():
    assert not collect('{"questions":',SOURCES,{'single':1},[])[0]
    damaged=json.loads(content());damaged['questions'][0]['prompt']='bad\f rac'
    assert not collect(json.dumps(damaged),SOURCES,{'single':1},[])[0]
