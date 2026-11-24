from backend.knowledge_focus import focus, fragments


def test_algorithm_anchor_excludes_nearby_different_algorithms():
    q={'prompt':'C4.5决策树算法选择划分属性的依据是？','explanation':'C4.5使用信息增益率','key_points':[]}
    text='21. C4.5决策树划分属性依据是什么？\nA.信息增益率\nB.基尼指数\n22. CART决策树划分属性依据是什么？\nA.基尼指数\n23. 朴素贝叶斯的假设是什么？'
    points=[{'title':'决策树','text':'C4.5使用信息增益率选择划分属性。'},{'title':'决策树','text':'CART决策树划分属性使用基尼指数。'}]
    result=focus(q,[{'source_id':'S1','name':'试卷','location':'第5页','text':text}],points)
    assert len(result['focused_sources'])==1
    assert '22.' not in result['focused_sources'][0]['text']
    assert result['focused_sources'][0]['text'] in text
    assert result['related_outline_points']==points[:1]


def test_no_matching_evidence_does_not_fill_quota():
    result=focus({'prompt':'C4.5决策树划分属性','explanation':'信息增益率'},[{'source_id':'S1','name':'资料','location':'第一页','text':'朴素贝叶斯使用条件独立假设。'}],[])
    assert not result['focused_sources'] and not result['related_outline_points']


def test_prose_is_deduplicated_and_bounded():
    q={'prompt':'数据预处理包括什么内容？','explanation':'数据清洗与数据集成'}
    points=[{'title':'预处理','text':f'数据预处理包括数据清洗与数据集成，步骤{i}。'} for i in range(10)]
    result=focus(q,[],points+points)
    assert len(result['related_outline_points'])==3
    assert len(list(fragments('定义一。\n\n定义二。')))==2


def test_extended_question_gets_comparisons_not_false_direct_evidence():
    q={'prompt':'C4.5决策树算法选择划分属性的依据是？','explanation':'ID3使用信息增益，C4.5使用信息增益率，CART使用基尼指数。'}
    sources=[{'source_id':'S1','name':'试卷','location':'第5页','text':'23. CART决策树算法选择划分属性的依据是？基尼指数。\n24. 朴素贝叶斯的假设是什么？条件独立。'}]
    result=focus(q,sources,[{'title':'决策树','text':'C4.5使用信息增益率。','scope':'course_outline'}])
    assert not result['has_direct_source'] and not result['focused_sources']
    assert len(result['related_outline_points'])==1
    assert len(result['comparison_sources'])==1
    assert '朴素' not in result['comparison_sources'][0]['text']
