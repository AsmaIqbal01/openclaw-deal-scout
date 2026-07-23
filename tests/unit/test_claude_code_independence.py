"""Claude Code independence gate — src/ must contain zero references to developer tooling."""
import re
from pathlib import Path

_PATTERN = re.compile(r"claude|anthropic", re.IGNORECASE)
_SRC_DIR = Path(__file__).resolve().parent.parent.parent / "src"


def test_no_claude_or_anthropic_references_in_src():
    """Every .py file under src/ must be free of 'claude' or 'anthropic' references.

    This gate ensures the production pipeline never gains a dependency on Claude Code
    or Anthropic APIs through accidental import or string reference.
    """
    matches = []
    for py_file in sorted(_SRC_DIR.rglob("*.py")):
        try:
            text = py_file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            if _PATTERN.search(line):
                rel = py_file.relative_to(_SRC_DIR)
                matches.append(f"  {rel}:{lineno}: {line.strip()}")

    assert matches == [], (
        f"Found {len(matches)} reference(s) to 'claude' or 'anthropic' in src/:\n"
        + "\n".join(matches)
        + "\n\nRemove all references to developer tooling from production source code."
    )
