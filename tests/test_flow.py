"""End-to-end teaching loop through the HTTP API with a fake Claude (no network, no cost)."""
import json

import pytest
from fastapi.testclient import TestClient

from backend import app as app_module, config, store


def tool_use(i, name, inp):
    return {"type": "tool_use", "id": f"tu{i}", "name": name, "input": inp}


def reply(*blocks, stop="tool_use"):
    return {"content": list(blocks), "stop_reason": stop,
            "usage": {"input_tokens": 1000, "output_tokens": 200}, "model": "claude-opus-5-5"}


class FakeLLM:
    def __init__(self, script):
        self.script = list(script)
        self.calls = []

    async def stream(self, *, model, effort, system, tools, messages, emit):
        self.calls.append(json.loads(json.dumps(messages)))
        r = self.script.pop(0)
        for b in r["content"]:
            if b["type"] == "text":
                await emit({"type": "text_delta", "text": b["text"]})
        return r


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    return TestClient(app_module.app)


def run(client, sid, body):
    with client.stream("POST", f"/api/sessions/{sid}/turn", json=body) as r:
        assert r.status_code == 200
        return [json.loads(l[6:]) for l in r.iter_lines() if l.startswith("data: ")]


def test_probe_plan_teach_flow(client):
    probe_q = {"kind": "probe", "question": "What is $O(n)$?", "options": ["a", "b"], "correct_index": 0, "explanation": "E"}
    fake = FakeLLM([
        reply({"type": "text", "text": "Let's see."}, tool_use(1, "quiz", probe_q)),
        reply(tool_use(2, "probe_done", {"current_understanding": "knows big-O", "goal": "BST", "gaps": [], "misconceptions": []}),
              tool_use(3, "plan_init", {"goal": "BST search", "nodes": [
                  {"id": "a", "title": "Trees", "depends_on": []}, {"id": "b", "title": "Height", "depends_on": ["a"]}]}),
              tool_use(4, "ask_question", {"question": "Accept?", "options": ["Accept the plan", "Change"]})),
        reply(tool_use(5, "plan_progress", {"node_id": "a", "status": "active"})),
        reply({"type": "text", "text": "Predict:"}, tool_use(6, "quiz", {"kind": "predict", "question": "Guess?"})),
    ])
    app_module.set_llm(fake)

    sid = client.post("/api/sessions", json={"topic": "BST search"}).json()["id"]
    events = run(client, sid, {"message": "BST search"})
    assert [e["type"] for e in events][-2:] == ["await_learner", "done"]

    v = client.get(f"/api/sessions/{sid}").json()
    assert v["status"] == "waiting"
    assert v["pending"][0]["input"].get("correct_index") is None  # answer key hidden

    events = run(client, sid, {"answers": {"tu1": {"choice": 0, "confidence": 80, "thinking": "linear"}},
                               "reading_thinking": "makes sense"})
    graded = [e for e in events if e["type"] == "graded"][0]
    assert graded["feedback"]["tu1"] == {"correct": True, "correct_index": 0, "explanation": "E"}
    assert events.index(graded) == 0  # instant feedback comes before anything from the model
    sent = fake.calls[1][-1]["content"]
    res = json.loads(sent[0]["content"])
    assert res["correct"] is True and res["confidence"] == "80%" and res["thinking"] == "linear"
    assert sent[-1]["text"].startswith("[Thinking while reading]")

    v = client.get(f"/api/sessions/{sid}").json()
    assert v["phase"] == "teach" and v["plan"]["goal"] == "BST search"
    assert v["pending"][0]["name"] == "ask_question"

    run(client, sid, {"answers": {"tu4": {"text": "Accept the plan"}}})
    # server tool results for probe_done/plan_init were held and sent together with the answer
    ids = [b["tool_use_id"] for b in fake.calls[2][-1]["content"]]
    assert ids == ["tu2", "tu3", "tu4"]

    v = client.get(f"/api/sessions/{sid}").json()
    assert v["plan"]["nodes"][0]["status"] == "active"
    assert v["pending"][0]["input"]["kind"] == "predict"
    kinds = [i["kind"] for i in v["items"]]
    assert {"learner_text", "teacher_text", "quiz", "probe_done", "plan", "ask", "reading_thinking"} <= set(kinds)
    assert v["usage"]["cost"] > 0
    assert client.get("/api/usage").json()["month_cost"] > 0


def test_interjection_and_invalid_tool(client):
    fake = FakeLLM([
        reply(tool_use(1, "quiz", {"kind": "probe", "question": "Q", "options": ["a", "b"]})),  # invalid: no key
        reply(tool_use(2, "quiz", {"kind": "probe", "question": "Q", "options": ["a", "b"], "correct_index": 1})),
        reply({"type": "text", "text": "Sure, it means..."}, tool_use(3, "quiz", {"kind": "probe", "question": "Q2"})),
    ])
    app_module.set_llm(fake)
    sid = client.post("/api/sessions", json={"topic": "x"}).json()["id"]
    run(client, sid, {"message": "x"})
    # the invalid call got an error result and the teacher retried within the same turn
    assert json.loads(fake.calls[1][-1]["content"][0]["content"])["error"]
    v = client.get(f"/api/sessions/{sid}").json()
    assert [p["id"] for p in v["pending"]] == ["tu2"]

    run(client, sid, {"message": "what does that symbol mean?"})
    res = json.loads(fake.calls[2][-1]["content"][0]["content"])
    assert res == {"learner_interjected_instead_of_answering": "what does that symbol mean?"}


def test_budget_blocks_calls(client):
    store.save_settings({**config.DEFAULT_SETTINGS, "monthly_budget_usd": 0})
    fake = FakeLLM([])
    app_module.set_llm(fake)
    sid = client.post("/api/sessions", json={"topic": "x"}).json()["id"]
    events = run(client, sid, {"message": "x"})
    assert any(e["type"] == "error" and "budget" in e["message"].lower() for e in events)
    assert fake.calls == []


def test_busy_session_rejected(client):
    sid = client.post("/api/sessions", json={"topic": "x"}).json()["id"]
    import asyncio
    lock = app_module._locks.setdefault(sid, asyncio.Lock())
    lock._locked = True  # simulate a running turn
    try:
        assert client.post(f"/api/sessions/{sid}/turn", json={"message": "hi"}).status_code == 409
    finally:
        lock._locked = False
