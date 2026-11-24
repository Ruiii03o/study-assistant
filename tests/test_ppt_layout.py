from backend.ppt_layout import extract_slide


def slide(shapes):
    return ('<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"><p:cSld><p:spTree>'+shapes+'</p:spTree></p:cSld></p:sld>').encode()


def shape(text,x=0,y=0,w=100,h=100,bullet=False):
    rows=''.join('<a:p>'+('<a:pPr><a:buChar char="•"/></a:pPr>' if bullet else '')+'<a:r><a:t>'+t+'</a:t></a:r></a:p>' for t in text.split('\n'))
    return f'<p:sp><p:spPr><a:xfrm><a:off x="{x}" y="{y}"/><a:ext cx="{w}" cy="{h}"/></a:xfrm></p:spPr><p:txBody><a:bodyPr/>{rows}</p:txBody></p:sp>'


def test_stacked_term_and_raw_preserved():
    result=extract_slide(slide(shape('曼\n彻\n斯\n特\n编\n码')))
    assert result['text']=='曼彻斯特编码'
    assert result['raw_text']=='曼\n彻\n斯\n特\n编\n码'


def test_bullet_and_binary_labels_are_not_concatenated():
    assert extract_slide(slide(shape('甲\n乙\n丙',bullet=True)))['text']=='甲\n乙\n丙'
    assert extract_slide(slide(shape('1')+shape('0',x=110)))['text']=='1\n\n0'


def test_same_row_fragments_and_reading_order():
    result=extract_slide(slide(shape('节点',x=110)+shape('网络',x=0)))
    assert result['text']=='网络节点'


def test_columns_and_paragraphs_stay_separate():
    result=extract_slide(slide(shape('左列\n下一段')+shape('右列',x=1000)))
    assert result['text']=='左列\n下一段\n\n右列'


def test_group_coordinates():
    group='<p:grpSp><p:grpSpPr><a:xfrm><a:off x="1000" y="2000"/><a:ext cx="200" cy="200"/><a:chOff x="0" y="0"/><a:chExt cx="100" cy="100"/></a:xfrm></p:grpSpPr>'+shape('组合文字',x=10,y=20)+'</p:grpSp>'
    block=extract_slide(slide(group))['blocks'][0]
    assert (block['x'],block['y'])==(1020,2040)


def test_visual_flag_and_no_invented_description():
    result=extract_slide(slide(shape('网络结构')+'<p:pic/>'))
    assert result['has_visual'] is True
    assert result['text']=='网络结构'
