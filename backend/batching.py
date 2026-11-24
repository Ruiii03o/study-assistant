"""Bound individual model calls, never silently discard selected source text."""
import hashlib
import json

BATCH_CHARS = 40000
UNIT_CHARS = 12000
MAX_UNITS = 250


def encode(value):
    return json.dumps(value,ensure_ascii=False)


def split_sources(sources):
    result=[]
    for source in sources:
        text=source['text']
        for start in range(0,len(text),UNIT_CHARS):
            end=min(len(text),start+UNIT_CHARS)
            item={**source,'text':text[start:end],'char_start':start,'char_end':end,'original_chars':len(text)}
            item['source_id']=f'S{len(result)+1}'
            if start or end<len(text):
                item['location']=f"{source['location']}（字符{start+1}–{end}）"
            result.append(item)
    return result


def pack_sources(sources):
    batches=[];current=[];size=2
    for source in sources:
        cost=len(encode(source))+2
        if cost>BATCH_CHARS:
            raise ValueError('单条资料元数据过长，无法构建请求')
        if current and (size+cost>BATCH_CHARS or len(current)>=MAX_UNITS):
            batches.append(current);current=[];size=2
        current.append(source);size+=cost
    if current:batches.append(current)
    return batches


def source_key(source):
    return hashlib.sha256(encode([source['material_id'],source['unit_index'],source.get('char_start',0),source['text']]).encode()).hexdigest()


def ranges(sources):
    result=[]
    for source in sources:
        whole=source.get('char_start',0)==0 and source.get('char_end',len(source['text']))==source.get('original_chars',len(source['text']))
        if result and whole and result[-1]['whole'] and result[-1]['material_id']==source['material_id'] and result[-1]['last_index']+1==source['unit_index']:
            result[-1]['end']=source['location'];result[-1]['last_index']=source['unit_index'];result[-1]['positions']+=1
        else:
            result.append({'material_id':source['material_id'],'name':source['name'],'start':source['location'],'end':source['location'],
                           'last_index':source['unit_index'],'positions':1,'whole':whole})
    return result
