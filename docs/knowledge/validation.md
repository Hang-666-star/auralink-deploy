# Isolated validation of the Deploy Knowledge candidate

Dated 2026-10-12. These are development observations, not production rollout,
rollback, capacity or data-reconciliation acceptance. No production installation,
configuration, database, account, service or provider was accessed by these tests.
The existing Web/Core preview was not restarted or rebuilt.

## Repository checks and reproducible synthetic cases

```sh
python3 -B -m unittest discover -s r25 -p 'test_*.py' -v
```

Local result: **166 tests, zero failures/errors/skips** in 13.084 seconds.
The final suite includes the unchanged V1 payload/transaction tests and new V2
policy, immutable configuration, public HTTP acceptance, asset/process contract,
controller-upgrade and application transaction tests. It covers:

- Changed business payload rejected by V1; only the exact explicitly approved V2
  source/run/attempt/JAR/payload/configuration accepted.
- Missing/corrupt/unreadable assets, unapproved configuration, owner/mode changes,
  catalog/schema drift and active work refused before application activation.
- Existing lock and lifecycle-owner conflicts, fixed source/cache checks and
  read-only SQL allowlist; sealed descriptor execution remains unchanged when
  the original psql path is replaced after verification.
- Seventeen fixed controller installation destinations, injected failures before
  and after each live write (34 fault subcases), explicit recovery, exact retry,
  drift refusal and unchanged application/CURRENT during controller installation.
- Actual Publisher/CoreRuntime/config-transform methods commit, repeat as no-op,
  recover partial installation, and restore the exact application/configuration
  baseline. Data drift refuses rollback. A committed V2's missing assets/expired
  acceptance session do not prevent rollback of an otherwise identifiable owned
  live process; foreign JAR drift still refuses before stopping it.

Controller-upgrade tests exercise actual R25Storage atomic files, fsync, metadata
and Linux flock in disposable directories. Lifecycle/watchdog, PostgreSQL, HTTP
and approval identities in those tests are synthetic/stubbed. Application
transaction tests additionally stub their FileFixture storage ownership/atomic
fsync, process/port ownership, candidate artifact identity, asset/process gates
and HTTP. They are not an actual production JVM restart or controller installation.

Required checks also executed: every shell script passes `bash -n`; legacy start
without opt-in exits 64; base and GPU Compose config validates; default services
are empty and every enabled service requires profile `legacy`. Local Compose
5.6.0 was downloaded to a task-only tools directory and its official SHA verified;
no global dependency install, daemon, container or legacy service was started.
CI repeats the repository checks with Python 3.11; local Python is 3.12.3.

## Focused real integration boundaries

The local evidence bundle is Git-external at
`/home/bailangguihun/artlive-database-migration/evidence/`. It contains no evidence
of production acceptance. Private inputs under `evidence/deploy-pg/private` must
never be copied into Git or a PR. The handoff identifies the exact commands and
receipts; tests do not auto-discover a production target.

| Boundary actually exercised | Result and scope | Evidence file |
| --- | --- | --- |
| `core_business.readonly_query` and retention validator to PostgreSQL 16.15 | Loopback55642, existing synthetic `artlive_knowledge_fixture`, V001–V013, 11 tables and 3 local media. Expected head/annotation/schema/SQL refusals; restored expected manifest accepted. Zero DB/media writes. | `deploy-pg-readonly.json` |
| Actual Publisher/CoreRuntime plus that real PG adapter | COMMITTED → CURRENT_VERIFIED_NOOP → COMMITTED_VERIFIED_NOOP → RESTORED → RESTORED_VERIFIED_NOOP; 14 read-only queries, identical 11-table response and media digests, all five application files restored. Application files/artifacts, storage and lifecycle/HTTP/process gates remain fixtures/stubs. | `deploy-coordinator-pg.json` |
| Actual new HTTP acceptance against existing candidate Java20480 and PG55642 | 14 GETs: Gallery/statistics6, names2, graph711/609, map35; three anonymous401; authenticated private-field sample1; media JSON404. Harness refreshed the existing isolated account session with one login POST, in memory only; publisher itself only GETs and never logs in. | `deploy-http-acceptance.json` |
| Actual candidate Spring YAML loader | Four dotted Knowledge keys bind; configured-provider preserved; application was not started. | `deploy-spring-config.json` |
| Real kernel non-root installation and candidate JAR snapshot classes | 36 named checks including real service readability, write/chmod/create/delete/rename refusals, missing/corrupt/unreadable503, independent graph/map behavior and same-JVM restoration200. | `deploy-assets/asset-isolation.stdout.json` |
| Actual Deploy asset gate with real OS metadata | 16 accepted/refused cases, including independent owner, expected hashes, inaccessible files and unsafe permissions. | `deploy-assets/deploy-asset-gate.json` |
| Root launcher privilege helper → exec actual Java17 in the same PID | 19 checks: globally RO tmpfs, UID0/five capability sets zero/NoNewPrivs across exec, actual process attestation, graph711/609/map35. Writes/chmod/unlink/create/proc-alias/remount/unmount refused; normal application working-directory writes and retained media remain usable. | `deploy-assets/root-asset-sandbox.json` |

The root tests used separate mount/network/PID namespaces, disposable tmpfs and
fixture approval records. They executed the real sandbox helper and candidate
JAR loader/controller classes, **not the entire installed launcher/lifecycle →
Spring startup → HTTP chain**. UID0 capability removal and asset immutability are
not a claim of general containment of every root-owned application file. The
actual process UID/configuration, root tmpfs cold-start provisioning and launcher
integration still need authorized installation acceptance.

The real local PG client is an exact owner/mode/hash-bound wrapper for an extracted
psql/lib directory; it executes through the sealed memfd path. Production's native
client/account/configuration must be independently verified. Synthetic approval
and retention files have no production authority. The retention query is bounded
but production-scale annotation volume/timing has not been accepted here.

## Reused and pending evidence

Web83 tests, Core24 local tests, desktop/narrow browser tests, and the completed
10,000 synthetic-painting/266,000-annotation validation are reused unchanged.
Core CI executed17 Maven tests and skipped7 PostgreSQL tests under its existing
opt-in conditions; those seven were exercised in the prior explicit local PG run.
The earlier1.585s HTTP median was warm-cache, single-concurrency and JIT-disabled;
it is not a production performance result.

Pending: owner review; final release artifact/approval identities; actual
installation/service/credential/effective-config preflight; exact map license;
Git-external immutable asset delivery and reboot recovery; full coordinated
controller/Core/Web production acceptance and rollback. No PR/CI result grants
these approvals. See [business contract](business-upgrade.md) and [assets](assets.md).
