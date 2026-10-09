# d1_agentic/d1_1_agentic_loop.py
"""
EXAM: Task 1.1 - Design and implement agentic loops for autonomous task execution
SCENARIO: 1 - Customer Support Resolution Agent (get_customer, lookup_order)
RUNS: mock mode (no API key needed)

What the exam tests:
  * Continue the loop while stop_reason == "tool_use"; stop on "end_turn".
  * Tool results are appended to the history so the model can reason about
    its next action (model-driven, NOT a pre-configured decision tree).
  * Anti-patterns: parsing text for "done", an iteration cap as the PRIMARY
    stop, or treating "the assistant produced text" as completion.

Run from the project root:
    python -m d1_agentic.d1_1_agentic_loop          # correct loop
    python -m d1_agentic.d1_1_agentic_loop wrong    # the anti-pattern
"""
import json
import sys

from common import MODEL, get_client

SYSTEM = "You are a customer support agent. Use the tools to look up facts before answering."

# Tool definitions. (Task 2.1 covers writing better descriptions.)
TOOLS = [
    {
        "name": "get_customer",
        "description": "Look up a customer by email address. Returns customer_id and name.",
        "input_schema": {
            "type": "object",
            "properties": {"email": {"type": "string"}},
            "required": ["email"],
        },
    },
    {
        "name": "lookup_order",
        "description": "Look up an order by order number, e.g. '12345'. Returns status and total.",
        "input_schema": {
            "type": "object",
            "properties": {"order_id": {"type": "string"}},
            "required": ["order_id"],
        },
    },
]


def run_tool(name: str, args: dict) -> dict:
    """Stubbed backend so you don't need real systems."""
    if name == "get_customer":
        return {"customer_id": "C-1001", "name": "Alex Doe", "email": args["email"]}
    if name == "lookup_order":
        return {"order_id": args["order_id"], "status": "delivered", "total_usd": 59.90}
    return {"error": f"unknown tool {name}"}


def execute_tools(response) -> list:
    """Run every tool_use block in this response and build the tool_result blocks."""
    results = []
    for block in response.content:
        if block.type == "tool_use":
            result = run_tool(block.name, block.input)
            results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": block.id,  # must match the request's id
                    "content": json.dumps(result),
                }
            )
    return results


# ---------------------------------------------------------------------------
# CORRECT: control flow driven by stop_reason
# ---------------------------------------------------------------------------
def agent_loop(user_message: str, max_iterations: int = 15) -> str:
    client = get_client()
    messages = [{"role": "user", "content": user_message}]

    # EXAM: the cap is only a BACKSTOP against runaway loops. It does not decide
    # when the task is finished; stop_reason does.
    for i in range(1, max_iterations + 1):
        response = client.messages.create(
            model=MODEL, max_tokens=1024, system=SYSTEM, tools=TOOLS, messages=messages
        )
        tool_names = [b.name for b in response.content if b.type == "tool_use"]
        print(f"[iteration {i}] stop_reason={response.stop_reason} tools={tool_names}")

        # EXAM: terminate on end_turn, and only on end_turn.
        if response.stop_reason == "end_turn":
            return "".join(b.text for b in response.content if b.type == "text")

        if response.stop_reason == "tool_use":
            # EXAM: keep the assistant turn in history so the model sees its own
            # tool request next to the result.
            messages.append({"role": "assistant", "content": response.content})
            # EXAM: ALL tool_result blocks for this turn go in ONE user message.
            messages.append({"role": "user", "content": execute_tools(response)})
            continue

        # max_tokens, refusal, etc. are not normal completion; surface them.
        raise RuntimeError(f"Unexpected stop_reason: {response.stop_reason}")

    raise RuntimeError("Hit the iteration backstop; investigate why the loop did not end.")


# ---------------------------------------------------------------------------
# WRONG (exam distractor): treats "assistant produced text" as completion
# ---------------------------------------------------------------------------
def wrong_loop(user_message: str) -> str:
    client = get_client()
    messages = [{"role": "user", "content": user_message}]
    for i in range(1, 16):
        response = client.messages.create(
            model=MODEL, max_tokens=1024, system=SYSTEM, tools=TOOLS, messages=messages
        )
        print(f"[iteration {i}] stop_reason={response.stop_reason}")

        # WRONG: Claude often writes text ("Let me look you up...") IN THE SAME
        # response as a tool_use block. Text present != task finished.
        text = "".join(b.text for b in response.content if b.type == "text")
        if text:
            return text

        messages.append({"role": "assistant", "content": response.content})
        messages.append({"role": "user", "content": execute_tools(response)})
    return ""


# Two more anti-patterns from the guide (shown as comments, do not use):
#   * Parsing natural language for termination:  if "done" in text.lower(): break
#     Fragile: wording varies, and "done" can appear mid-task.
#   * A small cap as the primary stop:  for _ in range(3): ...
#     Cuts off legitimate work, or keeps running after the task is finished.

if __name__ == "__main__":
    question = "Hi, I'm alex@example.com. Can you check on order #12345?"
    if len(sys.argv) > 1 and sys.argv[1] == "wrong":
        print("\nWRONG LOOP RESULT:\n", wrong_loop(question))
    else:
        print("\nFINAL ANSWER:\n", agent_loop(question))