"""Pure logic: plan validation, grading, tool validation, cost math, view building."""
import json

from backend.core import grading, plan
from backend.core.view import build_view, pending_tool_uses
from backend.llm import cost_of
from backend.tools import TOOLS, validate


def test_plan_valid_and_invalid():
    ok = [{"id": "a", "title": "A", "depends_on": []}, {"id": "b", "title": "B", "depends_on": ["a"]}]
    assert plan.plan_error(ok) is None
    assert "unknown" in plan.plan_error([{"id": "a", "title": "A", "depends_on": ["zz"]}])
    assert "unique" in plan.plan_error(ok + [{"id": "a", "title": "dup", "depends_on": []}])
    cyc = [{"id": "a", "title": "A", "depends_on": ["b"]}, {"id": "b", "title": "B", "depends_on": ["a"]}]
    assert "cycle" in plan.plan_error(cyc)


def test_plan_progress_single_active_and_replan_keeps_status():
    p = plan.make_plan("g", [{"id": "a", "title": "A", "depends_on": []}, {"id": "b", "title": "B", "depends_on": ["a"]}])
    assert plan.set_status(p, "a", "active") is None
    assert plan.set_status(p, "b", "active") is None
    assert [n["status"] for n in p["nodes"]] == ["todo", "active"]
    plan.set_status(p, "a", "done")
    p2 = plan.make_plan("g2", [{"id": "a", "title": "A", "depends_on": []}, {"id": "c", "title": "C", "depends_on": []}], p)
    assert [n["status"] for n in p2["nodes"]] == ["done", "todo"]
    assert plan.set_status(p, "nope", "done")


def test_grade_multiple_choice():
    q = {"kind": "check", "question": "?", "options": ["x", "y"], "correct_index": 1, "explanation": "because"}
    out, fb = grading.grade_quiz(q, {"choice": 1, "confidence": 70, "thinking": "hmm"})
    assert out["correct"] is True and out["confidence"] == "70%" and out["thinking"] == "hmm"
    assert fb["correct_index"] == 1
    out, _ = grading.grade_quiz(q, {"choice": 0})
    assert out["correct"] is False and "confidence" not in out
    out, _ = grading.grade_quiz(q, {"idk": True, "confidence": None})
    assert out["answer"] == "I don't know" and out["correct"] is False


def test_grade_free_response_left_to_teacher():
    out, fb = grading.grade_quiz({"kind": "predict", "question": "?"}, {"text": "O(log n)"})
    assert out == {"answer": "O(log n)"} and fb == {}


def test_validate_tools():
    assert validate("quiz", {"kind": "probe", "question": "q", "options": ["a", "b"], "correct_index": 0}) is None
    assert validate("quiz", {"kind": "probe", "question": "q", "options": ["a", "b"]})  # missing key
    assert validate("quiz", {"kind": "check", "question": "q"}) is None  # free response
    assert validate("quiz", {"kind": "nope", "question": "q"})
    assert validate("plan_init", {"goal": "g", "nodes": [{"id": "a", "title": "A", "depends_on": []}]}) is None
    assert validate("ask_question", {"question": ""})
    assert validate("ask_question", {"question": "q", "lesson": "## Diagram"}) is None
    assert validate("quiz", {"kind": "check", "question": "q", "lesson": 5})
    assert all(t["eager_input_streaming"] for t in TOOLS)
    assert [t["name"] for t in TOOLS] == sorted(t["name"] for t in TOOLS)  # fixed order for caching


def test_cost():
    c = cost_of("claude-opus-5-5", {"input_tokens": 1_000_000, "output_tokens": 100_000,
                                     "cache_read_input_tokens": 1_000_000, "cache_creation_input_tokens": 0})
    assert round(c, 4) == round(4 + 2 + 0.2, 4)


def test_view_hides_answer_key_until_answered():
    quiz = {"id": "tu1", "type": "tool_use", "name": "quiz",
            "input": {"kind": "probe", "question": "Q", "options": ["a", "b"], "correct_index": 1, "explanation": "E"}}
    s = {"messages": [{"role": "user", "content": [{"type": "text", "text": "teach me"}]},
                      {"role": "assistant", "content": [{"type": "text", "text": "hi"}, quiz]}],
         "pending_results": []}
    v = build_view(s)
    assert v["pending"][0]["input"] == {"kind": "probe", "question": "Q", "options": ["a", "b"]}
    assert all("correct_index" not in json.dumps(i) for i in v["items"])
    s["messages"].append({"role": "user", "content": [grading.tool_result("tu1", {"answer": "option 1: b", "choice_index": 1, "correct": True})]})
    v = build_view(s)
    assert v["pending"] == []
    q = [i for i in v["items"] if i["kind"] == "quiz"][0]
    assert q["quiz"]["correct_index"] == 1 and q["answer"]["correct"] is True
    assert pending_tool_uses(s) == []
