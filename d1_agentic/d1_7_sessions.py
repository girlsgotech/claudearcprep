# d1_agentic/d1_7_sessions.py
"""
EXAM: Task 1.7 - Manage session state, resumption, and forking
SCENARIO: 4 - Developer Productivity (exploring a codebase over several work sessions)
RUNS: mock by default (no key). Mode "sdk" needs Claude Code logged in (Pro machine).

What the exam tests:
  * Named session resumption:  claude --resume <session-name>  continues a specific
    earlier conversation with its full context.
  * fork_session: independent branches from a SHARED analysis baseline, e.g. to compare
    two testing strategies or two refactoring approaches.
  * After code changes, a resumed session holds STALE tool results. Either resume AND tell
    the agent exactly which files changed (targeted re-analysis), or start a NEW session
    seeded with a structured summary when prior results are mostly stale.

Run from the project root:
    python -m d1_agentic.d1_7_sessions            # all mock demos
    python -m d1_agentic.d1_7_sessions fork       # resume by name + fork only
    python -m d1_agentic.d1_7_sessions stale      # stale-result demo only
    python -m d1_agentic.d1_7_sessions sdk        # real Agent SDK (Pro machine)

CLI cheat sheet (terminal, Claude Code):
    claude --resume auth-investigation     # named session from the exam guide
    (SDK equivalents: resume=<session_id>, fork_session=True, see run_sdk below)
"""
import asyncio
import copy
import itertools
import json
import sys

DISK = {"auth.py": 1, "tokens.py": 1, "routes.py": 1}  # file -> version currently on disk
STORE = {}
_ids = itertools.count(1)


def reset():
    global _ids
    STORE.clear()
    _ids = itertools.count(1)


class Session:
    """SIMULATED session: a history plus the file versions its tool results came from."""

    def __init__(self, name, history=None, seen=None):
        self.id = f"sess-{next(_ids)}"
        self.name = name
        self.history = history or []   # messages and tool results
        self.seen = seen or {}         # file -> version at the time the tool result was stored

    def read_file(self, path, disk):
        self.seen[path] = disk[path]
        self.history.append(f"tool_result: read {path} (v{disk[path]})")

    def note(self, text):
        self.history.append(f"user: {text}")


def register(s):
    STORE[s.name] = s
    STORE[s.id] = s
    return s


def start(name):
    return register(Session(name))


def resume(key):
    # EXAM: resume = SAME session, SAME id, full prior context (including tool results).
    return STORE[key]


def fork(key, new_name):
    # EXAM: fork = NEW session id that starts from a copy of the baseline and then diverges.
    base = STORE[key]
    return register(Session(new_name, history=copy.deepcopy(base.history), seen=dict(base.seen)))


def answer(session, path, disk):
    v = session.seen.get(path)
    if v is None:
        return f"{path}: not read in this session"
    if v != disk[path]:
        return f"{path}: answered from STALE result (session saw v{v}, disk is v{disk[path]})  <-- WRONG"
    return f"{path}: answered from current content (v{v})"


def choose_strategy(changed, total):
    # Illustrative heuristic, NOT an official threshold: the exam wants you to reason about it.
    if changed / total > 0.5:
        return "fresh session + structured summary (most prior results are stale)"
    return "resume + tell it which files changed (prior context mostly valid)"


# ---------------------------------------------------------------------------
def demo_fork():
    reset()
    print("== Named resume ==")
    s = start("auth-investigation")
    for f in DISK:
        s.read_file(f, DISK)
    print(f"[day 1] '{s.name}' id={s.id} history={len(s.history)} items")
    r = resume("auth-investigation")
    print(f"[day 2] resumed by name -> same id: {r.id == s.id}; history still {len(r.history)} items")

    print("\n== fork_session: two strategies from ONE baseline ==")
    a = fork("auth-investigation", "strategy-unit")
    b = fork("auth-investigation", "strategy-integration")
    a.note("Plan: unit tests with mocks")
    b.note("Plan: integration tests with a test database")
    print(f"baseline id={s.id} history={len(s.history)} (unchanged)")
    print(f"fork A   id={a.id} history={len(a.history)} last='{a.history[-1]}'")
    print(f"fork B   id={b.id} history={len(b.history)} last='{b.history[-1]}'")


def demo_stale():
    reset()
    print("\n== Stale tool results after a code change ==")
    disk = dict(DISK)
    s = start("auth-investigation")
    for f in disk:
        s.read_file(f, disk)
    disk["auth.py"] = 2  # a teammate edits auth.py between your work sessions
    print("[change] auth.py modified on disk (v1 -> v2)")

    # WRONG (exam distractor): resume and carry on as if nothing changed.
    print("A) naive resume:               ", answer(s, "auth.py", disk))

    # CORRECT when prior context is mostly valid: resume AND name the changed file.
    s.note("auth.py changed since you read it; re-read ONLY that file and update your analysis")
    s.read_file("auth.py", disk)
    print("B) resume + inform + re-read:  ", answer(s, "auth.py", disk))
    print("   other files untouched:      ", answer(s, "tokens.py", disk))

    # CORRECT when most results are stale: new session seeded with a structured summary.
    summary = {"findings": ["tokens.py signs JWTs without an expiry", "routes.py skips auth on /health"],
               "files_to_reverify": ["auth.py"]}
    fresh = start("auth-investigation-v2")
    fresh.note("SUMMARY: " + json.dumps(summary))
    print("C) fresh session + summary:    ", f"history={len(fresh.history)} item; must re-read {summary['files_to_reverify']}")

    print("\n== Which strategy? ==")
    print("1 of 3 files changed ->", choose_strategy(1, 3))
    print("3 of 3 files changed ->", choose_strategy(3, 3))


# ---------------------------------------------------------------------------
# REAL Agent SDK run (needs Claude Code installed and logged in)
# ---------------------------------------------------------------------------
async def run_sdk():
    from claude_agent_sdk import ClaudeAgentOptions, ResultMessage, query

    async def run(prompt, **opts):
        sid = None
        options = ClaudeAgentOptions(allowed_tools=["Read", "Grep", "Glob"], max_turns=5, **opts)
        async for m in query(prompt=prompt, options=options):
            if isinstance(m, ResultMessage):
                sid = m.session_id  # present on every result, success or error
                print(m.result if m.subtype == "success" else f"[{m.subtype}]")
        return sid

    # NOTE: run this from the SAME directory each time, or resume looks in the wrong place.
    base = await run("Analyze the auth module in this repo and list its risks.")
    print("baseline session:", base)
    await run("Which of those risks is the most urgent?", resume=base)  # continues the baseline
    forked = await run("Instead, outline a migration to OAuth2.", resume=base, fork_session=True)
    print("fork session:", forked, "| differs from baseline:", forked != base)


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "all"
    if mode == "sdk":
        asyncio.run(run_sdk())
    else:
        if mode in ("all", "fork"):
            demo_fork()
        if mode in ("all", "stale"):
            demo_stale()