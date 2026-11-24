"""Validate exam candidates separately without inventing missing answers."""
import json
from backend.math_text import parse_model_json
import re
from pydantic import ValidationError
from backend import ai, practice_ai


def parse_candidates(content,sources,kind,limit):
    try:
        if not isinstance(content,str) or len(content)>150000:raise ValueError()
        text=content.strip()
        if text.startswith('```'):text=text.split('\n',1)[1].rsplit('```',1)[0]
        data=parse_model_json(text)
        rows=data.get('questions') if isinstance(data,dict) else None
        if not isinstance(rows,list) or len(rows)>100:raise ValueError()
    except (ValueError,TypeError,IndexError):
        raise ai.AIError('返回内容不是可解析的题目JSON，或题目列表过大；已保存题目保留，可重试当前批次')
    known={s['source_id'] for s in sources};valid=[];issues=[]
    for index,row in enumerate(rows,1):
        if not isinstance(row,dict):issues.append(f'候选{index}：题目格式无效');continue
        q={k:v for k,v in row.items() if k in practice_ai.Question.model_fields}
        if q.get('kind')!=kind:issues.append(f'候选{index}：题型与本批要求不符');continue
        answer=q.get('answer')
        if isinstance(answer,bool) and kind=='true_false':answer='正确' if answer else '错误'
        if isinstance(answer,str):
            answer=answer.strip()
            if kind=='multiple' and re.fullmatch(r'[A-Fa-f](?:[\s,，、;；]*[A-Fa-f])+',answer):answer=re.findall('[A-Fa-f]',answer.upper())
            else:answer=[answer]
        if isinstance(answer,list):
            answer=[v.strip() if isinstance(v,str) else v for v in answer]
            if kind in ('single','multiple'):answer=[v.upper() if isinstance(v,str) else v for v in answer]
            if kind=='true_false':answer=[{'true':'正确','false':'错误','对':'正确','错':'错误','√':'正确','×':'错误'}.get(str(v).lower(),v) for v in answer]
            if kind=='fill' and len(answer)>1 and all(isinstance(v,str) and v for v in answer):answer=['；'.join(f'第{i+1}空：{v}' for i,v in enumerate(answer))]
        q['answer']=answer
        for key in ('source_ids','key_points'):
            if isinstance(q.get(key),str):q[key]=[q[key].strip()]
            if isinstance(q.get(key),list) and all(isinstance(v,str) for v in q[key]):q[key]=list(dict.fromkeys(v.strip() for v in q[key]))
        try:
            parsed=practice_ai.Question.model_validate(q)
            if not set(parsed.source_ids)<=known:
                issues.append(f'候选{index}：引用不在本次提供的来源中');continue
            if len(valid)<limit:valid.append(parsed.model_dump())
        except ValidationError as error:
            fields=sorted({str(e['loc'][0]) if e['loc'] else '答案与题型一致性' for e in error.errors()})
            issues.append(f"候选{index}：需修正 {'、'.join(fields)}")
    if len(rows)<limit:issues.append(f'本次要求{limit}题，实际返回{len(rows)}题，缺题待补')
    if len(rows)>limit:issues.append('返回题数超出所需，仅选取足量合格题')
    return valid,issues
