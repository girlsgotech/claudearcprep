# =====================================================================
# HOW TO RUN THIS FILE (VS Code)
#   1. Open the PROJECT ROOT folder (claude-architect-prep) in VS Code.
#   2. Open a terminal (Ctrl+`) and activate the virtual environment:
#        Linux/macOS : source .venv/bin/activate
#        Windows     : .venv\Scripts\Activate.ps1
#   3. From the project root (NOT from inside d5_context), run:
#        python -m d5_context.d5_4_large_codebase
#   4. Requirements: Python 3.10+, standard library only, no API key.
#      d5_context/ must contain an (empty) __init__.py file.
#      It writes scratchpad and state files to a temporary folder and deletes them.
#   5. Save the file first (Ctrl+S). A dot on the tab means unsaved.
# =====================================================================
"""
Task 5.4  Manage context effectively in large codebase exploration
Scenarios 4 (Developer Productivity) and 2 (Code Generation with Claude Code)
RUNS: mock (scripted answers, token counts are a rough chars/4 estimate)

What this file shows
  1. Delegate verbose exploration to a subagent; the main context keeps only a summary.
  2. A scratchpad file keeps specific findings when the context degrades or is compacted.
  3. Inject a phase summary into the next phase's subagent instead of re-exploring.
  4. Crash recovery: each agent exports state, the coordinator loads a manifest on resume.
  5. /compact: shrink a context full of discovery output.
"""
import json
import tempfile
from pathlib import Path


def tokens(text):
    return len(text) // 4        # rough estimate, good enough to compare sizes


# ------------------------------------------------- FAKE CODEBASE
KEY_LINES = [
    "api/refunds.py:42: def create_refund(...)  -> RefundController.create",
    "billing/refund_service.py:88: RefundService.process(order_id, amount)",
    "billing/gateway.py:131: PaymentGateway.charge_back(order_id, amount)",
    "audit/log.py:20: AuditLog.record(event)",
]
FINDINGS = {
    "entry_point": "api/refunds.py::create_refund",
    "flow": "RefundController.create -> RefundService.process -> PaymentGateway.charge_back -> AuditLog.record",
    "tests": ["tests/billing/test_refund_service.py", "tests/api/test_refunds.py"],
    "dependencies": ["PaymentGateway -> StripeClient", "AuditLog -> events_queue"],
}


def verbose_discovery():
    """What a broad Grep + Read pass over a big codebase prints: mostly noise."""
    lines = [f"src/module_{m:02d}/handler.py:{n * 7}: refund = self._helper_{n}(order, ctx)  # plumbing"
             for m in range(1, 41) for n in range(1, 26)]
    mid = len(lines) // 2
    lines[mid:mid] = KEY_LINES      # the few lines that matter sit in the middle
    return "\n".join(lines)


QUESTION = "Trace the refund flow and find its tests."


# ------------------------------------------------- 1. SUBAGENT DELEGATION
def explore_subagent():
    # EXAM: the subagent reads the verbose output in ITS OWN context and returns a summary.
    raw = verbose_discovery()
    return FINDINGS, tokens(raw)


# ------------------------------------------------- 2. SCRATCHPAD + DEGRADATION
def write_scratchpad(path):
    path.write_text(
        "# Scratchpad: refund flow\n"
        f"- Entry point: {FINDINGS['entry_point']}\n"
        f"- Flow: {FINDINGS['flow']}\n"
        f"- Tests: {', '.join(FINDINGS['tests'])}\n"
        f"- Dependencies: {', '.join(FINDINGS['dependencies'])}\n")


def answer(question, context):
    """Scripted stand-in. A real model drifts to generic answers as context fills or is cleared."""
    if "RefundService.process" in context:
        return FINDINGS["flow"]
    # EXAM: context degradation = "typical patterns" instead of the specific classes found earlier.
    return "Typically a controller calls a service layer, which calls a payment provider."


# ------------------------------------------------- 3. PHASE SUMMARY INJECTION
def phase2_prompt(question, summary):
    # EXAM: summarize phase 1 findings, then INJECT them into the next subagent's prompt.
    if summary is None:
        return "Continue the investigation of the refund flow."          # WRONG (exam distractor)
    return f"<prior_findings>\n{json.dumps(summary)}\n</prior_findings>\n{question}"


# ------------------------------------------------- 4. MANIFEST + CRASH RECOVERY
AGENTS = ["find_tests", "trace_refund_flow", "map_dependencies", "summarize_api"]
AGENT_OUTPUT = {"find_tests": FINDINGS["tests"], "trace_refund_flow": FINDINGS["flow"],
                "map_dependencies": FINDINGS["dependencies"], "summarize_api": "3 public refund endpoints"}


class SimulatedCrash(Exception):
    pass


def run_pipeline(state_dir, crash_before=None, resume=False):
    manifest_path = state_dir / "manifest.json"
    if resume and manifest_path.exists():
        manifest = json.loads(manifest_path.read_text())      # EXAM: coordinator loads the manifest
    else:
        manifest = {"agents": {a: {"status": "pending"} for a in AGENTS}}
    prior = {a: json.loads((state_dir / i["state_file"]).read_text())
             for a, i in manifest["agents"].items() if i["status"] == "done"}
    ran, skipped, results = [], [a for a in AGENTS if a in prior], {}
    for a in AGENTS:
        if a in prior:
            continue
        if a == crash_before:
            raise SimulatedCrash(a)
        # EXAM: completed agents' state is injected into the next agent's prompt
        result = {"agent": a, "output": AGENT_OUTPUT[a], "saw_prior": sorted(prior)}
        (state_dir / f"{a}.json").write_text(json.dumps(result))              # agent exports its state
        manifest["agents"][a] = {"status": "done", "state_file": f"{a}.json"}
        manifest_path.write_text(json.dumps(manifest))                         # durable after EACH agent
        prior[a], results[a] = result, result
        ran.append(a)
    return ran, skipped, results


# ------------------------------------------------- 5. /compact
def compact(history, scratchpad_name):
    # What /compact does conceptually: replace verbose history with a short summary.
    summary = f"[compacted] key findings are in {scratchpad_name}. Flow: {FINDINGS['flow']}"
    return [{"role": "user", "content": summary}] + history[-1:]


def main():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)

        print("== 1. Delegate verbose exploration to a subagent ==")
        raw_tokens = tokens(verbose_discovery())
        summary, sub_tokens = explore_subagent()
        direct = tokens(QUESTION) + raw_tokens
        delegated = tokens(QUESTION) + tokens(json.dumps(summary))
        print(f"WRONG main agent explores directly : main context ~{direct:,} tokens (40 files of raw output)")
        print(f"RIGHT main agent delegates         : main context ~{delegated:,} tokens (structured summary only)")
        print(f"subagent's own context (discarded) : ~{sub_tokens:,} tokens")
        print(f"main context reduced by {100 * (1 - delegated / direct):.1f}%")

        print("\n== 2. Scratchpad file counters context degradation ==")
        pad = tmp / "scratchpad.md"
        write_scratchpad(pad)
        print(f"scratchpad written: {pad.name}, {tokens(pad.read_text())} tokens, {len(pad.read_text().splitlines())} lines")
        print("after a long session or a context reset (scripted answers):")
        print(f"WRONG no scratchpad : {answer('How does a refund flow through the code?', 'only the question')}")
        print(f"RIGHT reads {pad.name}: {answer('How does a refund flow through the code?', pad.read_text())}")

        print("\n== 3. Inject the phase 1 summary into the phase 2 subagent ==")
        for label, s in (("WRONG no context", None), ("RIGHT summary injected", summary)):
            p = phase2_prompt("Now find which callers need updating.", s)
            has = "RefundService.process" in p
            print(f"{label:<23}: prompt ~{tokens(p)} tokens, knows the specific classes: {has}"
                  f"{'' if has else ' -> must re-explore from scratch'}")

        print("\n== 4. Manifest-based crash recovery ==")
        crash_dir = tmp / "run1"
        crash_dir.mkdir()
        try:
            run_pipeline(crash_dir, crash_before="map_dependencies")
        except SimulatedCrash as e:
            print(f"first run crashed before '{e}'")
        manifest = json.loads((crash_dir / "manifest.json").read_text())
        print("manifest on disk: " + ", ".join(f"{a}={i['status']}" for a, i in manifest["agents"].items()))
        ran, skipped, results = run_pipeline(crash_dir, resume=True)
        print(f"RIGHT resume: loaded state for {skipped}, re-ran only {ran}")
        print(f"  map_dependencies prompt included prior findings from: {results['map_dependencies']['saw_prior']}")
        fresh = tmp / "run2"
        fresh.mkdir()
        ran_all, _, _ = run_pipeline(fresh)
        print(f"WRONG restart from scratch: re-ran all {len(ran_all)} agents")

        print("\n== 5. /compact when context fills with discovery output ==")
        raw = verbose_discovery()
        history = [{"role": "user", "content": QUESTION}, {"role": "tool", "content": raw},
                   {"role": "assistant", "content": "Found the flow."},
                   {"role": "user", "content": "Now find the tests."}, {"role": "tool", "content": raw},
                   {"role": "assistant", "content": "Found two test files."}]
        before = sum(tokens(m["content"]) for m in history)
        small = compact(history, pad.name)
        after = sum(tokens(m["content"]) for m in small)
        print(f"history ~{before:,} tokens -> ~{after:,} tokens after compact")
        print(f"specific classes survive in the summary: {'RefundService.process' in small[0]['content']}")


if __name__ == "__main__":
    main()