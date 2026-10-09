# d1_agentic/d1_4_enforcement_handoff.py
"""
EXAM: Task 1.4 - Implement multi-step workflows with enforcement and handoff patterns
SCENARIO: 1 - Customer Support Resolution Agent (sample Q1)
RUNS: mock mode (no API key needed)

What the exam tests:
  * Programmatic enforcement (gates/hooks) vs prompt-based guidance for workflow order.
    When errors have financial or security consequences, prompts alone have a
    NON-ZERO failure rate. Sample Q1: 12% of runs skipped get_customer -> answer A.
  * Block downstream tools until the prerequisite has returned a verified customer ID.
  * Structured handoff summaries for human agents who CANNOT see the transcript.

Run from the project root:
    python -m d1_agentic.d1_4_enforcement_handoff              # gate blocks the skip (correct)
    python -m d1_agentic.d1_4_enforcement_handoff prompt_only  # prompt says MANDATORY, no gate
    python -m d1_agentic.d1_4_enforcement_handoff handoff      # structured escalation packet
"""
import json
import sys

from common import MODEL, FakeResponse, TextBlock, ToolUseBlock, get_client

# WRONG (exam distractors B and C): the system prompt is only a request to the model.
SYSTEM = ("You are a support agent. Verifying the customer with get_customer is MANDATORY "
          "before any order operation.")

GATED_TOOLS = {"lookup_order", "process_refund"}
HANDOFF_FIELDS = ("customer_id", "root_cause", "refund_amount", "recommended_action")
HUMAN_QUEUE = []  # stands in for the human agents' inbox


def tool(name, desc, props, required):
    return {"name": name, "description": desc,
            "input_schema": {"type": "object", "properties": props, "required": required}}


TOOLS = [
    tool("get_customer", "Look up a customer by email. Returns a verified customer_id.",
         {"email": {"type": "string"}}, ["email"]),
    tool("lookup_order", "Look up an order by order_id. Requires a verified customer.",
         {"order_id": {"type": "string"}}, ["order_id"]),
    tool("process_refund", "Refund an order. Requires a verified customer.",
         {"customer_id": {"type": "string"}, "order_id": {"type": "string"}, "amount": {"type": "number"}},
         ["customer_id", "order_id", "amount"]),
    tool("escalate_to_human", "Hand off to a human agent who CANNOT see this conversation.",
         {f: {"type": "string"} for f in HANDOFF_FIELDS}, list(HANDOFF_FIELDS)),
]


def call_tool(name: str, args: dict, state: dict, gate: bool) -> dict:
    # EXAM Q1 (answer A): programmatic prerequisite. This runs in CODE, so it cannot be
    # skipped, forgotten or talked out of by the model, unlike an instruction in a prompt.
    if name in GATED_TOOLS and not state["customer_id"]:
        if gate:
            return {"isError": True, "error": "BLOCKED: call get_customer first; "
                                              "a verified customer_id is required."}
        print(f"  !! UNVERIFIED ACCESS: {name} ran with no verified customer")
    if gate and name == "process_refund" and args.get("customer_id") != state["customer_id"]:
        return {"isError": True, "error": "BLOCKED: customer_id does not match the verified customer."}

    if name == "get_customer":
        state["customer_id"] = "C-1001"  # set ONLY by a successful verification
        return {"customer_id": "C-1001", "name": "Alex Doe"}
    if name == "lookup_order":
        return {"order_id": args["order_id"], "status": "delivered", "total_usd": 59.90}
    if name == "process_refund":
        return {"refund_id": "R-77", "amount": args["amount"]}
    if name == "escalate_to_human":
        # EXAM: the human has NO transcript, so the packet must be complete and structured.
        missing = [f for f in HANDOFF_FIELDS if args.get(f) in (None, "")]
        if missing:
            return {"isError": True, "error": f"Handoff incomplete; missing: {missing}"}
        HUMAN_QUEUE.append(args)
        return {"status": "queued for human agent"}
    return {"isError": True, "error": f"unknown tool {name}"}


def run(script: list, gate: bool) -> str:
    client = get_client(script)
    messages = [{"role": "user", "content": "Hi, I'm alex@example.com. Refund order 12345 please."}]
    state = {"customer_id": None}
    for turn in range(1, 16):  # backstop only (see 1.1)
        r = client.messages.create(model=MODEL, max_tokens=1024, system=SYSTEM,
                                   tools=TOOLS, messages=messages)
        if r.stop_reason == "end_turn":
            return "".join(b.text for b in r.content if b.type == "text")
        messages.append({"role": "assistant", "content": r.content})
        results = []
        for b in r.content:
            if b.type == "tool_use":
                out = call_tool(b.name, b.input, state, gate)
                shown = out["error"] if out.get("isError") else "ok"
                print(f"[turn {turn}] {b.name} -> {shown}")
                results.append({"type": "tool_result", "tool_use_id": b.id,
                                "content": json.dumps(out), "is_error": bool(out.get("isError"))})
        messages.append({"role": "user", "content": results})
    raise RuntimeError("iteration backstop hit")


# --- Mock model behaviour (scripted) ----------------------------------------
def T(i, name, **args):
    return ToolUseBlock(i, name, args)


def turn(*blocks, reason="tool_use"):
    return FakeResponse(list(blocks), reason)


def script_skip():
    """The Q1 failure: the model skips get_customer and goes straight to lookup_order."""
    return [
        turn(TextBlock("Checking your order."), T("1", "lookup_order", order_id="12345")),
        turn(T("2", "get_customer", email="alex@example.com")),
        turn(T("3", "lookup_order", order_id="12345")),
        turn(T("4", "process_refund", customer_id="C-1001", order_id="12345", amount=59.90)),
        turn(TextBlock("Refunded $59.90 for order 12345."), reason="end_turn"),
    ]


def script_handoff():
    vague = {"customer_id": "C-1001", "summary": "Customer is upset, please help"}
    full = {"customer_id": "C-1001",
            "root_cause": "Duplicate charge on order 12399 caused by a payment retry",
            "refund_amount": "640.00",
            "recommended_action": "Amount exceeds agent authority; approve and process refund manually"}
    return [
        turn(T("1", "get_customer", email="alex@example.com")),
        turn(T("2", "escalate_to_human", **vague)),   # WRONG: no root cause, no amount, no action
        turn(T("3", "escalate_to_human", **full)),    # CORRECT: everything a human needs
        turn(TextBlock("I've passed this to a specialist with the full details."), reason="end_turn"),
    ]


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "gated"
    if mode == "handoff":
        print("FINAL:", run(script_handoff(), gate=True))
        print("\nHUMAN QUEUE:\n" + json.dumps(HUMAN_QUEUE, indent=2))
    else:
        print("FINAL:", run(script_skip(), gate=(mode == "gated")))