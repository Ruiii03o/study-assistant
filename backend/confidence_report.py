"""Confidence calibration uses submitted outcomes, never score weighting."""
import json


def analyze(records):
    groups={key:{'bands':[{'level':i,'correct':0,'partial':0,'incorrect':0,'pending':0,'graded':0,'rate':None} for i in (1,2,3)],'unrecorded':0,'items':[]} for key in ('first','retry','variant','exam')}
    for record in records:
        if record['status']!='submitted' or record.get('parent_id') or record.get('variant_of'):continue
        group=groups['retry' if record.get('parent_id') else 'variant' if record.get('variant_of') else 'exam' if record.get('attempt_kind')=='exam' else 'first']
        values=json.loads(record.get('confidence_values') or '{}')
        grades={g['id']:g for g in json.loads(record['result'])['questions']}
        for q in json.loads(record['questions']):
            level=values.get(q['id'])
            if type(level)!=int or level not in (1,2,3):group['unrecorded']+=1;continue
            grade=grades.get(q['id']);score=grade.get('score') if grade else None
            outcome='pending' if score is None else 'correct' if score>=grade['max_score'] else 'partial' if score>0 else 'incorrect'
            group['bands'][level-1][outcome]+=1
            group['items'].append({'practice_id':record['id'],'question_id':q['id'],'title':record['title'],'prompt':q['prompt'],'level':level,'outcome':outcome})
    for group in groups.values():
        for band in group['bands']:
            band['graded']=sum(band[k] for k in ('correct','partial','incorrect'))
            band['rate']=round(100*band['correct']/band['graded'],1) if band['graded'] else None
    return {'groups':groups}
