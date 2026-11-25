import itertools
import json
from types import SimpleNamespace

_ids = itertools.count(1)


def text(content):
    """A fake LLM reply that is plain text (no tool)."""
    return SimpleNamespace(content=content, tool_calls=None)


def call(name, **args):
    """A fake LLM reply that asks for one tool."""
    tool_call = SimpleNamespace(
        id=f"call_{next(_ids)}",
        function=SimpleNamespace(name=name, arguments=json.dumps(args)),
    )
    return SimpleNamespace(content=None, tool_calls=[tool_call])


class ScriptedLLM:
    """Plays back replies in order, one per LLM call.
    When the script runs out it repeats the last reply (handy for 'LLM that never stops').
    A reply that is an Exception is raised instead (simulates the LLM being down)."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = 0
        self.last_messages = None

    def __call__(self, messages, tools):
        self.last_messages = messages
        reply = self.replies[min(self.calls, len(self.replies) - 1)]
        self.calls += 1
        if isinstance(reply, Exception):
            raise reply
        return reply