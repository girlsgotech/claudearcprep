# =====================================================================
# HOW TO RUN THIS FILE (VS Code)
#   1. Open the PROJECT ROOT folder (claude-architect-prep) in VS Code.
#   2. Open a terminal (Ctrl+`) and activate the virtual environment:
#        Linux/macOS : source .venv/bin/activate
#        Windows     : .venv\Scripts\Activate.ps1
#   3. From the project root (NOT from inside d5_context), run:
#        python -m d5_context.d5_1_case_facts
#   4. Requirements: Python 3.10+, standard library only, no API key.
#      d5_context/ must contain an (empty) __init__.py file.
#   5. Save the file first (Ctrl+S). A dot on the tab means unsaved.
# =====================================================================
"""
Task 5.1  Manage conversation context to preserve critical information
Scenario  1 (Customer Support Resolution Agent)
RUNS: mock (scripted tool output; optional live call at the bottom)

What this file shows
  1. Trim verbose tool output (42 fields) to the few relevant fields.
  2. Progressive summarization loses numbers and dates; a persistent
     "case facts" block outside the summarized history keeps them.
  3. "Lost in the middle": put key findings first, use section headers,
     and keep metadata (source, date) in structured output.
  4. The API is stateless: send the complete history on every request.
"""
import json
import re

KEY_FACTS = ["A-1042", "$129.99", "2026-09-09", "A-2077", "$45.00", "full refund", "Friday"]


# ------------------------------------------------- 1. TRIM TOOL OUTPUT
def lookup_order(order_id):
    """Scripted backend: returns 42 fields, like a real order system."""
    order = {
        "order_id": order_id, "status": "delivered", "total": 129.99,
        "order_date": "2026-09-02", "delivered_date": "2026-09-09",
        "return_eligible_until": "2026-10-09",
        "item_sku": "HDPH-220", "item_name": "Wireless headphones",
    }
    for i in range(1, 35):
        order[f"internal_field_{i:02d}"] = f"x{i}"
    return order


# EXAM: keep only what the return decision needs BEFORE it enters context.
# 40+ fields per lookup accumulate and crowd out what matters.
RETURN_FIELDS = ["order_id", "status", "total", "delivered_date", "return_eligible_until"]


def trim_order(order):
    return {k: order[k] for k in RETURN_FIELDS}


# ------------------------------------------------- 2. CASE FACTS vs SUMMARY
TURNS = [
    "Customer: Hi, order #A-1042 arrived damaged. I paid $129.99 and I want a full refund, not store credit.",
    "Agent: Sorry to hear that. Checking order A-1042 now.",
    "Customer: It was delivered on 2026-09-09. I need this resolved by Friday.",
    "Agent: Found it. Delivered 2026-09-09, return window open until 2026-10-09.",
    "Customer: Also my second order #A-2077 never arrived, $45.00, status says shipped.",
]

# WRONG (exam distractor): progressive summarization condenses amounts, dates and
# customer expectations into vague prose.
NAIVE_SUMMARY = "The customer reported problems with two orders and wants them resolved soon."


def extract_case_facts(turns):
    # EXAM: transactional facts (amounts, dates, order numbers, expectations) go into
    # a structured block that is re-sent in EVERY prompt, outside the summarized history.
    text = " ".join(turns)
    return {
        "orders": sorted(set(re.findall(r"A-\d+", text))),
        "amounts": sorted(set(re.findall(r"\$\d+\.\d{2}", text))),
        "dates": sorted(set(re.findall(r"\d{4}-\d{2}-\d{2}", text))),
        "customer_expectations": [p for p in ("full refund", "Friday") if p in text],
    }


def render_case_facts(facts):
    return "<case_facts>\n" + json.dumps(facts) + "\n</case_facts>"


def survivors(text):
    return sum(f in text for f in KEY_FACTS)


# ------------------------------------------------- 3. POSITION EFFECTS
FINDINGS = [  # key=True: the finding the final report must not lose
    {"topic": "visual arts", "claim": "Illustration commissions fell 20%", "source": "survey-A", "date": "2024-03", "key": False},
    {"topic": "music", "claim": "Labels adopted AI mastering", "source": "report-B", "date": "2023-11", "key": False},
    {"topic": "film", "claim": "Studios must disclose AI-written scripts", "source": "contract-C", "date": "2023-09", "key": True},
    {"topic": "writing", "claim": "Publishers added AI clauses to contracts", "source": "news-D", "date": "2024-01", "key": False},
    {"topic": "games", "claim": "Studios use AI for concept art", "source": "blog-E", "date": "2024-02", "key": False},
]


def line(f):
    return f"{f['claim']} ({f['source']}, {f['date']})"


def flat_blocks(findings):
    # WRONG (exam distractor): one flat pile, the key finding sits in the middle.
    return [line(f) for f in findings]


def structured_blocks(findings):
    # EXAM: key findings summary FIRST, then detail under explicit section headers.
    # Each finding keeps its source and date (metadata) for downstream synthesis.
    key = "KEY FINDINGS (read first)\n" + "\n".join("- " + line(f) for f in findings if f["key"])
    return [key] + [f"## {f['topic']}\n{line(f)}" for f in findings]


def position_of_key(blocks, findings):
    claim = next(f["claim"] for f in findings if f["key"])
    return next(i for i, b in enumerate(blocks) if claim in b) + 1


# ------------------------------------------------- 4. STATELESS API
def build_system(facts):
    # case facts at the START of the prompt, every request
    return render_case_facts(facts) + "\nYou are a support agent. Treat <case_facts> as ground truth."


def build_messages(history, new_user_text):
    # EXAM: the API keeps no memory. Pass the complete history each time.
    return history + [{"role": "user", "content": new_user_text}]


def main():
    print("== 1. Trim verbose tool output ==")
    raw = lookup_order("A-1042")
    trimmed = trim_order(raw)
    print(f"raw lookup_order fields: {len(raw)}")
    print(f"kept for the return decision: {len(trimmed)} -> {trimmed}")

    print("\n== 2. Progressive summarization loses transactional facts ==")
    facts = extract_case_facts(TURNS)
    n_wrong = survivors(NAIVE_SUMMARY)
    n_right = survivors(render_case_facts(facts) + "\n" + NAIVE_SUMMARY)
    print(f"{'WRONG: summary only':<27} -> key facts surviving: {n_wrong} of {len(KEY_FACTS)}")
    print(f"{'RIGHT: case facts + summary':<27} -> key facts surviving: {n_right} of {len(KEY_FACTS)}")
    print(f"case facts: {json.dumps(facts)}")

    print("\n== 3. Lost in the middle: put key findings first ==")
    flat, structured = flat_blocks(FINDINGS), structured_blocks(FINDINGS)
    print(f"WRONG: flat list, key finding is block {position_of_key(flat, FINDINGS)} of {len(flat)} (middle)")
    text = "\n\n".join(structured)
    keeps_meta = all(f["source"] in text and f["date"] in text for f in FINDINGS)
    print(f"RIGHT: key finding is block {position_of_key(structured, FINDINGS)} of {len(structured)}; "
          f"every finding keeps source + date: {keeps_meta}")
    print(text)

    print("\n== 4. The API is stateless: resend the full history ==")
    history = [{"role": "user", "content": TURNS[0]},
               {"role": "assistant", "content": "Sorry to hear that. Checking order A-1042 now."}]
    right = build_messages(history, "What is the status of my refund?")
    wrong = [{"role": "user", "content": "What is the status of my refund?"}]
    print(f"RIGHT: request carries {len(right)} messages (earlier turns + new question)")
    print(f"WRONG: request carries {len(wrong)} message, the agent has lost the order number")
    print(f"system prompt starts with: {build_system(facts).splitlines()[0]}")


# ------------------------------------------------- OPTIONAL LIVE CALL
def live_turn(facts, messages):
    """Needs an API key. Case facts ride in the system prompt on every request."""
    import anthropic
    resp = anthropic.Anthropic().messages.create(
        model="claude-sonnet-5-5", max_tokens=500,
        system=build_system(facts), messages=messages,
    )
    return resp.content[0].text


if __name__ == "__main__":
    main()