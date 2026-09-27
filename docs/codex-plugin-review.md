# Codex Plugin Review

This file records the local Codex plugin marketplace review performed for the
repo-assistant CLI parity work. It is a point-in-time local catalog note, not a
durable upstream source of truth.

Source used:

- `codex plugin list` from the PyCharm-bundled Codex CLI `codex-cli 0.137.0`.
- Local cached plugin manifests under the OpenAI-curated marketplace.
- Official Codex manual sections for plugin install, MCP, hooks, and admin
  controls.

Approved initial install set:

| Plugin | Reason |
| --- | --- |
| `openai-developers@openai-curated` | OpenAI API, Agents SDK, ChatGPT Apps, API-key, and docs-oriented developer workflows are directly relevant to this repository. |
| `codex-security@openai-curated` | Adds security scan, diff scan, threat modeling, validation, and fix workflows for authorized code. |
| `superpowers@openai-curated` | Adds planning, TDD, debugging, code review, branch-finishing, and agentic workflow skills. |
| `plugin-eval@openai-curated` | Helps evaluate Codex skills/plugins and benchmark plugin quality. |
| `build-web-apps@openai-curated` | Adds frontend app building, frontend testing/debugging, React, shadcn, Stripe, and Supabase workflow guidance for future dashboard/app work. |

Important boundary:

- Plugin installation mutates persistent local Codex plugin state.
- Installing a plugin does not authorize external service access by itself.
- Plugins with `apps` or `mcpServers` may require separate sign-in, service
  permission review, and action-control decisions.
- Plugins with hooks require hook review before trusting the hook behavior.
- Start a new Codex CLI session after installation before relying on bundled
  skills or tools.

## Deferred Plugins

| Plugin | What it does | Reason deferred |
| --- | --- | --- |
| `adobe@openai-curated` | Adobe Creative Cloud/Acrobat creative and document workflows. | External app connector and account/storage access; not needed for CLI coding parity. |
| `airtable@openai-curated` | Read/create/update Airtable records and analyze structured operational data. | External data/write connector; no current Airtable workflow requirement. |
| `atlassian-rovo@openai-curated` | Jira and Confluence workflows. | External workspace connector; no approved Atlassian integration. |
| `boltz-api-cli@openai-curated` | Molecular/protein structure prediction and binder design workflows. | Domain-specific life-science tool; outside current repo-assistant scope. |
| `build-ios-apps@openai-curated` | iOS app building, simulator, profiling, and SwiftUI workflows. | Apple/iOS-specific and includes MCP; not relevant on this Windows/Python repo path. |
| `build-macos-apps@openai-curated` | macOS app building and debugging workflows. | macOS-specific; not relevant to this Windows/Python repo. |
| `build-web-data-visualization@openai-curated` | Web charts, maps, dashboards, reports, slides, and WebGL visualization workflows. | Useful later for dashboards, but narrower than `build-web-apps`; defer until visualization work starts. |
| `canva@openai-curated` | Canva design editing, resizing, brand checks, and bulk design workflows. | Requires Canva account connection for core value; not coding-agent parity. |
| `chatcut@openai-curated` | Install/open/connect ChatCut desktop app. | Desktop app integration; no current need. |
| `circleci@openai-curated` | Build/test/deploy workflows for CircleCI. | External CI service; this repo does not currently use CircleCI. |
| `clickup@openai-curated` | ClickUp task/project command center. | External project-management connector; no approved ClickUp integration. |
| `cloudflare@openai-curated` | Cloudflare Workers, Wrangler, Agents SDK guidance plus Cloudflare API MCP. | Useful for future deployment, but authenticated Cloudflare MCP is a separate access decision. |
| `coderabbit@openai-curated` | CodeRabbit AI-powered code review workflow. | Overlaps with Codex review/security; external vendor workflow should be evaluated separately. |
| `consensus@openai-curated` | Academic literature search/synthesis over peer-reviewed papers. | Research-focused external MCP; not needed for coding-agent parity. |
| `creative-production@openai-curated` | Campaign ideas, concept images, mood boards, ads, listings, and launch assets. | Creative production scope; external/app capabilities not needed for this repo. |
| `data-analytics@openai-curated` | Product/business analytics, reports, dashboards, notebooks, and data validation. | Broad app/MCP/write scope; useful later for dashboards or data work, but not first coding slice. |
| `datadog@openai-curated` | Datadog telemetry investigation and remediation. | External observability connector; no configured Datadog account/workflow. |
| `dropbox@openai-curated` | Dropbox file access, saving outputs, and sharing links. | External file connector; no approved Dropbox data boundary. |
| `expo@openai-curated` | Expo and React Native build/deploy/debug workflows. | Mobile/React Native-specific; outside current repo scope. |
| `figma@openai-curated` | Figma design implementation and design-system workflows. | External design connector; useful only after an approved design workflow exists. |
| `game-studio@openai-curated` | Browser game design, prototyping, assets, and playtesting. | Domain-specific; not needed for repo-assistant CLI parity. |
| `github@openai-curated` | Inspect repositories, triage PRs/issues, debug CI, and publish changes. | Highly relevant later, but external GitHub connector with write/publish implications; approve separately. |
| `gmail@openai-curated` | Gmail connector workflows. | Personal/work email access boundary; not needed for coding parity. |
| `google-calendar@openai-curated` | Scheduling, availability, briefs, and event management. | Calendar access/action boundary; unrelated to first coding slice. |
| `google-drive@openai-curated` | Drive, Docs, Sheets, and Slides workflows. | Useful for document parity later, but requires Google data permissions. |
| `granola@openai-curated` | Search meeting history for project context and planning notes. | Meeting-history/private data connector; needs separate privacy decision. |
| `higgsfield@openai-curated` | Image/video generation and product-shot/video ad workflows. | Creative external service; not needed for coding-agent parity. |
| `hyperframes@openai-curated` | HTML-to-video, GSAP animations, captions, and website-to-video capture. | Specialized video workflow; out of current scope. |
| `life-science-research@openai-curated` | Life-science research synthesis and public dataset discovery. | Domain-specific research workflow; not current repo scope. |
| `linear@openai-curated` | Search/create/update Linear issues, projects, and initiatives. | External project-management write connector; no approved Linear workflow. |
| `lovable@openai-curated` | Build apps and websites through Lovable. | External app builder; overlaps with local CLI/site work and needs separate decision. |
| `magicpath@openai-curated` | Find, inspect, install, create, and edit UI components. | Potentially useful for frontend work, but not needed until UI component work starts. |
| `mixpanel-headless@openai-curated` | Mixpanel analytics via Python SDK and Codex skills. | External analytics account/data boundary; no current Mixpanel workflow. |
| `monday-com@openai-curated` | monday.com boards, items, CRM, assignments, timelines, and automations. | External project-management/CRM write connector; not approved. |
| `ngs-analysis@openai-curated` | NGS/BCL/FASTQ/DNA/RNA-seq and genomics analysis workflows. | Domain-specific bioinformatics; outside current repo scope. |
| `notion@openai-curated` | Notion planning, research synthesis, meeting prep, and knowledge capture. | External knowledge-base connector and MCP; useful later only with explicit Notion data boundary. |
| `nvidia@openai-curated` | NVIDIA GPU/CUDA/AI agents/inference/robotics/simulation workflows. | Potentially useful for GPU/local inference later, but not needed for Codex CLI plugin parity. |
| `openai-ads-conversions@openai-curated` | OpenAI Ads measurement pixel and Conversions API setup. | Marketing/ads instrumentation; unrelated to repo-assistant. |
| `outlook-calendar@openai-curated` | Outlook calendar scheduling and event-prep workflows. | Calendar access/action boundary; not current scope. |
| `outlook-email@openai-curated` | Outlook email connector workflows. | Email privacy/write boundary; not current scope. |
| `posthog@openai-curated` | Product analytics, feature flags, experiments, errors, surveys, logs, and LLM analytics. | External analytics/write connector; no approved PostHog workflow. |
| `product-design@openai-curated` | Product design brief, product directions, flow audits, and prototypes. | Useful later for product/UI exploration, but not first coding-agent parity slice. |
| `public-equity-investing@openai-curated` | Listed-company research, earnings, valuation, catalysts, and investment memos. | Finance domain workflow; outside current repo scope. |
| `remotion@openai-curated` | Programmatic video with React/Remotion, animations, audio, captions, and 3D. | Specialized media workflow; out of current scope. |
| `sentry@openai-curated` | Inspect recent Sentry issues and events. | External observability connector; no approved Sentry account/workflow. |
| `sharepoint@openai-curated` | SharePoint connector workflows. | External Microsoft data connector; not current scope. |
| `shopify@openai-curated` | Store creation/management, products, inventory, discounts, orders, customers, and analytics. | E-commerce external write connector; not current scope. |
| `slack@openai-curated` | Slack integration workflows. | Workspace communications privacy/action boundary; not current coding slice. |
| `stripe@openai-curated` | Stripe products, prices, payment links, payments, subscriptions, invoices, refunds, disputes, customers, and docs. | Payments/account write boundary; defer until payments work is approved. |
| `supabase@openai-curated` | Supabase SQL, schema, edge functions, auth, logs, migrations, and branches. | Useful for app/database work, but can modify hosted data/schema; approve separately. |
| `teams@openai-curated` | Microsoft Teams connector workflows. | Workspace communications connector; not current scope. |
| `temporal@openai-curated` | Temporal app lifecycle, CLI, server, and cloud workflows. | Useful only if Temporal is adopted; no current infrastructure decision. |
| `test-android-apps@openai-curated` | Android emulator testing, screenshots, UI inspection, logs, and profiling. | Android-specific; outside current repo scope. |
| `twilio-developer-kit@openai-curated` | Twilio Messaging, Voice, Verify, SendGrid, and API workflows. | External communications APIs; no current Twilio work. |
| `vercel@openai-curated` | Build and deploy web apps and agents on Vercel. | Useful later for deployment, but external deployment/account write boundary. |
| `zoom@openai-curated` | Zoom meeting insights. | Meeting/private data connector; not current scope. |
| `zotero@openai-curated` | Zotero library search, BibTeX export, citations, and reference import. | Research-library workflow; not current coding slice. |
| `crowdstrike-falcon-foundry@openai-curated` | CrowdStrike Foundry security skills from a GitHub source. | External security/vendor package; review source and need before install. |
| `crowdstrike-falcon-fusion@openai-curated` | CrowdStrike Fusion security skills from a GitHub source. | External security/vendor package; review source and need before install. |
| `qodo@openai-curated` | Qodo coding skills from a GitHub source. | External coding vendor plugin; evaluate separately against existing Codex/Superpowers/CodeRabbit overlap. |
