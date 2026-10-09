# d3_claude_code/d3_1_claude_md.py
"""
EXAM: Task 3.1 - Configure CLAUDE.md files with appropriate hierarchy, scoping, and modular organization
SCENARIO: 2 - Code Generation with Claude Code (team conventions), 4 - Developer Productivity
RUNS: mock (no API key). A SIMULATOR builds a sample repo in a temp folder and shows which
      memory files a Claude Code session would load. Confirm the real thing with /memory.

What the exam tests:
  * Three levels: USER ~/.claude/CLAUDE.md (only you, never shared), PROJECT ./CLAUDE.md or
    ./.claude/CLAUDE.md (shared through version control), DIRECTORY CLAUDE.md files in
    subfolders (apply when working there).
  * A new teammate "not getting the instructions" usually means those instructions live in
    someone's USER-level file instead of the PROJECT-level file.
  * @path imports keep CLAUDE.md modular: each package imports only the standards it needs.
  * .claude/rules/ splits one big CLAUDE.md into focused topic files (testing.md, ...).
  * /memory shows which memory files are loaded, for diagnosing inconsistent behavior.
    (Newer docs also mention /context for what loaded into the current session.)

Docs details used here: imports are written as @path on their own line, resolve relative to the
file that contains them, nest up to 5 levels, and are ignored inside code blocks. Rules files
without a `paths` frontmatter load at launch (path-scoped rules are Task 3.3).
The loading order below is my simplified model; trust /memory for the real answer.

Run from the project root:
    python -m d3_claude_code.d3_1_claude_md            # all demos
    python -m d3_claude_code.d3_1_claude_md loads      # what loads, per working directory
    python -m d3_claude_code.d3_1_claude_md diagnose   # the "new teammate" problem
    python -m d3_claude_code.d3_1_claude_md split      # monolith vs .claude/rules/
"""
import re
import sys
import tempfile
from pathlib import Path

MAX_DEPTH = 5
IMPORT = re.compile(r"^@(\S+)\s*$")

TREE = {
    "repo/CLAUDE.md": ("# Project: Stocktracker\nUse Python 3.12 and type hints everywhere.\n"
                       "Tests live next to code; run `make test`.\n@docs/standards/testing.md\n"),
    "repo/docs/standards/testing.md": ("# Testing standards\nEvery bug fix needs a regression test.\n"
                                       "Use the shared fixtures in tests/fixtures.\n"),
    "repo/packages/api/CLAUDE.md": "# API package\n@standards/api-conventions.md\n",
    "repo/packages/api/standards/api-conventions.md": "# API conventions\nAll handlers are async.\n@error-codes.md\n",
    "repo/packages/api/standards/error-codes.md": "# Error codes\nReturn errors as JSON with a code field.\n",
    "repo/packages/web/CLAUDE.md": "# Web package\n@standards/react.md\n",
    "repo/packages/web/standards/react.md": "# React standards\nFunction components with hooks only.\n",
    "repo/.claude/rules/deployment.md": "# Deployment\nDeploys happen from main only.\n",
    "home_alex/.claude/CLAUDE.md": ("# Personal preferences\nAlways run `make lint` before committing.\n"
                                    "Explain changes in plain language.\n"),
}


def expand(file, depth, out, home):
    """Collect a file and everything it @imports (max 5 levels, code blocks ignored)."""
    out.append((file, depth))
    in_code = False
    for line in file.read_text().splitlines():
        if line.startswith("```"):
            in_code = not in_code
            continue
        m = IMPORT.match(line)
        if m and not in_code and depth < MAX_DEPTH:
            rel = m.group(1)
            target = home / rel[2:] if rel.startswith("~/") else (file.parent / rel).resolve()
            if target.exists():
                expand(target, depth + 1, out, home)


def loaded_for(root, home, cwd):
    entries = []
    user = home / ".claude" / "CLAUDE.md"
    if user.exists():
        entries.append(("user", user))
    d, chain = root, [root]
    for part in cwd.relative_to(root).parts:  # repo root down to the working directory
        d = d / part
        chain.append(d)
    for d in chain:
        f = d / "CLAUDE.md"
        if f.exists():
            entries.append(("project" if d == root else "directory", f))
    for rule in sorted((root / ".claude" / "rules").glob("*.md")):
        entries.append(("rule", rule))
    rows = []
    for scope, f in entries:
        chain_files = []
        expand(f, 0, chain_files, home)
        for path, depth in chain_files:
            rows.append(("@import" if depth else scope, depth, path))
    return rows


def label(path, root, home):
    p = Path(path)
    if home in p.parents:
        return "~/" + str(p.relative_to(home))
    return str(p.relative_to(root))


def instructions(rows):
    lines = set()
    for _, _, path in rows:
        for ln in Path(path).read_text().splitlines():
            if ln and not ln.startswith(("#", "@")):
                lines.add(ln)
    return lines


def demo_loads(root, home):
    print("== What loads, per working directory (user = Alex) ==")
    for cwd in (root, root / "packages" / "api", root / "packages" / "web"):
        print(f"\nclaude launched in: {label(cwd, root, home) if cwd != root else '(repo root)'}")
        for scope, depth, path in loaded_for(root, home, cwd):
            shared = "personal" if home in Path(path).parents else "shared via git"
            print(f"  {'  ' * depth}{scope:10}{label(path, root, home):48}{shared}")
    print("\nEach package imports ONLY the standards it needs (selective @import).")


def demo_diagnose(root, home_alex, home_sam):
    print("\n== The 'new teammate' problem ==")
    alex = instructions(loaded_for(root, home_alex, root))
    sam = instructions(loaded_for(root, home_sam, root))
    print(f"Alex's session sees {len(alex)} instructions; Sam's sees {len(sam)}.")
    print("Only Alex gets these (they live in ~/.claude/CLAUDE.md, which is never shared):")
    for line in sorted(alex - sam):
        print(f"   - {line}")
    print("\nFix: a TEAM standard belongs in project CLAUDE.md (committed). Personal taste stays at user level.")
    project = root / "CLAUDE.md"
    project.write_text(project.read_text() + "Always run `make lint` before committing.\n")
    sam_after = instructions(loaded_for(root, home_alex, root)) - instructions(loaded_for(root, home_sam, root))
    print("After moving the lint rule into repo/CLAUDE.md, Alex-only instructions are now:")
    for line in sorted(sam_after):
        print(f"   - {line}   (personal preference: correct to keep user-level)")


MONOLITH = {
    "general": ["Use Python 3.12 and type hints everywhere.", "Tests live next to code."],
    "testing": ["Every bug fix needs a regression test.", "Use the shared fixtures.", "Name tests test_<behavior>."],
    "api": ["All handlers are async.", "Return errors as JSON with a code field.", "Version every endpoint."],
    "deployment": ["Deploys happen from main only.", "Tag releases vMAJOR.MINOR.PATCH.", "Never deploy on Fridays."],
}


def demo_split():
    print("\n== One big CLAUDE.md vs focused .claude/rules/ files ==")
    total = sum(len(v) for v in MONOLITH.values())
    print(f"monolith: CLAUDE.md with {total} instructions mixed together, every one loaded every session")
    print("split:")
    print(f"  CLAUDE.md                         {len(MONOLITH['general'])} instructions (universal)")
    for topic in ("testing", "api", "deployment"):
        name = {"api": "api-conventions"}.get(topic, topic)
        print(f"  .claude/rules/{name + '.md':22}{len(MONOLITH[topic])} instructions")
    print("Focused files are easier to review and own. Add `paths:` frontmatter (Task 3.3) so a rule loads only when needed.")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "all"
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp).resolve()
        for rel, content in TREE.items():
            path = base / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
        (base / "home_sam" / ".claude").mkdir(parents=True)  # Sam has no personal CLAUDE.md
        root, alex, sam = base / "repo", base / "home_alex", base / "home_sam"
        if mode in ("all", "loads"):
            demo_loads(root, alex)
        if mode in ("all", "diagnose"):
            demo_diagnose(root, alex, sam)
        if mode in ("all", "split"):
            demo_split()