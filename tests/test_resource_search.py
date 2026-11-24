import json
import httpx
import pytest
from fastapi import HTTPException
from backend import resource_search as rs, ai
from test_practice import setup_practice


def body():return rs.SearchInput(subject='计算机网络',topic='网络层')


def test_real_url_filter_dedup_and_platform_labels():
    rows=[{'url':'https://www.bilibili.com/video/BV123','title':'网络层','snippet':'IP协议'},
          {'url':'https://www.bilibili.com/video/BV123#comment','title':'重复'},
          {'url':'javascript:alert(1)','title':'坏链接'},
          {'url':'https://bilibili.com.evil.test/video','title':'伪域名'},
          {'url':'https://user:password@csdn.net/a','title':'凭证链接'},
          {'url':'https://blog.csdn.net/author/article/details/123','title':'路由原理'}]
    def handle(request):
        assert request.url.path=='/v1/tools/search'
        data=json.loads(request.content)
        assert 'site:bilibili.com' in data['query'] and len(data['query'])<=128
        assert data['need_content'] is False
        return httpx.Response(200,json={'results':rows})
    items=rs.retrieve(body(),'fake',httpx.MockTransport(handle))
    assert len(items)==2 and items[0]['source']=='哔哩哔哩' and items[1]['source']=='CSDN'


def test_web_mode_keeps_public_domains_and_empty_response():
    result=rs.retrieve(rs.SearchInput(subject='math',topic='limits',scope='web'),'fake',httpx.MockTransport(lambda r:httpx.Response(200,json={'results':[{'url':'https://example.edu/a','title':'Limits'}]})))
    assert result[0]['source']=='example.edu'
    assert rs.retrieve(body(),'fake',httpx.MockTransport(lambda r:httpx.Response(200,json={'results':[]})))==[]


@pytest.mark.parametrize('status',[401,403,402,429,500])
def test_errors_never_expose_provider_response_or_key(status):
    with pytest.raises(ai.AIError) as e:rs.retrieve(body(),'sensitive-key',httpx.MockTransport(lambda r:httpx.Response(status,text='sensitive-key')))
    assert 'sensitive-key' not in str(e.value)


def test_model_cannot_replace_links_and_bad_ids_fall_back(monkeypatch):
    items=[{'id':1,'title':'Original','url':'https://csdn.net/a','source':'CSDN','summary':'snippet','summary_basis':'搜索摘要'}]
    monkeypatch.setattr(ai,'settings',lambda:{'model':'test'})
    monkeypatch.setattr(ai,'request_content',lambda *a:json.dumps({'items':[{'id':1,'summary':'整理介绍','url':'https://evil.test'}]}))
    result,warning=rs.organize(body(),items)
    assert result[0]['url']=='https://csdn.net/a' and not warning
    monkeypatch.setattr(ai,'request_content',lambda *a:json.dumps({'items':[{'id':9,'summary':'编造'}]}))
    result,warning=rs.organize(body(),items)
    assert result==items and warning


def test_proxy_credentials_not_sent_to_official_search(monkeypatch):
    monkeypatch.delenv('STUDY_SEARCH_KEY',raising=False)
    monkeypatch.setattr(ai,'settings',lambda:{'url':'https://proxy.example/chat/completions','api_key':'proxy-key'})
    with pytest.raises(ai.AIError):rs.search_settings()
    monkeypatch.setenv('STUDY_SEARCH_KEY','official-key')
    assert rs.search_settings()=='official-key'


def test_route_caches_results_and_isolates_courses_and_users(setup_practice,monkeypatch):
    _,course,call,*_=setup_practice;calls=[]
    monkeypatch.setattr(rs,'search_settings',lambda:'fake')
    monkeypatch.setattr(rs,'retrieve',lambda *a:calls.append(a) or [])
    first=call('/api/courses/{course_id}/resource-search','POST',course_id=course,body=body())
    second=call('/api/courses/{course_id}/resource-search','POST',course_id=course,body=body())
    assert not first['cached'] and second['cached'] and len(calls)==1
    with pytest.raises(HTTPException) as e:call('/api/courses/{course_id}/resource-search','POST',course_id=course,body=body(),user={'id':2})
    assert e.value.status_code==404


def test_failed_search_can_retry(setup_practice,monkeypatch):
    _,course,call,*_=setup_practice
    monkeypatch.setattr(rs,'search_settings',lambda:'fake')
    def fail(*a):raise ai.AIError('暂不可用')
    monkeypatch.setattr(rs,'retrieve',fail)
    with pytest.raises(HTTPException):call('/api/courses/{course_id}/resource-search','POST',course_id=course,body=body())
    monkeypatch.setattr(rs,'retrieve',lambda *a:[])
    assert call('/api/courses/{course_id}/resource-search','POST',course_id=course,body=body())['items']==[]
