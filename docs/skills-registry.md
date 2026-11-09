# Skills registry (generated — do not edit by hand)

Regenerate: `python scripts/generate_skill_registry.py`.
Checked in gate via `--check`.

| Tool | Category | Description | Parameters | Module |
|---|---|---|---|---|
| DelegateTaskTool | ? | Tool that lets a primary agent delegate bounded coding subtasks. | - | ai_agent.tools.delegation |
| create_file | write | Create a new file with specified content. Fails if file exists unless overwrite is True. | path, content, overwrite | filesystem |
| edit_file | write | Edit an existing file by replacing 'old_text' with 'new_text'. Both strings are literal file text: preserve indentation and do not add patch markers, read-output line numbers, or Markdown fences. To insert text without deleting the anchor, include old_text unchanged in new_text along with the added text. Retain existing content that the task requires unchanged. If old_text is omitted or empty, replaces full file content. | path, new_text, old_text | filesystem |
| list_dir | read | List files and directories within a directory up to max_depth. | path, max_depth | filesystem |
| read_file | read | Read content from a file with optional line range (1-indexed). Omitting bounds returns the entire file and consumes conversation context. For large files, locate relevant symbols with grep_search first, then supply start_line and end_line for focused excerpts. Set line_numbers=False to obtain literal text for exact edit anchors. | path, start_line, end_line, line_numbers | filesystem |
| git_diff | read | Show staged or unstaged Git diff, optionally narrowed to a path. | path, staged | git |
| git_status | read | Show workspace Git status without shell or remote operations. | - | git |
| request_owner_task | custom | Ask the human owner to do something only they can do: a manual test with steps, providing a secret/key, an access grant, or a decision. NEVER ask for secrets IN the task text — tell them where to put the secret (.env, User env). The run completes with the task filed; the owner answers in the inbox. | title, body | owner_tasks |
| python_runtime | read | Report the Python interpreter running this agent and workspace environment hints. This does not switch interpreters or execute workspace code. | - | python_runtime |
| python_navigate | read | Find Python definitions or references for the identifier at a one-based line and column. Results are limited to Python files inside the workspace; install the optional rename-preview extra to enable Jedi-backed navigation. | path, line, column, operation | refactor |
| RenameApplyTool | ? | Apply a reviewed preview only after policy authorization and digest checks. | - | ai_agent.tools.refactor |
| RenamePreviewTool | ? | Create a non-mutating, bounded preview of a Python symbol rename. | - | ai_agent.tools.refactor |
| FetchURLTool | ? | Retrieve bounded public text and record provenance outside model control. | - | ai_agent.tools.research |
| ResearchReportTool | ? | Read or replace only the configured Markdown report, never arbitrary files. | - | ai_agent.tools.research |
| SearchWebTool | ? | Expose queries only; models cannot choose credentials, costs, or routing. | - | ai_agent.tools.research_search |
| find_files | search | Find files matching a glob pattern (e.g. '*.py' or '*catalog*'). | pattern, path, max_results | search |
| grep_search | search | Search for exact text or regex patterns across workspace files. | query, path, is_regex, max_matches | search |
| run_command | shell | Execute a shell command (PowerShell on Windows, shell on POSIX) and return output. | command, cwd, timeout_seconds | shell |
| stage_file | write | Stage a complete new file version for owner review. Use this for EVERY project file change instead of writing directly: staged files are reviewed and applied by the owner after the run. Provide the full intended content, not a diff. | relpath, content | staged |
