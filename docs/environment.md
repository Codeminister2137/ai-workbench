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

## Loading `.env`

Python does not automatically read `.env` in this repository right now. That is
intentional: loading secrets is explicit, and no new dependency such as
`python-dotenv` is required.

To load `.env` into the current PowerShell session:

```powershell
Get-Content .env |
  Where-Object { $_ -and $_ -notmatch '^\s*#' } |
  ForEach-Object {
    $name, $value = $_ -split '=', 2
    [Environment]::SetEnvironmentVariable($name.Trim(), $value.Trim().Trim('"'), 'Process')
  }
```

This affects only the current terminal session. Opening a new terminal requires
loading `.env` again.

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
```

Local Ollama model location:

```text
OLLAMA_MODELS=D:\AI\Ollama\models
```

`BackendConfig.from_env()` uses `AI_PROVIDER_API_KEY` first. If it is unset, it
falls back to `OPENAI_API_KEY` for OpenAI and `REQUESTY_API_KEY` for Requesty.

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
Get-Content .env |
  Where-Object { $_ -and $_ -notmatch '^\s*#' } |
  ForEach-Object {
    $name, $value = $_ -split '=', 2
    [Environment]::SetEnvironmentVariable($name.Trim(), $value.Trim().Trim('"'), 'Process')
  }
```

Then run a hosted command with:

```powershell
--privacy external_allowed --provider openai --model gpt-5-mini
```

Requesty:

```powershell
Copy-Item .env.example .env
# Edit .env and set REQUESTY_API_KEY=...
Get-Content .env |
  Where-Object { $_ -and $_ -notmatch '^\s*#' } |
  ForEach-Object {
    $name, $value = $_ -split '=', 2
    [Environment]::SetEnvironmentVariable($name.Trim(), $value.Trim().Trim('"'), 'Process')
  }
```

Then run a hosted command with:

```powershell
--privacy external_allowed --provider requesty --model openai/gpt-5.1
```

## Future Decision

Automatic `.env` loading is not enabled yet. If the repo later needs that, make
it an explicit decision because it affects credential-loading behavior and may
justify either a small standard-library loader or a dependency such as
`python-dotenv`.
