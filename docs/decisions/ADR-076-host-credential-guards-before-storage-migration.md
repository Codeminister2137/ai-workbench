# ADR-076: Host credential guards before storage migration

Status: Accepted owner sequencing, implemented first slice, 2026-10-28.

## Decision and rationale

The owner agreed to the recommended order, provided the choices are not mutually
exclusive. They are complementary: host guards prevent known credential material
from entering model/tool traffic; a later credential-store migration can reduce
plaintext storage and accidental file discovery. Moving storage alone does not
stop credential-bearing process output. No specific vault or migration design
is selected by this sequencing.

The first slice retains existing environment/config loading and adds:

- Project-owned file tools refuse known credential paths, including `.env` and
  `.env.*` except `.env.example`, selected CLI/SDK auth files and SSH private keys.
  Requested and resolved paths are checked; search traversal omits these files.
- Tool arguments containing known credentials are refused before execution.
  Tool output, metadata and exception text containing known credentials are
  replaced by a fixed error before tool-result receipts or the next request. Effects
  may already have occurred; the refusal does not claim rollback.
- Native agent requests and the shared Chat Completions, Responses, Messages and
  Ollama builders refuse known credentials before transport. Official CLI launch
  prompts are checked before process/session setup. Rejection has no raw-input
  diagnostic fields; required context is not silently redacted or dropped.

Known values come from explicit configured credentials and secret-named environment
variables (minimum 16 characters for ambient discovery). Provider configs protect
explicit credentials of any length. Values remain in host memory; guards do not
read credential files, create a credential database or log matching values.

## Alternatives and consequences

- Guards first: closes the demonstrated `.env` tool-to-model path with existing
  loaders, but cannot establish complete secret/private-data detection.
- Storage migration first: reduces workspace plaintext, but requires a chosen
  platform/loader migration and would still need the same traffic guards.

## Limits

This is a bounded credential subset of the restricted-input plan's general
repository protection, not completion of that plan. Unknown/unloaded secrets,
arbitrary encodings, private semantic data, native clients' independent file
access and arbitrary shell/network/file effects remain outside this guarantee.
Commands retain existing permissions, including their own files/captures; result
withholding is not a disk-write guard or an OS sandbox. No additional
permission to send private Workbench source/plans or mailbox contents is granted.

Tests use synthetic credentials, actual tools/process output, MCP serialization,
scripted agent continuation and forbidden transport callbacks. Existing protocol
fixtures use distinct authentication tokens so they test protocol handling rather
than intentionally placing the authentication token into their own request text.
