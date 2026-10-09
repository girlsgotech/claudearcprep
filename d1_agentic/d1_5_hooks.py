# d1_agentic/d1_5_hooks.py
"""
EXAM: Task 1.5 - Apply Agent SDK hooks for tool call interception and data normalization
SCENARIO: 1 - Customer Support Resolution Agent (process_refund, lookup_order)
RUNS: mock by default (no key). Mode "sdk" needs Claude Code logged in (Pro machine).

What the exam tests:
  * PreToolUse hook = intercept an OUTGOING tool call: block a policy violation
    (refund over $500) and redirect to another workflow (human escalation).
  * PostToolUse hook = intercept a tool RESULT before the model sees it: normalize
    heterogeneous formats (Unix timestamps, ISO 8601, numeric status codes).
  * Hooks give DETERMINISTIC guarantees; prompt instructions are probabilistic.
    Choose hooks whenever a business rule needs guaranteed compliance.

Run from the project root:
    python -m d1_agentic.d1_5_hooks             # both demos
    python -m d1_agentic.d1_5_hooks gate        # PreToolUse refund limit only
    python -m d1_agentic.d1_5_hooks normalize   # PostToolUse normalization only
    python -m d1_agentic.d1_5_hooks sdk         # real Agent SDK (Pro machine)
"""
import asyncio
import json
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone

try:
    from claude_agent_sdk import HookMatcher
except ImportError:  # keeps the mock runnable even if the SDK is missing
    @dataclass
    class HookMatcher:
        matcher: str = None
        hooks: list = field(default_factory=list)
        timeout: float = None

SERVER = "support"  # MCP tools are named mcp__<server>__<tool>
REFUND_LIMIT = 500
ISO = "%Y-%m-%dT%H:%M:%SZ"
ORDER_STATUS = {0: "pending", 1: "shipped", 2: "delivered", 3: "cancelled"}

# WRONG (exam distractor): a prompt rule such as "Never refund more than $500; escalate
# instead." is only a request. It has a non-zero failure rate, so a hook is required when
# the rule must ALWAYS hold. (1.4 enforced order inside our own tool executor; with the
# Agent SDK you do NOT own the loop, so hooks are the interception point.)


# ---------------------------------------------------------------------------
# PreToolUse: block and redirect (Task 1.5, refunds over $500)
# ---------------------------------------------------------------------------
async def refund_gate(input_data, tool_use_id, context):
    if input_data["hook_event_name"] != "PreToolUse":
        return {}
    amount = float(input_data["tool_input"].get("amount", 0))
    if amount > REFUND_LIMIT:
        return {
            "hookSpecificOutput": {
                "hookEventName": input_data["hook_event_name"],
                "permissionDecision": "deny",  # EXAM: deny beats allow if any hook denies
                # The reason goes to the MODEL. Tell it what to do instead (the redirect).
                "permissionDecisionReason": (
                    f"Refunds over ${REFUND_LIMIT} require human approval. Do not retry. "
                    "Call escalate_to_human with customer_id, root_cause, refund_amount "
                    "and recommended_action."
                ),
            }
        }
    return {}  # empty dict = allow, no changes


# ---------------------------------------------------------------------------
# PostToolUse: normalize heterogeneous formats before the model reasons over them
# ---------------------------------------------------------------------------
def normalize(obj, key=""):
    if isinstance(obj, dict):
        return {k: normalize(v, k) for k, v in obj.items()}
    if isinstance(obj, list):
        return [normalize(v, key) for v in obj]
    if key.endswith("_at") and isinstance(obj, (int, float)):  # Unix timestamp
        return datetime.fromtimestamp(obj, tz=timezone.utc).strftime(ISO)
    if key.endswith("_at") and isinstance(obj, str):  # ISO 8601 with any offset
        return datetime.fromisoformat(obj).astimezone(timezone.utc).strftime(ISO)
    if key == "status" and isinstance(obj, int):  # numeric status code
        return ORDER_STATUS.get(obj, f"unknown({obj})")
    return obj


def _load(resp):
    """The shape of tool_response varies by tool; inspect it on your machine."""
    if isinstance(resp, dict):
        return resp, "dict"
    if isinstance(resp, str):
        return json.loads(resp), "str"
    if isinstance(resp, list) and resp and isinstance(resp[0], dict) and "text" in resp[0]:
        return json.loads(resp[0]["text"]), "blocks"
    raise ValueError("unrecognized tool_response shape")


def _dump(obj, kind):
    if kind == "str":
        return json.dumps(obj)
    if kind == "blocks":
        return [{"type": "text", "text": json.dumps(obj)}]
    return obj


async def normalize_results(input_data, tool_use_id, context):
    if input_data["hook_event_name"] != "PostToolUse":
        return {}
    try:
        data, kind = _load(input_data["tool_response"])
    except (ValueError, TypeError):
        return {}  # never break the agent because a hook could not parse something
    return {
        "hookSpecificOutput": {
            "hookEventName": input_data["hook_event_name"],
            # EXAM: replaces the result BEFORE the model sees it
            "updatedToolOutput": _dump(normalize(data), kind),
        }
    }


# The SAME dict works in ClaudeAgentOptions(hooks=HOOKS). Matchers filter by TOOL NAME only.
HOOKS = {
    "PreToolUse": [HookMatcher(matcher=f"mcp__{SERVER}__process_refund", hooks=[refund_gate])],
    "PostToolUse": [HookMatcher(matcher=f"^mcp__{SERVER}__", hooks=[normalize_results])],
}


# ---------------------------------------------------------------------------
# Mock harness: what the SDK does around every tool call
# ---------------------------------------------------------------------------
def impl_lookup_order(args):
    # Two backends, two formats: Unix int + numeric status vs ISO string with an offset.
    # Both timestamps are the SAME instant; the model should not have to work that out.
    return {"order_id": args["order_id"], "status": 2, "created_at": 1751328000,
            "billing": {"charged_at": "2025-07-01T02:00:00+02:00", "status": "captured"}}


IMPLS = {
    "lookup_order": impl_lookup_order,
    "process_refund": lambda a: {"refund_id": "R-77", "amount": a["amount"]},
    "escalate_to_human": lambda a: {"status": "queued for human agent"},
}


def matching(event_name, tool_name):
    found = []
    for m in HOOKS.get(event_name, []):
        if m.matcher is None or re.search(m.matcher, tool_name):
            found.extend(m.hooks)
    return found


async def run_tool(short_name, tool_input):
    full = f"mcp__{SERVER}__{short_name}"
    pre = {"hook_event_name": "PreToolUse", "tool_name": full, "tool_input": tool_input}
    for cb in matching("PreToolUse", full):
        hso = (await cb(pre, "tu_1", None)).get("hookSpecificOutput", {})
        if hso.get("permissionDecision") == "deny":
            return {"blocked": True, "reason": hso["permissionDecisionReason"]}
    result = IMPLS[short_name](tool_input)
    post = {"hook_event_name": "PostToolUse", "tool_name": full,
            "tool_input": tool_input, "tool_response": result}
    for cb in matching("PostToolUse", full):
        hso = (await cb(post, "tu_1", None)).get("hookSpecificOutput", {})
        if "updatedToolOutput" in hso:
            result = hso["updatedToolOutput"]
    return result


async def demo_gate():
    print("== PreToolUse gate: refund limit ==")
    for amount in (59.90, 640.00):
        out = await run_tool("process_refund", {"order_id": "12345", "amount": amount})
        if out.get("blocked"):
            print(f"process_refund amount={amount} -> DENIED: {out['reason']}")
            esc = await run_tool("escalate_to_human", {"customer_id": "C-1001"})
            print(f"  (model follows the hook's instruction) escalate_to_human -> {json.dumps(esc)}")
        else:
            print(f"process_refund amount={amount} -> {json.dumps(out)}")


async def demo_normalize():
    print("\n== PostToolUse normalization ==")
    print("RAW from tool: ", json.dumps(impl_lookup_order({"order_id": "12345"})))
    print("AFTER hook:    ", json.dumps(await run_tool("lookup_order", {"order_id": "12345"})))


# ---------------------------------------------------------------------------
# REAL Agent SDK run (needs Claude Code installed and logged in)
# ---------------------------------------------------------------------------
async def run_sdk():
    from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient, create_sdk_mcp_server, tool

    def text(obj):
        return {"content": [{"type": "text", "text": json.dumps(obj)}]}

    @tool("lookup_order", "Look up an order by order_id.", {"order_id": str})
    async def lookup_order(args):
        return text(impl_lookup_order(args))

    @tool("process_refund", "Refund an order. Args: order_id, amount in USD.", {"order_id": str, "amount": float})
    async def process_refund(args):
        return text(IMPLS["process_refund"](args))

    @tool("escalate_to_human", "Hand off to a human. Args: customer_id.", {"customer_id": str})
    async def escalate_to_human(args):
        return text(IMPLS["escalate_to_human"](args))

    server = create_sdk_mcp_server(name=SERVER, version="1.0.0",
                                   tools=[lookup_order, process_refund, escalate_to_human])
    options = ClaudeAgentOptions(
        mcp_servers={SERVER: server},
        allowed_tools=[f"mcp__{SERVER}__{t}" for t in IMPLS],
        hooks=HOOKS,  # <- the same callbacks as the mock
    )
    async with ClaudeSDKClient(options=options) as client:
        await client.query("Customer C-1001 wants a $640 refund on order 12345. Handle it.")
        async for message in client.receive_response():
            print(message)


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "all"
    if mode == "sdk":
        asyncio.run(run_sdk())
    else:
        if mode in ("all", "gate"):
            asyncio.run(demo_gate())
        if mode in ("all", "normalize"):
            asyncio.run(demo_normalize())