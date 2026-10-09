# d2_tools/d2_2_error_responses.py
"""
EXAM: Task 2.2 - Implement structured error responses for MCP tools
SCENARIOS: 1 - Customer Support (lookup_order, process_refund)
           3 - Multi-Agent Research (web search subagent, local recovery)
RUNS: mock (no API key). Deterministic backends stand in for real services.

What the exam tests:
  * MCP signals a failed tool call with the isError flag on the tool result.
  * Error categories: transient (timeout, service down), validation (bad input),
    business (policy violation), permission. Each needs a DIFFERENT recovery.
  * A uniform "Operation failed" hides the category, so the agent cannot choose
    between retry, fix the input, explain to the customer, or escalate.
  * Return errorCategory + isRetryable + a readable message. For business-rule
    violations also return a customer-friendly explanation and isRetryable=False.
  * An ACCESS FAILURE (timeout, needs a retry decision) is not a VALID EMPTY RESULT
    (the query worked and found nothing). Never confuse the two.
  * Subagents recover from transient failures LOCALLY and propagate to the coordinator
    only what they cannot fix, with partial results and what was attempted.

Naming note: the exam guide writes both isRetryable and "retriable: false". This file
uses isRetryable everywhere. The MCP field is isError; some SDK helpers spell it is_error,
so check the docs for the SDK version you use.

Run from the project root:
    python -m d2_tools.d2_2_error_responses            # all demos
    python -m d2_tools.d2_2_error_responses generic    # generic vs structured errors
    python -m d2_tools.d2_2_error_responses empty      # access failure vs valid empty
    python -m d2_tools.d2_2_error_responses subagent   # local recovery + propagation
"""
import json
import re
import sys

MAX_ATTEMPTS = 3  # production code would also back off between retries


# ---------------------------------------------------------------------------
# MCP-shaped results
# ---------------------------------------------------------------------------
def ok(data):
    return {"isError": False, "content": [{"type": "text", "text": json.dumps(data)}]}


def err(category, message, retryable, customer_message=None):
    body = {"errorCategory": category, "isRetryable": retryable, "message": message}
    if customer_message:
        body["customerMessage"] = customer_message
    return {"isError": True, "content": [{"type": "text", "text": json.dumps(body)}]}


def payload(result):
    return json.loads(result["content"][0]["text"])


def generic_error(result):
    """WRONG (exam distractor): throw the category away."""
    return {"isError": True, "content": [{"type": "text", "text": "Operation failed"}]}


# ---------------------------------------------------------------------------
# Stub backends (state["timeouts_left"] simulates a flaky service)
# ---------------------------------------------------------------------------
def lookup_order(args, state):
    if state["timeouts_left"] > 0:
        state["timeouts_left"] -= 1
        return err("transient", "Order service timed out", True)
    order_id = args["order_id"]
    if not re.fullmatch(r"\d{5}", order_id):
        return err("validation", "order_id must be exactly 5 digits, e.g. 12345", False)
    if order_id == "99999":
        return err("permission", "This order belongs to a different customer", False)
    return ok({"order_id": order_id, "status": "delivered", "age_days": 45})


def process_refund(args, state):
    order = payload(lookup_order(args, state))  # 45 days old in this stub
    if order["age_days"] > 30:
        return err("business", "Refund window of 30 days has passed", False,
                   customer_message="Orders older than 30 days can't be refunded automatically. "
                                    "I can connect you with a specialist to review options.")
    return ok({"refund_id": "R-77"})


ORDERS_BY_CUSTOMER = {"C-1001": ["12345"], "C-2002": []}  # C-2002 genuinely has no orders


def search_orders(args, state):
    if state["timeouts_left"] > 0:
        state["timeouts_left"] -= 1
        return err("transient", "Order search timed out", True)
    matches = ORDERS_BY_CUSTOMER.get(args["customer_id"], [])
    return ok({"customer_id": args["customer_id"], "matches": matches})


# ---------------------------------------------------------------------------
# Demo 1: generic vs structured errors
# ---------------------------------------------------------------------------
CASES = [
    ("transient timeout", lambda s: lookup_order({"order_id": "12345"}, s), 2),
    ("validation (bad id)", lambda s: lookup_order({"order_id": "12-45"}, s), 0),
    ("permission", lambda s: lookup_order({"order_id": "99999"}, s), 0),
    ("business rule", lambda s: process_refund({"order_id": "12345"}, s), 0),
]

ACTIONS = {
    "validation": lambda p: f"repair the input ({p['message']}) and call again",
    "permission": lambda p: "stop, do not retry; escalate (no access)",
    "business": lambda p: f"stop; tell the customer: \"{p['customerMessage']}\"",
}


def naive(call, state):
    """WRONG: every failure looks the same, so the only option is to retry."""
    for attempt in range(1, MAX_ATTEMPTS + 1):
        if not call(state)["isError"]:
            return attempt, "ok"
    return MAX_ATTEMPTS, "gave up: 'Operation failed' (why? nobody knows)"


def structured(call, state):
    for attempt in range(1, MAX_ATTEMPTS + 1):
        result = call(state)
        if not result["isError"]:
            return attempt, "ok"
        p = payload(result)
        if p["isRetryable"]:  # only transient errors are worth retrying
            continue
        return attempt, ACTIONS[p["errorCategory"]](p)
    return MAX_ATTEMPTS, "transient failure persisted -> propagate structured error upward"


def demo_generic():
    print("== Generic vs structured errors ==")
    print(f"{'case':22}{'naive':8}{'structured':12}action taken")
    for name, call, timeouts in CASES:
        n_attempts, _ = naive(call, {"timeouts_left": timeouts})
        s_attempts, action = structured(call, {"timeouts_left": timeouts})
        print(f"{name:22}{n_attempts:<8}{s_attempts:<12}{action}")
    print("\nThe same validation error, seen by the agent:")
    bad = lookup_order({"order_id": "12-45"}, {"timeouts_left": 0})
    print("  generic   :", generic_error(bad)["content"][0]["text"])
    print("  structured:", bad["content"][0]["text"])


# ---------------------------------------------------------------------------
# Demo 2: access failure vs valid empty result
# ---------------------------------------------------------------------------
def interpret(result):
    if result["isError"]:
        p = payload(result)
        return f"ACCESS FAILURE ({p['errorCategory']}, retryable={p['isRetryable']}): do NOT say the customer has no orders"
    matches = payload(result)["matches"]
    return "VALID EMPTY RESULT: tell the customer no orders were found (do not retry)" if not matches \
        else f"FOUND {matches}"


def swallow(result):
    """WRONG (exam anti-pattern): hide the failure by returning an empty success."""
    return ok({"matches": []}) if result["isError"] else result


def demo_empty():
    print("\n== Access failure vs valid empty result ==")
    print("C-1001      :", interpret(search_orders({"customer_id": "C-1001"}, {"timeouts_left": 0})))
    print("C-2002      :", interpret(search_orders({"customer_id": "C-2002"}, {"timeouts_left": 0})))
    print("timeout     :", interpret(search_orders({"customer_id": "C-1001"}, {"timeouts_left": 1})))
    swallowed = swallow(search_orders({"customer_id": "C-1001"}, {"timeouts_left": 1}))
    print("WRONG swallow:", interpret(swallowed), " <-- a real customer told they have no orders")


# ---------------------------------------------------------------------------
# Demo 3: local recovery in a subagent, propagate only what cannot be fixed
# ---------------------------------------------------------------------------
def web_search(query, state):
    if state["timeouts_left"] > 0:
        state["timeouts_left"] -= 1
        return err("transient", f"Search timed out for '{query}'", True)
    return ok({"results": [f"finding about {query}"]})


def research_subagent(queries, states):
    results, failures = {}, []
    for q in queries:
        for attempt in range(1, MAX_ATTEMPTS + 1):
            r = web_search(q, states[q])
            if not r["isError"]:
                results[q] = payload(r)["results"]  # recovered LOCALLY if earlier attempts timed out
                break
            p = payload(r)
            if not p["isRetryable"]:
                failures.append({"failureType": p["errorCategory"], "attemptedQuery": q, "attempts": attempt})
                break
        else:  # all attempts failed: only NOW does the coordinator need to know
            failures.append({
                "failureType": p["errorCategory"],
                "attemptedQuery": q,
                "attempts": MAX_ATTEMPTS,
                "alternatives": ["retry later", "try a narrower query", "use cached sources"],
            })
    status = "ok" if not failures else ("partial" if results else "failed")
    return {"status": status, "results": results, "failures": failures}


def demo_subagent():
    print("\n== Subagent: local recovery vs propagation ==")
    qs = ["AI in music", "AI in film"]
    a = research_subagent(qs, {"AI in music": {"timeouts_left": 0}, "AI in film": {"timeouts_left": 1}})
    print("A) one transient timeout -> coordinator sees only:", a["status"], list(a["results"]))
    b = research_subagent(qs, {"AI in music": {"timeouts_left": 0}, "AI in film": {"timeouts_left": 99}})
    print("B) film stays down -> coordinator receives structured context:")
    print(json.dumps(b, indent=2))


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "all"
    if mode in ("all", "generic"):
        demo_generic()
    if mode in ("all", "empty"):
        demo_empty()
    if mode in ("all", "subagent"):
        demo_subagent()