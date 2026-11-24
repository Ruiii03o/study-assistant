"""Read-only course reports computed from persisted, scored practice attempts."""
import json
import time
from collections import defaultdict
from fastapi import Depends
from backend.mistakes import mistake_items
from backend import exams

KINDS = ('single','multiple','true_false','fill','short')


def metrics(entries):
    graded = [entry for entry in entries if entry['score'] is not None]
    earned = round(sum(entry['score'] for entry in graded),2)
    possible = sum(entry['max_score'] for entry in graded)
    return {'questions':len(entries), 'graded':len(graded), 'pending':len(entries)-len(graded),
            'unanswered':sum(not entry['answered'] for entry in entries),
            'earned':earned, 'graded_max':possible,
            'score_rate':round(100*earned/possible,1) if possible else None,
            'full_score':sum(entry['score']==entry['max_score'] for entry in graded),
            'partial':sum(0 < entry['score'] < entry['max_score'] for entry in graded),
            'zero':sum(entry['score']==0 for entry in graded), 'small_sample':len(graded)<5}


def summarize_attempts(records):
    entries, chapters, recent = [], defaultdict(list), []
    chapter_materials = defaultdict(set)
    for record in records:
        if record['status'] != 'submitted':
            continue
        grades = {grade['id']:grade for grade in json.loads(record['result'])['questions']}
        answers = json.loads(record['answers'])
        sources = {source['source_id']:source for source in json.loads(record['sources'])}
        ranges = json.loads(record['selected_chapters'])
        this_attempt = []
        for question in json.loads(record['questions']):
            grade = grades[question['id']]
            entry = {'kind':question['kind'], 'mode':grade['mode'], 'score':grade['score'],
                     'max_score':grade['max_score'], 'answered':any(v.strip() for v in answers.get(question['id'],[]))}
            entries.append(entry); this_attempt.append(entry)
            titles = set()
            for ref in question['source_ids']:
                source = sources.get(ref)
                if not source:
                    continue
                for chapter in ranges:
                    if chapter['material_id'] == source['material_id'] and chapter['unit_index'] <= source['unit_index'] <= chapter['end_unit_index']:
                        title = chapter['title'].strip()
                        titles.add(title); chapter_materials[title].add(source['name'])
            if not titles:
                titles.add('未关联章节')
            for title in titles:
                chapters[title].append(entry)
        recent.append({'id':record['id'],'title':record['title'],'submitted_at':record['submitted_at'],**metrics(this_attempt)})
    chapter_rows = [{'title':title,'materials':sorted(chapter_materials[title]),**metrics(items),
                     'by_kind':[{'kind':kind,**metrics([e for e in items if e['kind']==kind])} for kind in KINDS]} for title,items in chapters.items()]
    chapter_rows.sort(key=lambda row:(row['score_rate'] is None,row['score_rate'] if row['score_rate'] is not None else 101,row['title']))
    submitted = [r for r in records if r['status']=='submitted']
    return {'submitted_attempts':len(submitted), 'ready_attempts':sum(r['status']=='ready' for r in records),
            'fully_scored_attempts':sum(all(q['score'] is not None for q in json.loads(r['result'])['questions']) for r in submitted),
            'totals':metrics(entries),
            'by_kind':[{'kind':kind,**metrics([e for e in entries if e['kind']==kind])} for kind in KINDS],
            'by_mode':[{'mode':mode,**metrics([e for e in entries if e['mode']==mode])} for mode in ('automatic','ai','self','blank')],
            'chapters':chapter_rows,
            'recent':sorted(recent,key=lambda r:(r['submitted_at'],r['id']),reverse=True)[:10]}


def build_report(course, records):
    first = summarize_attempts([r for r in records if not r['parent_id'] and r.get('attempt_kind','practice')!='exam' and not r.get('variant_of')])
    retries = summarize_attempts([r for r in records if r['parent_id']])
    exam_results = summarize_attempts([r for r in records if r.get('attempt_kind')=='exam'])
    variants = summarize_attempts([r for r in records if r.get('variant_of') and not r['parent_id']])
    variants['evaluation_mode']='correctness'
    for metric in [variants['totals'], *variants['by_kind'], *variants['by_mode'], *variants['chapters'], *variants['recent'], *[m for chapter in variants['chapters'] for m in chapter['by_kind']]]:
        metric['evaluation_mode']='correctness'
        metric['correct_rate']=round(100*metric['full_score']/metric['graded'],1) if metric['graded'] else None
    mistakes = mistake_items(records)['summary']
    suggestions = []
    pending = first['totals']['pending'] + retries['totals']['pending'] + exam_results['totals']['pending'] + variants['totals']['pending']
    if pending:
        suggestions.append(f'还有 {pending} 道已交卷题目待评分。先完成 AI 辅助批改或人工评分，再评估整体表现。')
    if mistakes['needs_practice']:
        suggestions.append(f'错题本有 {mistakes["needs_practice"]} 道题最近未满分，可先核对解析，再进行原题重做。')
    candidates = [row for row in first['chapters'] if row['graded']>=5 and row['score_rate']<100]
    if candidates:
        weakest = candidates[0]
        suggestions.append(f'可优先复习“{weakest["title"]}”：首次作答已评分 {weakest["graded"]} 题，得分率 {weakest["score_rate"]}%。该比较仅覆盖已练习内容。')
    if not first['totals']['questions']:
        suggestions.append('尚无已交卷的首次练习。完成一次练习后，这里会根据真实记录汇总。')
    elif first['totals']['small_sample'] or not any(row['graded']>=5 for row in first['chapters']):
        suggestions.append('首次作答或各章节的已评分题量不足5题，暂不据此判断章节强弱；可增加不同知识点的练习。')
    if retries['submitted_attempts']:
        suggestions.append('原题重做分数单独统计，可能受题目熟悉度影响，不与首次作答合并，也不等同于新题表现。')
    if any(row['graded'] for row in first['by_mode']+retries['by_mode']+variants['by_mode']+exam_results['by_mode'] if row['mode'] in ('ai','self')):
        suggestions.append('报告包含 AI 建议分或人工评分，请结合原文核对；评分修正后刷新报告即可更新。')
    if not suggestions:
        suggestions.append('当前已评分题目均为满分，可增加不同知识点的练习以扩大覆盖；已有结果不能代表未练习内容。')
    return {'course':{'id':course['id'],'name':course['name']},'generated_at':time.time(),
            'variants':variants,'first_attempts':first,'retries':retries,'exams':exam_results,'mistakes':mistakes,'suggestions':suggestions,
            'methodology':[
                '变式练习按正误统计：正确率 = 完全正确题数 ÷ 已评价题数；部分正确单列，待评价不进入分母，提交后的空题记为错误。历史内部评分仅用于兼容评价记录，不按分值加权。',
                '错题变式作为新题独立统计，不与首次练习、原题重做或限时考试混算；生成失败不计入作答。',
                '仅统计当前课程已交卷的练习。未交卷记录不计入题数或得分，失败的出题请求不算一次作答。',
                '得分率 = 已评分题目得分合计 ÷ 这些题目的满分合计；部分得分计入分子，待评分题目不计入分母。该指标不是答对率。',
                '首次作答指普通练习的首次交卷；原题重做与限时考试独立统计。相似题尚未做语义去重，也未实现新题巩固。',
                '章节按生成时的引用原文位置与选章快照关联；同名章节汇总，同一题在同一章节只计一次。跨章节题可计入多个章节，章节题数不能相加作为总题数。',
                '少于5道已评分题目标记为样本不足；5题只是界面提醒阈值，不代表统计结论可靠。报告不能推断未练习章节、考试成绩或学习时长。',
                '使用当前已保存的评分结果。AI或人工调整评分后历史汇总也会更新；最近记录反映题目集合差异，不能直接等同于能力上升或下降。']}


def register_report_routes(app, db, current_user, get_course):
    @app.get('/api/courses/{course_id}/report')
    def course_report(course_id: int, user=Depends(current_user)):
        course = get_course(course_id,user)
        with db() as conn:
            exams.expire(conn,user['id'])
            records = [dict(r) for r in conn.execute("SELECT * FROM practices WHERE owner_id=? AND course_id=? AND status IN ('submitted','ready') ORDER BY created_at", (user['id'],course_id))]
        return build_report(course,records)
