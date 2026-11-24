"""Recover valid practice candidates without relaxing answer/citation checks."""
import json
from backend.math_text import parse_model_json
from collections import Counter
from backend import ai
from backend.exam_candidates import parse_candidates
from backend.diversity import near_duplicate
from backend.practice_ai import ORDER


def collect(content,sources,counts,accepted):
    try:
        if not isinstance(content,str) or len(content)>150000:raise ValueError()
        raw=content.strip()
        if raw.startswith('```'):raw=raw.split('\n',1)[1].rsplit('```',1)[0]
        data=parse_model_json(raw)
        rows=data.get('questions') if isinstance(data,dict) else None
        if not isinstance(rows,list) or len(rows)>100:raise ValueError()
    except (ValueError,TypeError,IndexError):
        return accepted,['AI返回内容不是有效的题目JSON，或缺少questions列表。']
    issues=[]
    for kind in ORDER:
        wanted=counts.get(kind,0)-sum(q['kind']==kind for q in accepted)
        if wanted<=0:continue
        subset=[q for q in rows if isinstance(q,dict) and q.get('kind')==kind]
        valid,errors=parse_candidates(json.dumps({'questions':subset},ensure_ascii=False),sources,kind,len(subset))
        issues.extend(kind+'：'+e for e in errors)
        for q in valid:
            if wanted<=0:break
            if near_duplicate(q['prompt'],[a['prompt'] for a in accepted]):
                issues.append(kind+'：题干重复或过于相似，已剔除该候选。');continue
            accepted.append(q);wanted-=1
    missing={k:v-sum(q['kind']==k for q in accepted) for k,v in counts.items() if v>sum(q['kind']==k for q in accepted)}
    if missing:issues.append('尚缺题目：'+json.dumps(missing,ensure_ascii=False))
    return accepted,issues


def complete(config,system,course,counts,sources,transport=None,initial=None):
    from backend.practice_ai import Question
    from backend.scoring import stamp
    known={s['source_id'] for s in sources};accepted=[]
    for q in initial or []:
        parsed=Question.model_validate({k:v for k,v in q.items() if k in Question.model_fields}).model_dump()
        if set(parsed['source_ids'])<=known and sum(a['kind']==parsed['kind'] for a in accepted)<counts.get(parsed['kind'],0):accepted.append(parsed)
    issues=[];title='章节练习'
    for attempt in range(2):
        missing={k:v-sum(q['kind']==k for q in accepted) for k,v in counts.items() if v>sum(q['kind']==k for q in accepted)}
        if not missing:break
        payload={'course':course,'counts':missing,'sources':sources,'accepted_prompts':[q['prompt'] for q in accepted],'validation_feedback':issues[:12]}
        prompt=system+'\n只生成counts指定的缺题，不重复accepted_prompts；validation_feedback为上次校验问题，请修复。'
        try:
            content=ai.request_content(config,prompt,payload,transport,**({'timeout_seconds':45} if attempt else {}))
        except ai.AIError as error:
            issues.append(str(error));break  # Never auto-repeat a network failure.
        try:
            raw=content.strip()
            if raw.startswith('```'):raw=raw.split('\n',1)[1].rsplit('```',1)[0]
            candidate=parse_model_json(raw).get('title')
            if isinstance(candidate,str) and candidate.strip() and len(candidate)<=150:title=candidate
        except (ValueError,TypeError,AttributeError,IndexError):pass
        accepted,issues=collect(content,sources,counts,accepted)
    accepted.sort(key=lambda q:ORDER.index(q['kind']))
    paper=stamp({'title':title,'questions':[{'id':f'Q{i+1}',**q} for i,q in enumerate(accepted)]})
    if Counter(q['kind'] for q in accepted)!=Counter({k:v for k,v in counts.items() if v}):
        error=ai.AIError(f'练习尚未完整：已保留 {len(accepted)}/{sum(counts.values())} 道合格题。'+'；'.join(issues[:8])+'。可继续补题，无需重新上传资料。')
        error.partial_questions=paper['questions']
        raise error
    return paper
