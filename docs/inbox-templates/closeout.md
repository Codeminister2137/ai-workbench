# Inbox closeout template

Copy the body below when filing `task` closeouts for answered decisions.
Keep the blank line between the answer record and the instruction.

```text
Owner answered '[FILL: source item id]' ([FILL: source title]): [FILL: chosen option]
Note: [FILL: owner note verbatim, or (none)]

Implement the answer, run the proving checks, write the resolution on the source item, and close it.
```

Record `closeout_for` in metadata and link the source via
`context_refs` (`inbox:<source-id>`).
