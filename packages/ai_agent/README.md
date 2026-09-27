# ai-agent

Agentic tool execution loop, tool registry, permission policies, and multi-turn coding session management built on top of `ai_orchestrator` and `ai_provider`.

## Features
- **Provider-Neutral Tool Registry**: Define tools with strict JSON schemas and run them across local and hosted models.
- **Built-in Coding Tools**: Safe file reading, slice editing, creation, directory listing, regex/grep search, and shell execution.
- **Permission & Safety Control**: Configurable approval policies for read vs. write vs. command execution, with workspace boundary enforcement.
- **Authorization Boundary**: Secret-free contracts for external service authorization state, read/write grants, credential locations, and reusable diagnostics.
- **Agent Loop**: Provider-neutral multi-turn tool-calling cycle with permission enforcement, tool-result messages, and iteration limits.
