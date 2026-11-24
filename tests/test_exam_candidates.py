import json
import pytest
from backend.exam_candidates import parse_candidates
from backend import ai


def row(**kw):
    return dict(kind='fill',prompt='请填____和____',options=[],answer=['甲','乙'],explanation='解释',key_points=['甲','乙'],source_ids=['S1'],**kw)


def test_multiple_blanks_normalized_without_inventing_answers():
    q=row();q['id']='Q1';q['max_score']=999
    valid,issues=parse_candidates(json.dumps({'questions':[q]}),[{'source_id':'S1'}],'fill',5)
    assert len(valid)==1 and valid[0]['answer']==['第1空：甲；第2空：乙']
    assert 'max_score' not in valid[0] and issues


@pytest.mark.parametrize('field,value', [('answer',[]),('explanation',''),('source_ids',['FAKE']),('key_points',[])])
def test_bad_candidate_does_not_discard_good_candidate(field,value):
    bad=row();bad[field]=value
    valid,issues=parse_candidates(json.dumps({'questions':[bad,row()]}),[{'source_id':'S1'}],'fill',2)
    assert len(valid)==1 and issues


def test_excess_questions_capped():
    valid,_=parse_candidates(json.dumps({'questions':[row(),row(),row()]}),[{'source_id':'S1'}],'fill',2)
    assert len(valid)==2


def test_invalid_json_has_specific_message():
    with pytest.raises(ai.AIError,match='JSON'):parse_candidates('broken',[],'fill',5)
