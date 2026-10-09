# d2_tools/d2_1_tool_descriptions.py
"""
EXAM: Task 2.1 - Design effective tool interfaces with clear descriptions and boundaries
SCENARIOS: 1 - Customer Support (get_customer vs lookup_order, sample Q2)
           3 - Multi-Agent Research (analyze_content vs analyze_document)
RUNS: mock (no API key). Everything here is deterministic Python.

IMPORTANT - what this file is and is not:
  Real tool selection happens inside the model, and I cannot reproduce that offline.
  So this file gives you two honest, deterministic tools instead:
    1. A DESCRIPTION LINTER that checks the four things the exam says a good description
       contains (input formats, example queries, edge cases, boundaries).
    2. A CUE-MATCHING ROUTER that shows how much evidence each description gives a model.
       When descriptions share no cues, the router reports a tie: a real model would be
       guessing there, which is the root cause in sample Q2 (minimal descriptions).
  To watch a real model misroute, run the same tool sets against the API with a key.

What the exam tests:
  * Tool descriptions are the PRIMARY mechanism for tool selection. Minimal descriptions
    lead to unreliable selection among similar tools (sample Q2, answer B: expand them).
  * Good descriptions state input formats, example queries, edge cases and boundaries.
  * Overlapping descriptions cause misrouting (analyze_content vs analyze_document).
    Fix by RENAMING to remove overlap, or SPLITTING a generic tool into purpose-specific ones.
  * Keyword-sensitive system prompt wording can create unintended tool associations.

Run from the project root:
    python -m d2_tools.d2_1_tool_descriptions           # all demos
    python -m d2_tools.d2_1_tool_descriptions routing   # minimal vs rich descriptions
    python -m d2_tools.d2_1_tool_descriptions overlap   # rename and split
    python -m d2_tools.d2_1_tool_descriptions system    # keyword-sensitive prompts
"""
import re
import sys

STOP = {"the", "and", "for", "use", "with", "from", "that", "this", "are", "not", "you",
        "your", "any", "can", "but", "what", "where", "how", "check"}

# ---------------------------------------------------------------------------
# WRONG (sample Q2): minimal descriptions. Both tools accept similar identifiers and
# nothing tells the model which one is for what.
# ---------------------------------------------------------------------------
MINIMAL = {
    "get_customer": "Retrieves customer information",
    "lookup_order": "Retrieves order details",
}

# ---------------------------------------------------------------------------
# CORRECT (sample Q2, answer B): input formats, example queries, edge cases, boundaries
# ---------------------------------------------------------------------------
RICH = {
    "get_customer": (
        "Look up a customer profile or account.\n"
        "Input: email address (alex@example.com) or customer ID (C-1001).\n"
        "Use for: who is this customer, account status, profile, update my email, verify identity.\n"
        "Do NOT use for orders or shipments, and never with an order number like #12345; "
        "use lookup_order for those.\n"
        "Edge case: several matches returns a list; ask the user for another identifier, do not guess."
    ),
    "lookup_order": (
        "Look up an order, shipment or delivery.\n"
        "Input: order number (12345 or #12345) only.\n"
        "Use for: order status, where is my package, tracking, delivery date, order total.\n"
        "Do NOT use for customer profiles or account questions; use get_customer for emails and customer IDs.\n"
        "Edge case: an unknown order number returns an error; it is not an empty result."
    ),
}

QUERIES = [
    "check my order #12345",
    "what's the status of my account? alex@example.com",
    "where is my package",
]


def words(text):
    """Lowercase content words with a crude plural stem ('orders' -> 'order')."""
    out = set()
    for w in re.findall(r"[a-z]+", text.lower()):
        if len(w) > 3 and w.endswith("s"):
            w = w[:-1]
        if len(w) > 2 and w not in STOP:
            out.add(w)
    return out


def body(desc):
    """Cue text of a description: drop 'Do NOT' boundary lines and the section labels."""
    lines = [ln for ln in desc.split("\n") if not ln.startswith("Do NOT")]
    return "\n".join(re.sub(r"^(Input|Use for|Edge case):\s*", "", ln) for ln in lines)


def route(query, tools):
    """Cue matching: how many query words does each description give evidence for?"""
    q = words(query)
    scores = {name: len(q & words(body(d))) for name, d in tools.items()}
    ranked = sorted(scores.items(), key=lambda kv: -kv[1])
    (best, top), (_, second) = ranked[0], ranked[1]
    if top == 0:
        verdict = "NO CUES (a real model would be guessing)"
    elif top == second:
        verdict = "TIE (a real model would be guessing)"
    else:
        verdict = best
    return verdict, scores


# ---------------------------------------------------------------------------
# Description linter: the four things the exam says a good description contains
# ---------------------------------------------------------------------------
CHECKS = {"input format": "Input:", "example queries": "Use for:",
          "edge case": "Edge case:", "boundary": "Do NOT use"}


def lint(desc):
    return [name for name, marker in CHECKS.items() if marker not in desc]


def jaccard(a, b):
    wa, wb = words(body(a)), words(body(b))
    return len(wa & wb) / len(wa | wb)


def demo_routing():
    print("== Linter: what each description is missing ==")
    for label, tools in (("MINIMAL", MINIMAL), ("RICH", RICH)):
        for name, desc in tools.items():
            missing = lint(desc)
            print(f"{label:8} {name:13} missing: {', '.join(missing) if missing else 'nothing'}")
    print("\n== Router: how much evidence do the descriptions give? ==")
    for q in QUERIES:
        print(f"query: {q}")
        for label, tools in (("MINIMAL", MINIMAL), ("RICH", RICH)):
            verdict, scores = route(q, tools)
            print(f"   {label:8} -> {verdict}   scores={scores}")


# ---------------------------------------------------------------------------
# Overlap: rename, or split a generic tool (Scenario 3)
# ---------------------------------------------------------------------------
OVERLAPPING = {
    "analyze_content": "Analyzes content and returns results",
    "analyze_document": "Analyzes documents and returns results",
}

# EXAM fixes: rename analyze_content -> extract_web_results (web-specific), and split the
# generic analyze_document into three purpose-specific tools with clear contracts.
SPLIT = {
    "extract_web_results": (
        "Extract results from a web page or search result.\n"
        "Input: URL or HTML text.\n"
        "Use for: pull prices, headlines or links from a web page.\n"
        "Do NOT use for PDFs or uploaded files; use extract_data_points.\n"
        "Edge case: a page blocked by login returns an access error, not an empty list."
    ),
    "extract_data_points": (
        "Extract numbers, dates and named values from an uploaded document.\n"
        "Input: document ID.\n"
        "Use for: pull figures, totals and dates from a report or PDF.\n"
        "Do NOT use for summaries; use summarize_content.\n"
        "Edge case: a missing field returns null, never a guess."
    ),
    "summarize_content": (
        "Write a short summary of a document or page.\n"
        "Input: document ID or pasted text.\n"
        "Use for: give me the gist, key points, TL;DR.\n"
        "Do NOT use for exact figures; use extract_data_points.\n"
        "Edge case: very long input is truncated and the summary says so."
    ),
    "verify_claim_against_source": (
        "Check one claim against a named source.\n"
        "Input: claim text plus the source document ID.\n"
        "Use for: is this statement supported, fact-check a statistic.\n"
        "Do NOT use to find new sources; use extract_web_results.\n"
        "Edge case: a source silent on the claim returns unverifiable, not false."
    ),
}


def max_overlap(tools):
    names = list(tools)
    pairs = [(jaccard(tools[a], tools[b]), a, b) for i, a in enumerate(names) for b in names[i + 1:]]
    return max(pairs)


def demo_overlap():
    print("\n== Overlap: near-identical descriptions ==")
    score, a, b = max_overlap(OVERLAPPING)
    flag = "  <-- OVERLAP: likely misrouting" if score >= 0.5 else ""
    print(f"{a} vs {b}: overlap={score:.2f}{flag}")
    print("\n== After rename + split ==")
    score, a, b = max_overlap(SPLIT)
    print(f"worst pair: {a} vs {b}: overlap={score:.2f}")
    for name, desc in SPLIT.items():
        print(f"  {name:28} missing: {', '.join(lint(desc)) or 'nothing'}")


# ---------------------------------------------------------------------------
# System prompt keyword trap
# ---------------------------------------------------------------------------
GENERIC = {"get", "lookup", "find", "fetch"}


def keyword_trap(system_prompt, tools):
    """Flag imperative sentences containing words from tool NAMES (customer, order, ...)."""
    hits = []
    for sentence in re.split(r"(?<=[.!?])\s+", system_prompt):
        if not re.search(r"\b(always|never|must|first)\b", sentence.lower()):
            continue
        mentioned = [t for t in tools if (set(re.findall(r"[a-z]+", t)) - GENERIC) & words(sentence)]
        if mentioned:
            hits.append((sentence, mentioned))
    return hits


def demo_system():
    print("\n== Keyword-sensitive system prompts ==")
    traps = {
        "TRAP": "Always check the customer's order history first. Be polite and concise.",
        "OK": "Be polite and concise. Choose tools by reading their descriptions.",
    }
    for label, prompt in traps.items():
        hits = keyword_trap(prompt, RICH)
        if hits:
            for sentence, tools in hits:
                print(f"{label:5} WARNING: '{sentence}' -> pulls toward {tools}, can override descriptions")
        else:
            print(f"{label:5} no keyword-sensitive instructions found")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "all"
    if mode in ("all", "routing"):
        demo_routing()
    if mode in ("all", "overlap"):
        demo_overlap()
    if mode in ("all", "system"):
        demo_system()