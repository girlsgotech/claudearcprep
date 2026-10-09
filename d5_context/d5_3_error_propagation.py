# =====================================================================
# HOW TO RUN THIS FILE (VS Code)
#   1. Open the PROJECT ROOT folder (claude-architect-prep) in VS Code.
#   2. Open a terminal (Ctrl+`) and activate the virtual environment:
#        Linux/macOS : source .venv/bin/activate
#        Windows     : .venv\Scripts\Activate.ps1
#   3. From the project root (NOT from inside d5_context), run:
#        python -m d5_context.d5_3_error_propagation
#   4. Requirements: Python 3.10+, standard library only, no API key.
#      d5_context/ must contain an (empty) __init__.py file.
#   5. Save the file first (Ctrl+S). A dot on the tab means unsaved.
# =====================================================================
"""
Task 5.3  Implement error propagation strategies across multi-agent systems
Scenario  3 (Multi-Agent Research System). Mirrors sample Q8 (web search subagent times out)
RUNS: mock (scripted search backend, no API call needed)

What this file shows
  1. A valid EMPTY result and an ACCESS FAILURE both have zero findings but mean opposite things.
  2. Local recovery inside the subagent; propagate only what it cannot fix, with context.
  3. Four ways to report a failure: structured context (RIGHT) vs three anti-patterns.
  4. The coordinator uses the structured context to recover.
  5. Synthesis output carries coverage annotations (supported vs gaps).
"""
import json

MAX_LOCAL_ATTEMPTS = 2     # the subagent tries twice before it propagates anything

TOPICS = ["visual arts", "music", "film", "writing", "games"]
QUERIES = {t: f"AI in {t}" for t in TOPICS}
ALTERNATIVES = {"film": ["AI screenwriting and film studios"],
                "games": ["AI game development tools"]}


# ------------------------------------------------- SCRIPTED SEARCH BACKEND
class SearchTimeout(Exception):
    def __init__(self, partial=None):
        super().__init__("timeout")
        self.partial = partial or []


def fnd(claim, source):
    return {"claim": claim, "source": source}


BACKEND = {
    "AI in visual arts": [fnd("Illustration commissions fell", "survey-A"),
                          fnd("Studios adopt image generators", "report-B"),
                          fnd("Copyright suits filed", "news-C")],
    "AI in music": [fnd("Labels adopt AI mastering", "report-D"), fnd("Stem-splitting tools spread", "blog-E")],
    "AI in film": "DOWN",
    "AI screenwriting and film studios": [fnd("Studios must disclose AI scripts", "contract-F"),
                                          fnd("Previsualization uses AI", "report-G")],
    "AI in writing": [],        # query SUCCEEDS, nothing matched: a valid empty result
    "AI in games": "DOWN",
    "AI game development tools": "DOWN",
}
PARTIAL_BEFORE_TIMEOUT = {"AI in film": [fnd("Studios test AI previsualization", "report-H")]}
FLAKY = {"AI in music"}         # first attempt times out, second succeeds (transient)


def fake_search(query, attempt):
    data = BACKEND[query]
    if data == "DOWN":
        raise SearchTimeout(PARTIAL_BEFORE_TIMEOUT.get(query))
    if query in FLAKY and attempt == 1:
        raise SearchTimeout()
    return data


# ------------------------------------------------- 1-3. THE SUBAGENT
def run_query(topic, query, mode="structured"):
    attempts, partial, last = 0, [], None
    while attempts < MAX_LOCAL_ATTEMPTS:        # EXAM: local recovery for transient failures
        attempts += 1
        try:
            findings = fake_search(query, attempts)
            # EXAM: success with zero findings is a VALID EMPTY RESULT, not an error.
            return {"status": "ok", "topic": topic, "query": query,
                    "findings": findings, "attempts": attempts}
        except SearchTimeout as e:
            partial, last = e.partial or partial, e

    # Local recovery is exhausted. What do we tell the coordinator?
    if mode == "terminate":
        raise last                              # WRONG (exam distractor, Q8 option D)
    if mode == "empty_as_success":
        return {"status": "ok", "topic": topic, "query": query, "findings": [], "attempts": attempts}  # WRONG (Q8 C)
    if mode == "generic":
        return {"status": "error", "topic": topic, "message": "search unavailable"}      # WRONG (Q8 B)
    # RIGHT (Q8 A): structured error context
    return {"status": "error", "topic": topic,
            "failure_type": "timeout",
            "attempted_query": query,
            "attempts": attempts,
            "partial_results": partial,
            "alternatives": ALTERNATIVES.get(topic, [])}


def as_tool_result(tool_use_id, result):
    """Real API shape: a failed tool result carries is_error plus useful content."""
    return {"type": "tool_result", "tool_use_id": tool_use_id,
            "content": json.dumps(result), "is_error": result["status"] == "error"}


# ------------------------------------------------- 4. THE COORDINATOR
def coordinate(mode):
    coverage = {}
    for topic in TOPICS:
        try:
            coverage[topic] = run_query(topic, QUERIES[topic], mode)
        except SearchTimeout:
            return {"terminated_at": topic, "completed": list(coverage)}
    return {"coverage": coverage}


def decide(result, tried):
    if result["status"] == "ok":
        return ("use", None) if result["findings"] else ("record_no_matches", None)
    if "failure_type" not in result:
        return "cannot_decide", None            # a generic status carries no context
    untried = [a for a in result["alternatives"] if a not in tried]
    if untried:
        return "retry_alternative", untried[0]
    return "annotate_gap", None


def recover(coverage):
    decisions = {}
    for topic, r in list(coverage.items()):
        if r["status"] != "error":
            continue
        tried = {r["attempted_query"]}
        action, alt = decide(r, tried)
        decisions[topic] = (action, alt)
        if action != "retry_alternative":
            coverage[topic] = {"status": "gap", "topic": topic, "note": "no recovery path"}
            continue
        r2 = run_query(topic, alt)
        if r2["status"] == "ok":
            coverage[topic] = {
                "status": "ok", "topic": topic,
                "findings": r["partial_results"] + r2["findings"],     # EXAM: keep partial results
                "note": f"original query timed out; {len(r['partial_results'])} partial kept, "
                        f"{len(r2['findings'])} via alternative"}
        else:
            coverage[topic] = {
                "status": "gap", "topic": topic,
                "note": f"timeout on '{r['attempted_query']}' ({r['attempts']} attempts) "
                        f"and on alternative '{alt}'"}
    return decisions


# ------------------------------------------------- 5. COVERAGE ANNOTATIONS
def build_report(coverage):
    ok = {t: r for t, r in coverage.items() if r["status"] == "ok" and r["findings"]}
    empty = [t for t, r in coverage.items() if r["status"] == "ok" and not r["findings"]]
    gaps = {t: r for t, r in coverage.items() if r["status"] == "gap"}
    lines = ["WELL-SUPPORTED"]
    for t, r in ok.items():
        extra = f" [{r['note']}]" if r.get("note") else ""
        lines.append(f"- {t}: {len(r['findings'])} findings{extra}")
    lines.append("SEARCHED, NO MATCHES")
    lines += [f"- {t}: query succeeded, nothing matched (not a failure)" for t in empty]
    lines.append("GAPS (source unavailable, NOT evidence of absence)")
    lines += [f"- {t}: {r['note']}" for t, r in gaps.items()]
    summary = f"coverage: {len(ok)} of {len(TOPICS)} topics well-supported, {len(empty)} searched with no matches, {len(gaps)} gap"
    return "\n".join(lines), summary


def main():
    print("== 1. Valid empty result vs access failure ==")
    writing = run_query("writing", QUERIES["writing"])
    games = run_query("games", QUERIES["games"])
    print(f"writing -> status={writing['status']}, findings={len(writing['findings'])} (query worked, nothing matched)")
    print(f"games   -> status={games['status']}, failure_type={games['failure_type']}, "
          f"attempts={games['attempts']} (query never completed)")
    print("both have zero findings, but they need opposite handling")

    print("\n== 2. Local recovery first, propagate only what cannot be fixed ==")
    music = run_query("music", QUERIES["music"])
    print(f"music: attempt 1 timed out, attempt {music['attempts']} succeeded -> "
          f"status={music['status']}, findings={len(music['findings'])} (coordinator never saw an error)")
    film = run_query("film", QUERIES["film"])
    print(f"film: {film['attempts']} attempts, still timing out -> propagate structured context:")
    print(json.dumps(film, indent=2))
    tr = as_tool_result("tu_1", film)
    print(f"tool_result is_error={tr['is_error']}, content carries: {list(json.loads(tr['content']))}")

    print("\n== 3. Four ways to report film and games failing ==")
    for label, mode in (("RIGHT structured context", "structured"),
                        ("WRONG generic status", "generic"),
                        ("WRONG empty-as-success", "empty_as_success"),
                        ("WRONG terminate workflow", "terminate")):
        out = coordinate(mode)
        if "terminated_at" in out:
            print(f"{label:<26}: workflow killed at '{out['terminated_at']}', "
                  f"topics completed {len(out['completed'])} of {len(TOPICS)}, no report produced")
            continue
        cov = out["coverage"]
        if mode == "generic":
            bad = [t for t, r in cov.items() if r["status"] == "error"]
            verdicts = {decide(cov[t], set())[0] for t in bad}
            print(f"{label:<26}: errors on {', '.join(bad)}; coordinator decision: {', '.join(verdicts)} "
                  "(no failure type, query or partial results)")
        elif mode == "empty_as_success":
            claimed = [t for t, r in cov.items() if r["status"] == "ok" and not r["findings"]]
            silent = [t for t in claimed if t != "writing"]
            print(f"{label:<26}: report claims no results for {', '.join(claimed)}; "
                  f"silent gaps: {', '.join(silent)} (partial result lost too)")
        else:
            bad = [t for t, r in cov.items() if r["status"] == "error"]
            print(f"{label:<26}: errors on {', '.join(bad)}, each with failure_type, query, partial results, alternatives")

    print("\n== 4. Coordinator recovers using the structured context ==")
    coverage = coordinate("structured")["coverage"]
    for topic, (action, alt) in recover(coverage).items():
        tail = f" '{alt}'" if alt else ""
        print(f"{topic}: decision={action}{tail} -> final status={coverage[topic]['status']}")

    print("\n== 5. Synthesis with coverage annotations ==")
    report, summary = build_report(coverage)
    print(report)
    print(summary)


if __name__ == "__main__":
    main()