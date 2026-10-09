# =====================================================================
# HOW TO RUN THIS FILE (VS Code)
#   1. Open the PROJECT ROOT folder (claude-architect-prep) in VS Code.
#   2. Open a terminal (Ctrl+`) and activate the virtual environment:
#        Linux/macOS : source .venv/bin/activate
#        Windows     : .venv\Scripts\Activate.ps1
#   3. From the project root (NOT from inside d5_context), run:
#        python -m d5_context.d5_6_provenance
#   4. Requirements: Python 3.10+, standard library only, no API key.
#      d5_context/ must contain an (empty) __init__.py file.
#   5. Save the file first (Ctrl+S). A dot on the tab means unsaved.
# =====================================================================
"""
Task 5.6  Preserve information provenance and handle uncertainty in multi-source synthesis
Scenario  3 (Multi-Agent Research System)
RUNS: mock (hand-built subagent outputs; no API call needed)

What this file shows
  1. Subagents return structured claim-source mappings; summarizing to prose destroys them.
  2. Conflicting statistics are annotated with their sources, never silently picked or averaged.
  3. Publication dates turn fake "contradictions" into temporal differences.
  4. The coordinator decides how to reconcile BEFORE synthesis; synthesis preserves and merges mappings.
  5. The report separates established from contested findings and renders each content type properly.
"""

# ------------------------------------------------- 1. STRUCTURED SUBAGENT OUTPUT
REQUIRED = ["claim", "excerpt", "source", "date"]     # EXAM: content AND metadata, every time


def fnd(claim, source, date, excerpt, ctype, metric=None, value=None, unit=None, method=None):
    return {"claim": claim, "excerpt": excerpt, "source": source, "date": date, "content_type": ctype,
            "metric": metric, "value": value, "unit": unit, "method": method}


FINDINGS = [
    fnd("Illustrators reporting income loss", "Creative Union survey", "2024-03",
        "37% of surveyed illustrators reported lower income", "financial",
        "illustrator_income_loss", 37, "%", "member survey, n=1,200"),
    fnd("Illustrators reporting income loss", "Industry Board report", "2024-02",
        "26% of illustration firms saw revenue decline", "financial",
        "illustrator_income_loss", 26, "%", "firm survey, n=400"),
    fnd("Global AI art market size", "Market Watch", "2021-06",
        "The AI art market reached $2.1B", "financial", "ai_art_market_size", 2.1, "$B", "analyst estimate"),
    fnd("Global AI art market size", "Trend Insights", "2024-05",
        "The AI art market reached $8.9B", "financial", "ai_art_market_size", 8.9, "$B", "analyst estimate"),
    fnd("Studios must disclose AI-written scripts", "Guild contract C", "2023-09",
        "Section 4 requires disclosure of AI-written material", "news"),
    fnd("Studios must disclose AI-written scripts", "Trade press D", "2023-10",
        "Writers' contract now requires AI disclosure", "news"),
    fnd("AI stem-splitting is standard in mastering tools", "Audio Eng. report E", "2024-01",
        "Most mastering suites ship stem separation", "technical"),
]
SOURCES = sorted({f["source"] for f in FINDINGS})

# WRONG (exam distractor): a summarization step compresses findings into prose.
PROSE_SYNTHESIS = ("AI is reshaping creative work: many illustrators report income loss, the market is growing "
                   "fast, studios are adding disclosure rules, and mastering tools keep improving.")


def validate(finding):
    return [k for k in REQUIRED if not finding.get(k)]


def merge_claims(findings):
    """EXAM: the synthesis agent PRESERVES and MERGES claim-source mappings."""
    merged = {}
    for f in findings:
        entry = merged.setdefault(f["claim"], {"claim": f["claim"], "content_type": f["content_type"],
                                               "metric": f["metric"], "sources": []})
        entry["sources"].append({k: f[k] for k in ("source", "date", "excerpt", "value", "unit", "method")})
    return list(merged.values())


# ------------------------------------------------- 2-3. CONFLICTS vs TEMPORAL DIFFERENCES
def months_apart(d1, d2):
    (y1, m1), (y2, m2) = (int(x) for x in d1.split("-")), (int(x) for x in d2.split("-"))
    return abs((y1 - y2) * 12 + (m1 - m2))


def classify(entries, use_dates=True):
    values = {s["value"] for s in entries}
    if len(values) < 2:
        return "agree"
    if not use_dates:
        return "conflict"                       # WRONG: no dates, so every difference looks like a contradiction
    gap = max(months_apart(a["date"], b["date"]) for a in entries for b in entries)
    return "temporal" if gap > 12 else "conflict"     # EXAM: dates explain many "contradictions"


def analyze(findings, use_dates=True):
    """Document analysis: INCLUDE conflicting values, annotated. Do NOT pick one."""
    out = []
    for m in merge_claims([f for f in findings if f["metric"]]):
        out.append({"metric": m["metric"], "claim": m["claim"], "kind": classify(m["sources"], use_dates),
                    "sources": m["sources"]})
    return out


def reconcile(item):
    # EXAM: the COORDINATOR decides how to reconcile, before synthesis runs.
    if item["kind"] == "conflict":
        return "present both values with source attribution (not reconciled)"
    return "present values by date as a trend"


# ------------------------------------------------- 5. REPORT
def fmt(s):
    return f"${s['value']}B" if s["unit"] == "$B" else f"{s['value']}{s['unit']}"


def build_report(findings, analysis):
    est = [m for m in merge_claims([f for f in findings if not f["metric"]])]
    lines = ["ESTABLISHED"]
    for m in est:
        names = "; ".join(f"{s['source']}, {s['date']}" for s in m["sources"])
        tag = f"{len(m['sources'])} sources" if len(m["sources"]) > 1 else "single source"
        lines.append(f"- {m['claim']} [{names}] ({tag})")
    lines.append("CONTESTED")
    for a in (x for x in analysis if x["kind"] == "conflict"):
        lines.append(f"- {a['claim']}: " + " vs ".join(fmt(s) for s in a["sources"]))
        lines += [f"    {s['source']} ({s['date']}, {s['method']}): {fmt(s)}" for s in a["sources"]]
        lines.append("    not reconciled: both values reported as published")
    lines.append("OVER TIME (different dates, not a contradiction)")
    for a in (x for x in analysis if x["kind"] == "temporal"):
        lines.append(f"- {a['claim']}")
        lines += [f"    {s['date']}: {fmt(s)} ({s['source']})" for s in sorted(a["sources"], key=lambda s: s["date"])]
    return "\n".join(lines)


def render_by_type(findings):
    """EXAM: financial data as a table, news as prose, technical findings as a list."""
    fin = [f for f in findings if f["content_type"] == "financial" and f["metric"] == "ai_art_market_size"]
    table = ["| date    | value | source         |", "|---------|-------|----------------|"]
    table += [f"| {f['date']} | {fmt(f):<5} | {f['source']:<14} |" for f in sorted(fin, key=lambda f: f["date"])]
    news = next(f for f in findings if f["content_type"] == "news")
    prose = f"{news['claim']}, according to {news['source']} ({news['date']})."
    tech = next(f for f in findings if f["content_type"] == "technical")
    return "\n".join(table), prose, f"- {tech['claim']} ({tech['source']}, {tech['date']})"


def main():
    print("== 1. Claim-source mappings survive only if the structure survives ==")
    bad = {"claim": "Market grew", "excerpt": "grew fast", "source": None}
    print(f"required fields: {REQUIRED}")
    print(f"WRONG subagent output missing {validate(bad)} -> reject and ask again")
    print(f"WRONG prose synthesis keeps {sum(s in PROSE_SYNTHESIS for s in SOURCES)} of {len(SOURCES)} sources")
    merged = merge_claims(FINDINGS)
    kept = sum(len(m["sources"]) for m in merged)
    print(f"RIGHT merged claim-source mappings: {len(FINDINGS)} findings -> {len(merged)} claims, "
          f"{kept} of {len(SOURCES)} sources kept")
    two = next(m for m in merged if len(m["sources"]) == 2 and not m["metric"])
    print(f"  merged example: '{two['claim']}' <- {', '.join(s['source'] for s in two['sources'])}")

    print("\n== 2. Conflicting statistics: annotate, do not pick ==")
    conflict = next(a for a in analyze(FINDINGS) if a["kind"] == "conflict")
    vals = [s["value"] for s in conflict["sources"]]
    print(f"{conflict['claim']}: " + " vs ".join(f"{fmt(s)} ({s['source']}, {s['date']})" for s in conflict["sources"]))
    print(f"WRONG pick the first value : {vals[0]}% (drops the other source)")
    print(f"WRONG average the values   : {sum(vals) / len(vals):.1f}% (no source ever reported this number)")
    print("RIGHT keep both with source, date and method")

    print("\n== 3. Dates turn fake contradictions into temporal differences ==")
    no_dates = analyze(FINDINGS, use_dates=False)
    with_dates = analyze(FINDINGS)
    print("WRONG without dates : " + ", ".join(f"{a['metric']}={a['kind']}" for a in no_dates))
    print("RIGHT with dates    : " + ", ".join(f"{a['metric']}={a['kind']}" for a in with_dates))
    m = next(a for a in with_dates if a["kind"] == "temporal")
    gap = months_apart(m["sources"][0]["date"], m["sources"][1]["date"])
    print(f"market size readings are {gap} months apart: a trend, not a contradiction")

    print("\n== 4. Coordinator reconciles before synthesis ==")
    for a in with_dates:
        print(f"{a['metric']} ({a['kind']}) -> {reconcile(a)}")

    print("\n== 5. Report: established vs contested, content types rendered properly ==")
    print(build_report(FINDINGS, with_dates))
    table, prose, bullets = render_by_type(FINDINGS)
    print("\nfinancial data as a table:")
    print(table)
    print("news as prose:\n" + prose)
    print("technical finding as a list:\n" + bullets)
    wrong = [f"- {f['date']} {f['source']} {fmt(f)}" for f in FINDINGS if f["metric"] == "ai_art_market_size"]
    print("WRONG everything as bullets (columns lost):\n" + "\n".join(wrong))


if __name__ == "__main__":
    main()