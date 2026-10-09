# d3_claude_code/d3_2_commands_skills.py
"""
EXAM: Task 3.2 - Create and configure custom slash commands and skills
SCENARIO: 2 - Code Generation with Claude Code (sample Q4: the team /review command)
RUNS: mock (no API key). A SIMULATOR over sample files it builds in a temp folder.
      "export" mode writes those sample files out so you can copy them into a real repo.

What the exam tests:
  * Project-scoped commands: .claude/commands/ in the repo, shared through version control.
    User-scoped (personal): ~/.claude/commands/. (Sample Q4, answer A.)
  * Skills: .claude/skills/<name>/SKILL.md with frontmatter:
      context: fork    run in an ISOLATED subagent so verbose output / brainstorming does
                       not pollute the main conversation
      allowed-tools    limit the tools available while the skill runs
      argument-hint    shows developers which parameter to supply when they invoke it
  * Personal variants of a skill go in ~/.claude/skills/ under a DIFFERENT name, so they do
    not affect teammates.
  * Skill vs CLAUDE.md: a skill is loaded ON DEMAND for a task-specific workflow; CLAUDE.md is
    ALWAYS loaded and holds universal standards.

What the current docs add: custom commands have been MERGED into skills. .claude/commands/x.md
and .claude/skills/x/SKILL.md both create /x, and the skill wins if both exist. Old command files
still work with the same frontmatter. allowed-tools is described in the docs as tools Claude can
use WITHOUT permission prompts while the skill is active; the exam frames it as restricting tool
access. Treat that wording difference as something to check on your own machine.

Run from the project root:
    python -m d3_claude_code.d3_2_commands_skills             # all demos
    python -m d3_claude_code.d3_2_commands_skills list        # discovery, scope, sharing (+ Q4)
    python -m d3_claude_code.d3_2_commands_skills collide     # command vs skill, personal variant
    python -m d3_claude_code.d3_2_commands_skills lint        # frontmatter linter
    python -m d3_claude_code.d3_2_commands_skills invoke      # argument-hint + context: fork
    python -m d3_claude_code.d3_2_commands_skills export DIR  # write the sample files to DIR
"""
import re
import sys
import tempfile
from pathlib import Path

SAMPLES = {
    # --- project scope: committed, shared with the whole team -------------------
    "project/.claude/commands/review.md": """---
description: Run the team code review checklist
argument-hint: [file-or-directory]
---
Review $ARGUMENTS against our checklist:
1. Does every public function have a type hint?
2. Are errors handled, not swallowed?
3. Is there a test for every changed behavior?
""",
    "project/.claude/commands/lint-all.md": """---
description: Old-style command for linting
---
Run the linter on the whole repo.
""",
    "project/.claude/skills/lint-all/SKILL.md": """---
description: Lint the repo and summarize findings. Use after large edits.
allowed-tools: Read, Grep, Glob
---
Run the linter and summarize the findings by severity.
""",
    "project/.claude/skills/analyze-codebase/SKILL.md": """---
description: Analyze the codebase structure and report a short summary. Use when exploring unfamiliar code.
context: fork
agent: Explore
allowed-tools: Read, Grep, Glob
---
Map the main modules, entry points and dependencies. Return a summary of at most 10 lines.
""",
    "project/.claude/skills/scaffold-test/SKILL.md": """---
description: Create a test file for a given source file
argument-hint: [file-path]
allowed-tools: Read, Write
---
Create a test file for: $ARGUMENTS
If no file path was given, ask which file to cover before doing anything else.
""",
    # --- user scope: personal, never shared ---------------------------------------
    "user/.claude/commands/standup.md": """---
description: Draft my daily standup note
---
Summarize what I changed yesterday in three bullets.
""",
    "user/.claude/skills/review-mine/SKILL.md": """---
description: My stricter personal review (different name from the team's /review)
argument-hint: [file-or-directory]
allowed-tools: Read, Grep
---
Review $ARGUMENTS with extra focus on naming and edge cases.
""",
    # --- a file with mistakes, for the linter ---------------------------------------
    "lint_examples/bad-skill/SKILL.md": """---
tools: [Read, Write, Bash]
arguments: file
---
Brainstorm alternatives for $ARGUMENTS and audit the whole codebase.
""",
}

KNOWN = {"name", "description", "argument-hint", "allowed-tools", "disallowed-tools", "context", "agent",
         "model", "hooks", "disable-model-invocation", "when_to_use", "background", "paths"}


def parse(text):
    m = re.match(r"^---\n(.*?)\n---\n?(.*)$", text, re.S)
    if not m:
        return {}, text
    fm = {}
    for line in m.group(1).splitlines():
        if ":" in line and not line.startswith(" "):
            key, value = line.split(":", 1)
            fm[key.strip()] = value.strip().strip('"')
    return fm, m.group(2)


def discover(project, home):
    items = []
    for scope, base in (("project", project / ".claude"), ("user", home / ".claude")):
        for f in sorted((base / "commands").glob("*.md")):
            fm, _ = parse(f.read_text())
            items.append({"name": f.stem, "kind": "command", "scope": scope, "path": f, "fm": fm})
        for f in sorted((base / "skills").glob("*/SKILL.md")):
            fm, _ = parse(f.read_text())
            items.append({"name": fm.get("name", f.parent.name), "kind": "skill", "scope": scope, "path": f, "fm": fm})
    return items


def lint(path):
    fm, body = parse(path.read_text())
    out = []
    if "description" not in fm:
        out.append("no description (recommended: it tells Claude when to use this)")
    for key in fm:
        if key not in KNOWN:
            out.append(f"'{key}' is not a documented field (did you mean "
                       f"{'allowed-tools' if key == 'tools' else 'argument-hint' if key == 'arguments' else '...'}?)")
    tools = fm.get("allowed-tools", "")
    if tools.startswith("["):
        out.append("allowed-tools written as a list; use a plain comma-separated string")
    if re.search(r"\bBash\b(?!\()", tools):
        out.append("unrestricted Bash in allowed-tools; scope it, e.g. Bash(git *)")
    if "$ARGUMENTS" in body and "argument-hint" not in fm:
        out.append("body uses $ARGUMENTS but there is no argument-hint")
    text = (fm.get("description", "") + " " + body).lower()
    if any(w in text for w in ("analy", "explor", "brainstorm", "audit")) and fm.get("context") != "fork":
        out.append("hint: exploratory or verbose work; consider context: fork to keep it out of the main chat")
    return out


def demo_list(project, home):
    print("== Discovery: what exists, where, and who gets it ==")
    print(f"{'/name':18}{'kind':9}{'scope':9}{'shared?':16}frontmatter")
    for it in discover(project, home):
        shared = "shared via git" if it["scope"] == "project" else "personal"
        extras = [f"{k}={v}" for k, v in it["fm"].items() if k in ("context", "agent", "allowed-tools", "argument-hint")]
        print(f"/{it['name']:17}{it['kind']:9}{it['scope']:9}{shared:16}{'; '.join(extras)}")
    print("\nSample Q4: where should the team's /review command live so everyone gets it on clone or pull?")
    print("  A .claude/commands/ in the repo   <- correct: version-controlled, available to all")
    print("  B ~/.claude/commands/             personal, not shared")
    print("  C CLAUDE.md                       instructions, not command definitions")
    print("  D .claude/config.json             a commands array that does not exist")


def demo_collide(project, home):
    print("\n== Same name, command and skill (docs: the skill wins) ==")
    items = [i for i in discover(project, home) if i["name"] == "lint-all"]
    for it in items:
        print(f"  /lint-all as {it['kind']:8} at {it['path'].relative_to(project.parent)}")
    print("  -> /lint-all runs the SKILL; the old command file is shadowed. Migrate commands to skills over time.")
    print("\n== Personal variants ==")
    print("Team skill:       /review      (project, shared)")
    print("Personal variant: /review-mine (~/.claude/skills/, DIFFERENT name)")
    print("Giving the variant its own name means it cannot change what teammates get.")


def demo_lint(project, home, bad_root):
    print("\n== Frontmatter linter ==")
    paths = [i["path"] for i in discover(project, home) if i["kind"] == "skill"] + [bad_root / "bad-skill" / "SKILL.md"]
    for p in paths:
        problems = lint(p)
        name = p.parent.name
        print(f"{name:20}{'OK' if not problems else ''}")
        for pr in problems:
            print(f"    - {pr}")


def demo_invoke(project):
    print("\n== argument-hint and $ARGUMENTS ==")
    fm, body = parse((project / ".claude/skills/scaffold-test/SKILL.md").read_text())
    print(f"autocomplete shows:  /scaffold-test {fm['argument-hint']}")
    for args in ("src/payments.py", ""):
        text = body.replace("$ARGUMENTS", args if args else "(nothing)").strip().splitlines()
        print(f"typed '/scaffold-test {args}' -> {text[0]}")
    print("With no argument the skill's own instruction makes Claude ask which file first.")
    print("\n== context: fork keeps verbose work out of the main conversation ==")
    verbose, summary = 120, 10
    print(f"/analyze-codebase WITHOUT fork: ~{verbose} lines of exploration land in your main chat")
    print(f"/analyze-codebase WITH context: fork: runs in an isolated subagent, only ~{summary} summary lines return")
    print("(illustrative line counts, not measurements)")
    print("\n== Skill or CLAUDE.md? ==")
    print("CLAUDE.md : ALWAYS loaded, universal standards   -> 'type hints everywhere'")
    print("Skill     : ON DEMAND, task-specific workflow    -> 'scaffold a test for this file'")


def export(dest):
    dest = Path(dest)
    for rel, content in SAMPLES.items():
        path = dest / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    print(f"Wrote {len(SAMPLES)} sample files under {dest}/")
    print("  project/.claude/...  -> copy into the root of a real repo (shared via git)")
    print("  user/.claude/...     -> merge into ~/.claude/ by hand (personal; do not overwrite your real files)")
    print("  lint_examples/       -> deliberately broken, leave it here")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "all"
    if mode == "export":
        export(sys.argv[2] if len(sys.argv) > 2 else "sample_claude_config")
        sys.exit(0)
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp).resolve()
        for rel, content in SAMPLES.items():
            p = base / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content)
        project, home, bad = base / "project", base / "user", base / "lint_examples"
        if mode in ("all", "list"):
            demo_list(project, home)
        if mode in ("all", "collide"):
            demo_collide(project, home)
        if mode in ("all", "lint"):
            demo_lint(project, home, bad)
        if mode in ("all", "invoke"):
            demo_invoke(project)
