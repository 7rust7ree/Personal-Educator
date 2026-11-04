"""Turn a learner's answer into (a) the tool_result the teacher reads and (b) feedback for the UI."""
import json


def _conf(answer: dict) -> str | None:
    c = answer.get("confidence")
    return f"{int(c)}%" if isinstance(c, (int, float)) else None


def grade_quiz(quiz: dict, answer: dict) -> tuple[dict, dict]:
    """Returns (result_for_model, feedback_for_ui). Pure."""
    opts = quiz.get("options") or []
    out: dict = {}
    feedback: dict = {}
    if answer.get("idk"):
        out["answer"] = "I don't know"
        correct = False if opts else None
    elif opts:
        ch = answer.get("choice")
        if isinstance(ch, int) and 0 <= ch < len(opts):
            out["answer"] = f"option {ch}: {opts[ch]}"
            out["choice_index"] = ch
            correct = ch == quiz.get("correct_index")
        else:
            out["answer"] = "(no option selected)"
            correct = False
    else:
        out["answer"] = (answer.get("text") or "").strip() or "(blank)"
        correct = None  # free response: the teacher judges it
    if correct is not None:
        out["correct"] = correct
        feedback = {"correct": correct, "correct_index": quiz.get("correct_index"),
                    "explanation": quiz.get("explanation", "")}
    if (c := _conf(answer)) is not None:
        out["confidence"] = c
    if (t := (answer.get("thinking") or "").strip()):
        out["thinking"] = t
    return out, feedback


def ask_result(answer: dict) -> dict:
    out = {"answer": (answer.get("text") or "").strip() or "(blank)"}
    if (t := (answer.get("thinking") or "").strip()):
        out["thinking"] = t
    return out


def tool_result(tool_use_id: str, payload: dict, is_error: bool = False) -> dict:
    block = {"type": "tool_result", "tool_use_id": tool_use_id, "content": json.dumps(payload, ensure_ascii=False)}
    if is_error:
        block["is_error"] = True
    return block
