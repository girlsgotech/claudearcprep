# d3_claude_code/d3_3_path_rules.py
"""
EXAM: Task 3.3 - Apply path-specific rules for conditional convention loading
SCENARIO: 2 - Code Generation with Claude Code (sample Q6: conventions that follow file TYPE)
RUNS: mock (no API key). A SIMULATOR with its own glob matcher over sample files it builds in
      a temp folder. "export" mode writes the sample rule files so you can try them for real.

What the exam tests:
  * .claude/rules/*.md files can carry YAML frontmatter with a `paths:` list of GLOB patterns.
    A rule with paths loads ONLY when Claude works with a matching file, which saves context.
    A rule WITHOUT paths loads at launch, alongside CLAUDE.md.
  * Glob rules beat subdirectory CLAUDE.md files when a convention spans many directories,
    e.g. test files spread through the codebase: paths: ["**/*.test.*"].
  * Sample Q6, answer A. Why the others lose:
      B one big CLAUDE.md   relies on the model INFERRING which section applies
      C skills              need manual invocation or the model choosing to load them
      D CLAUDE.md per dir   directory-bound, so it cannot cover files spread across the tree

Caveats from the issue trackers (user reports, version-specific; verify on YOUR version):
  * Some versions failed to load rules with `paths:` at all, with conflicting reports about
    quoted vs unquoted patterns and list vs scalar syntax.
  * Rules with `paths:` placed in ~/.claude/rules/ (user level) were reported as never loading.
  * Patterns are matched against paths relative to the project root.
  Always confirm with /memory (or /context) that a path-scoped rule actually loads.

Run from the project root:
    python -m d3_claude_code.d3_3_path_rules            # all demos
    python -m d3_claude_code.d3_3_path_rules match      # how glob patterns match
    python -m d3_claude_code.d3_3_path_rules compare    # sample Q6: four approaches
    python -m d3_claude_code.d3_3_path_rules load       # what loads when you edit what
    python -m d3_claude_code.d3_3_path_rules lint       # frontmatter mistakes
    python -m d3_claude_code.d3_3_path_rules export DIR # write the sample rule files
"""
import re
import sys
import tempfile
from pathlib import Path

SAMPLES = {
    ".claude/rules/general.md": "# General\nUse clear names.\n",
    ".claude/rules/testing.md": '---\npaths: ["**/*.test.*"]\n---\n# Testing\nOne behavior per test.\nUse the shared fixtures.\nName tests test_<behavior>.\n',
    ".claude/rules/react.md": '---\npaths: ["src/components/**/*.tsx"]\n---\n# React\nFunction components with hooks only.\nNo class components.\n',
    ".claude/rules/api.md": '---\npaths: ["src/api/**/*"]\n---\n# API\nHandlers use async/await.\nReturn structured JSON errors.\n',
    ".claude/rules/models.md": '---\npaths: ["src/models/**/*"]\n---\n# Models\nUse the repository pattern.\nNo SQL in models.\n',
    ".claude/rules/terraform.md": '---\npaths: ["terraform/**/*"]\n---\n# Terraform\nPin provider versions.\nNever hard-code credentials.\n',
    # deliberately broken, for the linter
    ".claude/rules/broken.md": '---\npath: "src/**"\n---\n# Broken\nThe key should be `paths`.\n',
    ".claude/rules/rooted.md": '---\npaths: ["./src/api/**"]\n---\n# Rooted\nLeading ./ in a pattern.\n',
    ".claude/rule/typo.md": "# Typo\nThis folder is .claude/rule/, not .claude/rules/.\n",
}
PROJECT_FILES = [
    "src/components/Button.tsx", "src/components/Button.test.tsx", "src/components/forms/Input.test.tsx",
    "src/api/orders.ts", "src/api/orders.test.ts", "src/models/user.ts", "src/models/user.test.ts",
    "scripts/deploy.test.ts", "terraform/main.tf",
]
GOOD_RULES = ("general", "testing", "react", "api", "models", "terraform")


def glob_to_regex(pattern):
    """Standard glob semantics: * stays inside a folder, ** crosses folders, **/ may match zero folders."""
    i, out = 0, ""
    while i < len(pattern):
        if pattern.startswith("**/", i):
            out += "(?:.*/)?"
            i += 3
        elif pattern.startswith("**", i):
            out += ".*"
            i += 2
        elif pattern[i] == "*":
            out += "[^/]*"
            i += 1
        elif pattern[i] == "?":
            out += "[^/]"
            i += 1
        else:
            out += re.escape(pattern[i])
            i += 1
    return re.compile("^" + out + "$")


def matches(path, patterns):
    return any(glob_to_regex(p).match(path) for p in patterns)


def parse_rule(text):
    """Return (paths or None, frontmatter keys, body)."""
    m = re.match(r"^---\n(.*?)\n---\n?(.*)$", text, re.S)
    if not m:
        return None, [], text
    paths, keys, lines = None, [], m.group(1).splitlines()
    clean = lambda s: s.strip().strip("\"'")
    for idx, line in enumerate(lines):
        if re.match(r"^[A-Za-z_-]+:", line):
            key, val = line.split(":", 1)
            key, val = key.strip(), val.strip()
            keys.append(key)
            if key == "paths":
                if val.startswith("["):
                    paths = [clean(p) for p in val.strip("[]").split(",") if p.strip()]
                elif val:
                    paths = [clean(p) for p in val.split(",")]
                else:  # block list
                    paths = []
                    for nxt in lines[idx + 1:]:
                        mm = re.match(r"^\s*-\s*(.+)$", nxt)
                        if not mm:
                            break
                        paths.append(clean(mm.group(1)))
    return paths, keys, m.group(2)


def load_rules(root):
    rules = {}
    for f in sorted((root / ".claude" / "rules").glob("*.md")):
        paths, keys, body = parse_rule(f.read_text())
        rules[f.stem] = {"paths": paths, "keys": keys, "lines": len([l for l in body.splitlines() if l and not l.startswith("#")])}
    return rules


def demo_match():
    print("== How globs match (paths are relative to the project root) ==")
    cases = [
        ("**/*.test.*", ["Button.test.tsx", "src/api/orders.test.ts", "scripts/deploy.test.ts", "src/api/orders.ts"]),
        ("src/api/**/*", ["src/api/orders.ts", "src/api/v2/users.ts", "src/models/user.ts"]),
        ("terraform/**/*", ["terraform/main.tf", "terraform/modules/vpc/main.tf", "main.tf"]),
        ("*.md", ["README.md", "docs/guide.md"]),
    ]
    for pattern, paths in cases:
        print(f"pattern {pattern}")
        for p in paths:
            print(f"    {'MATCH   ' if matches(p, [pattern]) else 'no match'}  {p}")
    print("Note: '*' stays inside one folder, '**' crosses folders; '**/' may match zero folders.")


def demo_compare(root):
    rules = load_rules(root)
    print("\n== Sample Q6: tests spread across the codebase must follow ONE convention ==")
    tests = [f for f in PROJECT_FILES if ".test." in f]
    print("A) .claude/rules/testing.md with paths: [\"**/*.test.*\"]")
    for t in tests:
        hit = matches(t, rules["testing"]["paths"])
        print(f"     {'applies' if hit else 'MISSED '}  {t}")
    area_dirs = ["src/components", "src/api", "src/models"]
    print(f"D) a testing CLAUDE.md in each area directory {area_dirs}")
    for t in tests:
        hit = any(t.startswith(d + "/") for d in area_dirs)
        print(f"     {'applies' if hit else 'MISSED '}  {t}")
    print("   D only covers the folders it was placed in (and their subfolders). Any other folder with tests, like scripts/,")
    print("   needs yet another copy of the same rules, and every copy must be kept in sync.")
    print("B) root CLAUDE.md with headers: relies on the model INFERRING the right section (not deterministic)")
    print("C) skills: need manual invocation or the model choosing to load them (not automatic)")
    print("A is the only option that applies conventions automatically, by file path, wherever the file lives.")


def demo_load(root):
    rules = load_rules(root)
    always = [n for n in GOOD_RULES if rules[n]["paths"] is None]
    print("\n== What loads when you work on a file ==")
    print(f"at launch (no paths): {always}")
    every_line = sum(rules[n]["lines"] for n in GOOD_RULES)
    for target in ("terraform/main.tf", "src/components/Button.test.tsx", "src/api/orders.ts", "README.md"):
        hit = [n for n in GOOD_RULES if rules[n]["paths"] and matches(target, rules[n]["paths"])]
        lines = sum(rules[n]["lines"] for n in always + hit)
        print(f"editing {target:34} loads {always + hit}  ({lines} rule lines in context vs {every_line} if every rule always loaded)")
    print("Path-scoped rules only save context if they really are conditional: rules WITHOUT paths all load at launch.")


def lint(root):
    problems = []
    rules = root / ".claude" / "rules"
    if (root / ".claude" / "rule").exists():
        problems.append((".claude/rule/", "folder is not .claude/rules/; Claude will never read these files"))
    for f in sorted(rules.glob("*.md")):
        paths, keys, _ = parse_rule(f.read_text())
        for k in keys:
            if k != "paths":
                problems.append((f.name, f"unknown frontmatter key '{k}'" + (" (did you mean 'paths'?)" if k == "path" else "")))
        for p in paths or []:
            if p.startswith(("./", "/")):
                problems.append((f.name, f"pattern '{p}' should be relative to the project root: drop the leading '{'./' if p.startswith('./') else '/'}'"))
    return problems


def demo_lint(root):
    print("\n== Frontmatter linter ==")
    found = lint(root)
    for where, msg in found:
        print(f"  {where:16}{msg}")
    print("  (user-level ~/.claude/rules/ with paths: has been reported as never loading; prefer project-level rules)")


def export(dest):
    dest = Path(dest)
    for rel, content in SAMPLES.items():
        if rel.split("/")[1] == "rule" or Path(rel).stem in ("broken", "rooted"):
            continue  # do not export the deliberately broken examples as live config
        (dest / rel).parent.mkdir(parents=True, exist_ok=True)
        (dest / rel).write_text(content)
    print(f"Wrote the working sample rules under {dest}/.claude/rules/ (broken examples skipped).")
    print("Copy into a repo root, restart Claude Code, open a matching file, and check /memory.")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "all"
    if mode == "export":
        export(sys.argv[2] if len(sys.argv) > 2 else "sample_rules")
        sys.exit(0)
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp).resolve()
        for rel, content in SAMPLES.items():
            (root / rel).parent.mkdir(parents=True, exist_ok=True)
            (root / rel).write_text(content)
        if mode in ("all", "match"):
            demo_match()
        if mode in ("all", "compare"):
            demo_compare(root)
        if mode in ("all", "load"):
            demo_load(root)
        if mode in ("all", "lint"):
            demo_lint(root)