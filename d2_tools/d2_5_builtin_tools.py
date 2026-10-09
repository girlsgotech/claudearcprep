# d2_tools/d2_5_builtin_tools.py
"""
EXAM: Task 2.5 - Select and apply built-in tools (Read, Write, Edit, Bash, Grep, Glob) effectively
SCENARIO: 4 - Developer Productivity (explore an unfamiliar codebase with the built-in tools)
RUNS: mock (no API key). Works on a throwaway temp folder, so nothing of yours is touched.

CHEAT SHEET (what the exam tests):
  Grep  = search file CONTENTS (function names, error messages, import statements)
  Glob  = match file PATHS (names / extensions, e.g. **/*.test.tsx)
  Read  = load a whole file          Write = write a whole file
  Edit  = targeted change using UNIQUE text matching. If the anchor text appears more than
          once, Edit fails -> fall back to Read + Write.
  Bash  = run commands (tests, git, build)
  Explore incrementally: Grep for entry points, Read to follow imports and trace flows.
  Do NOT read every file upfront.
  To trace a function through wrapper modules: list ALL exported names first, then Grep each.

Run from the project root:
    python -m d2_tools.d2_5_builtin_tools            # all demos
    python -m d2_tools.d2_5_builtin_tools select     # which tool for which job
    python -m d2_tools.d2_5_builtin_tools search     # Glob, Grep, incremental reading, wrappers
    python -m d2_tools.d2_5_builtin_tools edit       # the Edit uniqueness problem
"""
import re
import sys
import tempfile
from pathlib import Path

FILES = {
    "src/payments.py": "def process_refund(order_id, amount):\n    return {'refund': order_id, 'amount': amount}\n",
    "src/wrappers.py": ("from payments import process_refund as do_refund\n\n"
                        "def issue_refund(order_id, amount):\n    return do_refund(order_id, amount)\n"),
    "src/api.py": ("from wrappers import issue_refund\n\n"
                   "def handle(request):\n    return issue_refund(request['order'], request['amount'])\n"),
    "src/reports.py": "from payments import process_refund\n\ndef monthly():\n    return process_refund('A1', 5)\n",
    "web/Button.tsx": "export const Button = () => null;\n",
    "web/Button.test.tsx": "test('renders', () => {});\n",
    "web/Cart.test.tsx": "test('totals', () => {});\n",
    "config.py": "[billing]\ntimeout = 30\n\n[shipping]\ntimeout = 30\n",
}


class Workspace:
    """Tiny stand-ins with the same semantics as the built-in tools."""

    def __init__(self, root):
        self.root = Path(root)
        self.reads = []

    def glob(self, pattern):  # PATHS
        return sorted(str(p.relative_to(self.root)) for p in self.root.glob(pattern) if p.is_file())

    def grep(self, pattern):  # CONTENTS
        hits = []
        for p in sorted(self.root.rglob("*")):
            if p.is_file():
                for n, line in enumerate(p.read_text().splitlines(), 1):
                    if re.search(pattern, line):
                        hits.append((str(p.relative_to(self.root)), n, line.strip()))
        return hits

    def read(self, path):
        self.reads.append(path)
        return (self.root / path).read_text()

    def write(self, path, text):
        (self.root / path).write_text(text)

    def edit(self, path, old, new):
        text = (self.root / path).read_text()
        count = text.count(old)
        if count == 0:
            raise ValueError("Edit failed: text not found")
        if count > 1:  # EXAM: Edit needs a UNIQUE anchor
            raise ValueError(f"Edit failed: text appears {count} times; anchor is not unique")
        self.write(path, text.replace(old, new))


TASKS = [
    ("find every file named *.test.tsx", "Glob", "matches file PATHS"),
    ("find all callers of process_refund", "Grep", "searches file CONTENTS"),
    ("find where the error 'Card declined' is raised", "Grep", "error messages live in contents"),
    ("understand what one module contains", "Read", "loads the whole file"),
    ("change one unique line", "Edit", "targeted change, unique anchor"),
    ("change text that appears many times (Edit failed)", "Read + Write", "the exam's fallback"),
    ("create a new file or rewrite one completely", "Write", "whole-file output"),
    ("run the tests or check git status", "Bash", "runs commands"),
]


def demo_select():
    print("== Which tool for which job ==")
    for task, tool, why in TASKS:
        print(f"  {task:52}{tool:14}{why}")


def show(hits):
    for path, n, line in hits:
        print(f"    {path}:{n}: {line}")


def demo_search(ws):
    print("\n== Glob matches paths; Grep matches contents ==")
    print("Glob **/*.test.tsx ->", ws.glob("**/*.test.tsx"))
    print("Grep 'process_refund' ->")
    show(ws.grep(r"process_refund"))

    print("\n== Build understanding incrementally (do not read everything upfront) ==")
    ws.reads.clear()
    entry = ws.grep(r"def issue_refund")[0][0]  # 1. Grep finds the entry point
    text = ws.read(entry)                       # 2. Read only that file
    module = re.search(r"from (\w+) import", text).group(1)  # 3. follow its import
    ws.read(f"src/{module}.py")                 # 4. Read the file it points to
    total = len(FILES)
    print(f"Grep -> {entry}; Read {ws.reads}; read {len(ws.reads)} of {total} files "
          f"(reading everything upfront would be {total})")

    print("\n== Tracing a function through wrapper modules ==")
    naive = sorted({h[0] for h in ws.grep(r"process_refund")})
    print("naive Grep for 'process_refund' finds:", naive, " <-- misses src/api.py")
    # EXAM: first identify ALL exported names that lead to the function, then search each.
    wrappers = ws.read("src/wrappers.py")
    names = {"process_refund"}
    for alias in re.findall(r"import process_refund as (\w+)", wrappers):
        names.add(alias)
        names.update(re.findall(rf"def (\w+)\([^)]*\):\n\s+return {alias}\(", wrappers))
    found = sorted({h[0] for n in sorted(names) for h in ws.grep(rf"\b{n}\b")})
    print(f"names to search: {sorted(names)}")
    print("complete search finds:", found)


def demo_edit(ws):
    print("\n== Edit needs a UNIQUE anchor ==")
    print("config.py before:\n" + "".join("    " + ln + "\n" for ln in ws.read("config.py").splitlines()))
    try:
        ws.edit("config.py", "timeout = 30", "timeout = 60")
    except ValueError as e:
        print("Edit 'timeout = 30' ->", e)

    # EXAM FALLBACK: Read the whole file, change it, Write the whole file back.
    text = ws.read("config.py")
    ws.write("config.py", text.replace("[billing]\ntimeout = 30", "[billing]\ntimeout = 60"))
    print("Read + Write fallback: billing timeout changed to 60")

    # Also works: make the anchor unique with surrounding context.
    ws.edit("config.py", "[shipping]\ntimeout = 30", "[shipping]\ntimeout = 45")
    print("Edit with a longer, unique anchor: shipping timeout changed to 45")
    print("config.py after:\n" + "".join("    " + ln + "\n" for ln in ws.read("config.py").splitlines()))


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "all"
    with tempfile.TemporaryDirectory() as tmp:
        for rel, content in FILES.items():
            path = Path(tmp) / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
        ws = Workspace(tmp)
        if mode in ("all", "select"):
            demo_select()
        if mode in ("all", "search"):
            demo_search(ws)
        if mode in ("all", "edit"):
            demo_edit(ws)