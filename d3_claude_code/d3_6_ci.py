# d3_claude_code/d3_6_ci.py
"""
EXAM: Task 3.6 - Integrate Claude Code into CI/CD pipelines
SCENARIO: 5 - Claude Code for Continuous Integration (sample Q10: the job that hangs)
RUNS: mock (no API key). The JSON handling is real; the "Claude" outputs are hard-coded samples.
      "export" mode writes a sample GitHub workflow, script and schema you can adapt.

What the exam tests:
  * -p (or --print) runs Claude Code NON-INTERACTIVELY: one prompt in, one result out, exit.
    Without it a CI job can hang waiting for input (sample Q10, answer A).
  * --output-format json plus --json-schema gives MACHINE-PARSEABLE findings (in the
    `structured_output` field) that a script can post as inline PR comments.
  * CLAUDE.md gives CI-invoked Claude Code its project context: testing standards, fixture
    conventions, review criteria.
  * A session that GENERATED code is a weak reviewer of it (it keeps its own reasoning).
    Use an INDEPENDENT review instance.
  * Re-running a review after new commits: include prior findings in context and ask for only
    NEW or STILL-UNADDRESSED issues, to avoid duplicate comments.
  * Test generation: put the EXISTING tests in context so it does not propose duplicates.

Run from the project root:
    python -m d3_claude_code.d3_6_ci              # all demos
    python -m d3_claude_code.d3_6_ci hang         # sample Q10, option by option
    python -m d3_claude_code.d3_6_ci schema       # structured findings -> inline PR comments
    python -m d3_claude_code.d3_6_ci rerun        # no duplicate comments on re-runs
    python -m d3_claude_code.d3_6_ci independent  # why a separate review session
    python -m d3_claude_code.d3_6_ci tests        # test generation without duplicates
    python -m d3_claude_code.d3_6_ci export DIR   # write a sample workflow, script and schema
"""
import json
import sys
from pathlib import Path

SCHEMA = {
    "type": "object",
    "properties": {"findings": {"type": "array", "items": {
        "type": "object",
        "properties": {
            "file": {"type": "string"},
            "line": {"type": "integer"},
            "severity": {"type": "string", "enum": ["critical", "high", "medium", "low"]},
            "category": {"type": "string", "enum": ["bug", "security", "performance", "other"]},
            "issue": {"type": "string"},
            "suggested_fix": {"type": "string"},
            "detected_pattern": {"type": "string"},  # lets you study dismissed findings later (Task 4.4)
        },
        "required": ["file", "line", "severity", "category", "issue", "suggested_fix"],
    }}},
    "required": ["findings"],
}


def demo_hang():
    print("== Sample Q10: the CI job hangs waiting for input ==")
    rows = [
        ("A", 'claude -p "Analyze this pull request..."', "CORRECT: -p / --print is the documented non-interactive mode"),
        ("B", "CLAUDE_HEADLESS=true claude ...", "no such environment variable"),
        ("C", "claude ... < /dev/null", "a Unix workaround that does not address Claude Code's own syntax"),
        ("D", "claude --batch ...", "no such flag"),
    ]
    for letter, cmd, verdict in rows:
        print(f"  {letter}  {cmd:44}{verdict}")


# Sample responses in the shape the docs describe: metadata + `result`, and `structured_output` with a schema.
WITHOUT_SCHEMA = {"type": "result", "session_id": "sess-ci-1",
                  "result": "I found a few problems: the refund handler ignores errors near line 42, and the token check in auth.py looks unsafe."}
WITH_SCHEMA = {"type": "result", "session_id": "sess-ci-2", "result": "Review complete.",
               "structured_output": {"findings": [
                   {"file": "payments.py", "line": 42, "severity": "high", "category": "bug",
                    "issue": "Refund handler swallows errors", "suggested_fix": "Catch specific exceptions and re-raise",
                    "detected_pattern": "bare_except"},
                   {"file": "auth.py", "line": 17, "severity": "critical", "category": "security",
                    "issue": "Token compared with ==", "suggested_fix": "Use hmac.compare_digest",
                    "detected_pattern": "non_constant_time_compare"},
               ]}}


def validate(finding):
    """A tiny validator for the schema above (required fields and enums only)."""
    props = SCHEMA["properties"]["findings"]["items"]
    problems = [f"missing '{k}'" for k in props["required"] if k not in finding]
    for key in ("severity", "category"):
        if key in finding and finding[key] not in props["properties"][key]["enum"]:
            problems.append(f"{key} '{finding[key]}' not in {props['properties'][key]['enum']}")
    return problems


def demo_schema():
    print("\n== --output-format json with and without --json-schema ==")
    print("without a schema, `result` is prose:")
    print("   ", WITHOUT_SCHEMA["result"])
    print("   -> a script cannot reliably turn that into inline comments on specific lines")
    print("with --json-schema, `structured_output` is parseable data:")
    comments = []
    for f in WITH_SCHEMA["structured_output"]["findings"]:
        problems = validate(f)
        print(f"    {f['file']}:{f['line']} [{f['severity']}] valid={not problems}")
        comments.append({"path": f["file"], "line": f["line"],
                         "body": f"**{f['severity'].upper()}**: {f['issue']}\nSuggested fix: {f['suggested_fix']}"})
    print("inline PR comments ready to post:")
    print(json.dumps(comments, indent=2))
    bad = {"file": "x.py", "line": 3, "severity": "scary", "category": "bug", "issue": "?", "suggested_fix": "?"}
    print("\nvalidator on a bad finding:", validate(bad))
    print("(schema output removes JSON syntax errors; semantic mistakes still need your own checks)")


# ---------------------------------------------------------------------------
PRIOR = [
    {"file": "auth.py", "pattern": "non_constant_time_compare", "status": "open"},
    {"file": "payments.py", "pattern": "bare_except", "status": "addressed"},
]
CURRENT = [("auth.py", "non_constant_time_compare"), ("payments.py", "bare_except"), ("orders.py", "missing_null_check")]


def review_run(prior_in_context):
    """SIMULATED model behavior for the second run, after new commits."""
    if not prior_in_context:
        return [{"file": f, "pattern": p, "kind": "new"} for f, p in CURRENT]  # re-reports everything
    known = {(x["file"], x["pattern"]): x["status"] for x in PRIOR}
    out = []
    for f, p in CURRENT:
        status = known.get((f, p))
        if status == "addressed":
            continue  # already dealt with: do not raise it again
        out.append({"file": f, "pattern": p, "kind": "still_open" if status == "open" else "new"})
    return out


def demo_rerun():
    print("\n== Re-running a review after new commits ==")
    for label, flag in (("WITHOUT prior findings in context", False), ("WITH prior findings + 'only new or still-unaddressed'", True)):
        out = review_run(flag)
        print(f"{label}: {len(out)} comment(s)")
        for o in out:
            print(f"    {o['file']} {o['pattern']} ({o['kind']})")
    print("The first run re-posts a finding the developer already addressed and duplicates an open thread.")
    print("Prompt line to add:  'Prior findings are in <prior>. Report only NEW or STILL-UNADDRESSED issues.'")


def demo_independent():
    print("\n== Why a separate review session ==")
    code_issues = ["eval() on user input", "no timeout on HTTP call", "off-by-one in pagination"]
    rationale = {"eval() on user input": "I used eval for speed; the input is trusted"}  # remembered by the generator
    same = [i for i in code_issues if i not in rationale]  # SIMULATION of anchoring on its own reasoning
    fresh = list(code_issues)
    print(f"same session that wrote the code finds {len(same)}/{len(code_issues)}: {same}")
    print(f"independent instance (no generator reasoning) finds {len(fresh)}/{len(code_issues)}")
    print("A self-review instruction or extended thinking does not remove the generator's context.")
    print("In CI: run the review as its own `claude -p` invocation, not as a follow-up in the generating session.")


def demo_tests():
    print("\n== Test generation without duplicates ==")
    existing = {"empty cart total", "single item total", "discount applied"}
    proposed = ["empty cart total", "single item total", "discount applied", "negative quantity rejected", "currency rounding"]
    print(f"proposed with NO existing tests in context: {len(proposed)} scenarios, "
          f"{len([p for p in proposed if p in existing])} duplicate(s)")
    new = [p for p in proposed if p not in existing]
    print(f"with the existing test file in context: {len(new)} new scenario(s): {new}")
    print("Also document testing standards, fixtures and what makes a test valuable in CLAUDE.md,")
    print("so CI-invoked Claude Code follows them and produces fewer low-value tests.")


FILES = {
    "review_schema.json": json.dumps(SCHEMA, indent=2) + "\n",
    "ci_review.sh": """#!/usr/bin/env bash
set -euo pipefail
# -p = non-interactive. --json-schema puts schema-valid findings in .structured_output
PRIOR="$(cat prior_findings.json 2>/dev/null || echo '[]')"
claude -p "Review this pull request. Prior findings: $PRIOR. Report only NEW or STILL-UNADDRESSED issues." \\
  --output-format json \\
  --json-schema "$(cat review_schema.json)" \\
  --allowedTools "Read,Grep,Glob" \\
  --max-turns 10 > review.json
jq '.structured_output.findings' review.json
""",
    ".github/workflows/claude-review.yml": """name: Claude Review
on:
  pull_request:
    types: [opened, synchronize]
permissions:
  contents: read
  pull-requests: write
jobs:
  review:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: anthropics/claude-code-action@v1
        with:
          anthropic_api_key: ${{ secrets.ANTHROPIC_API_KEY }}
          prompt: "Review this pull request. Report only new or still-unaddressed issues."
          claude_args: "--max-turns 10"
""",
    "CLAUDE_md_testing_snippet.md": """## Testing standards (for CI-invoked Claude Code)
- Use the shared fixtures in tests/fixtures; do not create ad-hoc test data.
- A valuable test covers a behavior, an edge case or a past bug. Skip tests that only restate the code.
- Do not propose scenarios already covered by existing tests in the same file.
""",
}


def export(dest):
    dest = Path(dest)
    for rel, content in FILES.items():
        path = dest / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    print(f"Wrote {len(FILES)} files under {dest}/")
    print("Adapt before use: the action's input names come from third-party guides, so check the action's README;")
    print("CI needs a credential (an API key secret, or Bedrock/Vertex). I have not verified subscription login in CI.")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "all"
    if mode == "export":
        export(sys.argv[2] if len(sys.argv) > 2 else "sample_ci")
        sys.exit(0)
    if mode in ("all", "hang"):
        demo_hang()
    if mode in ("all", "schema"):
        demo_schema()
    if mode in ("all", "rerun"):
        demo_rerun()
    if mode in ("all", "independent"):
        demo_independent()
    if mode in ("all", "tests"):
        demo_tests()