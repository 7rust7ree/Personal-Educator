"""The teaching loop for one learner submission.

A submission is either answers to the pending interactive questions, a free message,
or both. The loop calls Claude, runs server tools, and stops when the teacher asks
the learner something (quiz / ask_question) or ends its turn.
"""
import json
from dataclasses import dataclass, field

from . import config, store
from .core import grading, plan as plan_core
from .core.view import pending_tool_uses
from .llm import Emit, cost_of
from .tools import INTERACTIVE, TOOLS, validate


class BudgetExceeded(Exception):
    pass


@dataclass
class Submission:
    answers: dict = field(default_factory=dict)   # tool_use_id -> answer dict
    message: str = ""
    reading_thinking: str = ""


def system_blocks(profile: dict) -> list:
    prompt = (config.PROMPTS_DIR / "teacher.md").read_text()
    learner = "# The learner\n\n```json\n" + json.dumps(profile, indent=2, sort_keys=True) + "\n```"
    return [
        {"type": "text", "text": prompt},
        {"type": "text", "text": learner, "cache_control": {"type": "ephemeral"}},
    ]


def _build_user_content(session: dict, sub: Submission) -> tuple[list, dict]:
    """Returns (user message content, instant feedback per question for the UI)."""
    content: list = []
    feedback: dict = {}
    pending = pending_tool_uses(session)
    if pending:
        content.extend(session.get("pending_results", []))
        for tu in pending:
            ans = sub.answers.get(tu["id"])
            if ans is None:
                note = sub.message.strip() or "(the learner skipped this question)"
                payload = {"learner_interjected_instead_of_answering": note}
                content.append(grading.tool_result(tu["id"], payload))
                continue
            if tu["name"] == "quiz":
                payload, fb = grading.grade_quiz(tu["input"], ans)
                if fb:
                    feedback[tu["id"]] = fb
            else:
                payload = grading.ask_result(ans)
            content.append(grading.tool_result(tu["id"], payload))
        session["pending_results"] = []
        interjected = any(tu["id"] not in sub.answers for tu in pending)
        if sub.message.strip() and not interjected:
            content.append({"type": "text", "text": sub.message.strip()})
    elif sub.message.strip():
        content.append({"type": "text", "text": sub.message.strip()})
    if sub.reading_thinking.strip():
        content.append({"type": "text", "text": "[Thinking while reading] " + sub.reading_thinking.strip()})
    return content, feedback


def _run_server_tool(session: dict, name: str, inp: dict) -> tuple[dict, bool]:
    """Execute a non-interactive tool. Returns (payload, is_error)."""
    if name == "probe_done":
        session["probe"] = inp
        session["phase"] = "plan"
        return {"ok": True, "next": "Probe recorded. Now plan with plan_init."}, False
    if name == "plan_init":
        if session["phase"] == "probe":
            return {"error": "Finish probing first: call probe_done."}, True
        session["plan"] = plan_core.make_plan(inp["goal"], inp["nodes"], session.get("plan"))
        session["phase"] = "teach"
        return {"ok": True, "next": "Plan shown to the learner as a map. Ask whether they accept it."}, False
    if name == "plan_progress":
        if not session.get("plan"):
            return {"error": "No plan yet."}, True
        err = plan_core.set_status(session["plan"], inp["node_id"], inp["status"])
        return ({"error": err}, True) if err else ({"ok": True}, False)
    return {"error": f"unknown tool {name}"}, True


def _record_usage(session: dict, model: str, usage: dict) -> float:
    cost = cost_of(model, usage)
    u = session["usage"]
    u["input"] += usage.get("input_tokens", 0)
    u["output"] += usage.get("output_tokens", 0)
    u["cache_read"] += usage.get("cache_read_input_tokens") or 0
    u["cache_write"] += usage.get("cache_creation_input_tokens") or 0
    u["cost"] = round(u["cost"] + cost, 6)
    store.append_usage({"at": store.now_iso(), "session": session["id"], "model": model,
                        "usage": usage, "cost": cost})
    return cost


async def run_turn(session: dict, sub: Submission, llm, emit: Emit) -> None:
    settings = store.load_settings()
    profile = store.load_profile()

    content, feedback = _build_user_content(session, sub)
    if not content:
        await emit({"type": "error", "message": "Nothing to send."})
        return
    session["messages"].append({"role": "user", "content": content})
    store.save_session(session)
    if feedback:
        await emit({"type": "graded", "feedback": feedback})

    system = system_blocks(profile)
    for _ in range(config.MAX_STEPS_PER_TURN):
        if store.month_cost() >= settings["monthly_budget_usd"]:
            raise BudgetExceeded(
                f"Monthly budget of ${settings['monthly_budget_usd']:.2f} reached. Raise it in settings.")

        resp = await llm.stream(model=session["model"], effort=session["effort"], system=system,
                                tools=TOOLS, messages=session["messages"], emit=emit)
        session["messages"].append({"role": "assistant", "content": resp["content"]})
        _record_usage(session, resp.get("model", session["model"]), resp["usage"])
        store.save_session(session)
        await emit({"type": "usage", "session_cost": session["usage"]["cost"],
                    "month_cost": store.month_cost()})

        stop = resp["stop_reason"]
        tool_uses = [b for b in resp["content"] if b.get("type") == "tool_use"]
        if stop == "refusal":
            await emit({"type": "error", "message": "The model declined to continue this request."})
            return
        if not tool_uses:
            return  # teacher ended its turn with text

        results: list = []
        waiting = False
        for tu in tool_uses:
            name, inp = tu["name"], tu.get("input")
            err = "tool input was cut off (max_tokens)" if stop == "max_tokens" else validate(name, inp)
            if err:
                results.append(grading.tool_result(tu["id"], {"error": err}, is_error=True))
            elif name in INTERACTIVE:
                waiting = True
            else:
                payload, is_err = _run_server_tool(session, name, inp)
                results.append(grading.tool_result(tu["id"], payload, is_error=is_err))

        if waiting:
            session["pending_results"] = results
            store.save_session(session)
            await emit({"type": "await_learner"})
            return
        session["messages"].append({"role": "user", "content": results})
        store.save_session(session)

    await emit({"type": "error", "message": "The teacher took too many steps without asking you anything. "
                                            "Send a message to continue."})
