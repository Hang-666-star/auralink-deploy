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
