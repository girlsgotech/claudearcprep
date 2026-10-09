"""
Task 4.6  Design multi-instance and multi-pass review architectures
Scenario  5 (Claude Code for CI). Mirrors sample Q12 (14-file PR, inconsistent single-pass review)
RUNS: mock (real message shapes, scripted model answers; optional live call at the bottom)

What this file shows
  1. Self-review vs an independent instance: the generator's reasoning stays in context.
  2. WRONG: one pass over 14 files (attention dilution, inconsistent depth, missed bugs).
  3. RIGHT: per-file local passes + one cross-file integration pass.
  4. Per-finding confidence to route review attention (route, do not drop).
  5. WRONG: "run 3 times, keep issues found in 2 of 3" suppresses real bugs.
"""
from collections import Counter

MODEL = "claude-sonnet-5-5"

# ------------------------------------------------- 1. SELF-REVIEW vs INDEPENDENT
CODE = "def apply_discount(price, pct): return price - price * pct / 100"
GENERATION_TRANSCRIPT = [
    {"role": "user", "content": "Write apply_discount(price, pct)."},
    {"role": "assistant", "content": "Reasoning: pct is always 0-100, so no validation is needed.\n" + CODE},
]


def self_review_messages():
    # WRONG (exam distractor): same session. The generator's reasoning ("pct is always
    # 0-100") is still in context, so the model is unlikely to question its own decision.
    return GENERATION_TRANSCRIPT + [{"role": "user", "content": "Review the code above for bugs."}]


def independent_review_messages(code):
    # EXAM: a second instance gets ONLY the code, never the generator's reasoning.
    # This beats self-review instructions and extended thinking in the same session.
    return [{"role": "user", "content": f"Review this function for bugs.\n<code>\n{code}\n</code>"}]


def carries_reasoning(messages):
    return any("Reasoning:" in m["content"] for m in messages)


SCRIPTED_ANSWER = {
    "self": "No issues found. pct is always 0-100.",
    "independent": "medium | pct is not validated: pct=150 gives a negative price | fix: reject pct outside 0-100",
}

# ------------------------------------------------- 2. THE 14-FILE PR
FILES = ["ledger.py", "tickers.py", "alerts.py", "prices.py", "report.py", "portfolio.py", "orders.py",
         "fees.py", "cache.py", "config.py", "utils.py", "models.py", "export.py", "api.py"]
LOCAL_BUGS = {
    "ledger.py": "off-by-one: range(len(xs) - 1) skips the last row",
    "tickers.py": "None dereference when the symbol is unknown",
    "alerts.py": "wrong operator: > should be >=",
}
# Cross-file bug: invisible when reading either file alone.
INTERFACES = {
    "ledger.py": {"returns": "dollars"},
    "prices.py": {"returns": "cents"},
    "report.py": {"expects": "dollars"},
}
EDGES = [("prices.py", "report.py"), ("ledger.py", "report.py")]   # (producer, consumer)

# Scripted single-pass result, mirroring the failure in Q12.
SINGLE_PASS_COMMENTS = {"ledger.py": 6, "tickers.py": 5, "alerts.py": 0, "prices.py": 4, "report.py": 0,
                        "portfolio.py": 3, "orders.py": 0, "fees.py": 1, "cache.py": 0, "config.py": 0,
                        "utils.py": 1, "models.py": 0, "export.py": 0, "api.py": 1}
SINGLE_PASS_FOUND = {"ledger.py"}
SINGLE_PASS_CONTRADICTIONS = 1   # same pattern flagged in one file, approved in another


# ------------------------------------------------- 3. PER-FILE + INTEGRATION PASSES
def per_file_prompt(filename):
    # EXAM: same template for every file, one file per pass: consistent depth, no dilution.
    return (f"Review ONLY {filename} for local issues (logic, null handling, operators). "
            "End with: INTERFACE: what this file returns / expects.")


def per_file_pass(filename):
    return [(filename, LOCAL_BUGS[filename])] if filename in LOCAL_BUGS else []   # scripted


def integration_pass(interfaces, edges):
    # EXAM: a SEPARATE pass for cross-file data flow. It receives interface summaries
    # from the per-file passes, not all 14 full files.
    found = []
    for producer, consumer in edges:
        r, e = interfaces[producer]["returns"], interfaces[consumer]["expects"]
        if r != e:
            found.append(f"{producer} -> {consumer}: unit mismatch, {producer} returns {r}, {consumer} expects {e}")
    return found


# ------------------------------------------------- 4. CONFIDENCE ROUTING
FINDINGS = [  # (location, issue, self-reported confidence)
    ("ledger.py", "off-by-one", 0.95),
    ("tickers.py", "None dereference", 0.90),
    ("alerts.py", "wrong operator", 0.60),
    ("prices.py -> report.py", "unit mismatch", 0.70),
]
THRESHOLD = 0.8   # EXAM: calibrate on a labeled validation set (task 5.5), do not guess


def route(findings, threshold):
    post = [f[0] for f in findings if f[2] >= threshold]
    review = [f[0] for f in findings if f[2] < threshold]
    return post, review   # EXAM: low confidence goes to review, it is NOT dropped


# ------------------------------------------------- 5. CONSENSUS VOTING (WRONG)
RUNS = [{"ledger", "cross"}, {"ledger", "tickers"}, {"ledger", "alerts"}]   # 3 full-PR runs
REAL_BUGS = {"ledger", "tickers", "alerts", "cross"}


def main():
    print("== 1. Self-review vs independent instance ==")
    s, i = self_review_messages(), independent_review_messages(CODE)
    print(f"self-review: messages={len(s)}, carries generator reasoning: {carries_reasoning(s)}")
    print(f"  scripted answer: {SCRIPTED_ANSWER['self']}")
    print(f"independent: messages={len(i)}, carries generator reasoning: {carries_reasoning(i)}")
    print(f"  scripted answer: {SCRIPTED_ANSWER['independent']}")

    print("\n== 2. WRONG: single pass over 14 files (scripted) ==")
    counts = SINGLE_PASS_COMMENTS.values()
    zero = sum(c == 0 for c in counts)
    print(f"comments per file: min {min(counts)}, max {max(counts)}, files with zero comments: {zero} of {len(FILES)}")
    print(f"local bugs found: {len(SINGLE_PASS_FOUND & set(LOCAL_BUGS))} of {len(LOCAL_BUGS)}, "
          f"cross-file bugs found: 0 of 1, contradictory verdicts: {SINGLE_PASS_CONTRADICTIONS}")

    print("\n== 3. RIGHT: per-file passes + one integration pass ==")
    local = [f for name in FILES for f in per_file_pass(name)]
    print(f"per-file passes: {len(FILES)}, each sees 1 file with the same prompt template")
    print(f"local bugs found: {len(local)} of {len(LOCAL_BUGS)}")
    print(f"integration input: {len(INTERFACES)} interface summaries, not {len(FILES)} full files")
    for finding in integration_pass(INTERFACES, EDGES):
        print(f"cross-file bug found: {finding}")

    print("\n== 4. Per-finding confidence routes review attention ==")
    post, review = route(FINDINGS, THRESHOLD)
    print(f"post as PR comment (>= {THRESHOLD}): {', '.join(post)}")
    print(f"send to human review (< {THRESHOLD}): {', '.join(review)}")

    print("\n== 5. WRONG: keep only issues found in >= 2 of 3 runs ==")
    tally = Counter(x for run in RUNS for x in run)
    flagged = sorted(k for k, v in tally.items() if v >= 2)
    lost = sorted(REAL_BUGS - set(flagged))
    print(f"flagged: {flagged}")
    print(f"real bugs lost: {len(lost)} of {len(REAL_BUGS)} {lost}")


# ------------------------------------------------- OPTIONAL LIVE CALL
def live_review(files: dict[str, str]):
    """Needs an API key. Every call starts a fresh message list = an independent instance."""
    import anthropic
    client = anthropic.Anthropic()

    def ask(system, content):
        r = client.messages.create(model=MODEL, max_tokens=1000, system=system,
                                   messages=[{"role": "user", "content": content}])
        return r.content[0].text

    local = {name: ask(per_file_prompt(name), code) for name, code in files.items()}
    summaries = "\n".join(f"## {name}\n{text}" for name, text in local.items())
    integration = ask("Find cross-file issues only: data flow, units, contracts between files. "
                      "Give each finding a confidence from 0 to 1.", summaries)
    return local, integration


if __name__ == "__main__":
    main()