# SearXNG replacement investigation

**BLOCKED on operator/service selection — no working replacement identified.**

On 2026-10-05, the owner-authorized D2 investigation fetched the public
[SearX instance registry](https://searx.space/data/instances.json) and probed JSON
search using only `python official documentation`. No repository content,
private prompts or credentials were sent. No configured endpoint was changed.
Registry HTML-search availability does not establish JSON API availability.

| Search endpoint | Observed response |
| --- | --- |
| `https://search.mectov.my.id/search` (current) | HTTP 200, zero results, Google suspended for access denial |
| `https://etsi.me/search` | HTTP 429 |
| `https://baresearch.org/search` | Response could not be parsed as JSON |
| `https://opnxng.com/search` | HTTP 429 |
| `https://search.sapti.me/search` | TLS trust failure; certificate checks were retained |
| `https://search.inetol.net/search` | Response could not be parsed as JSON |
| `https://searx.tiekoetter.com/search` | HTTP 429 |

These are single bounded probes, not uptime or privacy guarantees. Public APIs
can rate-limit shared egress or disable programmatic JSON access. The snapshot
and timed receipts are preserved under ignored
`artifacts/continuation-acceptance-20261005/`.

Recommendation: retain direct URL fetching until the owner supplies a usable
operator or chooses an authenticated search provider. Hosting SearXNG introduces
a service and maintenance; choosing a keyed provider introduces credentials and
possibly billing. Both remain owner decisions. Repeating public probes without
a new candidate or changed conditions is unlikely to improve the current result.
