"""The desktop window uses the system WebKit, which is older than Chrome/Safari. Guard against syntax it can't parse."""
import re
from pathlib import Path

FRONTEND = Path(__file__).resolve().parent.parent / "frontend"


def test_no_regex_lookbehind_in_js():
    # (?<= and (?<! break the whole script in the desktop window's WebKit (seen 2026-10-27)
    for js in FRONTEND.glob("*.js"):
        assert not re.search(r"\(\?<[=!]", js.read_text()), f"regex lookbehind in {js.name}"
