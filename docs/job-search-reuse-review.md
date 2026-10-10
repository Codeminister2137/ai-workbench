# Job-search reuse review

Reviewed 2026-10-10. **Investigation complete for the comparison below;
deployment and runtime validation remain unselected.** The owner prefers researching,
reusing, adapting or cloning existing projects to building another application
from scratch, and identified open-jobs as a candidate.

The private Job Search Automation plan's ingestion and normalization phase was
compared with `apps/job_search/job-email`: vacancy records, deduplication,
evidence-backed preparation and guarded delivery exist; discovery does not.
Reusing a discovery source or a complete workspace can satisfy that phase.
The plan does not require us to implement our own crawler or dashboard.

## Candidates

| Candidate | Reusable responsibility | Benefits | Costs and remaining evidence |
| --- | --- | --- | --- |
| [open-jobs](https://github.com/elliottdehn/open-jobs) | Existing ATS-derived index, search tools, local feedback/ranking and shortlist exports | Avoids maintaining a crawl fleet; provides both hosted search and local tools; repository licence is CC0 | Not a complete application tracker. Semantic discovery sends the ideal-role description to its hosted embedding endpoint. Target-market coverage, index freshness and shortlist usefulness need a bounded trial. |
| [Openings](https://github.com/VincenzoImp/openings) | Collection, local ranking, application tracking, attachments, REST API and MCP | Can replace much of a custom job-search workspace; inspected licence is MIT; JSON/CSV export provides an integration boundary | Adds an application database, dependencies and a running web process; default Compose also runs a scheduler. Declares beta status. Its writable API/MCP needs explicit access scope; source coverage and reliability are untested here. |
| [JobSpy](https://github.com/speedyapply/JobSpy) | Python job-board collection library | Narrow reusable discovery component; MIT; documents an Indeed Poland option | Provides no application workspace. Scraper availability and board access remain source-specific; advertised coverage is not proof of successful collection. |
| [JobOps](https://github.com/DaKheera47/job-ops) | Search, fit scoring, CV tailoring and application tracking UI | Broad ready-made workflow; optional local or hosted AI providers | Broader deployment and privacy review. Documents analytics and optional Gmail integration. Its [licence](https://github.com/DaKheera47/job-ops/blob/main/LICENSE) is AGPLv3 plus Commons Clause, including a restriction on selling substantially derived services; reconsider before business-oriented reuse. |

These are capabilities found in primary documentation and selected source files,
not application-quality test results. No candidate is accepted merely because
its README lists matching features. JobTrail was also discovered, but its source
inspection was insufficient to rank it in this first comparison.

## Verified open-jobs boundary

Pinned source: `309f6c9e58d0ece4c4ffa6a00f83dc5cfdbdd87b`.
An isolated, shallow, no-checkout source snapshot is under
`artifacts/job-search-reuse-20261010/open-jobs`.

The inspected [client](https://github.com/elliottdehn/open-jobs/blob/309f6c9e58d0ece4c4ffa6a00f83dc5cfdbdd87b/tools/jobs.py)
sends the selected file's entire text, title and location to
`backend.dehnbostele.workers.dev/embed`. The backend embedding implementation
calls OpenAI. The [backend documentation](https://github.com/elliottdehn/open-jobs/blob/309f6c9e58d0ece4c4ffa6a00f83dc5cfdbdd87b/backend/DOCS.md)
describes the public data/index endpoints and optional server-side model work.
Local tool dependencies include NumPy and DuckDB; installed compatibility has
not been verified. The upstream workflow persists a local slice and user labels.

An eventual trial must choose an approved role-description payload and download
bound. Keep CVs, evidence profiles, application notes and labels out of that
embedding request. Use a small slice, not a full corpus mirror. Optional
enrichment, model-assisted ranking and the upstream ideas-posting channel are
separate operations, not implied by adopting discovery. None ran in this review.
Freshness and inferred fields remain source observations, not verified facts or
proof that a posting is open; preserve source identity and uncertainty.

## Verified Openings boundary

Pinned source: `156dedef348747652a72c961edde3eb103452c6d` (project version 0.4.2).
Its shallow, no-checkout snapshot is under the same artifact directory.

Inspected `LICENSE`, `pyproject.toml`, Compose and API authentication code.
The [API](https://github.com/VincenzoImp/openings/blob/156dedef348747652a72c961edde3eb103452c6d/docs/user/api.md)
exports job data and serves attachments, notes and status changes. Its token is
optional; absence leaves the API accessible to whoever can reach its port.
The [security guidance](https://github.com/VincenzoImp/openings/blob/156dedef348747652a72c961edde3eb103452c6d/SECURITY.md)
and [MCP contract](https://github.com/VincenzoImp/openings/blob/156dedef348747652a72c961edde3eb103452c6d/docs/user/mcp.md)
make clear that these surfaces can change personal data. Default Compose binds
the web port to loopback and uses a persistent data volume shared with a scheduler.
Do not automatically give a model all those read/write tools, or send private
attachments to its provider. Existing application approval boundaries still apply.
The bare `openings-web` entry point binds `0.0.0.0`, unlike Compose's loopback
port publication; do not assume a direct launch has the same access boundary.
Embeddings are enabled on save by default. They execute locally but lazily
download an ONNX model/tokenizer from Hugging Face. An offline/no-download trial
must explicitly disable them; the isolated persistence probes did so. These are
deployment requirements to resolve before running the app, not settings changed
by this review.

## Owner direction and next investigation

The owner subsequently selected **Openings as the better primary candidate**:
delegate discovery/tracking to an existing app and add our evidence-backed AI CV
tailoring and reviewed application delivery. Supplementing its search with
open-jobs is under consideration, not yet an accepted integration. Selecting a
candidate does not establish runtime fit or approve installation, cloud profile
processing, automatic submissions or a deployment/data contract.

Openings collects through JobSpy, direct ATS adapters, RSS, JobCloud and Adzuna;
it is not limited to JobSpy. Its configured employer list and open-jobs' broader
company index may be complementary. Actual additional useful vacancies, overlap
and current availability must be measured for the owner's target roles/locations.
Prefer measuring unique, relevant, currently open vacancies and review time over
raw posting count. Compare the same search criteria and observation interval.

The inspected Openings API supports adding jobs, application attachments, Q&A
notes and status updates. A small external adapter is therefore plausible without
first maintaining a fork. It is not a proven lossless multi-source import:
`ApplicationService.add_job` finds matches by posting key or identity and updates
an existing job, whereas collection's `upsert_jobs` explicitly attaches mirrors.
Before importing repeated open-jobs results, test URL/source retention, status
preservation, replay and distinct requisitions with identical titles. New intake
must explicitly request `new`; the manual API defaults to `shortlisted`.
An offline probe of pinned models/SQLite and AST-extracted service methods now
confirms the concern: an identity-matched manual import changed the displayed URL
to the second source, retained the original `source`, and left one posting record.
The crawler upsert retained the original URL and two posting records; repeating
either path preserved `applied` status. Scoring/embedding were disabled/stubbed;
this is narrow persistence evidence, not a complete API/runtime validation.
Results and reproducible probe are in ignored run artifacts. A production bridge
must resolve this rather than calling the manual API blindly.
A draft patch now routes a new mirror through existing collector upsert semantics.
The isolated probe retains both postings, original displayed provenance and
application status; it also checks distinct same-source requisitions and refused
blacklisted mirrors. This is a review artifact, not a deployed API fix or full
application integration test. The offline `openings_import` adapter in our email
prototype already accepts exported JSON rows without network access or approval
transfer.
Open-jobs' `top` produces HTML/Markdown, with compact embedded fields; read its
underlying data rather than treating a display excerpt as the full description.

Our preparation code currently selects existing CV variants and builds templated
messages; it does not generate a newly tailored CV document. Existing evidence
checks and approval-bound delivery are reusable foundations. Generated prose
still requires factual review; skill-name checks alone do not validate every
claim. Openings' tracking status is not permission to send an application.

Recommendation: establish an Openings baseline, then run a bounded open-jobs
coverage comparison. Add the second-source adapter only if its additional useful
results justify the extra maintenance. For application forms, first prepare the
CV, letter and answers for owner submission; evaluate individual ATS automation
only against an actual form and confirmed submission evidence. Email is an
alternative when an appropriate recruitment contact/channel is available; it is
not a guaranteed substitute for an employer's required application form.

The owner has supplied broad search criteria, retained in the ignored local
handoff. Detailed professional data is deferred to a future local knowledge bank;
source evaluation does not depend on that bank or require a CV. Its architecture
is not selected by this investigation. Prepare a concrete local trial with
dependency, download, collection and data boundaries before execution. No full
application trial or external submission has run; bounded public-page and offline
parser checks follow.

### Polish-board intake gap

The inspected Openings source registry and [JobSpy's supported sources](https://github.com/speedyapply/JobSpy)
do not include Just Join IT, Pracuj.pl or RocketJobs. Open-jobs offers an ATS index,
not demonstrated direct collection from these boards. Neither candidate has been
shown to replace this intake out of the box; marketplace coverage stays unknown.

Investigate existing integrations before creating custom scrapers:

- [VastHornet/justjoinit-scraper](https://github.com/VastHornet/justjoinit-scraper)
  is an existing Apify actor. Local reuse, licence, dependency requirements and
  collection permissions/reliability need checking; no service/account is chosen.
- [Gem-Hunter](https://github.com/wojciechsacewicz/Gem-Hunter) documents Just Join IT
  and RocketJobs intake. It is a student project with MongoDB and paid Gemini
  scoring; no reuse licence was established. Treat it as an investigation lead,
  not a ready dependency or reason to adopt its storage/scoring architecture.
- [Pracuj.pl's native saved-search alerts](https://pomoc.pracuj.pl/hc/pl/sections/204588567-Powiadomienia-i-e-maile)
  offer another possible intake path. User-provided links, exports or alerts may
  support an initial manual import without granting mailbox access. No account
  was accessed and no alert was configured.

Further source inspection found stronger local candidates:

- [janlukowicz/ai-job-search](https://github.com/janlukowicz/ai-job-search), pinned
  to the inspection snapshot under the run artifacts, has a MIT-licensed Just
  Join IT CLI with no runtime packages. Its selected offline parser tests passed
  on the installed Bun runtime: 26 tests, with `fetch` disabled. Other upstream
  tests are explicitly live and were excluded. Its HTTP helper has retries but
  no demonstrated overall timeout/body cap; do not run it as a bounded collector
  without a reviewed host boundary. This establishes fixture compatibility only.
  A subsequent bounded anonymous listing-page inspection (2 MiB maximum,
  20-second request limit, no redirects/retries/paging/detail calls) returned HTTP
  200 and 1,506,963 bytes. The pinned parser read 47 Python/mid/remote offers from
  that page with `fetch` disabled during parsing. This establishes one current
  listing shape, not posting freshness, completeness, Poland eligibility or
  sustained collection reliability. Source snapshot:
  `243098dd00850de00ec3aa3cbc7d36b6d8cd8eb8`.
- [WorkSphere](https://github.com/Pawwo/WorkSphere), inspected at
  `6543bca5eef2fd56e39db9eeb35f17e70a67535a`, is Apache-2.0 and includes collectors
  for all three Polish boards. They use Bun and shared dependencies; its full app
  targets Linux and adds a model/PDF/deployment stack. Prefer evaluating the
  collector boundary before considering an additional full workspace. Its
  RocketJobs path includes an internal API endpoint, and shared HTTP can spawn
  curl with redirects; collection permission, destination scope and complete
  resource bounds remain unproved. The full collector/application was not run
  or installed. Selected pure parsers were exercised with network and subprocess
  launch disabled against individual bounded public-page downloads.

WorkSphere's Pracuj `q=python` parameter was ignored: the page's own job query
contained no keyword. Its native `https://it.pracuj.pl/praca/python;kw` path
returned a query containing `kw: ["python"]`; the pinned parser read 80 cards,
all with Python in title or snippet. Group expansion can produce several cards
per vacancy. Descriptions were short listing snippets, not complete requirements.
Correcting the URL builder is necessary before a collector trial; its hard-coded
seniority/work-mode filters also need comparison with the owner's criteria.

RocketJobs' candidate `search=python` URL returned 50 structured records with
zero Python titles and zero keyword-matched HTML cards. Another `keyword=python`
page contained three matched anchors but lacked company/full-description fields
in WorkSphere's HTML parser. The MIT Just Join parser could read 50 structured
records from that page; its normalizer hard-codes Just Join URLs and must not be
used unchanged for RocketJobs. Neither check proves working server-side search,
complete discovery or permitted sustained collection. All page requests were
anonymous single GETs, capped at 2 MiB and 20 seconds without redirects/retries.

Direct bounded reads of Just Join IT and RocketJobs robots files returned HTTP
200; both disallow `/api/`. WorkSphere's RocketJobs API path therefore conflicts
with the inspected generic-crawler directives. Prefer its public-page path or
native alerts for evaluation; no bypass/proxy or API call was attempted there.
Robots directives are evidence about crawler paths, not a blanket legal permission.

Open-jobs' pinned slug inventory includes Polish-market employer candidates, but
names alone do not establish role/location coverage. One bounded GET to the
documented Netguru board route returned HTTP 401 (`unauthorized`), not job data.
No credentials were sought and there was no retry. Board-level API availability
is therefore unproved for an anonymous client; evaluate the documented public
data/index path instead. This refusal does not mean its public index has no jobs.
Bounded anonymous public metadata reads succeeded. The newest listed export and
manifest group prefix were dated 2026-10-05. A 64 KiB Range response showed a
25,167,455-byte manifest; it was not downloaded in full. The pinned Python client
downloads the full manifest and centroid file rather than using the documented
range strategy. Do not run it unchanged under a small-download trial scope.
Public board metadata files for Greenhouse, SmartRecruiters and Workable were
listed at 208,165, 58,685 and 123,544 bytes. Those are Parquet metadata exports,
not evidence of relevant vacancies. No Parquet reader is installed in the current
workspace, and no package was installed or job corpus downloaded. A future
targeted trial needs an approved reader/download path and freshness checks.

Integration decision accepted by the owner: fix the upstream manual-import mirror
semantics before an external API bridge (maintains a narrow client, but needs a
maintained patch/upstream acceptance). The alternative was integrating through
Openings' collector upsert path (existing mirror handling, but tighter coupling to its internal
interfaces/deployment). The approved pinned patch is retained in
`integrations/openings/`; `openings_api.py` implements bounded local intake/export,
with writes disabled until operator verification of that fix. Offline wire/local
peer tests pass; no Openings deployment or real-data intake has occurred. See
ADR-051 for the accepted boundary and remaining runtime validation.

Trial matching should distinguish role-specific seniority and onsite/remote
preferences. A remote flag does not establish eligibility to work from Poland;
country restrictions and unknown eligibility must remain visible. Do not turn
unspecified alternative roles, commuting radius, salary or contract conditions
into hidden filters.

### Initial recommendation (superseded by owner candidate selection)

Two viable starting points:

1. **Discovery first with open-jobs.** Trial the existing toolchain/index and
   reuse its exports. This is a smaller adoption step and directly addresses the
   owner's named candidate, but leaves application tracking to another component.
2. **Existing workspace first with Openings.** Evaluate a ready-made discovery
   and tracking app. This delegates more of the workflow, but needs an approved
   deployment/data/access contract and a broader compatibility trial.

Recommendation: start with a bounded open-jobs discovery trial and keep Openings
as the leading workspace candidate. First test relevant-role coverage and usable
exports; then choose whether a small adapter or an existing app owns tracking.
Do not build a replacement crawler/dashboard in advance of that evidence.
This is a recommendation, not an owner-selected architecture.

The initial comparison executed no candidate code. Subsequent isolated parser
and persistence probes are described above. No dependencies were installed,
application service started, private profile transmitted or model request made.
The source snapshots are inspection artifacts, not additions to the workspace
dependency graph. Adoption decisions should be recorded before implementation.
