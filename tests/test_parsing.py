from zipfile import ZipFile

import pytest

from backend.materials import extract, suggest_chapters


def test_docx_text_and_chapter_suggestion(tmp_path):
    path = tmp_path / 'notes.docx'
    with ZipFile(path, 'w') as archive:
        archive.writestr('word/document.xml', '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>第一章 数据库</w:t></w:r></w:p><w:p><w:r><w:t>关系模型</w:t></w:r></w:p></w:body></w:document>')
    units = extract(path, '.docx')
    assert units[1]['text'] == '关系模型'
    assert suggest_chapters(units) == [{'title':'第一章 数据库','unit_index':0,'end_unit_index':1,'included':True}]


def test_pptx_numeric_slide_order(tmp_path):
    path = tmp_path / 'slides.pptx'
    with ZipFile(path, 'w') as archive:
        for number in (10, 2, 1):
            archive.writestr(f'ppt/slides/slide{number}.xml', f'<a:root xmlns:a="urn:test"><a:t>Slide {number}</a:t></a:root>')
    assert [u['text'] for u in extract(path, '.pptx')] == ['Slide 1','Slide 2','Slide 10']


def test_image_requires_ocr(tmp_path):
    with pytest.raises(ValueError, match='OCR'):
        extract(tmp_path / 'image.png', '.png')


def test_pptx_runs_join_but_paragraphs_and_breaks_remain(tmp_path):
    path = tmp_path / 'formatted.pptx'
    with ZipFile(path, 'w') as archive:
        archive.writestr('ppt/slides/slide1.xml', '''<a:root xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
          <a:p><a:r><a:t>网络中的计算机称为</a:t></a:r><a:r><a:rPr b="1"/><a:t>主机</a:t></a:r><a:r><a:t>。</a:t></a:r></a:p>
          <a:p><a:r><a:t>第二段</a:t></a:r><a:br/><a:r><a:t>保留显式换行</a:t></a:r></a:p>
        </a:root>''')
    assert extract(path, '.pptx')[0]['text'] == '网络中的计算机称为主机。\n第二段\n保留显式换行'


def test_suggested_ranges_end_before_next_chapter():
    units = [{'text':t} for t in ['第一章 概述','内容','第二章 网络','内容']]
    assert [(c['unit_index'],c['end_unit_index']) for c in suggest_chapters(units)] == [(0,1),(2,3)]


def test_selected_content_inclusive_deduplicated_and_exclusions():
    from backend.materials import selected_units
    units = [{'text':str(i)} for i in range(8)]
    chapters = [dict(unit_index=1,end_unit_index=3,included=True), dict(unit_index=3,end_unit_index=5,included=True),dict(unit_index=6,end_unit_index=7,included=False)]
    assert [u['unit_index'] for u in selected_units(units,chapters)] == [1,2,3,4,5]
    assert [u['unit_index'] for u in selected_units(units,[dict(unit_index=2,included=True)])] == [2]
