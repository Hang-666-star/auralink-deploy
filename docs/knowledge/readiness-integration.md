# Approved no-map V2 integration — 2026-10-12

The actual modified coordinator successfully upgraded the exact `60c5…` baseline
to the new no-map Core PR candidate, accepted its real HTTP/PG/runtime identity,
and restored its compatible baseline. A second coordinator was terminated after
its first real JAR replacement; a fresh instance restored the interrupted state,
and repeated recovery verified a NOOP. The prior preview was not restarted.

The sanitized [no-map receipt](no-map-integration-evidence.json) records:

- Core source `9e42dc66c8c0ccd79b7e640af859ef51e07c48c9`, local JAR SHA256
  `4748f2bef01b551bcb7a6c1eec4175abcb814395f6dbd56afbed7e37ee551d12`,
  69632689bytes. This evidence covers those bytes, not a differing CI/release JAR.
- Manifest schemaVersion2 / `poetry-only`, exactly two real poetry files on a
  dedicated globally read-only tmpfs and no map packaged. The policy/configuration
  binds false. Actual authenticated responses are painting/poetry200 and the
  specific map-disabled503; all three anonymous routes remain401. Actual graph
  hashes match, with711 unique nodes/609 relationships, Gallery6, author names2,
  one authenticated public-field sample and media JSON error behavior preserved.
- Actual Publisher/CoreRuntime/BusinessGuard/R25Storage, Java17 processes and
  verified lifecycle Java methods, private PostgreSQL16, fsync/CAS/flock,
  zero candidate capabilities/NoNewPrivs and filesystem/process attestation.
  Lock and foreign lifecycle-process conflicts are refused.
- COMMITTED, current/committed NOOPs, RESTORED and restored NOOPs; injected abrupt
  exit after the first real JAR write is recovered from its durable INSTALL_INTENT.
  All44 public-table signatures,11 retained tables and3 synthetic media remain
  unchanged, and all5 application files restore exactly. Populated production
  user/task history is not represented by these fixtures.

Runner time34.519seconds, total invocation36.773seconds, exit0. Timing is the small
isolated transaction exercise, not performance acceptance. Reproduction uses the
same namespace invocation described below with the reviewed Git-external
`evidence/nomap/integration/run.py`; inspect the script and its inputs before any
rerun. Its exact SHA and result/execution hashes are in the receipt. No production
paths, credentials, sessions or private approval records are included in that
committed summary. Real snapshots and application JARs remain outside Git.

The paired c5ea/AI/Tunnel/watchdog, original production launcher/profile and real
approval provenance remain adapters exactly as listed in the receipt. The
17-file controller installation is separately covered by existing storage/fault
tests and was not executed by this harness. Database fixtures contain10 paintings;
there was no new10k run or production reconciliation. Isolated recovery does not
establish production rollout or rollback acceptance.

---

> Historical map-enabled integration receipt. Its recorded source/module/JAR
> hashes and three-file asset contract predate the approved no-map follow-up.
> Reuse only unchanged mechanism evidence; the workspace no-map readiness record
> identifies the new two-file execution and candidate artifact separately.

# Knowledge V2 focused readiness integration — 2026-10-12

The actual application transaction completed against the existing `60c5…` baseline and unchanged `550d…` Knowledge candidate, then restored the baseline. A second operation was killed immediately after its first actual JAR replacement. A fresh coordinator recovered the mixed installation and verified the restored runtime. This is isolated pre-release evidence, not production rollout or rollback acceptance.

The sanitized receipt is [readiness-integration-evidence.json](readiness-integration-evidence.json). It binds the exact tested source hashes, artifact hashes, outcomes, retained-data hashes, process isolation, HTTP results and both transaction phase histories. The test loaded the current `CoreRuntime` source after the legacy-query extraction; this V2 run does not exercise that V1 helper. Neither application JAR was rebuilt or rewritten.

## Closed gaps

| Earlier boundary | New execution | Practical guarantee demonstrated |
| --- | --- | --- |
| Simulated ownership/atomic file writes | Real root-owned 0600 files, private 0700 transaction directories, actual `R25Storage`, fsync and CAS | Both JAR copies, manifest, application configuration and handoff change consistently; the complete five-file baseline is restored. |
| Synthetic artifact bytes and payload identity | Exact historical JAR `60c5b95529e027ec2cd3634cc6fe190fe43b42c48eb402e2d9ba0f1ce7caaecb`; unchanged local PR-candidate JAR `550d1bb9e71717226d5fc7645c94b6cb21234ecbfff44aa3fdae4f1f9c1a84d8` | Actual different executable payloads pass the explicit V2 identity contract; accepted records remain synthetic test approvals. |
| Mock runtime lock | Real separately opened `flock` descriptor conflicts with actual coordinator lease | Conflicting publication refuses before a transaction or service stop. |
| Mock Java process/port | Verified lifecycle source's real `start_role`, `stop_role`, `/proc` PID/start-tick/session/executable checks and `ss` listener ownership, with actual Java 17 application processes | Candidate JVM identity agrees with installed files, registered source identity, controller CURRENT and HTTP identity. A real foreign executable substituted in fixture PID metadata is refused rather than adopted or signalled. |
| Mock asset/process gate | Three real existing assets on a dedicated globally read-only tmpfs; actual BusinessGuard/bootstrap capability preparation and process attestation | Root candidate has all five capability sets zero, NoNewPrivs, and cannot obtain a writable asset filesystem. Actual snapshot endpoints return 711 nodes, 609 edges and 35 map features. |
| Separately exercised PG/HTTP boundaries | Actual coordinator's read-only SQL adapter plus actual application HTTP | A private PostgreSQL 16.15 database contains the existing 10 synthetic paintings, 6 Gallery-eligible paintings and 2 normalized author names. Authentication, public projection and media JSON errors pass. |
| In-process exception-only recovery | Child coordinator calls `os._exit(73)` after first real live JAR write | Durable `INSTALL_INTENT` survives process loss with a mixed old/new JAR pair. A new coordinator acquires the released lock, validates snapshots/current/known bytes, restores and starts the baseline; repeated recovery is a verified NOOP. |

Final outcomes were: `FOREIGN_LIFECYCLE_PROCESS_REFUSED`, `LOCK_CONFLICT_REFUSED`, `COMMITTED`, `CURRENT_VERIFIED_NOOP`, `COMMITTED_VERIFIED_NOOP`, `RESTORED`, `RESTORED_VERIFIED_NOOP`, `PROCESS_INTERRUPTED_AFTER_FIRST_REAL_JAR_WRITE`, `RESTORED`, `RESTORED_VERIFIED_NOOP`.

The 11 contractual retention tables and 3 synthetic media files were unchanged. An additional independent SELECT-only inventory checked **all 44 public tables**, including empty user/task tables; before/after hashes match. These fixtures do not prove preservation of a populated production user/task history. Authentication uses a disposable copy of the existing synthetic SQLite account store; the test logs in once to that existing account and performs no account creation, task submission, upload or provider request.

## Isolation and remaining adapters

The runner requires root only inside disposable **mount, network and PID namespaces**. It overlays private `/root` and `/srv` tmpfs mounts, uses explicit `/srv/readiness-installation` and `/srv/readiness-c5ea` fixture roots, a preview-only JAR directory, loopback HTTP 19080 and a new private PostgreSQL 55644. It restores only the prior task's synthetic `public` schema; the completed 10,000-record test schemas are excluded. The original preview, original fixture database and source assets remain untouched. The PG service account is resolved from the existing local `nobody` account; pgpass is owned by that actual account, while the coordinator remains root. No production UID or credential ownership is assumed.

Still adapted, and not covered by this result:

- The lifecycle Engine factory supplies fixture c5ea, Guide, Critic, Tunnel and watchdog interfaces. Java lifecycle methods are real; these other services are not started or stopped. Their existing protocol/unit evidence remains separate.
- A small fixture bootstrap calls the actual BusinessGuard eligibility and sandbox methods, then starts Java using the existing **integration** profile. The original production launcher, production Spring profile, provider configuration and cross-service runtime have not been exercised by this harness.
- Source/artifact accepted records, review identifiers, policy and permission evidence are explicitly synthetic fixture inputs. They do not establish real approvals or release build provenance.
- The 17-file controller installation/upgrade transaction is not executed here. Its existing real-storage fault-injection tests and the separately fixed first-install query path have their own evidence.
- Production configuration reconciliation, actual service-account proof, final CI artifact binding and release-window acceptance remain later authorized checks.

## Reproduction and retained evidence

The workspace handoff points to the Git-external `evidence/readiness-integration/` directory. `run.py`, `execution.json`, `result.json`, and private setup/failure diagnostics are retained there. The receipt records the exact runner SHA. Private SQLite and fixture SQL inputs, credentials, actual JARs and runtime snapshots are intentionally not committed. Converting the local runner into a general installer is outside this change.

The actual invocation was:

```bash
wsl.exe --distribution Ubuntu --user root --exec \
  /usr/bin/unshare --mount --net --pid --fork --mount-proc \
  --propagation private /usr/bin/python3 -B "$READINESS_EVIDENCE/run.py" \
  "$(readlink /proc/self/ns/mnt)" "$(readlink /proc/self/ns/net)"
```

`READINESS_EVIDENCE` must refer to the existing task's evidence directory, not a production installation. Run only after inspecting that script and its explicit fixture paths. Exit code was **0**, wall time **35.848 seconds**. Timing measures a small local integration exercise, not production performance. Earlier harness setup refusals (private native-PG path access, socket-derived port identity, preview working directory, insufficient tmpfs reserve) were corrected within the disposable runner; no candidate safety check was weakened.
