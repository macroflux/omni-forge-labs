"""Dashboard route, local request, and path confinement regression tests."""
from pathlib import Path
import pytest
from omniforge.viewer import app as viewer


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(viewer, 'RUNS_DIR', tmp_path/'runs')
    monkeypatch.setattr(viewer, 'BOARD_PATH', tmp_path/'runs'/'board.json')
    monkeypatch.setattr(viewer, 'WORK_DIR', tmp_path/'runs'/'work')
    viewer.app.config.update(TESTING=True)
    return viewer.app.test_client()


def test_dashboard_renders(client):
    response = client.get('/')
    assert response.status_code == 200
    assert b'csrf_token' in response.data


def test_post_requires_token(client):
    assert client.post('/ticket/create', data={'project':'demo'}).status_code == 403


def test_create_and_approve_flow(client):
    token = viewer.FORM_TOKEN
    assert client.post('/ticket/create', data={'project':'demo','ticket_id':'T-1','csrf_token':token}).status_code == 302
    assert client.get('/ticket/T-1').status_code == 200
    assert client.post('/ticket/T-1/approve', data={'stage':'design','csrf_token':token}).status_code == 409


@pytest.mark.parametrize('value', ['..','.','../file','a/b','a\\b','x\n'])
def test_unsafe_segment_rejected(value):
    assert not viewer._safe(value)


def test_host_and_remote_address_rejected(client):
    assert client.get('/', headers={'Host':'evil.example'}).status_code == 403
    assert client.get('/', environ_overrides={'REMOTE_ADDR':'192.0.2.1'}).status_code == 403


def test_confined_path(client, tmp_path):
    with viewer.app.test_request_context('/'):
        with pytest.raises(Exception) as error:
            viewer._under(tmp_path/'runs', '..', 'outside')
        assert error.value.code == 400
