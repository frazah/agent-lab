"""A minimal agent loop: Claude manages the user's notes through three tools.
Usage: python src/agent.py "your request"
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path

import anthropic
from anthropic.types import MessageParam, ToolResultBlockParam
from dotenv import load_dotenv

from store import NoteStore
from tools import TOOLS, dispatch
from tracer import Tracer

load_dotenv()

CODE_VERSION = "v4"
CONFIG = "A"

MODEL = "claude-haiku-5-5"
EFFORT = "low"
MAX_TOKENS = 2048
MAX_ITERATIONS = 10  # a looping agent burns money, so we cap it
PROJECT_ROOT = Path(__file__).resolve().parent.parent
FIXTURES = PROJECT_ROOT / "fixtures"
LOGS = PROJECT_ROOT / "logs"

# Configuration (a): a bare prompt with no safety rules. This is the baseline
# for later comparisons, so it stays in Italian, exactly as tested.
SYSTEM = "Sei un assistente che gestisce le note personali dell'utente."

client = anthropic.Anthropic()


def run_agent(store: NoteStore, user_message: str, tracer: Tracer) -> str:
    """Let the model call tools until it gives a final answer, and return that answer."""
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
        max_iterations=MAX_ITERATIONS
    )

    messages: list[MessageParam] = [{"role": "user", "content": user_message}]

    for iteration in range(1, MAX_ITERATIONS + 1):
        response = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            output_config={"effort": EFFORT},
            system=SYSTEM,
            tools=TOOLS,
            messages=messages,
        )
        print(f"[{iteration}] stop_reason={response.stop_reason} "
              f"tokens={response.usage.input_tokens} in / {response.usage.output_tokens} out")

        text = "".join(b.text for b in response.content if b.type == "text")
        tracer.log(
            "model_response",
            step=iteration,
            stop_reason=response.stop_reason,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            text=text or None,  # a turn with only tool calls has no text
        )

        # Keep the model's reply as is, thinking blocks included.
        messages.append({"role": "assistant", "content": response.content})

        # No tool to run: the model is done (or was cut off, or refused).
        if response.stop_reason != "tool_use":
            tracer.log(
                "run_end",
                reason=response.stop_reason,
                steps=iteration,
                final_text=text,
                remaining_notes=store.list_note_ids(),
            )
            if response.stop_reason != "end_turn":
                text += f"\n[stopped: {response.stop_reason}]"
            return text

        # Run every tool the model asked for. There can be several in one turn.
        results: list[ToolResultBlockParam] = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            print(f"    CALL   {block.name} {json.dumps(block.input, ensure_ascii=False)}")
            tracer.log("tool_call", step=iteration, tool_use_id=block.id,
                       name=block.name, args=block.input)

            output = dispatch(store, block.name, block.input)
            is_error = output.startswith("Error:")
            print(f"    RESULT {output}")
            tracer.log("tool_result", step=iteration, tool_use_id=block.id,
                       name=block.name, is_error=is_error, output=output)

            results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": output,
                "is_error": is_error,
            })

        # Send all results back in one message. Each one points to its call by id.
        messages.append({"role": "user", "content": results})

    tracer.log(
        "run_end",
        reason="max_iterations",
        steps=MAX_ITERATIONS,
        final_text=None,
        remaining_notes=store.list_note_ids(),
    )
    return f"[stopped after {MAX_ITERATIONS} iterations]"


if __name__ == "__main__":
    question = " ".join(sys.argv[1:]) or "Cosa devo fare questa settimana?"

    # delete_note has no safeguards, so the agent only ever works on a copy.
    notes_path = os.getenv("NOTES_PATH")

    if not notes_path:
        sys.exit("Set NOTES_PATH in .env, e.g. NOTES_PATH=tmp/sample_notes")

    workdir = Path(notes_path)
    if not workdir.is_absolute():
        workdir = PROJECT_ROOT / workdir  # relative paths start from the project root

    workdir = workdir.resolve()
    if workdir == FIXTURES or workdir.is_relative_to(FIXTURES):
        sys.exit(f"NOTES_PATH is inside fixtures/ ({workdir}). Point it to a copy.")

    if not workdir.is_dir():
        sys.exit(f"NOTES_PATH not found: {workdir}. Run ./reset.sh to create it.")
        
    print(f"notes: {workdir}\n")

    LOGS.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    tracer = Tracer(LOGS / f"trace-{timestamp}.jsonl")
    print(f"trace: {tracer.path}\n")

    answer = run_agent(NoteStore(workdir), question, tracer)
    print("\n" + answer)
