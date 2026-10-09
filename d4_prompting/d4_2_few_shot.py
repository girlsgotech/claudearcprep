"""
Task 4.2  Apply few-shot prompting to improve output consistency and quality
Scenarios 5 (CI review) and 6 (structured extraction)
RUNS: mock (scripted outputs illustrate the effect; optional live call at the bottom)

What this file shows
  1. 2-4 targeted examples for ambiguous review cases: format + reasoning,
     including an ACCEPTABLE pattern next to genuine issues.
  2. Format consistency and false positives, instructions-only vs few-shot (scripted).
  3. Examples for varied document structures in extraction (null when absent).
"""
import json
import re

# ------------------------------------------------- 1. REVIEW EXAMPLES (CI)
# EXAM: each example shows WHY one action was chosen over a plausible alternative,
# and demonstrates the exact output format: location | severity | issue | fix.
REVIEW_EXAMPLES = [
    {
        "kind": "genuine",
        "code": 'db.py:18   query = f"SELECT * FROM users WHERE id = {uid}"',
        "reasoning": "User input is interpolated into SQL. Exploitable, so report it.",
        "output": "db.py:18 | critical | SQL built by string interpolation | fix: use a parameterized query",
    },
    {
        # EXAM: an ACCEPTABLE pattern next to genuine issues cuts false positives
        # while still letting the model generalize to patterns not listed.
        "kind": "acceptable",
        "code": 'cfg.py:7   try: port = cfg["port"]\n           except KeyError: port = 8080',
        "reasoning": "Optional key with a default. This is intentional, not a swallowed error. Do not report.",
        "output": "NO FINDING",
    },
    {
        "kind": "genuine",
        "code": 'sort.py:3  # returns items sorted ascending\n           return list(items)',
        "reasoning": "The comment claims sorting but the code does not sort. Claimed behavior contradicts code, so report.",
        "output": "sort.py:3 | medium | comment says sorted, code keeps input order | fix: sort or correct the comment",
    },
]


def build_review_prompt(examples):
    # EXAM: 2-4 targeted examples for ambiguous cases, not a pile of 5-8 generic ones.
    assert 2 <= len(examples) <= 4, "use 2-4 targeted examples"
    blocks = "\n".join(
        f"<example>\n<code>\n{e['code']}\n</code>\n"
        f"<reasoning>{e['reasoning']}</reasoning>\n<output>{e['output']}</output>\n</example>"
        for e in examples
    )
    return (
        "Review code. One line per issue: location | severity | issue | fix: <suggestion>.\n"
        "If the code is an acceptable pattern, answer exactly: NO FINDING.\n\n" + blocks
    )


# ------------------------------------------------- 2. SCRIPTED OUTPUTS
OUTPUT_RE = re.compile(
    r"^(NO FINDING|[\w./]+:\d+ \| (critical|high|medium|low) \| [^|]+ \| fix: .+)$"
)

# (kind of code reviewed, model output). Scripted to mirror the failure the guide describes.
WITHOUT_FEW_SHOT = [  # WRONG (exam distractor): instructions only
    ("genuine", "auth.py:12 | high | SQL built with f-string | fix: use a parameterized query"),
    ("genuine", "Line 40 of utils.py has a risky except block, maybe tighten it."),
    ("acceptable", "cfg.py:7 | medium | KeyError swallowed | fix: remove try/except"),
    ("acceptable", "Consider handling the missing key more explicitly."),
]
WITH_FEW_SHOT = [  # note utils.py:40 is a pattern NOT in the examples: generalization
    ("genuine", "auth.py:12 | high | SQL built with f-string | fix: use a parameterized query"),
    ("genuine", "utils.py:40 | high | bare except hides payment failure | fix: catch PaymentError and re-raise"),
    ("acceptable", "NO FINDING"),
    ("acceptable", "NO FINDING"),
]


def score(outputs):
    fmt_ok = sum(bool(OUTPUT_RE.match(o)) for _, o in outputs)
    acceptable = [o for kind, o in outputs if kind == "acceptable"]
    false_pos = sum(o != "NO FINDING" for o in acceptable)
    return fmt_ok, len(outputs), false_pos, len(acceptable)


# ------------------------------------------------- 3. EXTRACTION EXAMPLES
# EXAM: varied structures (inline citation vs bibliography vs nothing), informal
# measurements, and null when the source does not say. This reduces fabrication
# and empty/null extraction of fields that ARE present.
EXTRACTION_EXAMPLES = [
    {"doc": "Revenue rose roughly a dozen percent, according to Smith (2021).",
     "out": '{"measure": "revenue growth", "value_pct": 12, "source": "Smith", "year": 2021}'},
    {"doc": "Growth was strong across the sector [3].\n[3] Lee, J. Retail Outlook. 2020.",
     "out": '{"measure": "sector growth", "value_pct": null, "source": "Lee", "year": 2020}'},
    {"doc": "Margins improved.",
     "out": '{"measure": "margins", "value_pct": null, "source": null, "year": null}'},
]


def main():
    prompt = build_review_prompt(REVIEW_EXAMPLES)
    kinds = {e["kind"] for e in REVIEW_EXAMPLES}
    print("== 1. Few-shot review prompt ==")
    print(f"examples: {len(REVIEW_EXAMPLES)} (guide: 2-4 targeted examples)")
    print(f"includes acceptable-pattern example: {'acceptable' in kinds}")
    print(f"includes genuine-issue example: {'genuine' in kinds}")

    print("\n== 2. Scripted model outputs (illustration, not a live call) ==")
    for label, outs in (("instructions only", WITHOUT_FEW_SHOT), ("with few-shot", WITH_FEW_SHOT)):
        ok, n, fp, a = score(outs)
        print(f"{label:<18}: format ok {ok}/{n} ({ok / n:.0%}), false positives on acceptable code {fp}/{a}")

    parsed = [json.loads(e["out"]) for e in EXTRACTION_EXAMPLES]
    with_null = sum(any(v is None for v in d.values()) for d in parsed)
    print("\n== 3. Extraction examples for varied documents ==")
    print(f"examples: {len(parsed)}, valid JSON: True, showing null for absent info: {with_null}")


# ------------------------------------------------- OPTIONAL LIVE CALL
def live_review(code: str):
    """Needs an API key. Same few-shot prompt, real model."""
    import anthropic
    resp = anthropic.Anthropic().messages.create(
        model="claude-sonnet-5-5", max_tokens=500,
        system=build_review_prompt(REVIEW_EXAMPLES),
        messages=[{"role": "user", "content": code}],
    )
    return resp.content[0].text


if __name__ == "__main__":
    main()