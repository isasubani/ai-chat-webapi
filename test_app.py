import pytest
from fastapi.testclient import TestClient
from api_gemini_ai_chat import app, init_db, update_settings, DB_FILE

client = TestClient(app)

def test_list_models():
    init_db()
    response = client.get("/v1/models")
    assert response.status_code == 200
    data = response.json()
    assert data["object"] == "list"
    assert len(data["data"]) > 0
    assert data["data"][0]["id"] == "gemini-web"

def test_unauthorized_chat_completions():
    init_db()
    update_settings("", "my-secret-key", "http://localhost", "gemini-web")

    response = client.post(
        "/v1/chat/completions",
        json={"messages": [{"role": "user", "content": "Halo"}]}
    )
    assert response.status_code == 401

def test_chat_without_cookie_fails():
    init_db()
    # Kosongkan cookie langsung di database.db
    update_settings("", "dummy-key", "http://localhost", "gemini-web")
    
    # Reset global gemini client di app
    import api_gemini_ai_chat
    api_gemini_ai_chat.gemini = None

    response = client.post(
        "/v1/chat/completions",
        headers={"Authorization": "Bearer dummy-key"},
        json={"messages": [{"role": "user", "content": "Tes tanpa cookie"}]}
    )
    assert response.status_code == 500
    assert "SESSION_COOKIE not configured" in response.json()["error"]