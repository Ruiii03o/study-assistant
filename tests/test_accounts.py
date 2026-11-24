from fastapi.testclient import TestClient
from backend.app import create_app


def test_account_isolation_logout_and_persistence(tmp_path):
    path = tmp_path / "test.db"
    app = create_app(path)
    alice, bob = TestClient(app), TestClient(app)
    assert alice.get('/api/courses').status_code == 401
    for client, name in [(alice, 'alice'), (bob, 'bobby')]:
        body = {'username': name, 'password': 'test-password-123'}
        assert client.post('/api/auth/register', json=body).status_code == 201
        assert client.post('/api/auth/register', json=body).status_code == 409
        assert client.post('/api/auth/login', json=body).status_code == 200
    course = alice.post('/api/courses', json={'name': '数据库'}).json()
    assert alice.get(f'/api/courses/{course["id"]}').status_code == 200
    assert bob.get(f'/api/courses/{course["id"]}').status_code == 404
    assert bob.get('/api/courses').json() == []
    assert bob.put(f'/api/courses/{course["id"]}', json={'name':'intrusion'}).status_code == 404
    assert alice.put(f'/api/courses/{course["id"]}', json={'name':'SQL', 'description':'updated'}).status_code == 200
    assert alice.get(f'/api/courses/{course["id"]}').json()['name'] == 'SQL'
    assert alice.post('/api/courses', json={'name':'   '}).status_code == 422
    token = alice.cookies.get('study_session')
    resumed = TestClient(create_app(path))
    resumed.cookies.set('study_session', token)
    assert len(resumed.get('/api/courses').json()) == 1
    assert alice.post('/api/auth/logout').status_code == 200
    assert resumed.get('/api/auth/me').status_code == 401


def test_invalid_password_and_cross_origin(tmp_path):
    client = TestClient(create_app(tmp_path / 'test.db'))
    assert client.post('/api/auth/register', json={'username':'abc','password':'short'}).status_code == 422
    assert client.post('/api/auth/login', json={'username':'abc','password':'wrong-password'}).status_code == 401
    assert client.post('/api/auth/register', headers={'Origin':'https://other.example'}, json={'username':'abc','password':'valid-password'}).status_code == 403


def test_home_and_assets(tmp_path):
    client = TestClient(create_app(tmp_path / 'web.db'))
    response = client.get('/')
    assert response.status_code == 200
    assert '我的课程' in response.text
    assert client.get('/static/app.js').status_code == 200
    assert client.get('/static/styles.css').status_code == 200
