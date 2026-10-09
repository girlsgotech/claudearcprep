"""
Task 4.3  Enforce structured output using tool use and JSON schemas
Scenario  6 (Structured Data Extraction)
RUNS: mock (real tool/tool_choice shapes, scripted responses; optional live call at the bottom)

What this file shows
  1. tool_choice: auto vs any vs forced.
  2. A schema-valid result can still be semantically wrong.
  3. Required vs nullable fields: required-when-absent pushes the model to fabricate.
  4. Enum with "other" + detail string, and "unclear" for ambiguous cases.
"""
import copy

# ------------------------------------------------- 1. EXTRACTION TOOLS
# EXAM: the JSON schema lives in `input_schema`. The structured data you want is
# the tool_use block's `input`. Tool use removes JSON SYNTAX errors; optional
# "strict": True on the tool definition tightens schema adherence further.
EXTRACT_INVOICE = {
    "name": "extract_invoice",
    "description": "Extract fields from an invoice document. Use for invoices and bills only.",
    "input_schema": {
        "type": "object",
        "properties": {
            "vendor": {"type": "string"},
            # EXAM: nullable because the source may not contain it.
            "invoice_number": {"type": ["string", "null"]},
            "stated_total": {"type": ["number", "null"]},
            "line_items": {"type": "array"},
            # EXAM: extensible enum = fixed values + "other" + detail; "unclear" for ambiguity.
            "category": {"type": "string",
                         "enum": ["hardware", "software", "services", "other", "unclear"]},
            "category_detail": {"type": ["string", "null"]},
        },
        "required": ["vendor", "category"],
    },
}
EXTRACT_PAPER = {
    "name": "extract_paper_metadata",
    "description": "Extract title and year from a citation or paper. Use for papers only.",
    "input_schema": {
        "type": "object",
        "properties": {"title": {"type": "string"}, "year": {"type": ["integer", "null"]}},
        "required": ["title"],
    },
}
TOOLS = [EXTRACT_INVOICE, EXTRACT_PAPER]

# Format normalization rules go in the prompt next to the strict schema.
SYSTEM = (
    "Extract data by calling a tool. Normalization: dates as YYYY-MM-DD, "
    "amounts as plain numbers without currency symbols. "
    "If a value is not in the document, use null. Never invent values."
)

# ------------------------------------------------- 2. SCRIPTED MODEL
INVOICE_DOC = "ACME Ltd. Router $60, Support $60. Total due: $100. No invoice number printed."
PAPER_DOC = "Smith, J. (2021). Retail Outlook."

OUTPUTS = {
    "extract_invoice": {"vendor": "ACME Ltd.", "invoice_number": None, "stated_total": 100,
                        "line_items": [60, 60], "category": "other",
                        "category_detail": "network support bundle"},
    "extract_paper_metadata": {"title": "Retail Outlook", "year": 2021},
}


def fake_create(tool_choice, doc):
    """Mimics the response shape of client.messages.create(tools=..., tool_choice=...)."""
    kind = tool_choice["type"]
    if kind == "auto" and doc == PAPER_DOC:
        # EXAM: with "auto" the model MAY answer in text instead of calling a tool.
        return {"stop_reason": "end_turn",
                "content": [{"type": "text", "text": "That looks like a citation. Want details?"}]}
    if kind == "tool":
        name = tool_choice["name"]  # forced: this exact tool, no choice
    else:
        name = "extract_invoice" if "Total" in doc else "extract_paper_metadata"  # "any": model picks
    return {"stop_reason": "tool_use",
            "content": [{"type": "tool_use", "id": "tu_1", "name": name, "input": OUTPUTS[name]}]}


def get_input(resp):
    for block in resp["content"]:
        if block["type"] == "tool_use":
            return block["input"]
    return None


# ------------------------------------------------- 3. TINY VALIDATOR
PY = {"string": str, "number": (int, float), "integer": int, "array": list, "null": type(None)}


def validate(inst, schema):
    errs = []
    for f in schema.get("required", []):
        if f not in inst:
            errs.append(f"{f}: missing")
    for f, spec in schema["properties"].items():
        if f not in inst:
            continue
        types = spec["type"] if isinstance(spec["type"], list) else [spec["type"]]
        if not any(isinstance(inst[f], PY[t]) for t in types):
            errs.append(f"{f}: wrong type")
        if "enum" in spec and inst[f] not in spec["enum"]:
            errs.append(f"{f}: not in enum")
    return errs


def describe(resp):
    b = resp["content"][0]
    return f"tool_use {b['name']}" if b["type"] == "tool_use" else "text, no structured data"


def main():
    print("== 1. tool_choice (scripted responses) ==")
    rows = [
        ("auto", {"type": "auto"}, PAPER_DOC),
        ("any", {"type": "any"}, PAPER_DOC),
        ("forced extract_invoice", {"type": "tool", "name": "extract_invoice"}, INVOICE_DOC),
    ]
    for label, choice, doc in rows:
        r = fake_create(choice, doc)
        print(f"{label}: stop_reason={r['stop_reason']}, {describe(r)}")

    print("\n== 2. Schema-valid is not semantically correct ==")
    inv = get_input(fake_create({"type": "tool", "name": "extract_invoice"}, INVOICE_DOC))
    print(f"schema errors: {len(validate(inv, EXTRACT_INVOICE['input_schema']))}")
    # EXAM: strict schemas stop syntax errors, NOT values in the wrong place or totals that don't add up.
    print(f"sum(line_items)={sum(inv['line_items'])}, stated_total={inv['stated_total']}, "
          f"mismatch: {sum(inv['line_items']) != inv['stated_total']}")

    print("\n== 3. Nullable fields prevent fabrication ==")
    # WRONG (exam distractor): field required and non-null although the source may lack it.
    wrong = copy.deepcopy(EXTRACT_INVOICE)
    wrong["input_schema"]["properties"]["invoice_number"]["type"] = "string"
    wrong["input_schema"]["required"].append("invoice_number")
    fabricated = dict(inv, invoice_number="INV-0000")  # scripted: model fills the gap
    print(f"WRONG (required, non-null): scripted model fills invoice_number="
          f"{fabricated['invoice_number']!r}, schema errors: {len(validate(fabricated, wrong['input_schema']))}")
    print(f"WRONG: honest null is rejected: {validate(inv, wrong['input_schema'])}")
    # RIGHT: nullable, so the model can say "not in the document".
    print(f"RIGHT (nullable): invoice_number={inv['invoice_number']!r}, "
          f"schema errors: {len(validate(inv, EXTRACT_INVOICE['input_schema']))}")

    print("\n== 4. Enum with 'other' + detail, and 'unclear' ==")
    print(f"enum: {EXTRACT_INVOICE['input_schema']['properties']['category']['enum']}")
    print(f"category={inv['category']!r}, category_detail={inv['category_detail']!r}")


# ------------------------------------------------- OPTIONAL LIVE CALL
def live_extract(doc: str, force: str | None = None):
    """Needs an API key. Forced tool = that extraction runs first; "any" = must call some tool."""
    import anthropic
    choice = {"type": "tool", "name": force} if force else {"type": "any"}
    resp = anthropic.Anthropic().messages.create(
        model="claude-sonnet-5-5", max_tokens=1000, system=SYSTEM,
        tools=TOOLS, tool_choice=choice, messages=[{"role": "user", "content": doc}],
    )
    return next(b.input for b in resp.content if b.type == "tool_use")


if __name__ == "__main__":
    main()