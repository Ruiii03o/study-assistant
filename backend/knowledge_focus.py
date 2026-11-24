"""Conservative lexical ranking of existing source snapshots; no AI calls."""
import re
import unicodedata


def normalize(text):
    return unicodedata.normalize('NFKC', text).lower().replace('·', '.')


def terms(text):
    text = normalize(text)
    result = set(re.findall(r'[a-z][a-z0-9]*(?:[.\-][a-z0-9]+)*', text))
    for run in re.findall(r'[\u4e00-\u9fff]+', text):
        result.update(run[i:i+2] for i in range(len(run)-1))
    return result - set('下列 哪个 以下 正确 错误 属于 不属 依据 什么 可以 进行 选择 选项 答案 解析 主要 内容 算法 的是 是什'.split())


def fragments(text):
    # A numbered exam question stays with its options. Prose is split by paragraphs.
    boundaries = list(re.finditer(r'(?m)^\s*\d{1,3}[、．.)）]\s*(?!\d)', text))
    if len(boundaries) >= 2:
        starts = sorted(set([0] + [m.start() for m in boundaries] + [len(text)]))
        blocks = [text[a:b].strip() for a,b in zip(starts,starts[1:])]
    else:
        blocks = [p.strip() for p in re.split(r'\n\s*\n', text) if p.strip()]
    for block in blocks:
        if len(block) <= 700:
            if block: yield block
        else:
            for sentence in re.split(r'(?<=[。！？；])|\n', block):
                if sentence.strip(): yield sentence.strip()


def focus(question, sources, points):
    primary = terms(question.get('prompt',''))
    secondary = terms(question.get('explanation','')+' '+' '.join(question.get('key_points',[])))
    anchors = {t for t in primary if re.fullmatch(r'[a-z][a-z0-9]*(?:[.\-][a-z0-9]+)*',t) and t not in {'a','b','c','d','the','of','is'}}

    def rank(text, comparison=False):
        found=terms(text); hits=primary & found
        if comparison:
            contextual=secondary & found
            # Require both shared subject vocabulary and explanation context.
            chinese={t for t in hits if re.search(r'[\u4e00-\u9fff]',t)}
            if len(chinese)<3 or len(contextual)<3:return 0
            return len(chinese)*1.5+min(len(contextual),8)*0.25
        if anchors & found and len(secondary & found)>=2:
            return 6+len(anchors & found)*3+min(len(hits),8)*0.25
        if not primary or len(hits)<2 or len(hits)/len(primary)<0.18: return 0
        if anchors and not anchors.intersection(found): return 0
        return len(hits)/len(primary)*10 + min(len(secondary & found),8)*0.25 + len(anchors & found)*3

    def best(rows, text_key, comparison=False):
        ranked=sorted(((rank(r[text_key],comparison),i,r) for i,r in enumerate(rows)),key=lambda x:(-x[0],x[1]))
        if not ranked or ranked[0][0]<=0:return []
        cutoff=max(3,ranked[0][0]*0.65);seen=set();result=[]
        for score,_,row in ranked:
            key=normalize(row[text_key])
            if score<cutoff or key in seen:continue
            seen.add(key);result.append(row)
            if len(result)==3:break
        return result

    candidates=[]
    for source in sources:
        for index,excerpt in enumerate(fragments(source.get('text',''))):
            candidates.append({'source_id':source['source_id'],'name':source['name'],'location':source['location'],
                               'fragment_id':f"{source['source_id']}:{index}",'text':excerpt})
    direct_sources=best(candidates,'text');direct_points=best(points,'text')
    return {'focused_sources':direct_sources, 'related_outline_points':direct_points,
            'comparison_sources':best(candidates,'text',True) if not direct_sources else [],
            'comparison_points':best(points,'text',True) if not direct_points else [],
            'has_direct_source':bool(direct_sources),
            'focus_method':'lexical', 'highlight_terms':sorted(primary,key=lambda t:(-len(t),t))[:40]}
