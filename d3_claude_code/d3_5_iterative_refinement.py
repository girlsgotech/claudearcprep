# d3_claude_code/d3_5_iterative_refinement.py
"""
EXAM: Task 3.5 - Apply iterative refinement techniques for progressive improvement
SCENARIO: 2 - Code Generation with Claude Code (refactoring, migration scripts, new features)
RUNS: mock (no API key). The code under test is real Python. Only the "Claude fixes it" step
      is represented by a hand-written second version.

What the exam tests:
  * CONCRETE INPUT/OUTPUT EXAMPLES (2-3) are the most effective way to communicate an expected
    transformation when prose descriptions get interpreted inconsistently.
  * TEST-DRIVEN ITERATION: write the test suite first (expected behavior, edge cases,
    performance), then iterate by sharing the test FAILURES.
  * INTERVIEW PATTERN: have Claude ask you questions BEFORE implementing, to surface
    considerations you did not anticipate (cache invalidation, failure modes) in unfamiliar areas.
  * Fixing edge cases (null values in a migration script): give specific test cases with
    example input and expected output.
  * Issues that INTERACT go in ONE detailed message; INDEPENDENT issues can be fixed one at a time.

Run from the project root:
    python -m d3_claude_code.d3_5_iterative_refinement             # all demos
    python -m d3_claude_code.d3_5_iterative_refinement examples    # examples beat prose
    python -m d3_claude_code.d3_5_iterative_refinement tdd         # tests first, share failures
    python -m d3_claude_code.d3_5_iterative_refinement interview   # the interview pattern
    python -m d3_claude_code.d3_5_iterative_refinement batching    # one message or many?
"""
import re
import sys
import time

# ---------------------------------------------------------------------------
# Demo 1: prose gets interpreted several ways; 2-3 concrete examples pin it down
# ---------------------------------------------------------------------------
def digits_only(s):
    return re.sub(r"\D", "", s)


def keep_plus(s):
    return re.sub(r"[^\d+]", "", s)


def e164_v1(s):
    d = re.sub(r"[^\d+]", "", s)
    if d.startswith("+"):
        return d
    if d.startswith("0"):
        return "+49" + d[1:]
    return "+" + d


CANDIDATES = {"strip to digits": digits_only, "keep leading +": keep_plus, "E.164 with +49 default": e164_v1}
EXAMPLES = [("+49 351 123456", "+49351123456"), ("0351 123456", "+49351123456")]


def demo_examples():
    print("== Prose vs concrete examples ==")
    print("Prompt: 'clean up the phone numbers'  (vague; each candidate below is a reasonable reading)")
    for n in range(len(EXAMPLES) + 1):
        shown = EXAMPLES[:n]
        alive = [name for name, fn in CANDIDATES.items() if all(fn(i) == o for i, o in shown)]
        label = "no examples" if n == 0 else f"{n} example(s)"
        print(f"  {label:14} -> {len(alive)} interpretation(s) still fit: {alive}")
    print("Examples given:")
    for i, o in EXAMPLES:
        print(f"    {i!r:20} -> {o!r}")
    print("Two examples remove the ambiguity that a paragraph of prose left open.")


# ---------------------------------------------------------------------------
# Demo 2: write the tests first, then iterate by sharing failures
# ---------------------------------------------------------------------------
TESTS = [  # expected behavior AND edge cases, written BEFORE the implementation
    ("german national", "0351 123456", "+49351123456"),
    ("already international", "+49 351 123456", "+49351123456"),
    ("00 prefix", "0049 351 123456", "+49351123456"),
    ("null input", None, None),
    ("empty string", "", None),
]


def e164_v2(s):
    if not s:
        return None
    d = re.sub(r"[^\d+]", "", s)
    if d.startswith("+"):
        return d
    if d.startswith("00"):
        return "+" + d[2:]
    if d.startswith("0"):
        return "+49" + d[1:]
    return "+" + d


def run_tests(fn):
    failures = []
    for name, given, expected in TESTS:
        try:
            got = fn(given)
        except Exception as e:  # share what actually happened, not a guess
            got = type(e).__name__
        if got != expected:
            failures.append(f"FAIL {name}: input={given!r} expected={expected!r} got={got!r}")
    start = time.perf_counter()  # performance requirement: 20,000 numbers in under 2 seconds
    for _ in range(20000):
        fn("0351 123456")
    if time.perf_counter() - start > 2.0:
        failures.append("FAIL performance: 20,000 calls took more than 2.0s")
    return failures


def demo_tdd():
    print("\n== Test-driven iteration ==")
    for label, fn in (("round 1: first implementation", e164_v1), ("round 2: after sharing the failures", e164_v2)):
        failures = run_tests(fn)
        print(f"{label}: {len(TESTS) + 1 - len(failures)} of {len(TESTS) + 1} checks pass")
        for f in failures:
            print("   " + f)
    print("\nPaste the FAIL lines (input, expected, actual) back to Claude: specific cases beat 'it breaks on some numbers'.")
    print("Edge cases like null values in a migration script are fixed the same way: add the case, share the failure.")


# ---------------------------------------------------------------------------
# Demo 3: the interview pattern
# ---------------------------------------------------------------------------
INTERVIEW_PROMPT = ("I want to add a cache in front of order lookups, and I haven't built one before. "
                    "Before you write any code, interview me: ask about invalidation, failure modes and "
                    "anything else I may not have considered. Ask your questions first, then propose a design.")
SURFACED = [
    "When is a cached order wrong? (invalidation: who updates it, and how fast must readers see it?)",
    "What if the cache is down? (fail open to the database, or fail the request?)",
    "What if 500 requests miss at once? (stampede protection)",
    "How stale can an order be before a customer notices? (TTL)",
    "Several app instances: is one shared cache or one per instance acceptable? (consistency)",
]


def demo_interview():
    print("\n== The interview pattern (unfamiliar domain) ==")
    print("Prompt:\n  " + INTERVIEW_PROMPT)
    print("\nQuestions it surfaces BEFORE any code exists:")
    for q in SURFACED:
        print("  - " + q)
    print("Use it where you cannot yet list the requirements yourself; skip it for a one-line fix.")


# ---------------------------------------------------------------------------
# Demo 4: interacting issues in ONE message, independent issues one at a time
# ---------------------------------------------------------------------------
ISSUES = {
    1: "Dates in DD/MM/YYYY are parsed as MM/DD/YYYY",
    2: "Monthly report totals are wrong for those dates",
    3: "Typo in the CSV header 'recieved'",
    4: "Parsed dates shift by one day in UTC conversion",
}
INTERACTS = [(1, 2), (1, 4)]  # fixing one changes what the other should do


def groups(issues, links):
    parent = {i: i for i in issues}

    def find(x):
        while parent[x] != x:
            x = parent[x]
        return x

    for a, b in links:
        parent[find(a)] = find(b)
    out = {}
    for i in issues:
        out.setdefault(find(i), []).append(i)
    return list(out.values())


def demo_batching():
    print("\n== One message or several? ==")
    for g in groups(ISSUES, INTERACTS):
        if len(g) > 1:
            print(f"issues {g} INTERACT -> ONE detailed message (a fix to one changes what the others need):")
            for i in g:
                print(f"    {i}. {ISSUES[i]}")
        else:
            print(f"issue {g[0]} is INDEPENDENT -> fix on its own, sequentially: {ISSUES[g[0]]}")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "all"
    if mode in ("all", "examples"):
        demo_examples()
    if mode in ("all", "tdd"):
        demo_tdd()
    if mode in ("all", "interview"):
        demo_interview()
    if mode in ("all", "batching"):
        demo_batching()