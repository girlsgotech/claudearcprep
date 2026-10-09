# d1_agentic/d1_3_subagents.py
"""
EXAM: Task 1.3 - Configure subagent invocation, context passing, and spawning
SCENARIO: 3 - Multi-Agent Research System (web search, document analysis, synthesis)
RUNS: mock by default (no key). Mode "sdk" needs Claude Code logged in (Pro machine).

What the exam tests:
  * The Task tool spawns subagents, and "Task" must be in allowedTools for the
    coordinator to use it. (Current SDK docs call it "Agent"; exam says "Task".)
  * AgentDefinition = description + system prompt + tool restrictions per subagent.
  * Subagent context is ISOLATED: findings must be passed explicitly in the prompt.
  * Use structured data that separates content from metadata (source, page, date)
    so attribution survives handoffs.
  * PARALLEL spawn = several Task calls in ONE coordinator response, not across turns.
  * Coordinator prompts state goals and quality criteria, not step-by-step procedure.

Run from the project root:
    python -m d1_agentic.d1_3_subagents               # parallel spawn (correct)
    python -m d1_agentic.d1_3_subagents sequential    # one Task per turn (slower)
    python -m d1_agentic.d1_3_subagents wrong         # assumes context inheritance
    python -m d1_agentic.d1_3_subagents sdk           # real Agent SDK (Pro machine)
"""
import asyncio
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor

from common import FakeResponse, TextBlock, ToolUseBlock

# EXAM: the exam guide says "Task". Newer SDK versions emit "Agent". Match both.
SUBAGENT_TOOL_NAMES = ("Task", "Agent")

# ---------------------------------------------------------------------------
# AgentDefinition specs: description, prompt, tools (Scenario 3's subagents)
# ---------------------------------------------------------------------------
SPECS = {
    "web-searcher": {
        # EXAM: the description is how the coordinator decides WHEN to use this agent.
        "description": "Searches the web for sources on ONE subtopic. Use for news, reports, statistics.",
        "prompt": "You are a web research subagent. Research ONLY the subtopic you are given. "
                  "Return a JSON list of findings: claim, evidence, meta{source, page, published}.",
        "tools": ["WebSearch", "WebFetch"],  # EXAM: only what this role needs (see 2.3)
    },
    "doc-analyzer": {
        "description": "Analyzes provided documents for findings. Use for PDFs and reports.",
        "prompt": "You are a document analysis subagent. Analyze ONLY the document you are given. "
                  "Return a JSON list of findings: claim, evidence, meta{source, page, published}.",
        "tools": ["Read", "Grep", "Glob"],
    },
    "synthesizer": {
        "description": "Combines findings into a cited report. Use after research is complete.",
        "prompt": "You write a short cited report using ONLY the findings in your prompt. "
                  "Keep each claim's source and date.",
        "tools": ["Read"],  # no web tools: a synthesis agent that searches is misusing tools
    },
}

# EXAM (skill): coordinator prompt = GOALS and QUALITY CRITERIA, not a procedure.
COORD_PROMPT = (
    "You coordinate research on a topic and deliver a cited report. Quality criteria: "
    "every claim has a source and date; all major sectors are covered. Delegate independent "
    "work to subagents in parallel by issuing ALL those Task calls in ONE response. Pass "
    "complete findings to the synthesizer inside its prompt; it cannot see your conversation."
)


# ---------------------------------------------------------------------------
# Mock subagents (deterministic stand-ins for real model calls)
# ---------------------------------------------------------------------------
def mock_subagent(name: str, prompt: str) -> str:
    if name == "web-searcher":
        time.sleep(1)  # simulated work, so you can SEE parallel vs sequential timing
        return json.dumps([
            {"claim": "Generative tools are now used in music production workflows",
             "evidence": "Three studios reported adoption in 2025.",
             "meta": {"source": "https://example.com/music-ai", "page": None, "published": "2026-03-14"}},
            {"claim": "Film studios use AI for previsualization",
             "evidence": "Vendor survey of 40 productions.",
             "meta": {"source": "https://example.com/film-ai", "page": None, "published": "2025-09-01"}},
        ])
    if name == "doc-analyzer":
        time.sleep(1)
        return json.dumps([
            {"claim": "Writers report mixed effects on income",
             "evidence": "Survey table 4.",
             "meta": {"source": "survey-report.pdf", "page": 12, "published": "2025-11-02"}},
        ])
    if name == "synthesizer":
        # EXAM: isolation is enforced HERE. The synthesizer sees ONLY its prompt.
        if "FINDINGS_JSON:" not in prompt:
            return "I cannot see any findings. (Subagents do not inherit the coordinator's history.)"
        data = json.loads(prompt.split("FINDINGS_JSON:\n", 1)[1])
        return "\n".join(f"- {f['claim']} [{f['meta']['source']}, {f['meta']['published']}]" for f in data)
    raise ValueError(name)


def run_subagent(name: str, prompt: str) -> str:
    spec = SPECS[name]
    print(f"  [spawn] {name} tools={spec['tools']} prompt_chars={len(prompt)}")
    return mock_subagent(name, prompt)


def dispatch(response, parallel: bool = True) -> list:
    """Run every Task call found in ONE coordinator response."""
    calls = [b for b in response.content if b.type == "tool_use" and b.name in SUBAGENT_TOOL_NAMES]
    print(f"[coordinator] {len(calls)} subagent call(s) in this response")
    jobs = [(c.input["subagent_type"], c.input["prompt"]) for c in calls]
    # EXAM: several Task calls in the SAME response can run concurrently.
    if parallel and len(jobs) > 1:
        with ThreadPoolExecutor() as pool:
            return list(pool.map(lambda j: run_subagent(*j), jobs))
    return [run_subagent(*j) for j in jobs]


def run_mock(mode: str) -> None:
    search = ToolUseBlock("t1", "Task", {"subagent_type": "web-searcher",
                                         "prompt": "Subtopic: AI in music and film production. Return findings as JSON."})
    docs = ToolUseBlock("t2", "Task", {"subagent_type": "doc-analyzer",
                                       "prompt": "Analyze survey-report.pdf for AI impact on writers. Return findings as JSON."})
    start = time.time()
    if mode == "sequential":
        # WRONG (exam distractor): one Task call per turn means the tasks run one after another.
        results = dispatch(FakeResponse([TextBlock("Searching first."), search], "tool_use"))
        results += dispatch(FakeResponse([docs], "tool_use"))
    else:
        # CORRECT: independent tasks emitted together in a single response.
        results = dispatch(FakeResponse([TextBlock("Both tasks are independent; spawning together."),
                                         search, docs], "tool_use"))
    print(f"[coordinator] research phase took {time.time() - start:.1f}s")

    findings = [f for r in results for f in json.loads(r)]  # content + meta kept separate
    if mode == "wrong":
        # WRONG (exam distractor): assumes the subagent inherits the coordinator's context.
        prompt = "Synthesize the findings above into a short cited report."
    else:
        # CORRECT: complete findings, with source metadata, go directly in the prompt.
        # (In production the coordinator LLM writes this prompt; we build it in code.)
        prompt = ("Write a short cited report using ONLY these findings. Keep each source and date.\n"
                  "FINDINGS_JSON:\n" + json.dumps(findings, indent=2))
    out = dispatch(FakeResponse([ToolUseBlock("t3", "Task", {"subagent_type": "synthesizer",
                                                             "prompt": prompt})], "tool_use"))
    print("\nREPORT:\n" + out[0])


# ---------------------------------------------------------------------------
# REAL Agent SDK version (needs Claude Code installed and logged in)
# ---------------------------------------------------------------------------
async def run_sdk() -> None:
    from claude_agent_sdk import AgentDefinition, ClaudeAgentOptions, ToolUseBlock as SdkToolUse, query

    options = ClaudeAgentOptions(
        system_prompt=COORD_PROMPT,
        # EXAM: without the Task tool in allowed tools, the coordinator CANNOT spawn subagents.
        # "Task" = exam / older SDKs; "Agent" = current SDKs. Listing both is harmless.
        allowed_tools=["Task", "Agent", "Read"],
        agents={name: AgentDefinition(**spec) for name, spec in SPECS.items()},
    )
    async for message in query(prompt="Research the impact of AI on creative industries.", options=options):
        for block in getattr(message, "content", None) or []:
            if isinstance(block, SdkToolUse) and block.name in SUBAGENT_TOOL_NAMES:
                print(f"[spawn] {block.input.get('subagent_type')}")
        if hasattr(message, "result"):
            print("\nREPORT:\n", message.result)


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "parallel"
    if mode == "sdk":
        asyncio.run(run_sdk())
    else:
        run_mock(mode)