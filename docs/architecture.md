# Architecture

## Component diagram

```mermaid
graph TD
    U[User]
    H[Host Agent<br/>Google ADK + Gemini]
    W[Grid Load Agent<br/>LangGraph + Gemini]
    D[(Mock grid-load data<br/>9 NA Balancing Authorities)]

    U -- natural-language query --> H
    H -- A2A protocol over HTTP:10004 --> W
    W -- tool call --> D
    D --> W
    W -- A2A artifact --> H
    H -- aggregated summary --> U
```

## Sequence (single-BA query)

```mermaid
sequenceDiagram
    autonumber
    participant User
    participant Host as Host Agent (ADK)
    participant Worker as Grid Load Agent (LangGraph)
    participant Tool as get_grid_load_by_balancing_authority

    User->>Host: "What is the current grid load in PJM?"
    Host->>Worker: A2A SendMessage (text: "current grid load in PJM?")
    Worker->>Worker: LangGraph ReAct loop, picks tool
    Worker->>Tool: get_grid_load_by_balancing_authority("PJM")
    Tool-->>Worker: "Current grid load in PJM: 112458.3 MW (mock)"
    Worker-->>Host: A2A Artifact + complete TaskStatus
    Host-->>User: "PJM: 112458.3 MW (mock data)"
```

## Lifecycle and protocol notes

- AgentCard discovery: at startup the Host fetches the worker's AgentCard from `/.well-known/agent.json`.
- Task lifecycle: every user query becomes a Task. The worker emits TaskStatusUpdate (`working`, `input_required`, `completed`) and TaskArtifactUpdate events. The Host aggregates artifacts and surfaces them to the user.
- Session context: the Host carries `session_id` across multi-turn conversations so memory persists per user.
