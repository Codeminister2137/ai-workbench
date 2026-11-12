# ADR-086: Dashboard navigation and module activation

Status: Accepted by owner, 2026-11-12 (adcec2af=A).

The growing dashboard gave core, specialist, and administration views equal
prominence. Owner selected the navigation-and-activation scope proposed in run
153d078e, implemented by task c5d5a2b2.

Group existing views without merging their records. Keep core tools accessible;
offer activation for Overview, personal assistant/KnowMe, Meetings, client
Intake and book project tools. Catalogue distinguishes availability, installation
and activation; planned Trainer is visible but unavailable for activation.
Home becomes optional Overview with actionable work and warnings. Users choose
their landing view; explicit deep links remain authoritative.

A retains full installation: smaller and reversible, but inactive code still
occupies disk (accepted). B, optional installation now, would reduce installation
footprint sooner but require broader dependency/startup/install testing. B remains
future work. This does not supersede centralized data ownership (ADR-082).

Preferences extend the existing local dashboard JSON configuration. Omitted keys
preserve prior availability; saved selections explicitly choose active modules.
Deactivation blocks feature endpoints and UI entry, defers feature imports, and
preserves data. No specialist background jobs are introduced. Previously approved
runs retain their existing execution/approval lifecycle; activation is not a
security or cancellation boundary. No new service, storage engine or dependency.
