"""What the tests share: the path of the base notes and a fake model that costs nothing."""

from pathlib import Path
from types import SimpleNamespace

BASE_NOTES = Path(__file__).parent.parent / "fixtures" / "base_notes"


def response(stop_reason, content):
    usage = SimpleNamespace(input_tokens=100, output_tokens=10)
    return SimpleNamespace(stop_reason=stop_reason, content=content, usage=usage)


def text_block(text):
    return SimpleNamespace(type="text", text=text)


def tool_use_block(name, tool_input, id="t1"):
    return SimpleNamespace(type="tool_use", name=name, input=tool_input, id=id)


class FakeClient:
    """Stands in for anthropic.Anthropic(): plays the given responses in order.

    After the last one it keeps repeating it. Every new run (a request with a
    single message) starts the script again, so one client can serve a whole
    batch. `calls` keeps what the agent sent.
    """

    def __init__(self, *responses):
        self.script = list(responses)
        self.calls = []
        self.messages = self   # the agent calls client.messages.create(...)
        self._next = 0

    def create(self, **kwargs):
        if len(kwargs["messages"]) == 1:
            self._next = 0
        self.calls.append(kwargs)
        reply = self.script[min(self._next, len(self.script) - 1)]
        self._next += 1
        return reply


class BrokenClient:
    """An API that is down: every call fails."""

    def __init__(self):
        self.messages = self

    def create(self, **kwargs):
        raise RuntimeError("API down")


def delete_then_answer(note_id, answer="Fatto."):
    """A model that deletes one note, then answers."""
    return FakeClient(
        response("tool_use", [tool_use_block("delete_note", {"note_id": note_id})]),
        response("end_turn", [text_block(answer)]),
    )
