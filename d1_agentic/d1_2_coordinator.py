# d1_agentic/d1_2_coordinator.py
"""
EXAM: Task 1.2 - Orchestrate multi-agent systems with coordinator-subagent patterns
SCENARIO: 3 - Multi-Agent Research System (sample Q7: "impact of AI on creative industries")
RUNS: mock mode (no API key needed)

What the exam tests:
  * Hub-and-spoke: the coordinator decomposes, delegates, aggregates, and routes
    ALL communication. Subagents never talk to each other.
  * Subagents have ISOLATED context: they do not inherit the coordinator's history.
  * Too-narrow decomposition is the root cause when every subagent "works" but the
    report has missing coverage (sample Q7, answer B).
  * Refinement loop: evaluate coverage, re-delegate targeted gaps, repeat until
    covered (with a round limit as a backstop).

Run from the project root:
    python -m d1_agentic.d1_2_coordinator narrow    # the Q7 bug
    python -m d1_agentic.d1_2_coordinator fixed     # root-cause fix: better decomposition
    python -m d1_agentic.d1_2_coordinator refine    # bad decomposition rescued by the gap loop
"""
import json
import sys

from common import MODEL, FakeResponse, TextBlock, get_client

TOPIC = "impact of AI on creative industries"
MAX_ROUNDS = 4  # EXAM: a backstop for the refinement loop, not the stop condition

# EXAM: coordinator prompts state GOALS and QUALITY CRITERIA ("cover all major
# sectors"), not step-by-step procedures, so the model can adapt.
DECOMPOSE_SYSTEM = (
    "You are a research coordinator. Split the topic into distinct, non-overlapping "
    "subtopics that together cover ALL major sectors of the topic. "
    'Return ONLY JSON: {"subtasks": ["..."]}'
)
RESEARCH_SYSTEM = (
    "You are a research subagent. Research ONLY the subtopic you are given. "
    "Reply with 2-3 sentences of findings and one source."
)
EVAL_SYSTEM = (
    "You are a coverage reviewer. Given the topic and the findings so far, list "
    'subtopics that are still MISSING. Return ONLY JSON: {"gaps": ["..."]}. '
    "Use an empty list if coverage is sufficient."
)
SYNTH_SYSTEM = "You are a synthesis agent. Write a short report using ONLY the findings provided."


def ask(client, system: str, user: str) -> str:
    """One isolated call.

    EXAM: isolation is visible here. `messages` is built fresh for every call, so a
    subagent sees ONLY what the coordinator puts in `user`. It has no access to the
    coordinator's history or to other subagents' work.
    """
    response = client.messages.create(
        model=MODEL,
        max_tokens=1024,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    return "".join(b.text for b in response.content if b.type == "text")


def parse_json(raw: str) -> dict:
    """Real models sometimes wrap JSON in code fences; strip them."""
    return json.loads(raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```"))


# --- The spokes -------------------------------------------------------------
def decompose(client, topic: str) -> list:
    return parse_json(ask(client, DECOMPOSE_SYSTEM, f"Topic: {topic}"))["subtasks"]


def research(client, subtask: str) -> str:
    print(f"  [subagent] {subtask}")
    return ask(client, RESEARCH_SYSTEM, f"Subtopic: {subtask}")


def evaluate_coverage(client, topic: str, findings: dict) -> list:
    # EXAM: the coordinator passes the findings explicitly in the prompt.
    user = f"Topic: {topic}\nFindings so far:\n{json.dumps(findings, indent=2)}"
    return parse_json(ask(client, EVAL_SYSTEM, user))["gaps"]


# --- The hub ----------------------------------------------------------------
def coordinator(client, topic: str, check_coverage: bool) -> str:
    subtasks = decompose(client, topic)
    print(f"[coordinator] subtasks: {subtasks}")

    # EXAM: partition the scope so subagents don't duplicate work; each gets a
    # distinct subtopic. All results come back to the coordinator (the hub).
    findings = {s: research(client, s) for s in subtasks}

    if check_coverage:
        for round_no in range(1, MAX_ROUNDS + 1):
            gaps = evaluate_coverage(client, topic, findings)
            print(f"[coordinator] coverage round {round_no}: gaps = {gaps}")
            if not gaps:
                break
            for gap in gaps:
                findings[gap] = research(client, gap)
        else:
            # EXAM (5.3): never hide incomplete coverage. Report it.
            print("[coordinator] WARNING: round limit reached; coverage NOT re-verified")

    print(f"\nSubtopics investigated ({len(findings)}): {list(findings)}")
    # EXAM: subagents don't share memory, so the synthesis agent gets the complete
    # findings directly in its prompt.
    return ask(client, SYNTH_SYSTEM, f"Findings:\n{json.dumps(findings, indent=2)}")


# --- Mock scripts (replayed in order by the fake client) --------------------
NARROW = ["AI in digital art creation", "AI in graphic design", "AI in photography"]
BROAD = NARROW + ["AI in music production", "AI in writing and publishing", "AI in film production"]


def mk(text: str) -> FakeResponse:
    return FakeResponse([TextBlock(text)], "end_turn")


def finding(sub: str) -> FakeResponse:
    return mk(f"Finding on '{sub}': adoption is growing. (source: example.com/{sub.split()[-1]})")


def script_narrow():
    return ([mk(json.dumps({"subtasks": NARROW}))]
            + [finding(s) for s in NARROW]
            + [mk("REPORT covering: " + ", ".join(NARROW))])


def script_fixed():
    return ([mk(json.dumps({"subtasks": BROAD}))]
            + [finding(s) for s in BROAD]
            + [mk("REPORT covering: " + ", ".join(BROAD))])


def script_refine():
    gaps = BROAD[3:]
    return ([mk(json.dumps({"subtasks": NARROW}))]
            + [finding(s) for s in NARROW]
            + [mk(json.dumps({"gaps": gaps}))]
            + [finding(s) for s in gaps]
            + [mk(json.dumps({"gaps": []}))]
            + [mk("REPORT covering: " + ", ".join(BROAD))])


MODES = {
    # mode: (mock script, run the coverage loop?)
    "narrow": (script_narrow, False),  # EXAM Q7: subagents fine, decomposition too narrow
    "fixed": (script_fixed, False),    # root-cause fix: decomposition covers every sector
    "refine": (script_refine, True),   # safety net: gap loop catches the narrow decomposition
}

if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "narrow"
    make_script, check = MODES[mode]
    print(f"MODE: {mode}\n")
    report = coordinator(get_client(make_script()), TOPIC, check_coverage=check)
    print("\nREPORT:\n", report)