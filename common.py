# common.py  (project root)
# Mock mode (default) lets every raw-API example run with NO API key.
# The fake client returns scripted responses shaped like the real API
# (stop_reason, content blocks), so the control-flow code you write is
# identical to production code. Set USE_MOCK=0 to use the real API.
import json
import os
from dataclasses import asdict, dataclass, is_dataclass

MODEL = "claude-sonnet-5-5"
USE_MOCK = os.environ.get("USE_MOCK", "1") == "1"


@dataclass
class TextBlock:
    text: str
    type: str = "text"


@dataclass
class ToolUseBlock:
    id: str
    name: str
    input: dict
    type: str = "tool_use"


@dataclass
class FakeResponse:
    content: list
    stop_reason: str


class _FakeMessages:
    def __init__(self, script):
        self._script = list(script)

    def create(self, **kwargs):
        if not self._script:
            raise RuntimeError("Mock script exhausted: the loop asked for more turns than scripted.")
        return self._script.pop(0)


class FakeClient:
    def __init__(self, script):
        self.messages = _FakeMessages(script)


def mock_support_script():
    """Scenario 1 (support agent). Turn 1 returns TEXT plus a tool_use block
    together, which is why 'text present' is NOT a completion signal."""
    return [
        FakeResponse(
            [TextBlock("Let me look you up."),
             ToolUseBlock("toolu_1", "get_customer", {"email": "alex@example.com"})],
            "tool_use",
        ),
        FakeResponse([ToolUseBlock("toolu_2", "lookup_order", {"order_id": "12345"})], "tool_use"),
        FakeResponse([TextBlock("Order 12345 was delivered; the total was $59.90.")], "end_turn"),
    ]


def get_client(script=None):
    """Return the fake client (default) or the real Anthropic client (USE_MOCK=0)."""
    if USE_MOCK:
        return FakeClient(script if script is not None else mock_support_script())
    from anthropic import Anthropic

    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise SystemExit("USE_MOCK=0 needs ANTHROPIC_API_KEY. Use mock mode instead.")
    return Anthropic()


def pp(label: str, obj) -> None:
    """Pretty-print an API object, dataclass or dict."""
    if hasattr(obj, "model_dump"):
        obj = obj.model_dump()
    elif is_dataclass(obj):
        obj = asdict(obj)
    print(f"\n--- {label} ---")
    print(json.dumps(obj, indent=2, default=str))