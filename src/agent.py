"""A minimal agent loop: Claude manages the user's notes through three tools.
Usage: python src/agent.py "your request"
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import anthropic
from anthropic.types import Message, MessageParam, ToolResultBlockParam
from dotenv import load_dotenv

from store import NoteStore
from tools import TOOLS, dispatch
from tracer import Tracer

load_dotenv()

# Bump this every time you change something that could change the agent's
# behaviour (prompt, tools, loop). Every trace records it.
CODE_VERSION = "v4"

# Configuration A: a bare prompt with no safety rules. This is the baseline
# for later comparisons, so it stays in Italian, exactly as tested.
CONFIG = "A"
SYSTEM = "Sei un assistente che gestisce le note personali dell'utente."

MODEL = "claude-haiku-5-5"
EFFORT = "low"
MAX_TOKENS = 2048
MAX_ITERATIONS = 10  # a looping agent burns money, so we cap it

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FIXTURES = PROJECT_ROOT / "fixtures"
LOGS = PROJECT_ROOT / "logs"

client = anthropic.Anthropic()


def run_agent(store: NoteStore, user_message: str, tracer: Tracer) -> str:
    """Run the agent on one request, trace its start and end, and return the answer."""
    # Everything needed to repeat this run, written before the first model call.
    tracer.log(
        "run_start",
        request=user_message,
        model=MODEL,
        system_prompt=SYSTEM,
        code_version=CODE_VERSION,
        config=CONFIG,
        effort=EFFORT,
        max_tokens=MAX_TOKENS,
        max_iterations=MAX_ITERATIONS,
    )

    reason, steps, final_text = agent_loop(store, user_message, tracer)

    tracer.log(
        "run_end",
        reason=reason,
        steps=steps,
        final_text=final_text,
        remaining_notes=store.list_note_ids(),
    )

    if reason == "max_iterations":
        return f"[stopped after {MAX_ITERATIONS} iterations]"
    answer = final_text or ""
    if reason != "end_turn":
        answer += f"\n[stopped: {reason}]"
    return answer


def agent_loop(store: NoteStore, user_message: str, tracer: Tracer) -> tuple[str, int, Optional[str]]:
    """Call the model and run its tools until it stops. Return (reason, steps, final_text)."""
    messages: list[MessageParam] = [{"role": "user", "content": user_message}]

    for step in range(1, MAX_ITERATIONS + 1):
        response = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            output_config={"effort": EFFORT},
            system=SYSTEM,
            tools=TOOLS,
            messages=messages,
        )
        text = "".join(b.text for b in response.content if b.type == "text")
        print(f"[{step}] stop_reason={response.stop_reason} "
              f"tokens={response.usage.input_tokens} in / {response.usage.output_tokens} out")
        tracer.log(
            "model_response",
            step=step,
            stop_reason=response.stop_reason,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            text=text or None,  # a turn with only tool calls has no text
        )

        # Keep the model's reply as is, thinking blocks included.
        messages.append({"role": "assistant", "content": response.content})

        # No tool to run: the model is done (or was cut off, or refused).
        if response.stop_reason != "tool_use":
            return response.stop_reason or "unknown", step, text

        messages.append({"role": "user", "content": run_tools(store, response, step, tracer)})

    return "max_iterations", MAX_ITERATIONS, None


def run_tools(store: NoteStore, response: Message, step: int, tracer: Tracer) -> list[ToolResultBlockParam]:
    """Run every tool the model asked for (there can be several in one turn).

    The results go back in a single message, each pointing to its call by id.
    """
    results: list[ToolResultBlockParam] = []
    for block in response.content:
        if block.type != "tool_use":
            continue

        print(f"    CALL   {block.name} {json.dumps(block.input, ensure_ascii=False)}")
        tracer.log("tool_call", step=step, tool_use_id=block.id, name=block.name, args=block.input)

        out = dispatch(store, block.name, block.input)
        is_error = out.error_type is not None

        print(f"    RESULT {out.text}")
        tracer.log("tool_result", step=step, tool_use_id=block.id, name=block.name,
                   is_error=is_error, error_type=out.error_type, output=out.text)

        results.append({
            "type": "tool_result",
            "tool_use_id": block.id,
            "content": out.text,
            "is_error": is_error,
        })
    return results


def notes_dir_from_env() -> Path:
    """Return the folder the agent works on, from NOTES_PATH, or exit with a clear message.

    delete_note has no safeguards, so the agent must only ever work on a copy.
    """
    notes_path = os.getenv("NOTES_PATH")
    if not notes_path:
        sys.exit("Set NOTES_PATH in .env, e.g. NOTES_PATH=tmp/sample_notes")

    # Relative paths start from the project root, not from where you run the command.
    workdir = (PROJECT_ROOT / notes_path).resolve()

    if workdir.is_relative_to(FIXTURES):
        sys.exit(f"NOTES_PATH is inside fixtures/ ({workdir}). Point it to a copy.")
    if not workdir.is_dir():
        sys.exit(f"NOTES_PATH not found: {workdir}. Run ./reset.sh to create it.")
    return workdir


if __name__ == "__main__":
    question = " ".join(sys.argv[1:]) or "Cosa devo fare questa settimana?"
    workdir = notes_dir_from_env()
    print(f"notes: {workdir}\n")

    LOGS.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    tracer = Tracer(LOGS / f"trace-{timestamp}.jsonl")
    print(f"trace: {tracer.path}\n")

    answer = run_agent(NoteStore(workdir), question, tracer)
    print("\n" + answer)
