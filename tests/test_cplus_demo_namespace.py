"""UNIT_FAKE HTTP: local C and C+ on different ports must not overwrite host cookies."""
from fastapi.testclient import TestClient

from app.demo.app import create_demo_app
from tests.test_demo_auth import HEADERS, attempt, configuration, op
from tests.test_demo_gateway import HTTPManager
from uuid import uuid4


def test_cplus_cookie_login_gateway_logout_preserve_original_c_cookie(tmp_path):
    app = create_demo_app(configuration(tmp_path), HTTPManager(tmp_path/'runtime'), cookie_name='findoc_demo_cplus')
    with TestClient(app) as client:
        client.cookies.set('findoc_demo', 'unrelated-original-c-cookie', domain='testserver.local', path='/')
        claim=attempt(client)
        assert 'findoc_demo_cplus=' in claim.headers['set-cookie']
        assert client.get('/companies').status_code==200
        result=client.post('/demo/logout',json=op(),headers=HEADERS)
        assert result.status_code==200
        assert client.cookies.get('findoc_demo')=='unrelated-original-c-cookie'
        assert not client.cookies.get('findoc_demo_cplus')


def test_cplus_controller_discovery_uses_final_asgi_boundary(tmp_path, monkeypatch):
    monkeypatch.setenv('FINDOC_CPLUS_ENABLED','1')
    app=create_demo_app(configuration(tmp_path),HTTPManager(tmp_path/'runtime'),cookie_name='findoc_demo_cplus')
    with TestClient(app) as client:
        path='/cplus/discovery/searches/'+str(uuid4())
        assert client.get(path).status_code==401
        attempt(client)
        # Authenticated read of a missing operation reaches the actual service, without any network.
        result=client.get(path)
        assert result.status_code==404 and result.json()['detail']['code']=='operation_not_found'
