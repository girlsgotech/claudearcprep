"""
Task 4.1  Design prompts with explicit criteria to improve precision / reduce false positives
Scenario  5 (Claude Code for CI): automated PR review that developers must trust
RUNS: mock (pure Python, no API call needed; optional live call at the bottom)

What this file shows
  1. Vague / "be conservative" prompts (WRONG, exam distractors) vs explicit categorical criteria.
  2. Why confidence filtering does not fix false positives (data demo).
  3. Disabling high false-positive categories to restore developer trust.
"""
from collections import OrderedDict

# ---------------------------------------------------------------- 1. PROMPTS
# WRONG (exam distractor): vague instruction, no definition of what to report.
VAGUE_PROMPT = "Review this code. Check that comments are accurate and the code is good."

# WRONG (exam distractor): general instructions that sound careful but define nothing.
# EXAM: "be conservative" / "only report high-confidence findings" do NOT improve precision.
CONSERVATIVE_PROMPT = (
    "Review this code. Be conservative and only report findings you are highly confident about."
)

# RIGHT: specific categorical criteria (report vs skip) + severity with concrete code examples.
CRITERIA = OrderedDict(
    bug=("REPORT", "logic errors that produce wrong results or crashes (off-by-one, null deref, wrong operator)"),
    security=("REPORT", "injection, hardcoded secrets, missing auth checks, unsafe deserialization"),
    comment_accuracy=("REPORT", "ONLY when a comment's claimed behavior contradicts what the code actually does"),
    style=("SKIP", "naming, formatting, import order, minor style preferences"),
    local_pattern=("SKIP", "patterns that match existing conventions elsewhere in this repo"),
)

SEVERITY = """\
Severity (use exactly these levels):
- critical: exploitable or data-corrupting.   e.g. query = f"SELECT * FROM users WHERE id = {user_id}"
- high:     wrong result in normal use.       e.g. `for i in range(len(xs) - 1)` skips the last item
- medium:   wrong result in an edge case.     e.g. `total / count` when count can be 0
- low:      correct but fragile.              e.g. bare `except:` that hides the real error
"""


def build_prompt(disabled=frozenset()):
    """Build the review prompt. Categories in `disabled` are moved to the SKIP list."""
    report, skip = [], []
    for cat, (mode, desc) in CRITERIA.items():
        (skip if (mode == "SKIP" or cat in disabled) else report).append(f"- {cat}: {desc}")
    return (
        "You review pull requests. Output one finding per issue: location, category, severity, fix.\n\n"
        "REPORT only these categories:\n" + "\n".join(report) + "\n\n"
        "DO NOT report these categories:\n" + "\n".join(skip) + "\n\n" + SEVERITY
    )


# ---------------------------------------------------------------- 2. DATA
# (category, model_confidence, dismissed_by_developer)  dismissed=True means false positive
FINDINGS = [
    ("bug", 0.92, False), ("bug", 0.85, False), ("bug", 0.70, False), ("bug", 0.88, True),
    ("security", 0.95, False), ("security", 0.90, False), ("security", 0.60, False),
    ("style", 0.90, True), ("style", 0.85, True), ("style", 0.95, True),
    ("style", 0.80, False), ("style", 0.88, True),
    ("comment_accuracy", 0.90, True), ("comment_accuracy", 0.85, True),
    ("comment_accuracy", 0.82, False), ("comment_accuracy", 0.91, True),
    ("local_pattern", 0.87, True), ("local_pattern", 0.93, True), ("local_pattern", 0.55, False),
]


def fp_rate_by_category(findings):
    stats = OrderedDict()
    for cat, _conf, dismissed in findings:
        total, dis = stats.get(cat, (0, 0))
        stats[cat] = (total + 1, dis + int(dismissed))
    return stats


def main():
    print("== 1. Dismissal (false-positive) rate per category ==")
    for cat, (total, dis) in fp_rate_by_category(FINDINGS).items():
        print(f"{cat:<18}{total:>2} findings {dis:>2} dismissed {dis / total:>4.0%}")

    # EXAM: confidence filtering is the WRONG fix. The model is confidently wrong on false positives.
    kept = [f for f in FINDINGS if f[1] >= 0.8]
    fp_kept = sum(f[2] for f in kept)
    real_lost = sum(1 for f in FINDINGS if f[1] < 0.8 and not f[2])
    print("\n== 2. WRONG: filter by confidence >= 0.8 ==")
    print(f"kept {len(kept)} of {len(FINDINGS)}; real issues lost: {real_lost}; "
          f"false positives still shown: {fp_kept} ({fp_kept / len(kept):.0%} of what developers see)")

    # EXAM: temporarily disable the high false-positive categories, improve their prompts, re-enable later.
    threshold = 0.5
    stats = fp_rate_by_category(FINDINGS)
    disabled = {c for c, (t, d) in stats.items() if d / t > threshold}
    remaining = [f for f in FINDINGS if f[0] not in disabled]
    fp_remaining = sum(f[2] for f in remaining)
    print("\n== 3. RIGHT: disable categories with dismissal rate > 50% ==")
    print(f"disabled: {sorted(disabled)}")
    print(f"remaining {len(remaining)} findings, {fp_remaining} dismissed ({fp_remaining / len(remaining):.0%})")

    print("\n== Final prompt (explicit criteria, noisy categories disabled) ==")
    print(build_prompt(disabled))


# ---------------------------------------------------------------- OPTIONAL LIVE CALL
def live_review(diff: str):
    """Only runs with an API key. Same prompt, real model."""
    import anthropic
    client = anthropic.Anthropic()
    resp = client.messages.create(
        model="claude-sonnet-5-5", max_tokens=1000,
        system=build_prompt(), messages=[{"role": "user", "content": diff}],
    )
    return resp.content[0].text


if __name__ == "__main__":
    main()