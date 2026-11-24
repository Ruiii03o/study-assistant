"""Recommendations grounded in saved question outcomes, without model calls."""
import json
from backend.mistakes import mistake_items
from backend.scoring import maximum

def recommend(records,mode='all'):
    roots={r['id']:r for r in records}
    candidates=[]
    for item in mistake_items(records)['items']:
        if item.get('variant_of') or item['state']!='needs_practice':continue
        root=roots[item['practice_id']]
        category='exam' if root.get('attempt_kind')=='exam' else 'first'
        if mode!='all' and category!=mode:continue
        q=item['question'];values=json.loads(root.get('confidence_values') or '{}')
        level=values.get(q['id']);level=level if type(level)==int and level in (1,2,3) else None
        # Confidence describes the first answer, not subsequent retries.
        first_wrong=item['first_score'] is not None and item['first_score']<maximum(q)
        priority=0 if first_wrong and level==3 else 1 if first_wrong and level==2 else 2
        progress={'correct':0,'partial':0,'incorrect':0,'pending':0,'ready':0}
        key=item['practice_id']+':'+q['id']
        followups=[]
        for r in records:
            if r.get('variant_of')!=key or r.get('parent_id'):continue
            if r['status']=='ready':progress['ready']+=1;followups.append({'id':r['id'],'status':'ready'})
            elif r['status']=='submitted':
                grades={g['id']:g for g in json.loads(r['result'])['questions']}
                for vq in json.loads(r['questions']):
                    score=grades.get(vq['id'],{}).get('score')
                    outcome='pending' if score is None else 'correct' if score>=maximum(vq) else 'partial' if score>0 else 'incorrect'
                    progress[outcome]+=1
                followups.append({'id':r['id'],'status':'submitted'})
        candidates.append({'item':item,'category':category,'confidence':level,'first_wrong':first_wrong,'progress':progress,'followups':followups,
                           'priority':priority,'submitted_at':item['attempts'][-1]['submitted_at']})
    candidates.sort(key=lambda x:(x['priority'],-x['submitted_at'],x['item']['practice_id'],x['item']['question']['id']))
    return {'items':candidates[:3],'total':len(candidates)}
