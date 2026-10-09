"""
Task 4.4  Implement validation, retry, and feedback loops for extraction quality
Scenarios 6 (Structured Data Extraction) and 5 (CI review)
RUNS: mock (real Pydantic validation, scripted model outputs; optional live call at the bottom)

What this file shows
  1. Retry-with-error-feedback: document + failed extraction + SPECIFIC errors.
  2. Semantic validation: calculated_total vs stated_total, conflict_detected.
  3. Retry is useless when the information is absent from the source.
  4. detected_pattern on findings, to analyze dismissal patterns.
"""
import json
import re
from pydantic import BaseModel, ValidationError, field_validator, model_validator


# ------------------------------------------------- 1. SCHEMA + SEMANTIC CHECKS
class Invoice(BaseModel):
    vendor: str
    invoice_date: str
    line_items: list[float]
    stated_total: float | None          # what the document says
    calculated_total: float             # EXAM: extracted alongside stated_total
    conflict_detected: bool = False     # EXAM: flags inconsistent SOURCE data
    payment_terms_days: int             # required downstream

    @field_validator("invoice_date")
    @classmethod
    def date_format(cls, v):
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", v):
            raise ValueError(f"invoice_date {v!r} must be YYYY-MM-DD")  # format error: retry can fix
        return v

    @model_validator(mode="after")
    def totals(self):
        s = sum(self.line_items)
        if abs(s - self.calculated_total) > 0.01:
            raise ValueError(f"calculated_total {self.calculated_total:g} != sum(line_items) {s:g}")
        if (self.stated_total is not None and not self.conflict_detected
                and abs(self.calculated_total - self.stated_total) > 0.01):
            # EXAM: semantic error. Tool use + schema would NOT catch this.
            raise ValueError(
                f"calculated_total {self.calculated_total:g} != stated_total {self.stated_total:g}: "
                "re-read the source; if the source itself is inconsistent, set conflict_detected=true")
        return self


def fmt_err(e):
    text = e["msg"].removeprefix("Value error, ")
    return f"{e['loc'][0]}: {text}" if e["type"] == "missing" else text


def build_retry_prompt(doc, failed, errors):
    # EXAM: the follow-up includes the ORIGINAL document, the FAILED extraction,
    # and the SPECIFIC validation errors (not just "try again").
    return (
        "Your previous extraction failed validation. Fix ONLY the listed problems.\n"
        f"<document>\n{doc}\n</document>\n"
        f"<failed_extraction>\n{json.dumps(failed)}\n</failed_extraction>\n"
        "<validation_errors>\n" + "\n".join(f"- {e}" for e in errors) + "\n</validation_errors>"
    )


# ------------------------------------------------- 2. SCRIPTED MODEL
DOCS = {
    "A": "ACME Ltd. Invoice dated March 3rd 2024. Router 60, Support 40. Total due 100. Terms: 30 days.",
    "B": "BETA Corp. Dated 2024-05-01. Cable 30, Adapter 20. Total due 60. Terms: 45 days.",
    "C": "CORP Ltd. Dated 2024-06-09. Hosting 80. Total due 80. Terms: see master agreement (not attached).",
}


def rec(vendor, date, items, stated, calc, conflict, days=None):
    d = dict(vendor=vendor, invoice_date=date, line_items=items, stated_total=stated,
             calculated_total=calc, conflict_detected=conflict)
    if days is not None:
        d["payment_terms_days"] = days
    return d


SCRIPT = {  # (doc, attempt) -> model output
    ("A", 1): rec("ACME Ltd.", "March 3rd 2024", [60, 40], 100, 100, False, 30),  # format error
    ("A", 2): rec("ACME Ltd.", "2024-03-03", [60, 40], 100, 100, False, 30),      # fixed
    ("B", 1): rec("BETA Corp.", "2024-05-01", [30, 20], 60, 50, False, 45),       # totals disagree
    ("B", 2): rec("BETA Corp.", "2024-05-01", [30, 20], 60, 50, True, 45),        # flags the conflict
    ("C", 1): rec("CORP Ltd.", "2024-06-09", [80], 80, 80, False),                # field missing
    ("C", 2): rec("CORP Ltd.", "2024-06-09", [80], 80, 80, False),                # still missing
}

# EXAM: a missing field is only worth retrying if the source could contain it.
SOURCE_HINT = {"payment_terms_days": "days"}


def retry_can_help(err, doc):
    if err["type"] == "missing":
        return SOURCE_HINT.get(err["loc"][0], "") in doc.lower()
    return True  # format / structural / semantic errors are fixable by re-reading


def process(name, smart=True, max_retries=2):
    doc, attempts, first_prompt = DOCS[name], 0, None
    while True:
        attempts += 1
        raw = SCRIPT[(name, min(attempts, 2))]
        try:
            inv = Invoice(**raw)
            return {"status": "ok", "attempts": attempts, "conflict": inv.conflict_detected,
                    "prompt": first_prompt}
        except ValidationError as ex:
            errs = ex.errors()
            messages = [fmt_err(e) for e in errs]
            if smart and not all(retry_can_help(e, doc) for e in errs):
                # EXAM: absent info (e.g. terms in an external document). Do not burn retries.
                return {"status": "human_review", "attempts": attempts, "errors": messages}
            if attempts > max_retries:
                return {"status": "failed", "attempts": attempts, "errors": messages}
            prompt = build_retry_prompt(doc, raw, messages)
            first_prompt = first_prompt or prompt


# ------------------------------------------------- 3. FEEDBACK LOOP: detected_pattern
# EXAM: record WHICH code construct triggered each finding, so dismissals can be analyzed.
FINDINGS = [  # (detected_pattern, dismissed_by_developer)
    ("bare_except", True), ("bare_except", True), ("bare_except", False),
    ("sql_fstring", False), ("sql_fstring", False),
    ("todo_comment", True), ("todo_comment", True),
]


def main():
    a = process("A")
    print("== 1. Retry prompt (document + failed extraction + specific errors) ==")
    print(a["prompt"])

    print("\n== 2. Retry succeeds: format and semantic errors ==")
    print(f"A (bad date format): status={a['status']}, attempts={a['attempts']}")
    b = process("B")
    print(f"B (totals disagree, source inconsistent): status={b['status']}, "
          f"attempts={b['attempts']}, conflict_detected={b['conflict']}")

    print("\n== 3. Retry cannot help: info absent from source ==")
    c = process("C")
    print(f"C smart: status={c['status']}, attempts={c['attempts']}, errors={c['errors']}")
    w = process("C", smart=False)  # WRONG (exam distractor): blind retry loop
    print(f"C blind retry (WRONG): status={w['status']}, attempts={w['attempts']}")

    print("\n== 4. detected_pattern: dismissal rate per pattern ==")
    stats = {}
    for pattern, dismissed in FINDINGS:
        t, d = stats.get(pattern, (0, 0))
        stats[pattern] = (t + 1, d + int(dismissed))
    for pattern, (t, d) in sorted(stats.items(), key=lambda kv: -kv[1][1] / kv[1][0]):
        print(f"{pattern:<14}{t} findings {d} dismissed {d / t:>4.0%}")


# ------------------------------------------------- OPTIONAL LIVE CALL
def live_retry(doc: str, failed: dict, errors: list[str]):
    """Needs an API key. The Pydantic model doubles as the tool's JSON schema."""
    import anthropic
    resp = anthropic.Anthropic().messages.create(
        model="claude-sonnet-5-5", max_tokens=1000,
        tools=[{"name": "extract_invoice", "description": "Extract invoice fields.",
                "input_schema": Invoice.model_json_schema()}],
        tool_choice={"type": "tool", "name": "extract_invoice"},
        messages=[{"role": "user", "content": build_retry_prompt(doc, failed, errors)}],
    )
    return next(b.input for b in resp.content if b.type == "tool_use")


if __name__ == "__main__":
    main()