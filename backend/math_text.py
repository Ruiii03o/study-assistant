"""Parse model JSON while preserving common unescaped LaTeX commands."""
import json
import re

COMMANDS=set('frac dfrac tfrac lim limsup liminf sum prod int iint infty sqrt sin cos tan cot arcsin arccos arctan ln log exp left right begin end alpha beta gamma delta epsilon theta lambda mu pi rho sigma tau phi omega Delta Gamma Sigma Omega cdot times div pm mp le leq ge geq ne neq approx sim equiv to rightarrow leftarrow mapsto forall exists partial nabla mathbb mathcal mathrm mathbf text underbrace overbrace underline overline vec hat bar dot ddot quad qquad displaystyle'.split())


def parse_model_json(content):
    if not isinstance(content,str) or len(content)>150000:raise ValueError('response too large')
    text=content.strip()
    if text.startswith('```') and text.endswith('```'):text=text.split('\n',1)[1].rsplit('```',1)[0]
    result=[];inside=False;i=0
    while i<len(text):
        ch=text[i]
        if ch=='"':inside=not inside
        if inside and ch=='\\' and i+1<len(text):
            if text[i+1] in '\\"/':result.append(text[i:i+2]);i+=2;continue
            command=re.match(r'[A-Za-z]+',text[i+1:])
            if (command and command.group() in COMMANDS) or text[i+1] in '()[]':
                result.append('\\\\');i+=1;continue
            result.append(text[i:i+2]);i+=2;continue
        result.append(ch);i+=1
    return json.loads(''.join(result))
