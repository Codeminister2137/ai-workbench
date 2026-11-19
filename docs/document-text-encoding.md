# Document text encoding and consolidation

## Investigation (2026-11-19)

The private `company-names-consolidated.md` contained literal ASCII question
marks in its authored introduction, including inside a Polish place name and
where quotation marks and dashes belonged. Its appended source documents still
contained intact Unicode. This establishes corruption in the saved text rather
than a preview-only font problem.

A local Windows PowerShell 5.1 diagnostic reported `$OutputEncoding` as
`us-ascii`. Piping Polish text and punctuation into Python replaced the
non-ASCII characters with `?`. An explicit UTF-8 file write in Python cannot
repair input that was already damaged. The agent's foreground and background
shell tools both launched PowerShell without configuring that pipe encoding.
This is a reproduced defect consistent with the document's pattern; the exact
historical creation command was not recovered, so its attribution remains an
inference rather than a proven reconstruction.

The investigation searched for PowerShell native-pipe character loss and checked
Microsoft's [character encoding documentation](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.core/about/about_character_encoding?view=powershell-5.1)
and [OutputEncoding documentation](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.core/about/about_preference_variables).
Those describe the separate pipe and file encoding settings.

The recovered source report independently began with a truncated table row.
Copying that fragment into prose and an appendix did not restore its missing
header. The repair marks the omission, supplies a header for the surviving row,
and normalizes appendix heading levels and indentation. Candidate tables and
research caveats are retained; missing research is not reconstructed. Original
private bytes and a repair diff are saved locally under
`.tmp/document-repair-ddcd9a260d88/`; private content is not committed here.

## Prevention and limits

- Agent-owned Windows foreground and background commands configure UTF-8 for
  PowerShell native pipes, console streams and Python redirected streams. The
  foreground capture reader explicitly decodes UTF-8; the background reader
  already uses it. Other validation callers retain their existing defaults.
- Markdown download responses declare `charset=utf-8`, matching the preview's
  UTF-8 contract. Original bytes are served unchanged.
- File editors should use explicit UTF-8 and re-read the result. Native clients
  and manually opened shells do not inherit the agent tool's child-process
  settings. In PowerShell 5.1, use explicit `-Encoding utf8` for file cmdlets;
  avoid piping Unicode source code to Python without configuring
  `$OutputEncoding` first. Prefer file-edit tools or running a UTF-8 script file.
- An existing `?` is valid UTF-8 and can also be legitimate punctuation. Do not
  globally replace question marks or guess lost letters. Recover from intact
  sources or contextual evidence and preserve the original before repair.
- UTF-8 transport does not fix model-authored misspellings, truncated reports,
  or arbitrary native programs that intentionally emit another encoding.

Regression tests exercise actual PowerShell-to-Python input, exact UTF-8 file
bytes, stdout and stderr in both shell paths, plus HTTP Markdown download and
preview text with Polish letters. These tests use synthetic text and no model
inference.
