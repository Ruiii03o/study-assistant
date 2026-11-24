"""Local document extraction. No AI calls; chapters are editable suggestions."""
import re
import zipfile
from xml.etree import ElementTree as ET


def extract(path, suffix):
    if suffix in ('.docx', '.pptx'):
        with zipfile.ZipFile(path) as archive:
            if sum(i.file_size for i in archive.infolist()) > 100 * 1024 * 1024:
                raise ValueError('文件解压后过大，请拆分上传')
            if suffix == '.docx':
                root = ET.fromstring(archive.read('word/document.xml'))
                ns = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
                units = [{'location': f'段落 {i+1}', 'text': ''.join(p.itertext())} for i, p in enumerate(root.findall('.//w:p', ns))]
            else:
                names = sorted((n for n in archive.namelist() if re.fullmatch(r'ppt/slides/slide\d+\.xml', n)), key=lambda n: int(re.search(r'slide(\d+)', n).group(1)))
                units = []
                for i, name in enumerate(names):
                    from backend.ppt_layout import extract_slide
                    units.append({'location': f'幻灯片 {i+1}', **extract_slide(archive.read(name))})
    elif suffix == '.pdf':
        try:
            from pypdf import PdfReader
        except ImportError:
            raise ValueError('PDF解析依赖尚未安装，请安装 requirements.txt 后重试')
        reader = PdfReader(path)
        if reader.is_encrypted:
            raise ValueError('请先解除PDF密码保护再上传')
        if len(reader.pages) > 300:
            raise ValueError('单份PDF最多300页，请拆分上传')
        units = [{'location': f'第 {i+1} 页', 'text': page.extract_text() or ''} for i, page in enumerate(reader.pages)]
    else:
        raise ValueError('图片已保存；OCR尚未接入，目前不能识别图片文字')
    if sum(len(u['text']) for u in units) > 1000000:
        raise ValueError('提取文本超过100万字符，请拆分资料')
    return units


def suggest_chapters(units):
    chapters = []
    for index, unit in enumerate(units):
        for line in unit['text'].splitlines():
            title = line.strip()
            if len(title) <= 100 and re.match(r'^(第[一二三四五六七八九十百\d]+[章节]|Chapter\s+\d+|\d+\.\s+)', title, re.I):
                chapters.append({'title': title, 'unit_index': index, 'included': True})
    chapters = chapters[:100]
    for chapter in chapters:
        next_starts = [c['unit_index'] for c in chapters if c['unit_index'] > chapter['unit_index']]
        chapter['end_unit_index'] = min(next_starts) - 1 if next_starts else len(units) - 1
    return chapters


def selected_units(units, chapters):
    indexes = set()
    for chapter in chapters:
        if chapter.get('included', True):
            start = chapter['unit_index']
            end = chapter.get('end_unit_index')
            end = start if end is None else end
            indexes.update(range(start, end + 1))
    return [{'unit_index': i, **units[i]} for i in sorted(indexes) if 0 <= i < len(units)]
