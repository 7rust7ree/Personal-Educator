"""Tool definitions the teacher can call, plus input validation.

Interactive tools (quiz, ask_question) pause the turn until the learner answers.
Server tools (probe_done, plan_init, plan_progress) run immediately.
"""

INTERACTIVE = {"quiz", "ask_question"}

_MD = "Markdown. Math goes in $...$ (inline) or $$...$$ (display). Code in fenced blocks."

TOOLS = [
    {
        "name": "ask_question",
        "description": "Ask the learner an open question or offer choices (goal, scope, plan approval). "
                       "Not graded. The learner can always type their own answer instead of a listed option.",
        "input_schema": {
            "type": "object",
            "properties": {
                "lesson": {"type": "string",
                           "description": "What the learner reads right above the question: your explanation, "
                                          "worked example, diagram (```mermaid), code, or feedback on their last answer. "
                                          "The learner sees ONLY what is inside tool inputs. " + _MD},
                "question": {"type": "string", "description": _MD},
                "options": {"type": "array", "items": {"type": "string"}, "maxItems": 6,
                            "description": "Suggested answers. May be empty for a free-text question."},
            },
            "required": ["question"],
        },
    },
    {
        "name": "plan_init",
        "description": "Set (or replace) the lesson plan: the minimal dependency map from what the learner "
                       "already holds to the goal. Coarse nodes, not chapters. Only after probe_done.",
        "input_schema": {
            "type": "object",
            "properties": {
                "goal": {"type": "string", "description": "One sentence: what will feel obviously true at the end."},
                "nodes": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 14,
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string", "description": "Short slug, e.g. 'bst_height'."},
                            "title": {"type": "string", "description": "2-7 words."},
                            "depends_on": {"type": "array", "items": {"type": "string"}},
                        },
                        "required": ["id", "title", "depends_on"],
                    },
                },
            },
            "required": ["goal", "nodes"],
        },
    },
    {
        "name": "plan_progress",
        "description": "Mark where the learner is on the plan map. 'active' when you start a node, "
                       "'done' when its check has been passed.",
        "input_schema": {
            "type": "object",
            "properties": {
                "node_id": {"type": "string"},
                "status": {"type": "string", "enum": ["active", "done"]},
            },
            "required": ["node_id", "status"],
        },
    },
    {
        "name": "probe_done",
        "description": "End the probe phase. Record a precise picture of the learner's current understanding "
                       "and goal. After this, plan with plan_init.",
        "input_schema": {
            "type": "object",
            "properties": {
                "current_understanding": {"type": "string",
                                          "description": "What they hold as obviously true, and where their edge is."},
                "goal": {"type": "string"},
                "gaps": {"type": "array", "items": {"type": "string"},
                         "description": "Missing prerequisites the goal depends on."},
                "misconceptions": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["current_understanding", "goal", "gaps", "misconceptions"],
        },
    },
    {
        "name": "quiz",
        "description": "Ask a question the learner answers with confidence and their thinking. "
                       "kind=probe (find their edge), predict (they guess the next move before you explain), "
                       "check (graded test that the step landed). With options it is multiple choice "
                       "(an 'I don't know' option is added automatically); without options it is free response.",
        "input_schema": {
            "type": "object",
            "properties": {
                "kind": {"type": "string", "enum": ["probe", "predict", "check"]},
                "lesson": {"type": "string",
                           "description": "What the learner reads right above the question: your explanation, "
                                          "worked example, diagram (```mermaid), code, or feedback on their last answer. "
                                          "The learner sees ONLY what is inside tool inputs. " + _MD},
                "question": {"type": "string", "description": _MD},
                "options": {"type": "array", "items": {"type": "string"}, "maxItems": 5,
                            "description": "2-5 options for multiple choice; omit for free response. " + _MD},
                "correct_index": {"type": "integer",
                                  "description": "0-based index of the correct option (multiple choice only). "
                                                 "Hidden from the learner until they answer."},
                "explanation": {"type": "string",
                                "description": "Short explanation shown right after they answer (multiple choice). "
                                               + _MD},
            },
            "required": ["kind", "question"],
        },
    },
]

# Stream tool inputs as they are generated (we validate them ourselves below).
for _t in TOOLS:
    _t["eager_input_streaming"] = True


def _str(x) -> bool:
    return isinstance(x, str) and x.strip() != ""


def _str_list(x) -> bool:
    return isinstance(x, list) and all(isinstance(i, str) for i in x)


def validate(name: str, inp) -> str | None:
    """Return an error message, or None if the input is usable."""
    if not isinstance(inp, dict):
        return "input must be an object"
    if "lesson" in inp and not isinstance(inp["lesson"], str):
        return "lesson must be a string"
    if name == "quiz":
        if inp.get("kind") not in ("probe", "predict", "check"):
            return "kind must be probe, predict or check"
        if not _str(inp.get("question")):
            return "question is required"
        opts = inp.get("options")
        if opts:
            if not _str_list(opts) or not 2 <= len(opts) <= 5:
                return "options must be 2-5 strings"
            ci = inp.get("correct_index")
            if not isinstance(ci, int) or not 0 <= ci < len(opts):
                return "multiple choice needs a valid correct_index"
        return None
    if name == "ask_question":
        if not _str(inp.get("question")):
            return "question is required"
        if "options" in inp and not _str_list(inp["options"]):
            return "options must be strings"
        return None
    if name == "probe_done":
        for k in ("current_understanding", "goal"):
            if not _str(inp.get(k)):
                return f"{k} is required"
        for k in ("gaps", "misconceptions"):
            if not _str_list(inp.get(k, [])):
                return f"{k} must be a list of strings"
        return None
    if name == "plan_init":
        from .core.plan import plan_error
        if not _str(inp.get("goal")):
            return "goal is required"
        return plan_error(inp.get("nodes"))
    if name == "plan_progress":
        if not _str(inp.get("node_id")) or inp.get("status") not in ("active", "done"):
            return "node_id and status (active|done) are required"
        return None
    return f"unknown tool {name}"
