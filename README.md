# Investment Intelligence Operating System (IIOS)

IIOS is an AI-native research and decision-support platform I built to explore how specialized AI agents, live data, governance controls, and a browser-based operations interface can work together as one system.

> **Status:** Active personal engineering project. Built with AI-assisted development workflows and validated through code review, tests, runtime checks, and iterative debugging. This project is for research and paper-trading workflows only; it does not execute live trades.

## Why I built it

I wanted to go beyond a single chatbot and learn how to build an operating system around AI: multiple specialized agents, evidence collection, decision gates, memory, telemetry, APIs, and a UI that makes the system's state understandable.

The project became a hands-on way to learn how to turn an ambiguous product idea into a working, evolving software system.

## What the system does

IIOS coordinates an investment-research workflow that can:

- ingest market and research inputs from external services;
- route work through specialized AI/analysis components;
- preserve evidence and provenance around decisions;
- apply deterministic risk and governance gates;
- maintain paper-portfolio state and learning records;
- expose backend capabilities through FastAPI routes;
- surface system activity through a React/TypeScript browser interface;
- monitor runtime health, freshness, and operational state.

## What I personally focused on

My work has centered on **figuring out how the system should work, building it, testing it, finding where it breaks, and iterating until the behavior is understandable and reliable**.

Examples include:

- designing the multi-agent workflow and system architecture;
- building and integrating Python/FastAPI backend services;
- wiring LLM and external-data integrations into governed workflows;
- creating agent orchestration, routing, and memory/learning components;
- building React/TypeScript/Vite frontend experiences;
- adding health checks, telemetry, evidence traces, and fail-closed behavior;
- working through deployment, configuration, API, frontend/backend, and runtime problems;
- using Git/GitHub branches, commits, pull requests, tests, and deployment checkpoints;
- using modern AI coding tools as development collaborators while validating the resulting system through tests and runtime evidence.

## Tech stack

### Backend

- Python
- FastAPI
- REST APIs / JSON
- OpenAI and other model/data integrations
- environment-based configuration
- automated tests and validation harnesses

### Frontend

- React 19
- TypeScript
- Vite
- ESLint

### Engineering workflow

- Git / GitHub
- branch-based development
- API integration and debugging
- test-driven validation for critical workflows
- deployment and runtime verification
- observability / telemetry
- AI-assisted software development

## Architecture themes

IIOS has several recurring design principles:

1. **Evidence before action** - important outputs should be traceable to their inputs.
2. **Fail closed** - missing or stale evidence should reduce system authority rather than silently pass.
3. **Specialized agents** - different components own different analytical responsibilities.
4. **Human-visible state** - the UI should show what the system is actually doing, not a decorative simulation.
5. **Learning loops** - outcomes can be recorded and used to improve later decisions.
6. **Paper-first execution** - experimentation stays separated from live financial execution.

## Selected implementation areas

The repository includes working code and documentation for areas such as:

- FastAPI application and health endpoints
- multi-agent orchestration and opportunity dispatch
- cross-case and historical-regime memory
- agent calibration and weighting
- market/opportunity collection
- paper execution controls
- deterministic risk inspection
- governance and provenance checks
- frontend command-center and factory experiences
- runtime telemetry and health verification

## Repository structure

```text
BACK END/    Python/FastAPI services, agents, orchestration, validation, telemetry
FRONT END/   React + TypeScript + Vite user interface
DOCS/        Architecture, implementation plans, decision records, tickets, and operating documentation
```

## What I learned building IIOS

The biggest lesson has been that building AI software is less about getting one impressive model response and more about everything around it: clear contracts, data quality, APIs, failures, retries, state, observability, testing, provenance, deployment, and knowing when a system should abstain.

I am still early in my software-engineering career, and IIOS is intentionally a learning-by-building project. The value of the project for me is that it forced me to work through real integration and reliability problems instead of stopping at a demo.

## Portfolio note

I am currently pursuing early-career roles in AI operations, AI automation, applied AI, and forward-deployed engineering where I can keep doing this kind of work: understand a problem, learn the tools, build the workflow, ship it, and own the result.

---

**Project:** Investment Intelligence Operating System  
**Primary language:** Python  
**Frontend:** React + TypeScript + Vite  
**Development style:** AI-assisted, test-validated, iterative engineering
