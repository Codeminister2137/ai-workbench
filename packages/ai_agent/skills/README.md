# Portable skill sources

These repository-owned `SKILL.md` sources use shared operation names and preserve
the caller's permissions. They are source examples for the approved development
foundation, not an installed skill registry or a capability manifest.

`review-repo-change` reviews an existing staged or unstaged local Git change
using read/search and bounded Git tools. It does not grant shell, write or network
access. Client-specific tool prefixes must resolve to the same implementations.

Clients discover skills from different directories. Until a common distribution
contract is selected, copy a source only into an explicitly selected test fixture
or installation location; do not change user-wide configuration automatically.
The provider-native CLI does not yet discover or invoke these sources as skills.
Skill syntax/discovery and actual invocation are separate acceptance checks.
