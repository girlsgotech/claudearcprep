# =====================================================================
# HOW TO RUN THIS FILE (VS Code)
#   1. Open the PROJECT ROOT folder (claude-architect-prep) in VS Code.
#   2. Open a terminal (Ctrl+`) and activate the virtual environment:
#        Linux/macOS : source .venv/bin/activate
#        Windows     : .venv\Scripts\Activate.ps1
#   3. From the project root (NOT from inside d5_context), run:
#        python -m d5_context.d5_2_escalation
#   4. Requirements: Python 3.10+, standard library only, no API key.
#      d5_context/ must contain an (empty) __init__.py file.
#   5. Save the file first (Ctrl+S). A dot on the tab means unsaved.
# =====================================================================
"""
Task 5.2  Design effective escalation and ambiguity resolution patterns
Scenario  1 (Customer Support Resolution Agent). Mirrors sample Q3 (55% first-contact resolution)
RUNS: mock (criteria expressed as code stand in for the model; optional live call at the bottom)

What this file shows
  1. Explicit escalation criteria + few-shot examples in the system prompt.
  2. WRONG proxies: sentiment and self-reported confidence misroute cases.
  3. Explicit human request = escalate immediately; frustration alone = offer resolution first.
  4. Policy gap or exception = escalate. Multiple customer matches = ask, never guess.
"""

# ------------------------------------------------- 1. THE SYSTEM PROMPT
# EXAM: the root cause of bad escalation is an unclear decision boundary. The
# proportionate first fix is explicit criteria with few-shot examples, before
# any classifier or sentiment layer.
CRITERIA = """\
ESCALATE (call escalate_to_human) when:
1. The customer asks for a human. Escalate immediately, do not investigate first.
2. The request is a policy exception, or the policy is silent on it
   (e.g. competitor price matching when policy only covers our own site).
3. You cannot make meaningful progress (tools keep failing, no next step).

RESOLVE AUTONOMOUSLY when the request is covered by policy and you have the
evidence, even if the customer is upset (e.g. damage replacement with photo).
If the customer is frustrated but has not asked for a human: acknowledge the
frustration, offer the resolution, and escalate only if they repeat the request.

If get_customer returns MORE THAN ONE match: ask for another identifier
(email or phone). Never pick a match by heuristic."""

FEW_SHOT = [
    {"customer": "My headphones arrived broken, here is a photo. I am furious, replace them!",
     "decision": "RESOLVE",
     "why": "Damage replacement with photo evidence is covered. Anger does not change complexity. "
            "Acknowledge the frustration, then process the replacement."},
    {"customer": "Store X sells this for $20 less. Can you match their price?",
     "decision": "ESCALATE",
     "why": "Policy only covers price adjustments on our own site. It is silent on competitors, "
            "so this is a policy gap. Do not improvise."},
    {"customer": "I want to talk to a person.",
     "decision": "ESCALATE",
     "why": "Explicit request for a human. Escalate now, with no investigation first."},
]


def build_system_prompt(examples):
    # EXAM: 2-4 targeted examples of the AMBIGUOUS boundary, with the reasoning.
    assert 2 <= len(examples) <= 4, "use 2-4 targeted examples"
    shots = "\n".join(
        f'<example>\n<customer>{e["customer"]}</customer>\n'
        f'<decision>{e["decision"]}</decision>\n<why>{e["why"]}</why>\n</example>'
        for e in examples
    )
    return "You are a support resolution agent.\n\n" + CRITERIA + "\n\n" + shots


# ------------------------------------------------- 2. THREE ROUTERS ON 8 CASES
POLICY_COVERED = {"damage_replacement", "exchange", "order_status", "account_access"}
POLICY_EXCEPTION = {"late_return"}      # anything in neither set is a policy GAP (silent)

CASES = [  # id, text, request_type, asks_human, progress_possible, sentiment (0-1 angry), self_confidence (1-10)
    ("c1", "Headphones arrived damaged, photo attached. Furious, want a replacement.",
     "damage_replacement", False, True, 0.85, 4),
    ("c2", "Mug arrived cracked, photo attached. Please replace.",
     "damage_replacement", False, True, 0.15, 9),
    ("c3", "Store X sells this for $20 less. Can you match it?",
     "competitor_price_match", False, True, 0.10, 9),
    ("c4", "Return window closed 3 days ago. Can you make an exception?",
     "late_return", False, True, 0.30, 8),
    ("c5", "I want to talk to a human.",
     "damage_replacement", True, True, 0.50, 9),
    ("c6", "Where is my order? I am so annoyed.",
     "order_status", False, True, 0.90, 8),
    ("c7", "Locked out. Password reset failed 3 times and the tools keep erroring.",
     "account_access", False, False, 0.40, 3),
    ("c8", "Wrong colour delivered. I would like an exchange.",
     "exchange", False, True, 0.30, 7),
]
TRUTH = {"c1": "resolve", "c2": "resolve", "c3": "escalate", "c4": "escalate",
         "c5": "escalate", "c6": "resolve", "c7": "escalate", "c8": "resolve"}


def policy_status(request_type):
    if request_type in POLICY_COVERED:
        return "covered"
    return "exception" if request_type in POLICY_EXCEPTION else "silent"


def route_by_sentiment(case):
    # WRONG (exam distractor): sentiment measures mood, not case complexity.
    return "escalate" if case[5] >= 0.7 else "resolve"


def route_by_confidence(case):
    # WRONG (exam distractor): self-reported confidence is poorly calibrated.
    # The agent is already confidently wrong on the hard cases.
    return "escalate" if case[6] < 6 else "resolve"


def route_by_criteria(case):
    # RIGHT: the explicit criteria from the prompt, applied to the case.
    # In production the MODEL applies them (criteria + few-shot). Here code stands in.
    _id, _text, request_type, asks_human, progress, _sent, _conf = case
    if asks_human:
        return "escalate"
    if policy_status(request_type) != "covered":    # exception OR silent
        return "escalate"
    if not progress:
        return "escalate"
    return "resolve"


def score(router):
    wrong = [c[0] for c in CASES if router(c) != TRUTH[c[0]]]
    return len(CASES) - len(wrong), wrong


# ------------------------------------------------- 3. HUMAN REQUESTS
def agent_turn(signal, investigate_first=False):
    """signal: 'demands_human' | 'frustrated' | 'reiterates'. Returns (action, tools called)."""
    if signal in ("demands_human", "reiterates"):
        # EXAM: honor an explicit request for a human immediately.
        tools = ["get_customer", "lookup_order"] if investigate_first else []
        return "escalate_to_human", tools
    # EXAM: frustration alone is not a request for a human. Acknowledge, offer the fix.
    return "acknowledge + offer resolution", ["get_customer", "lookup_order"]


# ------------------------------------------------- 4. MULTIPLE MATCHES
CUSTOMERS = [
    {"id": "C-100", "name": "Jordan Lee", "email": "j.lee@a.com", "last_order": "2026-08-01"},
    {"id": "C-200", "name": "Jordan Lee", "email": "j.lee@b.com", "last_order": "2026-09-20"},
]
TRUE_CUSTOMER = "C-100"     # the person actually chatting


def get_customer(name, email=None):
    return [c for c in CUSTOMERS if c["name"] == name and (email is None or c["email"] == email)]


def pick_by_heuristic(matches):
    # WRONG (exam distractor): guess, e.g. "most recent order". Refunds the wrong person.
    return max(matches, key=lambda c: c["last_order"])["id"]


def resolve_customer(matches):
    # EXAM: more than one match means ask for another identifier. Never select by heuristic.
    if len(matches) == 1:
        return "proceed", matches[0]["id"]
    return "ask_for_identifier", None


def main():
    print("== 1. Explicit criteria + few-shot examples in the system prompt ==")
    prompt = build_system_prompt(FEW_SHOT)
    decisions = [e["decision"] for e in FEW_SHOT]
    print(f"examples: {len(FEW_SHOT)} (guide: 2-4 targeted), decisions: {decisions}")
    print(f"criteria cover: human request, policy gap/exception, no progress: "
          f"{all(k in prompt for k in ('asks for a human', 'policy is silent', 'meaningful progress'))}")
    print(f"prompt length: {len(prompt.splitlines())} lines")

    print("\n== 2. Three routers on 8 cases (truth: escalate c3, c4, c5, c7) ==")
    for label, router in (("sentiment >= 0.7 (WRONG)", route_by_sentiment),
                          ("self-confidence < 6 (WRONG)", route_by_confidence),
                          ("explicit criteria (RIGHT)", route_by_criteria)):
        ok, wrong = score(router)
        print(f"{label:<29}: correct {ok}/{len(CASES)}, misrouted: {', '.join(wrong) or 'none'}")
    print("note: sentiment never escalates calm policy gaps and always escalates angry simple cases; "
          "confidence is 9 on hard cases c3 and c5 but 4 on easy case c1.")

    print("\n== 3. Honor an explicit request for a human immediately ==")
    action, tools = agent_turn("demands_human")
    print(f"RIGHT  'I want a human agent.'      -> {action}, tool calls before escalating: {len(tools)}")
    action, tools = agent_turn("demands_human", investigate_first=True)
    print(f"WRONG  investigate first            -> {action}, tool calls before escalating: {len(tools)}")
    action, tools = agent_turn("frustrated")
    print(f"RIGHT  'My order is late, ugh!'     -> {action}, tool calls: {len(tools)}")
    action, tools = agent_turn("reiterates")
    print(f"RIGHT  'I still want a person.'     -> {action}, tool calls before escalating: {len(tools)}")

    print("\n== 4. Policy gap, and multiple customer matches ==")
    print(f"policy status of 'competitor_price_match': {policy_status('competitor_price_match')} -> escalate")
    print(f"policy status of 'late_return': {policy_status('late_return')} -> escalate")
    matches = get_customer("Jordan Lee")
    print(f"get_customer('Jordan Lee') returned {len(matches)} matches")
    guess = pick_by_heuristic(matches)
    print(f"WRONG heuristic (latest order) picks {guess}; true customer is {TRUE_CUSTOMER}; "
          f"refund goes to the wrong account: {guess != TRUE_CUSTOMER}")
    print(f"RIGHT: {resolve_customer(matches)[0]} (email or phone)")
    matches = get_customer("Jordan Lee", email="j.lee@a.com")
    action, cid = resolve_customer(matches)
    print(f"after the customer gives j.lee@a.com: {len(matches)} match -> {action} with {cid}")


# ------------------------------------------------- OPTIONAL LIVE CALL
def live_agent(customer_message):
    """Needs an API key. Same prompt, real model. Add your four tools to complete the loop."""
    import anthropic
    resp = anthropic.Anthropic().messages.create(
        model="claude-sonnet-5-5", max_tokens=500,
        system=build_system_prompt(FEW_SHOT),
        messages=[{"role": "user", "content": customer_message}],
    )
    return resp.content[0].text


if __name__ == "__main__":
    main()