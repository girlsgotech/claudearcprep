# d1_agentic/d1_6_decomposition.py
"""
EXAM: Task 1.6 - Design task decomposition strategies for complex workflows
SCENARIOS: 5 - Claude Code for CI (large PR review, sample Q12), 4 - Developer Productivity
           (legacy codebase), 1 - Customer Support (multi-concern request, from Task 1.4)
RUNS: mock (no API key). The "model" is SIMULATED so results are deterministic.

What the exam tests:
  * Prompt chaining (fixed sequential pipeline) for PREDICTABLE multi-aspect work, e.g.
    a big code review = per-file local passes, then ONE cross-file integration pass.
    A single pass over many files suffers attention dilution (sample Q12, answer A).
  * Dynamic adaptive decomposition for OPEN-ENDED work: map the structure, find the
    high-impact areas, build a prioritized plan, and adapt it as dependencies appear.
  * Multi-concern requests: split into distinct items, investigate each in parallel
    with shared context, then synthesize ONE unified resolution.

Run from the project root:
    python -m d1_agentic.d1_6_decomposition            # all four demos
    python -m d1_agentic.d1_6_decomposition single     # WRONG: one pass over every file
    python -m d1_agentic.d1_6_decomposition chain      # CORRECT: per-file + integration
    python -m d1_agentic.d1_6_decomposition dynamic    # open-ended legacy-code plan
    python -m d1_agentic.d1_6_decomposition multi      # multi-concern customer request
"""
import sys
from concurrent.futures import ThreadPoolExecutor

# A small stand-in for the PR in sample Q12 (the real one had 14 files, stock tracking module).
# "local" = issues visible inside one file. "exports"/"uses" = the cross-file contract.
FILES = {
    "prices.py":    {"local": ["get_price divides by volume without a zero check"],
                     "exports": {"get_price": "dict"}, "uses": []},
    "portfolio.py": {"local": [], "exports": {"total_value": "float"},
                     "uses": [("prices.get_price", "float")]},  # expects float, gets dict
    "alerts.py":    {"local": ["bare except swallows errors"], "exports": {}, "uses": []},
    "orders.py":    {"local": ["bare except swallows errors"], "exports": {}, "uses": []},
    "reports.py":   {"local": ["off-by-one in date range"], "exports": {},
                     "uses": [("portfolio.total_value", "float")]},
    "cache.py":     {"local": [], "exports": {}, "uses": []},
}


def show(title, lines):
    print(f"\n== {title} ==")
    for line in lines:
        print("  -", line)


# ---------------------------------------------------------------------------
# WRONG (exam distractor A/C/D context): everything in ONE pass
# ---------------------------------------------------------------------------
def single_pass_review(files, depth=3):
    """SIMULATES attention dilution (sample Q12): detailed feedback for the first few
    files, superficial for the rest, so identical code gets different verdicts."""
    findings = []
    for i, (name, f) in enumerate(files.items()):
        if i < depth:
            findings += [f"{name}: {issue}" for issue in f["local"]]
        else:
            findings.append(f"{name}: looks fine")  # superficial: real bugs missed
    return findings


# ---------------------------------------------------------------------------
# CORRECT (sample Q12, answer A): prompt chain = N focused passes + 1 integration pass
# ---------------------------------------------------------------------------
def per_file_pass(name, f):
    """Pass 1..N. Each call sees ONE file, so depth is the same for every file."""
    return [f"{name}: {issue}" for issue in f["local"]]


def integration_pass(summaries):
    """Final pass. EXAM: it receives compact CONTRACT summaries, not all source files,
    and looks only at cross-file data flow."""
    problems = []
    for name, s in summaries.items():
        for target, expected in s["uses"]:
            module, fn = target.split(".")
            actual = summaries.get(module + ".py", {}).get("exports", {}).get(fn)
            if actual != expected:
                problems.append(f"{name} expects {target} -> {expected}, but it returns {actual}")
    return problems


def review_chain(files):
    local = []
    for name, f in files.items():  # each file could also run in parallel
        local += per_file_pass(name, f)
    summaries = {n: {"exports": f["exports"], "uses": f["uses"]} for n, f in files.items()}
    return local, integration_pass(summaries)


# ---------------------------------------------------------------------------
# Dynamic decomposition: "add comprehensive tests to a legacy codebase"
# ---------------------------------------------------------------------------
def dynamic_test_plan():
    print("\n== Dynamic decomposition: add tests to a legacy codebase ==")
    # A fixed pipeline cannot do this: the hidden dependency is only discovered mid-task.
    modules = {"billing": {"risk": 9, "hidden_dep": "payment-gateway fake"},
               "auth": {"risk": 8},
               "reports": {"risk": 3}}
    print("[map] modules found:", ", ".join(modules))
    queue = sorted(modules, key=lambda m: -modules[m]["risk"])  # high-impact areas first
    print("[prioritize] order by risk:", queue)
    while queue:
        task = queue.pop(0)
        dep = modules.get(task, {}).get("hidden_dep")
        if dep:
            print(f"[discover] '{task}' needs a {dep} first -> plan adapted")
            modules[task]["hidden_dep"] = None
            queue[0:0] = [dep, task]  # insert the dependency, then retry the task
            continue
        print(f"[do] {task}")


# ---------------------------------------------------------------------------
# Multi-concern request: split, investigate in parallel with shared context, synthesize
# ---------------------------------------------------------------------------
REQUEST = "I was charged twice on order 12399, my address is wrong on order 12400, and please cancel my subscription."
ITEMS = [("duplicate charge", "order 12399"), ("wrong address", "order 12400"),
         ("cancel subscription", "account")]
FINDINGS = {"duplicate charge": "confirmed; $59.90 refund is eligible",
            "wrong address": "order has not shipped; address can be updated",
            "cancel subscription": "can be cancelled at period end"}


def investigate(item, shared):
    name, ref = item
    # EXAM: shared context (verified customer) is passed explicitly to every investigation.
    return {"item": name, "ref": ref, "customer": shared["customer_id"], "finding": FINDINGS[name]}


def multi_concern():
    print("\n== Multi-concern request ==")
    print("REQUEST:", REQUEST)
    shared = {"customer_id": "C-1001"}  # verified once, reused by every item
    with ThreadPoolExecutor() as pool:  # independent items run in parallel
        results = list(pool.map(lambda it: investigate(it, shared), ITEMS))
    print("ITEMS investigated:")
    for r in results:
        print(f"  - {r['item']} ({r['ref']}, customer {r['customer']}): {r['finding']}")
    # EXAM: synthesize ONE unified resolution, not three disconnected replies.
    parts = [f"{r['item']}: {r['finding']}" for r in results]
    print("UNIFIED REPLY: All three requests are covered. " + "; ".join(parts) + ".")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "all"
    if mode in ("all", "single"):
        show("WRONG - single pass over all files", single_pass_review(FILES))
    if mode in ("all", "chain"):
        local, cross = review_chain(FILES)
        show("Pass 1..N - per-file local analysis", local)
        show("Final pass - cross-file integration", cross)
    if mode in ("all", "dynamic"):
        dynamic_test_plan()
    if mode in ("all", "multi"):
        multi_concern()