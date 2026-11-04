"""Plan tree: validation and progress. Pure functions, no IO."""


def plan_error(nodes) -> str | None:
    """Return why a node list is not a valid dependency DAG, or None."""
    if not isinstance(nodes, list) or not nodes:
        return "nodes must be a non-empty list"
    ids = []
    for n in nodes:
        if not isinstance(n, dict) or not isinstance(n.get("id"), str) or not n["id"].strip():
            return "every node needs an id"
        if not isinstance(n.get("title"), str) or not n["title"].strip():
            return f"node {n['id']} needs a title"
        if not isinstance(n.get("depends_on", []), list):
            return f"node {n['id']}: depends_on must be a list"
        ids.append(n["id"])
    if len(set(ids)) != len(ids):
        return "node ids must be unique"
    known = set(ids)
    deps = {n["id"]: list(n.get("depends_on", [])) for n in nodes}
    for nid, ds in deps.items():
        for d in ds:
            if d not in known:
                return f"node {nid} depends on unknown node {d}"
    # cycle check (DFS)
    state: dict[str, int] = {}

    def visit(v: str) -> bool:
        state[v] = 1
        for d in deps[v]:
            if state.get(d) == 1 or (state.get(d) is None and visit(d)):
                return True
        state[v] = 2
        return False

    if any(state.get(v) is None and visit(v) for v in ids):
        return "plan has a dependency cycle"
    return None


def make_plan(goal: str, nodes: list, old: dict | None = None) -> dict:
    """Build plan state, keeping statuses of nodes that survive a re-plan."""
    old_status = {n["id"]: n.get("status") for n in (old or {}).get("nodes", [])}
    return {
        "goal": goal,
        "nodes": [
            {"id": n["id"], "title": n["title"], "depends_on": list(n.get("depends_on", [])),
             "status": old_status.get(n["id"]) or "todo"}
            for n in nodes
        ],
    }


def set_status(plan: dict, node_id: str, status: str) -> str | None:
    """Update one node; returns an error message if the node doesn't exist."""
    for n in plan["nodes"]:
        if n["id"] == node_id:
            if status == "active":
                for m in plan["nodes"]:  # only one active node at a time
                    if m["status"] == "active":
                        m["status"] = "todo"
            n["status"] = status
            return None
    return f"no plan node with id {node_id}"
