# Family-3 S2: acceptance storage layering exception

Status: Accepted by owner, inbox `ed066ac7bf02418490ff1adf785ae175`, option A.
Date: 2026-11-20.

The owner approved adding `acceptance_storage.py` to the frozen provider
up-importer set. The exception covers only the existing neutral contracts
`AccessMethod`, `load_model_catalog` and `ScheduledTaskStatus`, moved from
`acceptance_jobs.py`. It authorizes no orchestration behavior or further importer
growth. No additional owner rationale was supplied.

The selected option preserves the cycle-free storage boundary, existing data
format and compatibility re-exports, at the cost of one additional importer.
The alternative was to retain the importer set and redesign the extraction;
that preserves the old ratchet but requires more invasive separation or
injection of catalog validation and scheduling status. The technical
recommendation was the narrow exception because it preserves the existing
contracts with less change.

`tests/test_package_layering.py` pins both the importer allowance and the exact
neutral imports. `tests/test_family3_import_boundaries.py` checks import cycles,
entry-point isolation and compatibility identity. Acceptance-job tests cover
the existing storage and execution contracts. This decision does not authorize
live inference or change the acceptance job format.
