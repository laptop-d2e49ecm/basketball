from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
import json
import pytest
from fastapi import HTTPException, UploadFile
from PIL import Image
from app.api import agent


@pytest.fixture
def images(tmp_path, monkeypatch):
    monkeypatch.setattr(agent, "settings", SimpleNamespace(runs_dir=tmp_path))
    monkeypatch.setattr(agent.task_repo, "get_task", lambda key: {"status": "ready"} if key in {"video-one", "video-two"} else None)
    return tmp_path


def upload(data=None):
    if data is None:
        buffer = BytesIO()
        Image.new("RGB", (32, 24), "red").save(buffer, format="PNG")
        data = buffer.getvalue()
    return agent.upload_chat_image("video-one", UploadFile(filename="court.png", file=BytesIO(data))).result


def test_upload_stores_normalized_image_and_serves_preview(images):
    image = upload()
    response = agent.get_chat_image("video-one", image["id"])
    with Image.open(response.path) as picture:
        assert picture.format == "JPEG"
        assert picture.size == (32, 24)
    assert image["url"].endswith(image["id"])
    with pytest.raises(agent.NotFoundError) as error:
        agent.get_chat_image("video-two", image["id"])
    assert error.value.status_code == 404


@pytest.mark.parametrize("data,status", [(b"not-an-image", 400), (b"x" * (10 * 1024 * 1024 + 1), 413)])
def test_upload_rejects_bad_or_oversize_images(images, data, status):
    with pytest.raises(HTTPException) as error:
        upload(data)
    assert error.value.status_code == status
    assert not list(images.rglob("*.jpg"))


def test_attachment_is_passed_to_real_detection_tool_and_saved_in_history(images, monkeypatch):
    from app.agent import tools
    image = upload()
    path = agent._chat_image_path("video-one", image["id"])
    monkeypatch.setattr(tools, "_detector", lambda: SimpleNamespace(api_detect=lambda data: {
        "boxes": [{"conf": .9}], "player_count": 1, "dropped_boxes": 0, "infer_ms": 2,
    }))
    received = []
    class FakeAgent:
        def invoke(self, payload):
            received.extend(payload["messages"])
            assert str(path) in received[-1]["content"]
            result = tools.player_detect.invoke({"image_path": str(path)})
            return {"messages": [
                SimpleNamespace(type="ai", tool_calls=[{"id": "detect", "name": "player_detect", "args": {"image_path": str(path)}}]),
                SimpleNamespace(type="tool", tool_call_id="detect", content=result),
                SimpleNamespace(type="ai", tool_calls=[], content="检测到 1 名球员。"),
            ]}
    saved = []
    monkeypatch.setattr(agent, "_get_agent", lambda _: FakeAgent())
    monkeypatch.setattr(agent.agent_sessions, "new_session", lambda _: "session-one")
    monkeypatch.setattr(agent.agent_sessions, "append_history", lambda _, history: saved.extend(history))
    monkeypatch.setattr(agent, "_write_log", lambda *args: None)
    monkeypatch.setattr(agent, "_provider_name", lambda: "test")
    result = agent.agent_chat(agent.AgentChatRequest(task_id="video-one", message="这张图有几名球员？", image_id=image["id"]), None)
    assert result.result["tool_calls"][0]["tool"] == "player_detect"
    assert result.result["tool_calls"][0]["status"] == "ok"
    assert saved[0]["image"]["id"] == image["id"]
    assert str(path) in agent._history_to_messages(saved, "video-one")[0]["content"]
    with pytest.raises(agent.NotFoundError):
        agent.agent_chat(agent.AgentChatRequest(task_id="video-two", message="检测图片", image_id=image["id"]), None)


def test_image_multipart_http_contract(images):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.core.errors import register_exception_handlers
    app = FastAPI()
    app.include_router(agent.router, prefix="/api/v1")
    register_exception_handlers(app)
    buffer = BytesIO()
    Image.new("RGB", (16, 16), "blue").save(buffer, format="PNG")
    with TestClient(app) as client:
        response = client.post("/api/v1/agent/images", data={"task_id": "video-one"}, files={"file": ("frame.png", buffer.getvalue(), "image/png")})
        assert response.status_code == 200
        image = response.json()["result"]
        preview = client.get(image["url"])
        assert preview.status_code == 200
        assert preview.headers["content-type"] == "image/jpeg"
        assert client.get(image["url"].replace("video-one", "video-two")).status_code == 404
        bad = client.post("/api/v1/agent/images", data={"task_id": "video-one"}, files={"file": ("bad.png", b"bad", "image/png")})
        assert bad.status_code == 400


def test_multiple_images_are_passed_and_preserved_in_order(images, monkeypatch):
    first, second = upload(), upload()
    saved = []
    class FakeAgent:
        def invoke(self, payload):
            text = payload["messages"][-1]["content"]
            assert str(agent._chat_image_path("video-one", first["id"])) in text
            assert str(agent._chat_image_path("video-one", second["id"])) in text
            assert "分别调用工具" in text
            return {"messages": [SimpleNamespace(type="ai", tool_calls=[], content="两张图片") ]}
    monkeypatch.setattr(agent, "_get_agent", lambda _: FakeAgent())
    monkeypatch.setattr(agent.agent_sessions, "new_session", lambda _: "session-many")
    monkeypatch.setattr(agent.agent_sessions, "append_history", lambda _, rows: saved.extend(rows))
    monkeypatch.setattr(agent, "_write_log", lambda *args: None)
    monkeypatch.setattr(agent, "_provider_name", lambda: "test")
    agent.agent_chat(agent.AgentChatRequest(task_id="video-one", message="分别检测人数", image_ids=[first["id"], second["id"]]), None)
    assert [item["id"] for item in saved[0]["images"]] == [first["id"], second["id"]]
    restored = agent._history_to_messages(saved, "video-one")[0]["content"]
    assert first["id"] in restored and second["id"] in restored
