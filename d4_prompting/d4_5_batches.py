"""
Task 4.5  Design efficient batch processing strategies
Scenarios 5 (Claude Code for CI) and 6 (Structured Data Extraction)
Mirrors sample Q11 (pre-merge check vs overnight report)
RUNS: mock (real request/result shapes, scripted processing; optional live call at the bottom)

What this file shows
  1. Match the API to the latency requirement: sync for blocking, batch for latency-tolerant.
  2. custom_id correlates requests and results; results are NOT in submission order.
  3. Resubmit ONLY the failures, modified (chunk oversized documents).
  4. SLA math: submission window + 24h processing must fit inside the SLA.
  5. Refine the prompt on a small sample BEFORE a big batch.
"""
import re

MODEL = "claude-sonnet-5-5"
BATCH_DISCOUNT = 0.5          # EXAM: 50% cost savings
BATCH_WINDOW_H = 24           # EXAM: up to 24 hours, NO guaranteed latency SLA
CONTEXT_LIMIT_PAGES = 100


# ------------------------------------------------- 1. SYNC vs BATCH
def choose_api(blocking, needs_tools_mid_request):
    if blocking:
        # EXAM: a blocking pre-merge check cannot wait on a batch with no latency SLA.
        return "sync", "blocking: batch has no latency SLA"
    if needs_tools_mid_request:
        # EXAM: a batch request cannot run tools mid-request and feed results back (no multi-turn tool loop).
        return "sync", "needs tool results mid-request"
    return "batch", "latency-tolerant, 50% cheaper"


WORKFLOWS = [  # (name, blocking, needs_tools_mid_request)
    ("pre-merge security check", True, False),
    ("overnight tech debt report", False, False),
    ("weekly audit", False, False),
    ("nightly test generation", False, False),
    ("agentic investigation w/ tools", False, True),
]


# ------------------------------------------------- 2. BATCH REQUESTS + RESULTS
DOCS = [("doc-001", 12), ("doc-002", 40), ("doc-003", 7),
        ("doc-004", 180), ("doc-005", 55), ("doc-006", 30)]   # (id, pages)


def make_request(custom_id, pages):
    # EXAM: custom_id is how you match each result to its request.
    return {"custom_id": custom_id,
            "params": {"model": MODEL, "max_tokens": 500,
                       "messages": [{"role": "user", "content": f"Extract fields. DOC pages={pages}"}]}}


def fake_run_batch(requests, attempt):
    """Scripted batch: result types match the real API (succeeded / errored / expired)."""
    results = []
    for req in requests:
        pages = int(re.search(r"pages=(\d+)", req["params"]["messages"][0]["content"]).group(1))
        cid = req["custom_id"]
        if pages > CONTEXT_LIMIT_PAGES:
            res = {"type": "errored", "error": "prompt too long"}
        elif attempt == 1 and cid == "doc-006":
            res = {"type": "expired"}
        else:
            res = {"type": "succeeded"}
        results.append({"custom_id": cid, "result": res})
    return results[::-1]   # EXAM: result order is not guaranteed to match request order


def tally(results):
    t = {"succeeded": 0, "errored": 0, "expired": 0}
    for r in results:
        t[r["result"]["type"]] += 1
    return f"succeeded={t['succeeded']} errored={t['errored']} expired={t['expired']}"


# ------------------------------------------------- 3. RESUBMIT ONLY FAILURES
def split_pages(pages):
    parts = []
    while pages > 0:
        parts.append(min(pages, CONTEXT_LIMIT_PAGES))
        pages -= CONTEXT_LIMIT_PAGES
    return parts


def build_resubmission(results, pages_by_id):
    failed = sorted((r for r in results if r["result"]["type"] != "succeeded"),
                    key=lambda r: r["custom_id"])
    new, notes = [], []
    for r in failed:
        cid, res = r["custom_id"], r["result"]
        if res["type"] == "errored":
            # EXAM: fix the cause. An oversized document is chunked, not resent unchanged.
            for i, pages in enumerate(split_pages(pages_by_id[cid]), start=1):
                new.append(make_request(f"{cid}-p{i}", pages))
            notes.append(f"{cid} (errored: {res['error']})")
        else:
            new.append(make_request(cid, pages_by_id[cid]))   # expired: resend as is
            notes.append(f"{cid} ({res['type']})")
    return new, notes


# ------------------------------------------------- 4. SLA MATH
def worst_case_hours(submit_interval_h):
    # A document can arrive just after a submission, wait a full interval, then take 24h.
    return submit_interval_h + BATCH_WINDOW_H


# ------------------------------------------------- 5. REFINE ON A SAMPLE FIRST
def batch_cost(n_docs, first_pass_success):
    failed = round(n_docs * (1 - first_pass_success))
    total_requests = n_docs + failed          # failures are paid for again on resubmission
    return total_requests, total_requests * BATCH_DISCOUNT


def main():
    print("== 1. Match the API to the workflow ==")
    for name, blocking, tools in WORKFLOWS:
        api, why = choose_api(blocking, tools)
        print(f"{name} -> {api} ({why})")

    print("\n== 2. custom_id correlates results ==")
    requests = [make_request(cid, pages) for cid, pages in DOCS]
    results = fake_run_batch(requests, attempt=1)
    print(f"submitted {len(requests)} requests")
    print("results arrived in order: " + ", ".join(r["custom_id"] for r in results))
    print(tally(results))

    print("\n== 3. Resubmit only the failures ==")
    new, notes = build_resubmission(results, dict(DOCS))
    print("failed: " + ", ".join(notes))
    print(f"RIGHT: resubmit {[r['custom_id'] for r in new]} ({len(new)} requests, not {len(requests)})")
    second = fake_run_batch(new, attempt=2)
    print("second batch: " + tally(second))
    done = {r["custom_id"].rsplit("-p", 1)[0]
            for r in results + second if r["result"]["type"] == "succeeded"}
    print(f"every document now has a result: {done == {cid for cid, _ in DOCS}}")
    # WRONG (exam distractor): resend everything unchanged.
    again = fake_run_batch(requests, attempt=2)
    print(f"WRONG: resubmit all {len(requests)} requests -> {tally(again)} (doc-004 unchanged, fails again)")

    print("\n== 4. SLA math (30h SLA, 24h batch processing) ==")
    for interval in (4, 6, 8):
        wc = worst_case_hours(interval)
        print(f"submit every {interval}h: worst case {wc}h -> meets 30h SLA: {wc <= 30}")
    print(f"max interval = 30 - {BATCH_WINDOW_H} = {30 - BATCH_WINDOW_H}h; "
          f"the guide's example uses 4h windows ({30 - worst_case_hours(4)}h margin)")

    print("\n== 5. Refine the prompt on a sample before the big batch ==")
    n = 1000
    print(f"sync baseline: {n} requests -> cost {n * 1.0:.0f}")
    for label, rate in (("v1", 0.60), ("v2", 0.95)):
        total, cost = batch_cost(n, rate)
        print(f"prompt {label} (first-pass success {rate:.0%}): {total} requests in batch -> cost {cost:.0f}")


# ------------------------------------------------- OPTIONAL LIVE CALL
def live_batch(docs):
    """Needs an API key. Submit, poll, then match results by custom_id."""
    import time
    import anthropic
    client = anthropic.Anthropic()
    batch = client.messages.batches.create(requests=[make_request(c, p) for c, p in docs])
    while client.messages.batches.retrieve(batch.id).processing_status != "ended":
        time.sleep(60)   # polling for completion; no latency SLA, so never block a developer on this
    return {r.custom_id: r.result.type for r in client.messages.batches.results(batch.id)}


if __name__ == "__main__":
    main()