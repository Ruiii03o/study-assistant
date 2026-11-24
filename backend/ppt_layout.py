"""Conservative PPT text reconstruction; no invented words or diagram interpretation."""
import re
from xml.etree import ElementTree as ET

NS={'a':'http://schemas.openxmlformats.org/drawingml/2006/main','p':'http://schemas.openxmlformats.org/presentationml/2006/main'}
A='{'+NS['a']+'}'
P='{'+NS['p']+'}'


def paragraph_text(p):
    return ''.join((e.text or '') if e.tag==A+'t' else '\n' if e.tag==A+'br' else '' for e in p.iter())


def join_text(left,right):
    left=left.rstrip();right=right.lstrip()
    if not left:return right
    if not right:return left
    # Separate adjacent English words; Chinese and punctuation need no added space.
    return left+(' ' if re.search(r'[A-Za-z0-9]$',left) and re.match(r'[A-Za-z0-9]',right) else '')+right


def body_text(body):
    paragraphs=body.findall('a:p',NS)
    rows=[paragraph_text(p).strip() for p in paragraphs]
    prop=body.find('a:bodyPr',NS)
    vertical=prop is not None and prop.get('vert','horz')!='horz'
    listed=any(p.find('a:pPr/a:buChar',NS) is not None or p.find('a:pPr/a:buAutoNum',NS) is not None or (p.find('a:pPr',NS) is not None and p.find('a:pPr',NS).get('lvl') not in (None,'0')) for p in paragraphs)
    pieces=[line.strip() for row in rows for line in row.splitlines() if line.strip()]
    # A single text box with one Chinese character per line is usually a stacked label.
    stacked=len(pieces)>=3 and all(re.fullmatch(r'[\u4e00-\u9fff]',s) for s in pieces)
    if (vertical or stacked) and not listed:
        return ''.join(pieces) if stacked else '\n'.join(row.replace('\n','') for row in rows if row),'vertical_normalized'
    if listed:return '\n'.join(rows),'list'
    # Keep actual paragraphs. Only stitch short fragments within an explicit soft break.
    cleaned=[]
    for row in rows:
        parts=row.split('\n');lines=[]
        for part in parts:
            if lines and part and lines[-1] and not re.search(r'[。！？；：.!?;:]$',lines[-1]) and not re.match(r'^(\d+[.、）)]|[一二三四五六七八九十]+[、）])',part) and (len(lines[-1])<8 or len(part)<5):
                lines[-1]=join_text(lines[-1],part)
            else:lines.append(part)
        cleaned.append('\n'.join(lines))
    return '\n'.join(cleaned),'text'


def extract_slide(xml):
    root=ET.fromstring(xml)
    raw='\n'.join(paragraph_text(p) for p in root.findall('.//a:p',NS))
    if not raw:raw='\n'.join(e.text or '' for e in root.iter() if e.tag.endswith('}t'))
    blocks=[]
    def walk(node,transform=(1,1,0,0)):
        sx,sy,ox,oy=transform
        for child in node:
            if child.tag==P+'grpSp':
                xf=child.find('p:grpSpPr/a:xfrm',NS)
                next_transform=transform
                if xf is not None:
                    off=xf.find('a:off',NS);ext=xf.find('a:ext',NS);co=xf.find('a:chOff',NS);ce=xf.find('a:chExt',NS)
                    if all(x is not None for x in (off,ext,co,ce)) and int(ce.get('cx',0)) and int(ce.get('cy',0)):
                        nsx=sx*int(ext.get('cx'))/int(ce.get('cx'));nsy=sy*int(ext.get('cy'))/int(ce.get('cy'))
                        next_transform=(nsx,nsy,ox+sx*int(off.get('x'))-nsx*int(co.get('x')),oy+sy*int(off.get('y'))-nsy*int(co.get('y')))
                walk(child,next_transform)
            elif child.tag==P+'sp':
                body=child.find('p:txBody',NS)
                if body is None:continue
                text,kind=body_text(body)
                if not text.strip():continue
                xf=child.find('p:spPr/a:xfrm',NS);off=xf.find('a:off',NS) if xf is not None else None;ext=xf.find('a:ext',NS) if xf is not None else None
                ph=child.find('p:nvSpPr/p:nvPr/p:ph',NS)
                title=ph is not None and ph.get('type') in ('title','ctrTitle')
                block={'text':text,'kind':'title' if title else kind,'order':len(blocks)}
                if off is not None and ext is not None:
                    block.update(x=ox+sx*int(off.get('x',0)),y=oy+sy*int(off.get('y',0)),w=sx*int(ext.get('cx',0)),h=sy*int(ext.get('cy',0)))
                blocks.append(block)
            elif child.tag==P+'graphicFrame':
                table=child.find('.//a:tbl',NS)
                if table is not None:
                    rows=[' | '.join(body_text(cell.find('a:txBody',NS))[0] if cell.find('a:txBody',NS) is not None else '' for cell in row.findall('a:tc',NS)) for row in table.findall('a:tr',NS)]
                    blocks.append({'text':'\n'.join(rows),'kind':'table','order':len(blocks)})
    tree=root.find('p:cSld/p:spTree',NS)
    if tree is not None:walk(tree)
    visual=bool(root.findall('.//p:pic',NS) or root.findall('.//p:cxnSp',NS) or root.findall('.//a:graphic',NS))
    if not blocks:return {'text':raw,'raw_text':raw,'blocks':[],'extraction_version':2,'has_visual':visual}
    # Positioned frames use top-to-bottom order; unpositioned frames retain XML order.
    positioned=sorted((b for b in blocks if 'x' in b and b['kind']!='title'),key=lambda b:(b['y'],b['x']))
    lines=[]
    for b in positioned:
        if lines:
            previous=lines[-1]
            same_line=abs(b['y']-previous['y'])<=min(b['h'],previous['h'])*0.25
            gap=b['x']-(previous['x']+previous['w'])
            short=len(b['text'])<32 and len(previous['text'])<200 and not re.fullmatch(r'[\d\s.+−-]+',b['text']) and not re.fullmatch(r'[\d\s.+−-]+',previous['text'])
            if same_line and -min(b['w'],previous['w'])*0.15<=gap<=max(b['h'],previous['h'])*0.8 and short and '\n' not in b['text'] and '\n' not in previous['text'] and b['kind']=='text' and previous['kind']=='text':
                previous['text']=join_text(previous['text'],b['text']);previous['w']=b['x']+b['w']-previous['x'];continue
        lines.append(dict(b))
    ordered=[b for b in blocks if b['kind']=='title']+[b for b in blocks if 'x' not in b and b['kind']!='title']+lines
    return {'text':'\n\n'.join(b['text'] for b in ordered),'raw_text':raw,'blocks':ordered,'extraction_version':2,'has_visual':visual}
