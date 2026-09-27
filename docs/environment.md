# Environment And Secrets Policy

This repository uses environment variables for local machine settings and
provider credentials. Secrets belong in a local `.env` file or in the current
terminal process environment, never in committed code or documentation.

## Files

- `.env.example` is committed and contains safe placeholder values.
- `.env` is local-only and ignored by Git.
- `.env.*` is ignored by Git.
- `!.env.example` is explicitly allowed by `.gitignore`.

Create your local file by copying the example:

```powershell
Copy-Item .env.example .env
```

Then edit `.env` yourself and add real values only there.

## Where To Run Commands

Use either the PyCharm Terminal tab or a normal Windows PowerShell window.

Run commands from the repository root:

```powershell
cd C:\Users\Jakub\PycharmProjects\AI-projects
```

Confirm the directory:

```powershell
git status --short
```

## Normal Command Path

For normal CLI use, run the wrapper script:

```powershell
.\scripts\repo-assistant.ps1 "YOUR REQUEST" --provider ollama --model qwen2.5-coder:14b --execute --start-ollama
```

If Windows blocks direct script execution, use:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\repo-assistant.ps1 "YOUR REQUEST" --provider ollama --model qwen2.5-coder:14b --execute --start-ollama
```

The wrapper script:

1. finds the repository root;
2. loads `.env` into the script process if `.env` exists;
3. starts `packages\ai_provider\examples\repo_coding_assistant.py`;
4. passes the rest of your command arguments through to the Python CLI.

This means you normally do not need to manually run separate `.env` loading
commands.

## Manual `.env` Loading

Python does not automatically read `.env` in this repository right now. The
PowerShell wrapper loads it for CLI runs. If you are running another Python
entrypoint directly, you can manually load `.env` into the current PowerShell
session:

```powershell
Get-Content .env |
  Where-Object { $_ -and $_ -notmatch '^\s*#' } |
  ForEach-Object {
    $name, $value = $_ -split '=', 2
    [Environment]::SetEnvironmentVariable($name.Trim(), $value.Trim().Trim('"'), 'Process')
  }
```

This affects only the current terminal session. Opening a new terminal requires
loading `.env` again, unless you use `.\scripts\repo-assistant.ps1`.

## Current Variables

Provider defaults:

```text
AI_PROVIDER_KIND=ollama
AI_PROVIDER_MODEL=qwen2.5-coder:14b
AI_PROVIDER_BASE_URL=http://localhost:11434
AI_PROVIDER_TIMEOUT_SECONDS=60
```

Generic provider API key:

```text
AI_PROVIDER_API_KEY=
```

Provider-specific API keys:

```text
OPENAI_API_KEY=
REQUESTY_API_KEY=
GEMINI_API_KEY=
GOOGLE_API_KEY=
```

For Google/Gemini routes, either `GEMINI_API_KEY` or `GOOGLE_API_KEY` is enough.
Prefer `GEMINI_API_KEY` when using Google AI Studio style Gemini credentials.

Local Ollama model location:

```text
OLLAMA_MODELS=D:\AI\Ollama\models
```

Optional external-agent command overrides:

```text
CODEX_COMMAND=
ANTIGRAVITY_COMMAND=
GITHUB_COPILOT_COMMAND=
KIRO_COMMAND=
CODEX_HOME=
```

Leave these blank unless auto-discovery cannot find the executable or Codex
config root you want. `CODEX_COMMAND` can point to the Codex CLI executable;
`CODEX_HOME` changes where Codex looks for its config. The repo assistant never
needs real passwords in these fields.

The repo assistant also supports explicit local resource profiles:

```text
gaming  -> OLLAMA_CONTEXT_LENGTH=4096
balanced -> OLLAMA_CONTEXT_LENGTH=8192
full    -> OLLAMA_CONTEXT_LENGTH=32768
```

These profiles are applied to an Ollama server started by the assistant and
also set `OLLAMA_NUM_PARALLEL=1` and `OLLAMA_MAX_LOADED_MODELS=1`. They are
memory/concurrency profiles, not exact GPU-percentage limits. A running Ollama
server must be restarted for a changed profile to take effect.

`BackendConfig.from_env()` uses `AI_PROVIDER_API_KEY` first. If it is unset, it
falls back to `OPENAI_API_KEY` for OpenAI, `REQUESTY_API_KEY` for Requesty, and
`GEMINI_API_KEY` or `GOOGLE_API_KEY` for Google.

## Privacy Rules

- Local Ollama is the default privacy-preserving path.
- Hosted providers are external processors.
- Use hosted providers only with `--privacy external_allowed` or another
  intentionally selected external-compatible privacy class.
- Do not send secrets, private documents, or broad unreviewed directories as
  prompt context.
- Do not log or paste API keys into chat, source code, tests, docs, or commits.
- Do not add real values to `.env.example`.
- Review `git diff` and `git status --short` before committing after touching
  configuration.

## Hosted Provider Setup

OpenAI:

```powershell
Copy-Item .env.example .env
# Edit .env and set OPENAI_API_KEY=...
```

Then run a hosted command with the wrapper:

```powershell
.\scripts\repo-assistant.ps1 "YOUR REQUEST" --privacy external_allowed --provider openai --model gpt-5-mini --cost-policy billing_allowed --execute
```

Requesty:

```powershell
Copy-Item .env.example .env
# Edit .env and set REQUESTY_API_KEY=...
```

Then run a hosted command with the wrapper:

```powershell
.\scripts\repo-assistant.ps1 "YOUR REQUEST" --privacy external_allowed --provider requesty --model openai/gpt-5.1 --execute
```

## Future Decision

Automatic Python-level `.env` loading is not enabled yet. The PowerShell wrapper
loads `.env` for CLI runs. If the Python packages later need direct automatic
`.env` loading, make it an explicit decision because it affects
credential-loading behavior and may justify either a small standard-library
loader or a dependency such as `python-dotenv`.
