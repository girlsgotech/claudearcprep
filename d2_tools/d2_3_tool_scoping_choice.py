# d2_tools/d2_3_tool_scoping_choice.py
"""
EXAM: Task 2.3 - Distribute tools appropriately across agents and configure tool choice
SCENARIO: 3 - Multi-Agent Research System (sample Q9: the verify_fact tool)
RUNS: mock (no API key). The tool_choice behavior is SIMULATED to show the semantics.

What the exam tests:
  * Too many tools (18 instead of 4-5) degrades selection reliability.
  * Agents given tools outside their specialization misuse them (a synthesis agent that
    starts web searching). Give each agent only the tools its role needs.
  * Replace generic tools with constrained ones (fetch_url -> load_document that validates).
  * Give a role a SCOPED cross-role tool for high-frequency needs (verify_fact for the
    synthesis agent); route complex cases through the coordinator (sample Q9, answer A).
  * tool_choice: "auto" (may answer in text), "any" (must call SOME tool), forced
    (must call THIS tool). Force a tool to guarantee an ordering such as
    extract_metadata first, then continue in follow-up turns.

API note: the exam writes tool_choice: "any" loosely. In the Messages API the parameter is an
object: {"type": "auto"} | {"type": "any"} | {"type": "tool", "name": "<tool>"}.

Run from the project root:
    python -m d2_tools.d2_3_tool_scoping_choice           # all demos
    python -m d2_tools.d2_3_tool_scoping_choice scope     # scoped tools + constrained fetch
    python -m d2_tools.d2_3_tool_scoping_choice verify    # the Q9 verify_fact trade-off
    python -m d2_tools.d2_3_tool_scoping_choice choice    # auto / any / forced
"""
import json
import re
import sys
from urllib.parse import urlparse

# ---------------------------------------------------------------------------
# Demo 1: scoped tool access per agent
# ---------------------------------------------------------------------------
EVERYTHING = [  # WRONG (exam distractor): one agent holding all 18 tools
    "web_search", "fetch_url", "load_page", "load_document", "read_pdf", "ocr_scan",
    "extract_web_results", "extract_data_points", "summarize_content", "verify_claim_against_source",
    "verify_fact", "translate_text", "write_section", "format_report", "export_pdf",
    "send_email", "create_ticket", "query_database",
]
ROLE_ALLOWED = {
    "web-searcher": {"web_search", "load_page", "extract_web_results"},
    "doc-analyzer": {"load_document", "read_pdf", "ocr_scan", "extract_data_points", "summarize_content"},
    "synthesizer": {"write_section", "format_report", "summarize_content"},
}
# EXAM: a SCOPED cross-role tool for a high-frequency need, not the whole other toolbox.
CROSS_ROLE_OK = {"synthesizer": {"verify_fact"}}
MAX_TOOLS = 5


def audit(role, tools):
    allowed = ROLE_ALLOWED[role] | CROSS_ROLE_OK.get(role, set())
    return {"count": len(tools), "outside_role": sorted(set(tools) - allowed), "too_many": len(tools) > MAX_TOOLS}


CONFIGS = {
    "WRONG  one agent, all tools": ("synthesizer", EVERYTHING),
    "WRONG  synthesizer + web tools (Q9 option C)": ("synthesizer", ["write_section", "format_report", "web_search", "fetch_url", "load_page"]),
    "RIGHT  synthesizer + verify_fact": ("synthesizer", ["write_section", "format_report", "summarize_content", "verify_fact"]),
    "RIGHT  web-searcher": ("web-searcher", ["web_search", "load_page", "extract_web_results"]),
}

ALLOWED_DOMAINS = {"example.com", "docs.example.org"}
DOC_TYPES = (".pdf", ".docx", ".txt")


def fetch_url(url):
    """WRONG: a generic tool will fetch ANYTHING, including internal addresses."""
    return {"ok": True, "fetched": url}


def load_document(url):
    """RIGHT: a constrained replacement that validates before it fetches."""
    p = urlparse(url)
    if p.scheme != "https":
        return {"ok": False, "errorCategory": "validation", "message": "only https URLs are allowed"}
    if p.hostname not in ALLOWED_DOMAINS:
        return {"ok": False, "errorCategory": "permission", "message": f"{p.hostname} is not an approved source"}
    if not p.path.lower().endswith(DOC_TYPES):
        return {"ok": False, "errorCategory": "validation", "message": f"expected a document ({', '.join(DOC_TYPES)})"}
    return {"ok": True, "loaded": url}


def demo_scope():
    print("== Scoped tools per agent ==")
    for label, (role, tools) in CONFIGS.items():
        a = audit(role, tools)
        notes = []
        if a["too_many"]:
            notes.append(f"{a['count']} tools (limit {MAX_TOOLS})")
        if a["outside_role"]:
            notes.append(f"outside role: {a['outside_role'] if a['count'] <= 6 else str(len(a['outside_role'])) + ' tools'}")
        print(f"{label:46} -> {'; '.join(notes) if notes else 'OK'}")
    print("\n== Generic fetch_url vs constrained load_document ==")
    for url in ("https://example.com/report.pdf", "http://169.254.169.254/latest/meta-data",
                "https://evil.test/report.pdf", "https://example.com/login"):
        print(f"{url}\n    fetch_url    -> {json.dumps(fetch_url(url))}\n    load_document -> {json.dumps(load_document(url))}")


# ---------------------------------------------------------------------------
# Demo 2: sample Q9 - verify_fact for the common case, coordinator for the rest
# ---------------------------------------------------------------------------
VERIFICATIONS = ["simple"] * 17 + ["complex"] * 3  # the guide's 85% / 15% split, per 20 checks
TRIPS_PER_DELEGATION = 2  # assumption: the guide says each round trip adds 2-3 coordinator hops


def demo_verify():
    print("\n== Sample Q9: verification overhead (toy count) ==")
    total = len(VERIFICATIONS)
    before = total * TRIPS_PER_DELEGATION
    print(f"before: every check goes via the coordinator: {total} x {TRIPS_PER_DELEGATION} = {before} coordinator round trips")
    simple = VERIFICATIONS.count("simple")
    complex_ = VERIFICATIONS.count("complex")
    after = complex_ * TRIPS_PER_DELEGATION
    print(f"after (A): {simple} direct verify_fact calls + {complex_} complex x {TRIPS_PER_DELEGATION} = {after} coordinator round trips")
    print("Q9 options: A scoped verify_fact (least privilege, keeps the coordinator for complex cases);")
    print("            B batching creates blocking dependencies; C hands over all web tools (over-provisioned);")
    print("            D speculative caching cannot predict what will need verifying.")


# ---------------------------------------------------------------------------
# Demo 3: tool_choice auto / any / forced (semantics SIMULATED)
# ---------------------------------------------------------------------------
DEMO_TOOLS = [
    {"name": "get_weather", "cues": {"weather", "rain", "temperature"}},
    {"name": "extract_metadata", "cues": {"document", "metadata", "author"}},
]
CHOICES = {
    "auto": {"type": "auto"},
    "any": {"type": "any"},
    "forced": {"type": "tool", "name": "extract_metadata"},
}


def simulate(tool_choice, user):
    kind = tool_choice["type"]
    if kind == "tool":
        return f"tool_use: {tool_choice['name']}"  # guaranteed, whatever the user said
    words = set(re.findall(r"[a-z]+", user.lower()))
    score, best = max((len(words & t["cues"]), t["name"]) for t in DEMO_TOOLS)
    if kind == "any":
        return f"tool_use: {best if score else '<model must pick one>'}"  # never plain text
    return f"tool_use: {best}" if score else "end_turn: plain text answer"  # auto may skip tools


def demo_choice():
    print("\n== tool_choice semantics ==")
    print(f"{'user message':36}{'auto':32}{'any':32}forced extract_metadata")
    for user in ("what's the weather in Dresden?", "hello, how are you?", "who is the author of this document?"):
        row = [simulate(c, user) for c in CHOICES.values()]
        print(f"{user:36}{row[0]:32}{row[1]:32}{row[2]}")
    print("\n== Forcing an ordering: extract_metadata first, then follow-up turns ==")
    turns = [
        {"turn": 1, "tool_choice": {"type": "tool", "name": "extract_metadata"}, "why": "guaranteed first call"},
        {"turn": 2, "tool_choice": {"type": "auto"}, "why": "send the result back; enrichment tools, model decides"},
    ]
    for t in turns:
        print(json.dumps(t))
    print("Use {'type': 'any'} when several extraction schemas exist and the document type is unknown (Task 4.3).")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "all"
    if mode in ("all", "scope"):
        demo_scope()
    if mode in ("all", "verify"):
        demo_verify()
    if mode in ("all", "choice"):
        demo_choice()