# Sentrya

AI-powered runtime security testing for open-source repositories using isolated **Daytona sandboxes**.

## Problem

GitHub provides tools such as CodeQL, Dependabot, and secret scanning to identify many common security issues. However, these tools primarily analyze source code, dependencies, and known vulnerability patterns.

They don't fully answer a different question:

> **What actually happens when the project is running and we actively test it?**

Sentrya addresses this by running repositories in isolated sandboxes using Daytona and applying custom runtime security tests.

## How It Works

A user provides a GitHub repository or asks the agent to find a suitable open-source repository for a specific purpose.

The agent:

* Analyzes the repository
* Identifies relevant entry points and attack surfaces
* Selects appropriate tests
* Adapts the tests to the repository
* Runs them in isolated Daytona sandboxes
* Collects and interprets the results
* Generates a security report

Tests can run independently and in parallel, with each test type using its own sandbox.

## Testing

The initial testing framework includes five custom runtime tests:

* **Fuzzing** — malformed and unexpected inputs
* **Injection** — SQL, command, path traversal, and template injection
* **Filesystem** — unexpected file access and path traversal
* **Network** — unexpected outbound connections and runtime network behavior
* **Resource abuse** — CPU, memory, disk, and process consumption

These tests are implemented in the `testing/` module. They are predefined by the project rather than customizable by the end user.

The agent is responsible for adapting the tests to each repository.

## Running it

One command starts both halves:

```bash
./dev.sh
```

* App — <http://localhost:5173>
* Agent API — <http://127.0.0.1:8000> (OpenAPI docs at `/docs`)

`dev.sh` creates `.venv`, installs `requirements.txt`, installs the app's npm
dependencies on first run, then starts the agent and the Vite dev server together.

To run the halves separately:

```bash
# agent + testing
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
PYTHONPATH=. .venv/bin/python -m uvicorn agent.server:app --port 8000

# app
cd app && npm install && npm run dev
```

The app auto-detects the agent. If `/api/health` answers it runs live; if not it
falls back to a built-in demo mode so the UI is always usable. Force either way with
`VITE_DEMO_MODE=true|false` in `app/.env`.

## How the parts talk

```text
app/  ──HTTP──▶  agent/  ──in-process──▶  testing/  ──▶  sandboxes
 UI              orchestrator             5 suites       one per suite
```

The app knows four endpoints and nothing else about how an evaluation happens:

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/health` | mode detection |
| `POST` | `/api/auditions` | start a run, returns an `Audition` |
| `GET` | `/api/auditions/{id}` | full state, including partial results |
| `GET` | `/api/auditions/{id}/status` | just the status |
| `DELETE` | `/api/auditions/{id}` | cancel |

The app polls `GET /api/auditions/{id}` while a run is in flight. The orchestrator
writes each suite into the store the moment it lands, which is what makes results
appear progressively instead of all at once.

`agent/models.py` and `app/src/types/audition.ts` are the same data model in two
languages — change one and change the other.

## Project Structure

```text
project/
├── app/        # User interface / API
├── agent/      # AI agent for repository analysis and orchestration
├── testing/    # Runtime security tests
└── README.md
```

### `app/`

Handles user interaction, repository input, testing requests, and displaying results.

### `agent/`

Analyzes repositories, selects and configures tests, and interprets their results.

### `testing/`

Contains the reusable runtime security testing framework and Daytona sandbox integration.

## Future Features

* Automatically discover suitable open-source repositories
* Validate new features before creating pull requests
* Automatically fix discovered issues
* Iteratively test changes in isolated sandboxes
* Compare original and modified project behavior

## Tech Stack

* Python
* FastAPI
* Daytona
* LLM-based agent
* GitHub
* Custom runtime security tests
