"""Turn the stored API messages into lesson blocks for the UI. Pure."""
import json

from ..tools import INTERACTIVE


def _blocks(content) -> list[dict]:
    if isinstance(content, str):
        return [{"type": "text", "text": content}]
    return content or []


def _parse(result_block: dict) -> dict:
    c = result_block.get("content")
    if isinstance(c, list):  # list of text blocks
        c = "".join(b.get("text", "") for b in c if isinstance(b, dict))
    try:
        v = json.loads(c) if isinstance(c, str) else {}
        return v if isinstance(v, dict) else {"raw": v}
    except json.JSONDecodeError:
        return {"raw": c}


def pending_tool_uses(session: dict) -> list[dict]:
    """Interactive tool_use blocks in the last assistant message still waiting for the learner."""
    msgs = session["messages"]
    if not msgs or msgs[-1]["role"] != "assistant":
        return []
    done = {r["tool_use_id"] for r in session.get("pending_results", [])}
    return [b for b in _blocks(msgs[-1]["content"])
            if b.get("type") == "tool_use" and b.get("name") in INTERACTIVE and b["id"] not in done]


def public_quiz(inp: dict) -> dict:
    """Quiz input with the answer key removed (for unanswered questions)."""
    return {k: v for k, v in inp.items() if k not in ("correct_index", "explanation")}


def build_view(session: dict) -> dict:
    results: dict[str, dict] = {}
    for m in session["messages"]:
        if m["role"] == "user":
            for b in _blocks(m["content"]):
                if b.get("type") == "tool_result":
                    results[b["tool_use_id"]] = b
    for b in session.get("pending_results", []):
        results[b["tool_use_id"]] = b

    items: list[dict] = []
    for m in session["messages"]:
        for b in _blocks(m["content"]):
            t = b.get("type")
            if m["role"] == "user":
                if t == "text":
                    txt = b["text"]
                    kind = "learner_text"
                    if txt.startswith("[Thinking while reading] "):
                        kind, txt = "reading_thinking", txt[len("[Thinking while reading] "):]
                    items.append({"kind": kind, "text": txt})
                continue
            if t == "thinking" and b.get("thinking", "").strip():
                items.append({"kind": "agent_thinking", "text": b["thinking"]})
            elif t == "text" and b.get("text", "").strip():
                items.append({"kind": "teacher_text", "text": b["text"]})
            elif t == "tool_use":
                name, inp, rid = b["name"], b.get("input") or {}, b["id"]
                res = results.get(rid)
                answer = _parse(res) if res else None
                if res and res.get("is_error"):
                    continue  # invalid call the teacher retried; nothing to show
                if name == "quiz":
                    items.append({"kind": "quiz", "id": rid,
                                  "quiz": inp if answer else public_quiz(inp),
                                  "answer": answer})
                elif name == "ask_question":
                    items.append({"kind": "ask", "id": rid, "question": inp, "answer": answer})
                elif name == "probe_done":
                    items.append({"kind": "probe_done", "summary": inp})
                elif name == "plan_init":
                    items.append({"kind": "plan", "plan": inp})

    pending = [
        {"id": b["id"], "name": b["name"],
         "input": public_quiz(b.get("input") or {}) if b["name"] == "quiz" else b.get("input") or {}}
        for b in pending_tool_uses(session)
    ]
    return {"items": items, "pending": pending}
