# Installation and external runtimes

## Python workspace

This repository uses a `uv` workspace with dependencies declared in
`pyproject.toml` and resolved in `uv.lock`. `uv sync` creates or updates the
project's `.venv`; `uv run` executes in that workspace environment. The supported
Python range is `>=3.13,<3.15`.

```powershell
python -m uv sync
python -m uv run --no-sync ai-assistant --help
```

Apply Python dependency changes through the project configuration and lockfile.
Avoid installing project dependencies into an unrelated system interpreter.
IDE interpreter configuration and the interpreter used to launch `uv` are not
necessarily the resulting workspace interpreter; check them when troubleshooting.

## External prerequisites are separate

A Python virtual environment does not install Node.js, Ollama, native coding-agent
clients, model files or their authenticated accounts. Copying `.venv` to another
machine is not a deployment procedure. Recreate Python dependencies, provision
the selected external prerequisites, configure local paths, then authenticate
through each official client.

| Selected path | Additional prerequisite | What remains outside Python dependency resolution |
| --- | --- | --- |
| Ollama local inference | Ollama runtime and selected model files | Runtime version, service lifecycle, GPU/driver compatibility, model storage and downloads |
| Codex / Copilot / Kiro / Antigravity | Selected official native client | Client version, account sign-in, entitlement, native tools/settings and approved MCP mapping |
| Gemini CLI (individual access retired) | Compatible Node/npm and official Gemini CLI | Historical adapter/setup only. Google retired individual/free access on 2026-06-18; enterprise/API access is a separate, unapproved route |
| Hosted provider API | Configured supported adapter and API credential | Network access, account limits, cost policy and data contract; no local Node requirement merely for HTTP API access |

Provision only the paths selected for a deployment. Installing every possible
agent or model is unnecessary. The application's source-state reference records
which integrations exist and which remain planned:
[provider source state](../packages/ai_provider/docs/source-state.md).

## Project-local setup direction

The owner selected project-scoped environment changes rather than unrelated
machine-wide installs. Use the existing ignored `.tools/` convention for portable
external runtimes/clients when the official distribution supports that placement.
Keep Python dependencies in `.venv`; keep Node/client dependencies in their own
project-local prefix. Do not make `uv sync` appear to manage these runtimes.

Gemini CLI execution is experimental and opt-in. Its documented prerequisite is Node.js
20 or newer; the selected release's actual package requirements must also be
checked. Before installation, pin runtime/client versions and record the source
and verification procedure. Use explicit paths or a process-local PATH; avoid
global PATH changes. Obtain attended readiness when an operation is known to
require owner input. Routine approved checks need no separate readiness request;
stop at an unexpected approval prompt, as required by AGENTS.md.

For another machine, the installation recipe must identify:

1. Supported OS/architecture and Python, `uv`, Node/runtime/client versions.
2. Official downloads or package sources, verification and project-local locations.
3. Model prerequisites and resource requirements for local inference.
4. Environment variable names and local command overrides, without credentials.
5. Owner-controlled native sign-in, permissions, allowance and overage settings.
6. Offline discovery/configuration checks followed by separately authorized live
   tool, coding-quality and cleanup acceptance.

Credentials, native sessions, machine-specific absolute paths, `.venv`, `.tools`,
model binaries and private run artifacts do not belong in the public repository.
Account state must be re-established on the destination machine. No broad
installer, automatic downloads, daemon or bundled runtime system is implemented
by this document.

## Windows installation and connection commands

Run these examples from the repository root in PowerShell. They are manual setup
recipes, not commands executed automatically by the application. Install only the
selected tools. Fresh versions below were resolved on 2026-10-13; they are setup
candidates, not versions accepted by our adapters. Preserve existing installations
and models. Other OS/architecture combinations need their matching distributions.

### Portable Node and Gemini CLI

**Access correction, 2026-10-14:** Google retired Gemini CLI access for individual
free, AI Pro and AI Ultra accounts on 2026-06-18. The owner's native sign-in
returned the matching retirement error. The historical recipe below installs the
client but cannot restore individual access. Do not retry sign-in or change
versions to bypass this restriction. The application refuses its experimental
individual free route; cached sessions do not admit it. Enterprise/API access is
different and is not substituted. See the
[official retirement announcement](https://github.com/google-gemini/gemini-cli/discussions/28017).

This Windows x64 recipe keeps the runtime and npm prefix under ignored `.tools/`.
Node's official LTS metadata selected `v24.21.0`; Gemini's npm metadata selected
`0.64.0` with Node `>=20`. Recheck compatibility before using a different release.
The archive hash below was read from the official Node checksum manifest.

```powershell
$nodeVersion = 'v24.21.0'
$nodeArchive = "node-$nodeVersion-win-x64.zip"
$nodeHash = '158f7685b44de51f6c0df1d153526cbcd3e1bc739a8dfc607721cef75de9e541'
$toolsRoot = Join-Path (Get-Location) '.tools'
New-Item -ItemType Directory -Force $toolsRoot | Out-Null
$archivePath = Join-Path $toolsRoot $nodeArchive
$nodeDirectory = Join-Path $toolsRoot "node-$nodeVersion-win-x64"
if (Test-Path $nodeDirectory) { throw 'Existing Node directory: inspect before replacing.' }
Invoke-WebRequest "https://nodejs.org/dist/$nodeVersion/$nodeArchive" -OutFile $archivePath
if ((Get-FileHash $archivePath -Algorithm SHA256).Hash -ne $nodeHash) {
    throw 'Node archive checksum mismatch.'
}
Expand-Archive -LiteralPath $archivePath -DestinationPath $toolsRoot
& (Join-Path $nodeDirectory 'node.exe') --version

# Current PowerShell process only; no user/system PATH change.
$previousPath = $env:PATH
$env:PATH = "$nodeDirectory;$previousPath"
$geminiPrefix = Join-Path $toolsRoot 'gemini-cli'
& (Join-Path $nodeDirectory 'npm.cmd') install --prefix $geminiPrefix `
    --cache (Join-Path $toolsRoot 'npm-cache') --save-exact --no-audit --no-fund `
    '@google/gemini-cli@0.64.0'
if ($LASTEXITCODE -ne 0) { throw 'Gemini CLI installation failed.' }
$geminiCommand = Join-Path $geminiPrefix 'node_modules/.bin/gemini.cmd'
& $geminiCommand --version
& $geminiCommand --help
```

Installation can execute npm package lifecycle scripts. Keep the generated npm
lockfile with the local setup evidence; the Python `uv.lock` does not cover it.
These version/help checks use no model prompt. For native authentication, run:

```powershell
& $geminiCommand
# Choose Sign in with Google; the owner completes the browser flow.
# Exit after sign-in without submitting a model task.
$env:PATH = $previousPath
```

Google-account access is distinct from API-key/Vertex billing. Re-establish the
process-local Node PATH before running the npm command shim in another terminal.
The experimental adapter supports this pinned Node/client pair, project-local
discovery, and `GEMINI_CLI_COMMAND` / `GEMINI_NODE_COMMAND` overrides. It invokes
Node directly rather than relying on a global PATH or a Windows shell shim.
Use the separate `packages/ai_orchestrator/examples/gemini_cli_catalog.toml`
catalog to opt in; the default catalog is unchanged. Shared inspection/coding
tools are required. The adapter creates `.gemini/settings.json` exclusively for
the invocation, refuses an existing file, verifies the client's effective
settings before inference, and removes only its unchanged generated file.
It disables native tools/hooks/extensions/updates, local `.env` loading and
prompt telemetry, while the shared host enforces the selected approval policy.
API-key/Vertex overrides refuse. The individual free route now refuses regardless
of cache presence because its service access was retired. Offline tools passed;
the approved live pilot never started and is blocked. See
[external-agent guidance](repo-assistant/external-agents.md).
Sources: [Gemini installation](https://geminicli.com/docs/get-started/installation/),
[authentication](https://geminicli.com/docs/get-started/authentication/),
[Node releases](https://nodejs.org/dist/index.json).

### Portable Ollama, model download and connection

The official Windows standalone archive supports explicit foreground operation.
This x64 example uses release `v0.40.3`; its release metadata supplied the checksum.
It is not an instruction to upgrade this workstation's existing Ollama installation.
GPU library requirements vary; see the [Windows guide](https://docs.ollama.com/windows).

```powershell
$ollamaVersion = 'v0.40.3'
$ollamaDirectory = Join-Path (Get-Location) ".tools/ollama-$ollamaVersion"
if (Test-Path $ollamaDirectory) { throw 'Existing Ollama directory: inspect before replacing.' }
New-Item -ItemType Directory -Force '.tools' | Out-Null
$ollamaArchive = Join-Path (Get-Location) ".tools/ollama-$ollamaVersion.zip"
Invoke-WebRequest `
    "https://github.com/ollama/ollama/releases/download/$ollamaVersion/ollama-windows-amd64.zip" `
    -OutFile $ollamaArchive
if ((Get-FileHash $ollamaArchive -Algorithm SHA256).Hash -ne `
    'e5ecff02dfc7cae8ddf6d6b7a7ac5f727ffeedf4491f44ae75ff5b0820dbbbd5') {
    throw 'Ollama archive checksum mismatch.'
}
Expand-Archive -LiteralPath $ollamaArchive -DestinationPath $ollamaDirectory
$ollamaCommand = Join-Path $ollamaDirectory 'ollama.exe'
& $ollamaCommand --version
$env:OLLAMA_HOST = '127.0.0.1:11434'
$env:OLLAMA_MODELS = Join-Path (Get-Location) '.tools/ollama-models'
& $ollamaCommand serve
```

`serve` occupies that terminal until stopped with Ctrl+C. If port 11434 is already
served by the intended runtime, use it instead of starting a competing process.
In another terminal, set `$ollamaCommand` to the same executable, then:

```powershell
Invoke-RestMethod 'http://127.0.0.1:11434/api/version'
& $ollamaCommand list
# Explicit model download; size/resource suitability must be checked first.
& $ollamaCommand pull 'qwen2.5-coder:14b'
```

Add the following non-secret values to local `.env`, preserving any existing model
storage choice. Set `OLLAMA_MODELS` before starting the server, not only its client.

```dotenv
AI_PROVIDER_KIND=ollama
AI_PROVIDER_BASE_URL=http://127.0.0.1:11434
AI_PROVIDER_MODEL=qwen2.5-coder:14b
# OLLAMA_MODELS='absolute path to selected model storage'
```

Inspect application routing without inference:

```powershell
.\scripts\repo-assistant.ps1 --mode plan --provider ollama `
    --model qwen2.5-coder:14b 'Check this configured route.'
```

Connection/model listing is not a model-quality test. A live coding request still
needs its selected privacy, resource and acceptance scope. The root launcher does
not currently resolve this portable executable automatically; start the selected
server explicitly, or add its directory to the current process PATH before using
`--start-ollama`. Do not turn this recipe into an unapproved persistent service.

### Other official clients

For an existing client, configure its absolute executable path in local `.env`:

```dotenv
CODEX_COMMAND='absolute path to Codex executable'
GITHUB_COPILOT_COMMAND='absolute path to Copilot executable'
KIRO_COMMAND='absolute path to kiro-cli executable'
ANTIGRAVITY_COMMAND='absolute path to agy executable'
```

Codex account connection uses `codex login`, followed by `codex login status`.
Use the [official installation guide](https://learn.chatgpt.com/docs/codex/cli)
when no binary exists. Native sign-in is owner-controlled; API-key access is a
different billing route. [Authentication reference](https://learn.chatgpt.com/docs/auth).

For Copilot, with the portable Node PATH configured as above, a local npm prefix
can replace the official guide's global installation. Select an explicit version:

```powershell
$copilotVersion = Read-Host 'Copilot version selected from official release metadata'
if ($copilotVersion -notmatch '^\d+\.\d+\.\d+$') { throw 'Expected an explicit release version.' }
& (Join-Path $nodeDirectory 'npm.cmd') install --prefix '.tools/copilot' `
    --cache '.tools/npm-cache' --save-exact --no-audit --no-fund "@github/copilot@$copilotVersion"
& '.tools/copilot/node_modules/.bin/copilot.cmd' --version
& '.tools/copilot/node_modules/.bin/copilot.cmd'
# In the native prompt, enter /login and complete the owner browser flow.
```

The documented alternative `winget install GitHub.Copilot` changes the user/machine
installation rather than the project prefix; it is not the selected setup here.
Current npm prerequisite is Node 22+. [Copilot setup](https://docs.github.com/en/copilot/get-started/cli-quickstart).

For Kiro Windows installation, open the [official setup page](https://kiro.dev/docs/cli/setup/)
and choose its Windows installer. No project-local installer prefix was verified;
do not assume the IDE installer installs a compatible CLI or reuse Unix commands
in PowerShell. After installing the selected official client:

```powershell
kiro-cli --version
kiro-cli login
```

Antigravity's Windows installer defaults to the user's local application directory.
The script inspected on 2026-10-13 also supports `--dir` and forwards other options
to native environment setup. Download and inspect it before executing it:

```powershell
Invoke-WebRequest 'https://antigravity.google/cli/install.ps1' `
    -OutFile '.tools/antigravity-install.ps1'
Get-Content '.tools/antigravity-install.ps1'
$antigravityDirectory = Join-Path (Get-Location) '.tools/antigravity'
& '.tools/antigravity-install.ps1' --dir $antigravityDirectory --skip-path --skip-aliases
& (Join-Path $antigravityDirectory 'agy.exe') --version
& (Join-Path $antigravityDirectory 'agy.exe')
# Complete native browser sign-in if requested; do not submit a task yet.
```

Installer flags and behavior must be checked against the downloaded script before
execution. The current installer still stages downloads in user AppData and reports
background client self-updates; a local binary directory does not isolate all
client state or pin future updates. Record the installed version and verification
evidence for deployment. Existing authenticated installs need no reinstall.
[Antigravity setup](https://www.antigravity.google/docs/cli/install/).

Hosted Requesty needs an API key from its account dashboard, not Node or a native
agent install. Put `REQUESTY_API_KEY` in local `.env` using an editor; never include
the actual key in saved commands or documentation.

OpenRouter now has an experimental free-only API adapter. Configure
`OPENROUTER_API_KEY` in the ignored local `.env` using an editor, or in the process
environment. Never paste it into chat or a saved command. The existing PowerShell
launcher loads `.env` through `uv --env-file`; direct Python calls require the
environment to be loaded explicitly. No Node install or Google sign-in is needed.
Use the separate opt-in
[`openrouter_free_catalog.toml`](../packages/ai_orchestrator/examples/openrouter_free_catalog.toml)
with the existing repo-assistant catalog option. The global catalog is unchanged.

The adapter requires an exact named `:free` model, current zero prices for every
advertised charge, tool support and a consistent positive
`free_model_daily_requests` observation before every model call. It sends zero
provider price caps, `require_parameters=true` and `data_collection=deny`. Missing
metadata or unavailable compliant endpoints refuse; credits are not free quota.
This filter reflects OpenRouter's provider-policy knowledge and does not guarantee
that the gateway itself has no retention. Only approved synthetic/public context
belongs in initial acceptance. No paid plugin, model router, deposit or paid retry
is enabled. [Routing filters](https://openrouter.ai/docs/guides/routing/provider-selection)
and [account limits](https://openrouter.ai/docs/api_reference/limits).

The example Qwen candidate is provisional STANDARD, not evaluated coding quality;
its public endpoint listing was empty on 2026-10-14. Local tests establish software
behavior, not account readiness or usable capacity. Authenticate/configure the key
locally, then perform an attended metadata-only check and obtain a fresh bounded
synthetic acceptance grant before inference. The unused Gemini pilot grant does
not authorize OpenRouter inference.

Final contract check found a conflict: the [pricing table](https://openrouter.ai/pricing/)
excludes data-policy routing from Free, while routing/provider-logging guidance
describes filters without that qualification. The client therefore refuses a
key reporting `is_free_tier=true` or unknown tier before inference. Offline success
fixtures simulate an already non-free-tier account using zero-priced models;
they do not prove Free-plan filter enforcement. Resolve this contract before a
free-account pilot. This is not a recommendation or authorization to deposit.

See the [external-client guide](repo-assistant/external-agents.md) for current
command overrides and restrictions, and [ADR-057](decisions/ADR-057-free-gemini-cli-and-openrouter-direction.md)
for the approved Gemini CLI/OpenRouter direction.
