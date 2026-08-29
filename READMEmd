# Sentrya

AI-powered runtime security testing for open-source repositories using isolated **Daytona sandboxes**.

## Problem

GitHub provides tools such as CodeQL, Dependabot, and secret scanning to identify many common security issues. However, these tools primarily analyze source code, dependencies, and known vulnerability patterns.

They don't fully answer a different question:

> **What actually happens when the project is running and we actively test it?**

Sentrya addresses this by running repositories in isolated sandboxes and applying custom runtime security tests.

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
