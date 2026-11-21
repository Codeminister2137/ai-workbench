# E2E promotion corpus audit - run 73249b26a80a47a1a45259c34f443d1f

Audit timestamp: 2026-11-21T10:31:41.601831+00:00. Branch: docs/e2e-corpus-audit-73249b26.

## INCOMPLETE - lifecycle audit verified; behavior triage outstanding

No browser interaction tool is available in this execution context. Static UI tests and HTTP reads do not independently exercise the owner interaction, OS reduced-motion, or end-to-end chat scenarios in the historical checklists. These scenarios are not marked passed by this audit.

## Result and scope

All 83 original checklists are **already consumed**: each is submitted, has a submission timestamp, and points to an existing matching immutable report. Every task and report was cross-checked against the current served API and shared on-disk records. No task was resubmitted, edited, deleted, or newly closed. Submitted is the existing terminal lifecycle state; adding a new closed state would change the data contract unnecessarily.

Corpus disposition: **83 consumed; 0 open/draft; 0 additional stale, superseded, or stale-serve closures; 0 newly re-issued tasks.** Reasons are exclusive: consumption takes precedence over historical supersession. This is a lifecycle count, not a claim of 83 passing behaviors. **Current live defects: 0 independently reproduced in this audit; exhaustive current behavior verification remains INCOMPLETE.** Do not interpret zero reproduced as proof that no defects remain.

Historical reports: **33 pass, 50 fail**. Across their items: 70 pass, 36 fail, 22 bad-test. The earlier local unattended plan's `83 submitted/0 failed` statement cannot be used as a report-verdict count. Historical failures remain preserved and continue to affect promotion under ADR-087; this audit grants no promotion approval.

## Verification

- GET /api/version: commit `67bc53fceb5c`, branch `develop`, started `2026-11-21T10:14:24.817180+00:00`. Matches the inspected develop commit `67bc53fceb5ce306deebeb23ad32bd7735165234`.
- GET /api/e2e/tasks?status=submitted: 83 records; GET /api/e2e/reports: 83 records. Compared all ids, submission states, report links, report task ids and commits; every served report equals its on-disk JSON.
- Focused current-code suite: `python -m pytest apps/workbench_dashboard/tests/test_e2e.py apps/workbench_dashboard/tests/test_e2e_cases.py apps/workbench_dashboard/tests/test_e2e_promotion.py apps/workbench_dashboard/tests/test_e2e_agent_checks.py -q`: **85 passed**.
- Current `scripts/e2e-promotion.py generate d16ed73 --dry-run`: `needs_pointers: true`, `grounded: false`. The old report's specific `needs_pointers: false` failure no longer reproduces. Dry-run output was inspected; no new checklist was filed.
- UI contract suite: `python -m pytest apps/workbench_dashboard/tests/test_dashboard_ui.py -q`: **108 passed**. Combined with the focused suite: **193 passed**; these tests do not establish all historical behavior outcomes.
- Existing store implementation rejects repeat submissions and counts only open tasks for attention. Pending item fields inside a submitted task are original checklist definitions; the linked report owns verdicts.

## Follow-up limitations and next action

48 action-bearing reports have a directly linked E2E follow-up inbox record, all already closed. These closures are observed records, **not independently verified fixes**. Eight further action-bearing reports lack a direct metadata report-id link (listed below); same-merge follow-ups and later reports exist in several cases, but are not assumed to cover every observation. Latest same-commit reports are shown as lineage only: they do not prove current behavior or automatically supersede another report's individual steps.

No failure was re-issued solely because it appeared in a historical report. No consumed acceptance run, paid inference, or mutating owner test was replayed by the audit tools. No product fixes were made.

**Next action:** reproduce the unresolved observations from action-bearing reports on the recorded current serve, starting with the eight missing direct links; inspect full follow-up resolution evidence and later per-step reports for the other 48. File a fresh task only after a specific current failure is reproduced, with current commit, exact steps and expected/actual result. Completion condition: each failure/note has current reproduction evidence or an independently checked supersession/consumption chain. This audit establishes original-task consumption for all 83, but does not yet establish that stronger condition for all historical observations.

Missing direct report-id links (original task ids):

- `03dbaccf4df3441783bc88d5a198ccca`
- `220bb7f5e7104ccf9c5e06309f7f5714`
- `27cedba6a2864dcebc2ae78fa2a180f7`
- `405769cec55a4de49dee21e764bcf3e3`
- `4f61616cf28740e3b9aef5dca2b93fb4`
- `5e8cb6796a5445ccae12a35a4926880d`
- `5f839073782f48b0aeff7a39f373cecb`
- `f2280e3c98204f0692f0d9dbaa3294bb`

## Per-task ledger

Evidence root: `C:/Users/Jakub/PycharmProjects/ai-workbench/apps/workbench_dashboard/data`. Task ids resolve to `e2e_tasks/<id>.json`; report ids to `e2e_reports/<id>.json`; follow-ups to `inbox/<id>.json`. This table records actual observed terminal state rather than rewriting historical verdicts.

| Task id | Merge | Matching report id | Historical overall | Submitted at | Direct follow-up record | Latest same-commit report (historical only) | Original-task disposition |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 01938d6ac71741f0a62a2b3cc8e87bfc | e1367d3 | 527079b16942496aa9ef4824cc82282e | pass | 2026-11-14T14:43:35.004478+00:00 | not needed | 527079b16942496aa9ef4824cc82282e (pass) | consumed |
| 03dbaccf4df3441783bc88d5a198ccca | fb0286b | 9c3020a2e30d47f980a8f283554fe2d2 | pass | 2026-11-16T17:01:19.293648+00:00 | no direct link; action-bearing | 9c3020a2e30d47f980a8f283554fe2d2 (pass) | consumed |
| 11292552b8c44af392ef7ec730e1176a | fe8b64a | cecae9c4a29147969bf9c46622fe6159 | pass | 2026-11-14T12:04:38.325929+00:00 | not needed | cecae9c4a29147969bf9c46622fe6159 (pass) | consumed |
| 115eec0a57e840f39d9d9174a80984fd | ab6f14e | 5899713af70b4ef79ea3ebe842d8c27e | pass | 2026-11-16T23:53:10.881165+00:00 | closed eb57ae17051644a681d6ff7db5866887 | 5899713af70b4ef79ea3ebe842d8c27e (pass) | consumed |
| 125f581784924861ad2afbe332dca3b7 | 37a65c3 | 13699bd86fac4bbab97a59155b774a21 | fail | 2026-11-16T21:16:29.822718+00:00 | closed d7b576e0f3a54eecb0ca87148398be22 | db8c9424069b4145b3632a453776717f (pass) | consumed |
| 1d08593298754d9db34905043034438a | 4d35b5a | 0dc42e191f9643dc8f8ca76731634ef0 | fail | 2026-11-17T22:36:29.968691+00:00 | closed 02d4694f4ee949d8a39e268093975c36 | 0dc42e191f9643dc8f8ca76731634ef0 (fail) | consumed |
| 1d0a1886b9cd4bc9a9f50c37731ebead | 7aced19 | 5f9df89eadbd412da05cec2352c3b064 | fail | 2026-11-16T22:28:44.531398+00:00 | closed 0ca531a4910d4361b199cbdd1107ef76 | 4f149dc2d3b34b639c923aa29973cd2f (fail) | consumed |
| 220bb7f5e7104ccf9c5e06309f7f5714 | d16ed73 | a30c5c29a7b040da9d580c73f81efb1c | fail | 2026-11-16T15:20:53.289293+00:00 | no direct link; action-bearing | dbc7afcae6ad46159457ed677e635e14 (pass) | consumed |
| 22c4c2b1aa964af182e59b5371be7804 | a6e828a | 64e9ac46897f4bdca4961b2a6c596c03 | fail | 2026-11-17T15:48:07.927620+00:00 | closed 5e01b817d86c4741a155014f31613ebf | 64e9ac46897f4bdca4961b2a6c596c03 (fail) | consumed |
| 264e25062b334c84a19a3f3d9dacad78 | fb9ed81 | 69f39513169a40ae878ac6020fedb891 | pass | 2026-11-14T13:18:04.500864+00:00 | not needed | 69f39513169a40ae878ac6020fedb891 (pass) | consumed |
| 27cedba6a2864dcebc2ae78fa2a180f7 | a4183bf | 8768bca8e8b54ac3b90620952e08f6a3 | fail | 2026-11-16T15:37:03.858146+00:00 | no direct link; action-bearing | ea285cfbf3c14195a79d5c31d75f4d0b (fail) | consumed |
| 2823752223994a66af7b78d24ed00ec5 | fe8b64a | 53001218e16a4b86b558c82866996124 | pass | 2026-11-14T11:52:42.426437+00:00 | not needed | cecae9c4a29147969bf9c46622fe6159 (pass) | consumed |
| 2d128378f5cc4279b932f60297fa1953 | 6b87fca | ebc42f89ceae45f1b8bd87f1c6bef12d | fail | 2026-11-16T21:15:29.998315+00:00 | closed 7a98ce384041498a85d8a3e818016bd1 | cd1332c80b3c4a5d9f70212d176b12d3 (pass) | consumed |
| 2ebdc5e06f3445b68a0433ccfd38ab0a | 44b6eec | 1413f957bc0d42f29911442d020f8dcc | fail | 2026-11-17T13:57:18.260657+00:00 | closed 7412b2df6eb441e0aa491bba541430db | 1413f957bc0d42f29911442d020f8dcc (fail) | consumed |
| 367b3f65cd6a4960bc33f8bb3030dd94 | 705363b | dc973a15d0054a088f56535d53fcdfa5 | fail | 2026-11-16T22:53:09.178868+00:00 | closed 716144fa2f9a49c387e782548170cbdc | dc973a15d0054a088f56535d53fcdfa5 (fail) | consumed |
| 3932eb28e0a3441691be345c11e1fc44 | a20feee | 39d99bd3d312429d809598fd748fa3ba | fail | 2026-11-16T17:51:03.387820+00:00 | closed 5d5b9b41059b4ea6ac4d2e2a2c014c33 | 8a73b280e2e4446eb964b23360739d12 (pass) | consumed |
| 3ebb45718f3749aca0ff970ae82481c8 | 6b87fca | cd1332c80b3c4a5d9f70212d176b12d3 | pass | 2026-11-17T09:21:59.269507+00:00 | not needed | cd1332c80b3c4a5d9f70212d176b12d3 (pass) | consumed |
| 40438953e655428b85d5aa9730fd32f6 | 316c943 | f492a856d08f4acaaf6a72701b5bcfc4 | pass | 2026-11-17T11:39:47.085533+00:00 | not needed | f492a856d08f4acaaf6a72701b5bcfc4 (pass) | consumed |
| 405769cec55a4de49dee21e764bcf3e3 | d85c545 | 90bd15351cfc416ba5f646cfd096fb1a | fail | 2026-11-16T15:44:21.010440+00:00 | no direct link; action-bearing | 014f493f1a6045478212cbe27c57d97c (fail) | consumed |
| 41a4983c321d415d801b100e12170749 | 743c542 | 1be8db7128534b8ab41d91dd4d4b7ed8 | fail | 2026-11-16T22:26:10.486416+00:00 | closed 472d2af6c1674589a6e72f55856e5338 | 39e5eefd50324546a8f6e6a90f552d0f (fail) | consumed |
| 46bec73e59f9434281925ae3185e91ff | 20caab2 | cdf983e128e9464b8ab872729ce7e774 | fail | 2026-11-16T21:17:44.450408+00:00 | closed 35a80f5ef4b040a799d94aef8ab8172e | 49253937c438463092ca6d20882c57da (fail) | consumed |
| 4afdac43111b44cd9c8c880e7430f586 | bf18dc2 | 2e364940b21844a0a6a3d5af4d893efe | fail | 2026-11-16T22:57:42.315683+00:00 | closed 265c8c210af044119aa70c826c20617e | 2e364940b21844a0a6a3d5af4d893efe (fail) | consumed |
| 4c87ba96f908482db47ea3cc196ce653 | 8321b11 | 7fa73c5d163346b28cdf5bb61ddcf124 | pass | 2026-11-14T11:52:41.160027+00:00 | not needed | 7fa73c5d163346b28cdf5bb61ddcf124 (pass) | consumed |
| 4e0f6d61659e4fcc93005064bce5d87b | 37a65c3 | db8c9424069b4145b3632a453776717f | pass | 2026-11-17T12:01:43.319939+00:00 | not needed | db8c9424069b4145b3632a453776717f (pass) | consumed |
| 4ec3699689ae4b4886effe85a9425ac0 | a20feee | ce16951df72147949b8b95752857ae5f | fail | 2026-11-16T21:09:16.715230+00:00 | closed 3883251db01f411da5b1fd368880357e | 8a73b280e2e4446eb964b23360739d12 (pass) | consumed |
| 4f61616cf28740e3b9aef5dca2b93fb4 | bf18dc2 | 893624917b5a47e69f6de92759a28fb4 | fail | 2026-11-16T16:46:47.576562+00:00 | no direct link; action-bearing | 2e364940b21844a0a6a3d5af4d893efe (fail) | consumed |
| 55b3a8f1dcd149029f134db6813da9ce | 0ef0829 | 76c6e9b16e1a4a058c68aa6d578ccbbd | fail | 2026-11-16T21:05:02.908967+00:00 | closed 8287d09c36d74b66af8ff939da6d2a71 | 977a363363d14b8794e48bbdc1e2ae39 (fail) | consumed |
| 5698f3cddad3445db331ed757a3c7152 | a4183bf | f2eb528a9984401eb7a68095271006bd | fail | 2026-11-16T21:03:55.506614+00:00 | closed 6e4fbab55f6b4e6baec05c22fcd65406 | ea285cfbf3c14195a79d5c31d75f4d0b (fail) | consumed |
| 5c655451c9b946bca395f81c7c7f7f78 | 7aced19 | 4f149dc2d3b34b639c923aa29973cd2f | fail | 2026-11-17T11:42:58.892389+00:00 | closed 6e19c0f1959945778d65809ccc36b962 | 4f149dc2d3b34b639c923aa29973cd2f (fail) | consumed |
| 5e8cb6796a5445ccae12a35a4926880d | 072087a | c3e244f5a26140658a66b5a3af98517f | fail | 2026-11-16T16:43:49.932028+00:00 | no direct link; action-bearing | 7ff0358be9884e289ff197530245666d (pass) | consumed |
| 5f839073782f48b0aeff7a39f373cecb | 0ef0829 | 6eac20069a37402d88b1803f75baad08 | fail | 2026-11-16T15:30:54.886064+00:00 | no direct link; action-bearing | 977a363363d14b8794e48bbdc1e2ae39 (fail) | consumed |
| 62456abbf1fe4de68616f1ca6f718396 | afba5f2 | 8fd12ffef56a4e32be635f32b3f14d9e | pass | 2026-11-14T11:52:41.790078+00:00 | not needed | 8fd12ffef56a4e32be635f32b3f14d9e (pass) | consumed |
| 636f6fb4ae6f43678cb67ed0c0bc4fcd | d16ed73 | dbc7afcae6ad46159457ed677e635e14 | pass | 2026-11-16T22:20:02.007234+00:00 | not needed | dbc7afcae6ad46159457ed677e635e14 (pass) | consumed |
| 64081050bda440aa9107752e093aa917 | 2f8f589 | 43f0b9e284104a2f8454cd06cd85f681 | pass | 2026-11-16T18:41:44.058532+00:00 | not needed | 43f0b9e284104a2f8454cd06cd85f681 (pass) | consumed |
| 65791589ef3b4911977b5d6424c25aa9 | faff767 | e17b4d85e16045e7815c9e3af6e5545a | fail | 2026-11-16T21:08:11.121301+00:00 | closed 5e9242908ef4471eb24c84857e659ca2 | 8e16e78efed146e3a9ee00a5bafda69b (fail) | consumed |
| 65f46e13e59248669710d730d9e14583 | 8e4cf7c | bdefe10db58a40419cf01057f003bb96 | pass | 2026-11-14T11:52:41.584284+00:00 | not needed | bdefe10db58a40419cf01057f003bb96 (pass) | consumed |
| 667d1d2c913e4c6e994ed90936300024 | 96c1a08 | 3c05764acc50492fa2b3d89ea8a7b43c | pass | 2026-11-16T21:00:32.782271+00:00 | not needed | 3c05764acc50492fa2b3d89ea8a7b43c (pass) | consumed |
| 6767e8d8b273458aade530006a891f72 | 1c53e12 | 4b2842a8807943058bf1e86d6b372f50 | fail | 2026-11-17T19:21:10.311519+00:00 | closed eddf3391de1d4e0cbef91abcd3c32d82 | 4b2842a8807943058bf1e86d6b372f50 (fail) | consumed |
| 69199e67b34c4657b7b65ae742512124 | be14fdf | 0b05cf6dcc304bdeac417f7af414c4a0 | pass | 2026-11-14T11:52:42.003926+00:00 | not needed | 26ec6c61dc944f99ae9bbbd8e952f914 (pass) | consumed |
| 6af39d3cc384499eb11290287d0bfdd4 | 37a65c3 | 8d146a8c73464fdda791590629cc16ad | fail | 2026-11-16T22:52:01.408980+00:00 | closed b7392c934d9a4a3f9d70d2b6d3bb97e7 | db8c9424069b4145b3632a453776717f (pass) | consumed |
| 706d855cdf43457c91f47e1287bfaa3c | 91e5f75 | da46fd5ad313448ebebc49b124136db6 | pass | 2026-11-14T11:52:42.219967+00:00 | not needed | 78d310c0c9b340edb6d7bcc9f4c405b7 (pass) | consumed |
| 7652a6cf59734fcfa2f1bd9a730b6609 | 1b8fa9c | e7d27cdc746247d4a287ea352e50aa75 | pass | 2026-11-16T17:00:07.081001+00:00 | not needed | e7d27cdc746247d4a287ea352e50aa75 (pass) | consumed |
| 7ccae6fbf2064a6384b87b6e7aaabd6c | 44b6eec | 3b5e11deeed54e8283f0e0093c6897ff | fail | 2026-11-16T22:49:09.035136+00:00 | closed 0e74066aed9746938d107bf4f562be4c | 1413f957bc0d42f29911442d020f8dcc (fail) | consumed |
| 86bb28b8d52645e8950da5944097187d | bf18dc2 | edd88baa464b4287995ec02e64de85de | fail | 2026-11-16T21:02:27.369488+00:00 | closed 081a21d5ab294029a045f27e3bfc379f | 2e364940b21844a0a6a3d5af4d893efe (fail) | consumed |
| 8a6ea3b2cd284ed08891a0a1c1ebe7e2 | f8a5460 | 6ee0953e25d64a60a209f35a96c2de05 | pass | 2026-11-14T11:52:40.943135+00:00 | not needed | 6ee0953e25d64a60a209f35a96c2de05 (pass) | consumed |
| 8dc8d179421942b292c6d50a2cef4485 | acff0c1 | dbd849fea0fe45eab44fce75c4013f7c | fail | 2026-11-16T17:47:07.243861+00:00 | closed e17035fad4044c839e7b9cc5db5170d9 | b4c55e18f8e34f35aea376764a190fc7 (fail) | consumed |
| 91973d3649d54d028c6a47dc81c2001d | 44b6eec | 402dd90015fc4f96b6b5cc59469d2263 | fail | 2026-11-17T09:27:23.537520+00:00 | closed 497f388032ed40a9bb5897f53c43ad4d | 1413f957bc0d42f29911442d020f8dcc (fail) | consumed |
| 93a0ec1619584f978822465a751b9e38 | 7b15c26 | e3811118e29543ef90e714294a4ee1ca | fail | 2026-11-16T22:54:47.278782+00:00 | closed 320c1e03ba704e48b91d23fc1e17c03e | e3811118e29543ef90e714294a4ee1ca (fail) | consumed |
| 960880f397194010a593cc49e547bdaf | 14f35af | 221dc6d5858541fe8081d174ca139406 | fail | 2026-11-16T21:18:36.090713+00:00 | closed 9cd4e495e37046a4b391bdaabb77cd98 | d333fc0907c649dfa8d9272b1a411e5d (fail) | consumed |
| 9bed37c75f1f4a6d8e4f2c0d1e770255 | 63c9c37 | 9c0d9a3408c14b54bacdb68d0c67fd51 | pass | 2026-11-14T14:29:27.763090+00:00 | not needed | 9c0d9a3408c14b54bacdb68d0c67fd51 (pass) | consumed |
| 9e8d249ff7f549b280936945b2388e2f | 7119d20 | 16f0927d05d3486bbb0d81920ae7ec32 | fail | 2026-11-16T22:13:55.919266+00:00 | closed ca3894b2d1c74e37abb8060602b097fe | 16f0927d05d3486bbb0d81920ae7ec32 (fail) | consumed |
| a03ac81c816c4df9b6a1bbc8fcdb1402 | 20caab2 | 49253937c438463092ca6d20882c57da | fail | 2026-11-17T11:44:49.617796+00:00 | closed 7ea1f1be259b4f1792c9d33213e95985 | 49253937c438463092ca6d20882c57da (fail) | consumed |
| a1019cb8d7b44fddb25dde94b0a88694 | ab6f14e | 2174c4884f9844cbbe15034fd8f664c5 | fail | 2026-11-16T22:56:47.658799+00:00 | closed 133d9115ea004270aec0326dc9b782fa | 5899713af70b4ef79ea3ebe842d8c27e (pass) | consumed |
| a132ac0d2a754ff3a4233d6b97f496dd | 29cafb8 | 7035fc80a3e248958375b89c409bdb9d | pass | 2026-11-14T11:52:41.364854+00:00 | not needed | 7035fc80a3e248958375b89c409bdb9d (pass) | consumed |
| a4225f46a7004996afa2a47fef33253d | 7b15c26 | 0a26ef23b7e544d680c60c7999f25b9a | fail | 2026-11-16T20:57:34.738794+00:00 | closed 21f56e74ceb14dceaec5a4d6904b92b8 | e3811118e29543ef90e714294a4ee1ca (fail) | consumed |
| ac8946bd0389430f9337668d3d10cf32 | 743c542 | 39e5eefd50324546a8f6e6a90f552d0f | fail | 2026-11-17T09:23:05.071795+00:00 | closed f12036493b744ad1bbde6844fa644640 | 39e5eefd50324546a8f6e6a90f552d0f (fail) | consumed |
| ad801c26170542fca15e7be214eef094 | 26344ea | 085b9d95c3884dc1b5ca005b54321c0f | pass | 2026-11-16T18:40:49.081456+00:00 | not needed | 085b9d95c3884dc1b5ca005b54321c0f (pass) | consumed |
| ae594db5d2b142e6a3aaef37d6f160c5 | a4183bf | ea285cfbf3c14195a79d5c31d75f4d0b | fail | 2026-11-16T22:59:36.160324+00:00 | closed b762fc6cee9b4015946011d10fbef764 | ea285cfbf3c14195a79d5c31d75f4d0b (fail) | consumed |
| b285a745555641bcb48a8b2258232827 | 44b6eec | d2adeaa2e9bc447dad8e2eb90d836422 | fail | 2026-11-17T11:47:26.965526+00:00 | closed f91803de8f0a4fb8bd48a4b8315f8b9e | 1413f957bc0d42f29911442d020f8dcc (fail) | consumed |
| bfdd19f7a50a406c8f0a3dc1da9ef9df | 072087a | 7ff0358be9884e289ff197530245666d | pass | 2026-11-16T22:15:06.162294+00:00 | closed 46378d44598f41db89236d58b4438b4a | 7ff0358be9884e289ff197530245666d (pass) | consumed |
| c23ffbcdac7e4994a8a1d3f35e4e7e98 | 14f35af | d333fc0907c649dfa8d9272b1a411e5d | fail | 2026-11-17T11:44:39.456831+00:00 | closed dc45700e6a0742dfb35e45696852a6b7 | d333fc0907c649dfa8d9272b1a411e5d (fail) | consumed |
| c730e39e6afc4a91aa660bd6dbbd792f | ab6f14e | f3a2fbaad2fb4d13b969165de6829290 | fail | 2026-11-16T20:59:49.533388+00:00 | closed d8d0f6738cf841e6a5b2d3fa3e30ad79 | 5899713af70b4ef79ea3ebe842d8c27e (pass) | consumed |
| cd2916de9f4c447ba49b1deec4384fb4 | 0ef0829 | 977a363363d14b8794e48bbdc1e2ae39 | fail | 2026-11-16T22:59:01.840978+00:00 | closed 7a79ee7d3962407292fd6935ac12f0cc | 977a363363d14b8794e48bbdc1e2ae39 (fail) | consumed |
| cd4ab743c1df42fe8e5ef176fe0c7913 | acff0c1 | b4c55e18f8e34f35aea376764a190fc7 | fail | 2026-11-17T11:44:30.133172+00:00 | closed 4d6dbd4ffdaf481084a34e8b2ebc7ab6 | b4c55e18f8e34f35aea376764a190fc7 (fail) | consumed |
| cdf39d2e652846f495ed5d3196af0328 | be14fdf | 26ec6c61dc944f99ae9bbbd8e952f914 | pass | 2026-11-14T12:04:37.882398+00:00 | not needed | 26ec6c61dc944f99ae9bbbd8e952f914 (pass) | consumed |
| d66a7961b5d743d4ab4f0e01db2e2f6f | 7aced19 | 0e68c25d1ac44d17bd24333befa3837f | fail | 2026-11-16T17:57:29.752588+00:00 | closed 10948e382a6e4e17aecdf08508c08984 | 4f149dc2d3b34b639c923aa29973cd2f (fail) | consumed |
| da57bcce90594f41aeb3321b25fe0323 | 5c11c11 | e4362e06833c491ca8ba6e672ae99f74 | pass | 2026-11-16T22:05:37.304020+00:00 | not needed | e4362e06833c491ca8ba6e672ae99f74 (pass) | consumed |
| dae099b0f39a4400bde8fafd12860ce8 | 8279e24 | 773bdc4d5cd7422ea0b85d8d08599c05 | pass | 2026-11-16T22:31:09.720774+00:00 | closed a707862a17f449e8bae961161647efc6 | 773bdc4d5cd7422ea0b85d8d08599c05 (pass) | consumed |
| de36f40a4fe04e898ca8ab1ab942d11a | 79005ac | 2a09abbd0b654171b6db14d99c225699 | pass | 2026-11-16T16:50:06.947865+00:00 | not needed | 2a09abbd0b654171b6db14d99c225699 (pass) | consumed |
| df3d04a8cbf240aca5bf08cbf0ed3f63 | 75055f3 | 68841f56569b43e6a998507601484c89 | pass | 2026-11-16T17:43:00.850960+00:00 | closed 1615aaffa67249edbe9b0d3ea58cb13c | 68841f56569b43e6a998507601484c89 (pass) | consumed |
| e0888fcbd17d47ec8933f7bb50964cc4 | 53f0e6d | 119fc2a52a9d400e9d9eddff318ce089 | pass | 2026-11-14T14:17:12.568378+00:00 | not needed | 119fc2a52a9d400e9d9eddff318ce089 (pass) | consumed |
| e326255193de490fbd803d226390afba | 6b87fca | 3e0b8172940d47219cf5f352bd3a20cc | fail | 2026-11-16T22:50:56.751553+00:00 | closed 08460f8473fa4288a6a183a87fd55453 | cd1332c80b3c4a5d9f70212d176b12d3 (pass) | consumed |
| e464aa9b2d174278b611ece2ed5509de | 45c38f0 | 0f3e448041f94d94b3fee506fc13971d | fail | 2026-11-17T11:08:22.222091+00:00 | closed 0a90eee3d53f493692ab5a3a48ef4b32 | 0f3e448041f94d94b3fee506fc13971d (fail) | consumed |
| e89198d9e1da4a76900da1c215afe6d7 | 705363b | 562cb736fe974337b2f385f5950ace5b | fail | 2026-11-16T21:13:16.073916+00:00 | closed 65271a4063fc44ceb502620071db680e | dc973a15d0054a088f56535d53fcdfa5 (fail) | consumed |
| ec0fa2fd7b014c9fbd56911d60a82138 | d85c545 | 014f493f1a6045478212cbe27c57d97c | fail | 2026-11-16T22:23:44.906739+00:00 | closed aadea3114b40498c8a35d9f6af3950b9 | 014f493f1a6045478212cbe27c57d97c (fail) | consumed |
| ed026812944f49f39eb7af7d9514de1c | b6bd430 | f91ec0452c99485eac0352213804c326 | fail | 2026-11-17T19:11:12.301794+00:00 | closed a7e5f7ca940542a089dcd498c55eb129 | f91ec0452c99485eac0352213804c326 (fail) | consumed |
| ed6274bf124a4cc1851a93123503256b | 91e5f75 | 78d310c0c9b340edb6d7bcc9f4c405b7 | pass | 2026-11-14T12:04:38.110286+00:00 | not needed | 78d310c0c9b340edb6d7bcc9f4c405b7 (pass) | consumed |
| edb0f064a8db4864a1762840c4d32c4f | 5ec4af5 | 6ba6b5ff84b64cffadbfe2532c75c12a | pass | 2026-11-14T12:04:38.542851+00:00 | not needed | 6ba6b5ff84b64cffadbfe2532c75c12a (pass) | consumed |
| ee9ddd9d0a9544d991db5bf7cc00df35 | 743c542 | 7c21902b5d4c448ab7a8cbf1ea98ecc7 | fail | 2026-11-16T18:14:10.819014+00:00 | closed b6e1453755a04cc598f83c49069c969f | 39e5eefd50324546a8f6e6a90f552d0f (fail) | consumed |
| ef1f530211744d1dba0856cad04d957e | d658c3c | 0051d4564a064e73bb11ec85cd6d3eaa | pass | 2026-11-16T22:33:16.405855+00:00 | closed 182a9616b7af41fe8916843eb7954c55 | 0051d4564a064e73bb11ec85cd6d3eaa (pass) | consumed |
| f2280e3c98204f0692f0d9dbaa3294bb | faff767 | 54307aee2dd8461eb0309e28c16bfa54 | fail | 2026-11-16T17:07:25.258148+00:00 | no direct link; action-bearing | 8e16e78efed146e3a9ee00a5bafda69b (fail) | consumed |
| fc9457abf869416e975421ba41aae96d | a20feee | 8a73b280e2e4446eb964b23360739d12 | pass | 2026-11-16T22:58:09.557120+00:00 | not needed | 8a73b280e2e4446eb964b23360739d12 (pass) | consumed |
| fcb4ae3317814b6a9ce95c9ff8468d7a | faff767 | 8e16e78efed146e3a9ee00a5bafda69b | fail | 2026-11-16T23:00:22.688463+00:00 | closed ba83f79146b747cd866c0a9bb1807032 | 8e16e78efed146e3a9ee00a5bafda69b (fail) | consumed |
