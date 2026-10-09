# d2_tools/d2_4_mcp_config/check_mcp_config.py
"""
EXAM: Task 2.4 - Integrate MCP servers into Claude Code and agent workflows
SCENARIOS: 4 - Developer Productivity (built-in tools plus MCP servers),
           1 - Customer Support (MCP tools get_customer, lookup_order, ...)
RUNS: mock (no API key, no network). Reads the sample .json files in this folder.

What the exam tests:
  * Scope: project-level .mcp.json = shared TEAM tooling (committed to version control);
    user-level ~/.claude.json = PERSONAL or experimental servers (not shared).
    (The Claude Code docs also have a third, default "local" scope: private to you, one project.
    Precedence when names collide: local > project > user.)
  * Credentials: use ${VAR} (and ${VAR:-default}) so secrets never get committed.
  * Tools from ALL configured servers are discovered at connection time and are available
    to the agent SIMULTANEOUSLY.
  * MCP RESOURCES expose content catalogs (issue summaries, documentation hierarchies, database
    schemas) so the agent does not make many exploratory tool calls. Tools are for actions.
  * Write detailed MCP tool descriptions, or the agent prefers built-in tools like Grep.
  * Prefer an existing community server for standard integrations (e.g. Jira); build custom
    servers only for team-specific workflows.

Run from the project root (these sample files are NOT live config; see the copy notes in the lesson):
    python d2_tools/d2_4_mcp_config/check_mcp_config.py            # all demos
    python d2_tools/d2_4_mcp_config/check_mcp_config.py env        # ${VAR} expansion + lint
    python d2_tools/d2_4_mcp_config/check_mcp_config.py scopes     # project vs user, precedence
    python d2_tools/d2_4_mcp_config/check_mcp_config.py resources  # resources vs exploratory tools
"""
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).parent
VAR = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-([^}]*))?\}")  # ${VAR} or ${VAR:-default}
SECRET = re.compile(r"(ghp_|github_pat_|sk-[A-Za-z0-9]|xox[bp]-|AKIA[0-9A-Z]{16})")
HOME_PATH = re.compile(r"^(/home/|/Users/|[A-Za-z]:\\Users\\)")


def load(name):
    return json.loads((HERE / name).read_text())["mcpServers"]


def strings(node, path=""):
    """Yield (path, text) for every string value in a config."""
    if isinstance(node, dict):
        for k, v in node.items():
            yield from strings(v, f"{path}.{k}" if path else k)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from strings(v, f"{path}[{i}]")
    elif isinstance(node, str):
        yield path, node


# ---------------------------------------------------------------------------
# Demo 1: environment variable expansion and a config linter
# ---------------------------------------------------------------------------
def lint_file(name, env):
    servers = load(name)
    print(f"-- {name}: {len(servers)} server(s)")
    problems = 0
    for server, cfg in servers.items():
        for path, text in strings(cfg):
            for m in VAR.finditer(text):
                var, default = m.group(1), m.group(2)
                if var in env:
                    state = "set"
                elif default is not None:
                    state = f"unset -> falls back to '{default}'"
                else:
                    state = "MISSING, no default: server still loads, with the literal text unexpanded"
                print(f"   {server}.{path}: ${{{var}}} -> {state}")
            # EXAM: a secret typed straight into a shared file gets committed with it.
            if SECRET.search(text) and not VAR.search(text):
                problems += 1
                print(f"   PROBLEM {server}.{path}: looks like a hard-coded secret; use ${{VAR}} instead")
            if HOME_PATH.match(text):
                problems += 1
                print(f"   PROBLEM {server}.{path}: machine-specific path in a shared file; "
                      "use ${CLAUDE_PROJECT_DIR:-.} or move this server to user scope")
    print("   OK" if not problems else f"   {problems} problem(s)")


def demo_env():
    print("== ${VAR} expansion and lint ==")
    lint_file("project.mcp.json", env={"GITHUB_TOKEN": "present"})
    print("\n(same file, GITHUB_TOKEN not set on this machine)")
    lint_file("project.mcp.json", env={})
    print("\n(a file that should NOT be committed)")
    lint_file("bad_project.mcp.json", env={})


# ---------------------------------------------------------------------------
# Demo 2: scopes, precedence, simultaneous availability
# ---------------------------------------------------------------------------
def effective(local, project, user):
    merged, origin = {}, {}
    for scope, servers in (("user", user), ("project", project), ("local", local)):  # later wins
        for name, cfg in servers.items():
            merged[name], origin[name] = cfg, scope
    return merged, origin


def demo_scopes():
    print("\n== Scopes: shared team tooling vs personal servers ==")
    project, user, local = load("project.mcp.json"), load("user_scope_example.json"), {}
    merged, origin = effective(local, project, user)
    print(f"{'server':14}{'wins from':12}notes")
    for name in merged:
        in_scopes = [s for s, d in (("project", project), ("user", user), ("local", local)) if name in d]
        note = f"also defined in {[s for s in in_scopes if s != origin[name]]}: shadowed" if len(in_scopes) > 1 else ""
        print(f"{name:14}{origin[name]:12}{note}")
    print(f"\nAvailable at connection time, ALL at once: {sorted(merged)}")
    print("Tools from every one of these servers are discovered together; the agent sees them simultaneously.")
    print("\nShared (commit to git):  .mcp.json at the repo root  <- project scope; teammates approve it on first use")
    print("Personal / experimental: ~/.claude.json              <- user scope; never shared")


# ---------------------------------------------------------------------------
# Demo 3: MCP resources (content catalogs) vs exploratory tool calls
# ---------------------------------------------------------------------------
DOCS = {
    "docs/onboarding.md": "new hire checklist", "docs/deploy.md": "release process",
    "docs/security.md": "key handling rules", "docs/refunds.md": "refund policy and limits",
    "docs/holidays.md": "office calendar", "docs/expenses.md": "expense claims",
    "docs/oncall.md": "pager rota",
}
CLASSIFY = [
    ("list of open issue summaries", "RESOURCE", "read-only content catalog"),
    ("create an issue", "TOOL", "an action with side effects"),
    ("database schema", "RESOURCE", "lets the agent see what exists before querying"),
    ("run an UPDATE statement", "TOOL", "an action"),
    ("documentation hierarchy", "RESOURCE", "catalog of what is available"),
    ("send a notification", "TOOL", "an action"),
]
WEAK = "Searches code"
RICH = ("Search the team's indexed code AND tickets by meaning, not by exact string. Use when the question is a "
        "concept ('where do we validate refunds?'). Returns ranked results with file path and ticket link. "
        "For an exact string or symbol, use Grep instead.")


def demo_resources():
    print("\n== MCP resources: a catalog beats exploring ==")
    order = list(DOCS)
    position = order.index("docs/refunds.md") + 1
    before = 1 + position  # one directory listing, then open files until the answer turns up
    after = 2              # read the catalog resource once, then open the right file
    print("Question: 'What is our refund limit?'")
    print(f"without a catalog: list the folder (1) + open files one by one until #{position} = {before} tool calls")
    print(f"with a catalog resource: read the catalog (1) + open the right file (1) = {after} tool calls")
    print("\nThe catalog resource the server would expose:")
    for path, summary in DOCS.items():
        print(f"  {path} - {summary}")
    print("\nResource or tool?")
    for what, kind, why in CLASSIFY:
        print(f"  {what:32}{kind:10}{why}")
    print("\n== Why the agent prefers Grep over your MCP tool ==")
    print("WEAK :", WEAK)
    print("RICH :", RICH)
    print("A vague MCP description loses to the familiar built-in tool; capabilities and outputs must be spelled out.")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "all"
    if mode in ("all", "env"):
        demo_env()
    if mode in ("all", "scopes"):
        demo_scopes()
    if mode in ("all", "resources"):
        demo_resources()