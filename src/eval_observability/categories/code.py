"""Code: implement a function whose tests live in the suite.

Gold ships pytest-style tests; we write the candidate implementation and the
tests to a temp directory and run pytest in a subprocess.
"""

from __future__ import annotations

import re
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path

import yaml

from ._base import Example, ScoreResult

name = "code"
TEST_TIMEOUT_S = 15

_CODE_FENCE_RE = re.compile(r"```(?:python)?\s*(.*?)```", re.DOTALL)


def load_suite(path: Path) -> list[Example]:
    raw = yaml.safe_load(path.read_text())
    out: list[Example] = []
    for item in raw["examples"]:
        out.append(
            Example(
                id=item["id"],
                category=name,
                input=item["input"],
                gold={
                    "function_name": item["gold"]["function_name"],
                    "tests": item["gold"]["tests"],
                },
                metadata=item.get("metadata", {}),
            )
        )
    return out


def build_prompt(example: Example) -> str:
    return (
        "Implement the following Python function. Reply with the function "
        "definition only — no surrounding prose, no fences.\n"
        f"[[example_id={example.id}]]\n"
        f"{example.input}"
    )


def _extract_code(output: str) -> str:
    match = _CODE_FENCE_RE.search(output)
    if match:
        return match.group(1).strip()
    return output.strip()


def _run_pytest(tmpdir: Path) -> tuple[bool, str]:
    cmd = [sys.executable, "-m", "pytest", str(tmpdir / "test_solution.py"), "-q", "--tb=short"]
    try:
        proc = subprocess.run(  # noqa: S603 — sandboxed temp dir, fixed argv
            cmd,
            capture_output=True,
            text=True,
            timeout=TEST_TIMEOUT_S,
            cwd=tmpdir,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return False, "timeout"
    return proc.returncode == 0, (proc.stdout + proc.stderr)[-2000:]


def score(example: Example, output: str) -> ScoreResult:
    code = _extract_code(output)
    test_block = textwrap.dedent(example.gold["tests"])

    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        (tmpdir / "solution.py").write_text(code + "\n")
        test_src = "from solution import *  # noqa\n\n" + test_block
        (tmpdir / "test_solution.py").write_text(test_src)
        ok, log = _run_pytest(tmpdir)

    return ScoreResult(
        score=1.0 if ok else 0.0,
        passed=ok,
        details={"function_name": example.gold["function_name"], "log_tail": log},
    )
