import json

import httpx
import pytest

from backend import ai

SOURCES = [{'source_id':'S1','text':'主机是连接在网络上的计算机。'}]
VALID = {'title':'网络基础','sections':[{'title':'主机','points':[{'text':'主机连接网络。','source_ids':['S1']}]}]}
CONFIG = {'url':'https://api.deepseek.com/chat/completions','model':'deepseek-flash','api_key':'test-secret'}


@pytest.fixture(autouse=True)
def isolate_ai_environment(monkeypatch):
    # Tests never use the developer's actual credentials.
    for name in ('deepseek_api_base','deepseek_api_key','deepseek_model','STUDY_AI_URL','STUDY_AI_KEY','STUDY_AI_MODEL'):
        monkeypatch.delenv(name,raising=False)


@pytest.mark.parametrize('base,expected', [
    ('https://api.deepseek.com','https://api.deepseek.com/chat/completions'),
    ('https://api.deepseek.com/v1/','https://api.deepseek.com/v1/chat/completions'),
    ('https://api.deepseek.com/chat/completions','https://api.deepseek.com/chat/completions'),
])
def test_user_environment_names_and_base_url(tmp_path,monkeypatch,base,expected):
    monkeypatch.setattr(ai,'CONFIG_PATH',tmp_path/'absent.json')
    monkeypatch.setenv('deepseek_api_base',base)
    monkeypatch.setenv('deepseek_api_key','test-user-key')
    monkeypatch.setenv('STUDY_AI_KEY','test-legacy-key')
    assert ai.settings() == {'url':expected,'api_key':'test-user-key','model':'deepseek-flash'}


def test_user_environment_overrides_file(tmp_path,monkeypatch):
    path = tmp_path/'ai-config.json'
    path.write_text(json.dumps(CONFIG),encoding='utf-8')
    monkeypatch.setattr(ai,'CONFIG_PATH',path)
    monkeypatch.setenv('deepseek_api_base','https://api.deepseek.com/v1')
    monkeypatch.setenv('deepseek_api_key','test-user-key')
    monkeypatch.setenv('deepseek_model','test-model')
    assert ai.settings() == {'url':'https://api.deepseek.com/v1/chat/completions','api_key':'test-user-key','model':'test-model'}


def test_deepseek_payload_and_valid_result():
    def handle(request):
        body = json.loads(request.content)
        assert request.headers['Authorization'] == 'Bearer test-secret'
        assert body['thinking'] == {'type':'disabled'}
        assert body['response_format'] == {'type':'json_object'}
        assert json.loads(body['messages'][1]['content'])['sources'] == SOURCES
        return httpx.Response(200,json={'choices':[{'finish_reason':'stop','message':{'content':json.dumps(VALID)}}]})
    assert ai.generate_outline(CONFIG,'网络','目标','精简',SOURCES,transport=httpx.MockTransport(handle)) == VALID


@pytest.mark.parametrize('content', ['not JSON', '{}', json.dumps({'title':'错引','sections':[{'title':'主题','points':[{'text':'知识','source_ids':['S999']}]}]})])
def test_invalid_output_or_invented_citation_rejected(content):
    with pytest.raises(ai.AIError):
        ai.validate_outline(content,SOURCES)


@pytest.mark.parametrize('status',[401,429,500])
def test_provider_errors_do_not_leak_response(status):
    transport = httpx.MockTransport(lambda request: httpx.Response(status,text='private-provider-error'))
    with pytest.raises(ai.AIError) as error:
        ai.generate_outline(CONFIG,'网络','','精简',SOURCES,transport=transport)
    assert 'private-provider-error' not in str(error.value)
    assert 'test-secret' not in str(error.value)


def test_config_missing_and_file_loading(tmp_path,monkeypatch):
    path = tmp_path/'ai-config.json'
    monkeypatch.setattr(ai,'CONFIG_PATH',path)
    for name in ['STUDY_AI_URL','STUDY_AI_MODEL','STUDY_AI_KEY']:
        monkeypatch.delenv(name,raising=False)
    with pytest.raises(ai.AIError):
        ai.settings()
    path.write_text(json.dumps(CONFIG),encoding='utf-8')
    assert ai.settings() == CONFIG
    monkeypatch.setenv('STUDY_AI_KEY','override-key')
    assert ai.settings()['api_key'] == 'override-key'


def test_truncated_response_rejected():
    transport = httpx.MockTransport(lambda request: httpx.Response(200,json={'choices':[{'finish_reason':'length','message':{'content':json.dumps(VALID)}}]}))
    with pytest.raises(ai.AIError):
        ai.generate_outline(CONFIG,'网络','','详细',SOURCES,transport=transport)
