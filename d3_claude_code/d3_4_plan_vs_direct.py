# d3_claude_code/d3_4_plan_vs_direct.py
"""
EXAM: Task 3.4 - Determine when to use plan mode vs direct execution
SCENARIO: 2 - Code Generation with Claude Code (sample Q5: monolith to microservices)
RUNS: mock (no API key). A transparent rubric, not a Claude feature: it exists so you can see
      WHICH signals push a task toward plan mode, in the same way the exam reasons about it.

What the exam tests:
  * PLAN MODE: complex tasks with large-scale changes, multiple valid approaches, architectural
    decisions, or multi-file modifications. It allows safe, read-only exploration and design
    BEFORE committing to changes, which prevents costly rework.
  * DIRECT EXECUTION: simple, well-scoped changes (one validation check in one function, a
    single-file bug fix with a clear stack trace).
  * The Explore subagent isolates verbose discovery output and returns a SUMMARY, so a
    multi-phase task does not exhaust the main context window.
  * COMBINE them: plan mode for investigation, then direct execution of the planned approach
    (for example, plan a library migration, then carry it out).

How you enter plan mode (per the docs; the Shift+Tab cycle order varies by version, so watch
the footer indicator):  Shift+Tab, `claude --permission-mode plan`, or prefix a prompt with /plan.
Plan mode reads files and writes a plan but does not edit your source. Approving the plan exits
plan mode and starts editing.

Run from the project root:
    python -m d3_claude_code.d3_4_plan_vs_direct            # all demos
    python -m d3_claude_code.d3_4_plan_vs_direct classify   # score the exam's example tasks
    python -m d3_claude_code.d3_4_plan_vs_direct q5         # sample Q5, option by option
    python -m d3_claude_code.d3_4_plan_vs_direct explore    # why the Explore subagent matters
    python -m d3_claude_code.d3_4_plan_vs_direct hybrid     # plan first, then execute
"""
import sys

PLAN_THRESHOLD = 3  # illustrative cut-off for THIS rubric, not an official number

TASKS = [
    {"task": "Restructure a monolith into microservices", "files": 40, "architectural": True, "approaches": 3, "scope_clear": False},
    {"task": "Library migration affecting 45+ files", "files": 45, "architectural": False, "approaches": 2, "scope_clear": False},
    {"task": "Pick between integration approaches (different infra)", "files": 3, "architectural": True, "approaches": 2, "scope_clear": True},
    {"task": "New feature, several valid implementations", "files": 6, "architectural": False, "approaches": 3, "scope_clear": False},
    {"task": "Single-file bug fix with a clear stack trace", "files": 1, "architectural": False, "approaches": 1, "scope_clear": True},
    {"task": "Add a date validation conditional to one function", "files": 1, "architectural": False, "approaches": 1, "scope_clear": True},
    {"task": "Rename one variable inside one file", "files": 1, "architectural": False, "approaches": 1, "scope_clear": True},
    {"task": "BORDERLINE: mechanical rename across 12 files", "files": 12, "architectural": False, "approaches": 1, "scope_clear": True},
]


def assess(t):
    """Each signal the exam names adds weight toward plan mode."""
    score, why = 0, []
    if t["files"] >= 10:
        score += 2
        why.append(f"{t['files']} files")
    elif t["files"] >= 2:
        score += 1
        why.append(f"{t['files']} files")
    if t["architectural"]:
        score += 3
        why.append("architectural decisions")
    if t["approaches"] > 1:
        score += 2
        why.append(f"{t['approaches']} valid approaches")
    if not t["scope_clear"]:
        score += 2
        why.append("scope not known yet")
    return score, why


def demo_classify():
    print("== Plan mode or direct execution? (illustrative rubric) ==")
    print(f"{'task':56}{'score':7}{'decision':26}signals")
    for t in TASKS:
        score, why = assess(t)
        if score >= PLAN_THRESHOLD:
            decision = "PLAN MODE"
            if t["files"] >= 10:
                decision += " -> then direct"
        else:
            decision = "DIRECT"
        print(f"{t['task']:56}{score:<7}{decision:26}{', '.join(why) or 'none: small and clear'}")
    print("\nThe borderline row is a judgment call: the exam uses clear cases, and your REASONING is what it checks.")


def demo_q5():
    print("\n== Sample Q5: monolith to microservices, dozens of files, service boundaries undecided ==")
    rows = [
        ("A", "Enter plan mode, explore dependencies, design, then change", "CORRECT: exactly the large, architectural, multi-approach case"),
        ("B", "Direct execution, let boundaries emerge incrementally", "risks costly rework when dependencies are found late"),
        ("C", "Direct execution with exhaustive upfront instructions", "assumes you already know the right structure without exploring"),
        ("D", "Start direct, switch to plan mode if complexity appears", "the complexity is already stated; it is not a surprise to wait for"),
    ]
    for letter, option, verdict in rows:
        print(f"  {letter}  {option:62}{verdict}")


PHASES = ["map the services", "trace data flows", "find shared libraries"]


def demo_explore():
    print("\n== Why the Explore subagent matters on multi-phase work ==")
    verbose, summary = 300, 12  # illustrative line counts, not measurements
    main = 0
    print("WITHOUT isolation: all discovery output lands in the main conversation")
    for p in PHASES:
        main += verbose
        print(f"  phase '{p}': +{verbose} lines  -> main context now ~{main} lines")
    iso = 0
    print("WITH the Explore subagent (read-only, separate context window): only a summary comes back")
    for p in PHASES:
        iso += summary
        print(f"  phase '{p}': +{summary} lines  -> main context now ~{iso} lines")
    print("The built-in Explore and Plan subagents have Write and Edit denied, so exploring stays safe too.")


def demo_hybrid():
    print("\n== Combining them: migrate a library across 45 files ==")
    steps = [
        ("1", "PLAN MODE", "read-only: find every usage, compare migration strategies, write the plan"),
        ("2", "YOU", "review the plan; refine it if the approach is wrong ('No, keep planning')"),
        ("3", "APPROVE", "approving exits plan mode and switches to an editing mode"),
        ("4", "DIRECT", "execute the approved plan file by file; the thinking is already done"),
    ]
    for n, who, what in steps:
        print(f"  {n}. {who:10}{what}")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "all"
    if mode in ("all", "classify"):
        demo_classify()
    if mode in ("all", "q5"):
        demo_q5()
    if mode in ("all", "explore"):
        demo_explore()
    if mode in ("all", "hybrid"):
        demo_hybrid()