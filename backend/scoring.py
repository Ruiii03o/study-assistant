"""Server-owned scoring snapshots. Unmarked historical questions stay at 2 points."""
from decimal import Decimal, ROUND_HALF_UP

POINTS = {'single':2, 'true_false':2, 'fill':2, 'multiple':3, 'short':5}


def maximum(question):
    return question.get('max_score', 2)


def stamp(paper):
    return {**paper, 'questions':[{**q, 'max_score':POINTS[q['kind']], 'scoring_version':2} for q in paper['questions']]}


def point_score(question, verdicts):
    if len(verdicts)!=len(question['key_points']) or not verdicts or any(v not in ('met','partial','missed') for v in verdicts):
        raise ValueError('每个评分要点必须恰好评价一次')
    if question.get('scoring_version')==2 and question['kind']=='short':
        units=sum(Decimal({'met':'1','partial':'0.5','missed':'0'}[v]) for v in verdicts)
        return float((Decimal(str(maximum(question)))*units/len(verdicts)).quantize(Decimal('0.01'),rounding=ROUND_HALF_UP))
    return maximum(question) if all(v=='met' for v in verdicts) else 0 if all(v=='missed' for v in verdicts) else maximum(question)/2
