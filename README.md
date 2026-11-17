# agent-lab

Agent Reliability & Safety Lab.

A small agent that manages personal notes through three tools (`search_notes`, `get_note`, `delete_note`), used to study how it behaves with and without safeguards.

## Layout

- `src/store.py` – reads, searches and deletes the Markdown notes
- `src/tools.py` – tool definitions for the model, and the dispatcher that runs them
- `src/agent.py` – the agent loop
- `fixtures/base_notes/` – the original notes. The agent never touches these.
- `experiments.md` – experiment log and findings

## Setup

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

Create a `.env` file:

```
ANTHROPIC_API_KEY=...
NOTES_PATH=tmp/sample_notes
```

## Run

```sh
./reset.sh                                  # fresh copy of the notes in tmp/
.venv/bin/python src/agent.py "your request"                # config A
.venv/bin/python src/agent.py "your request" --config B     # A, B or C
.venv/bin/python -m pytest                  # tests
```

`delete_note` has no safeguards, so the agent only runs on the copy in `NOTES_PATH` and refuses to start if it points inside `fixtures/`.
