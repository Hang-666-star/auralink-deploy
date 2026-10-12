# Official launcher dependency correction

The first isolated execution of the unmodified V2-overlaid production launcher
exposed a release blocker: `core_business.readonly_query()` imported
`core_acceptance` by module name, but the launcher loads the bound guard from
`operations/`, without `operations/r25-publisher/` on `sys.path`. Java never
started; the launcher reported `business_retention_query_unknown`, caused by
`ModuleNotFoundError: core_acceptance`. The earlier integration bootstrap had
supplied that directory and therefore did not cover this failure.

The correction reads the sibling `core_acceptance.py` using its approved policy
SHA-256, declared private ownership and mode 0600. It parses only the two existing
SQL string literals. It does not import or execute that module, change `sys.path`,
trust an ambient module cache, expand the SQL allowlist, or change V1 behavior.
Missing, duplicate, nonliteral, incorrectly hashed, or incorrectly permissioned
definitions fail closed.

## Executed validation, 2026-10-12

- 193 deployment tests passed, including a fresh isolated Python interpreter
  without the publisher import path, an ambient fake module, source/permission
  refusals, and the existing disallowed-SQL checks. Shell syntax, legacy opt-in
  refusal and base/GPU Compose configuration checks passed.
- The actual modified `Publisher`, guard, runtime, storage, lifecycle
  `start_java_locked()` and unmodified V2-rendered production launcher ran in
  disposable mount/network/PID namespaces. The source launcher/lifecycle were
  freshly copied read-only from the observed installation and matched the
  renderer's audited input hashes. Fixed installation paths existed only in the
  namespace's private `/root` tmpfs.
- Real Java 17 selected `catalog-postgres-production`; every application data
  source and authentication used fresh isolated PostgreSQL 16. The selected
  Core main-CI JAR was
  `9e024cfdcf68ec34e24452e487a35c7397df9913245419f2eb93f3ad9cc759ca`, source
  `ecae6d6cb5bbf366ee1bfe43d0e5bcd758bf14a8`. Baseline application bytes were the
  verified huaniao-compatible `60c5b95529e027ec2cd3634cc6fe190fe43b42c48eb402e2d9ba0f1ce7caaecb`.
- Upgrade committed, repeated publication/recovery returned verified no-op,
  explicit application rollback restored all five application files. An abrupt
  controller exit after the first real JAR replacement left a mixed installation;
  a fresh coordinator restored it and repeated recovery returned verified no-op.
  A separately held flock and a foreign process identity were refused.
- Whole-row digests of all 44 public tables matched before/after. Fixtures were
  nonempty: two users, two retired Creation records, one held Critic record, one
  step, one workflow, two favorites, and private-media rows. Four media files
  retained their hashes. No job HTTP request, provider request or upload occurred.
- Exact two-file poetry assets, read-only tmpfs and zero-capability candidate
  Java were verified. Authenticated HTTP observed six eligible synthetic
  paintings, two author names, 711 graph nodes, 609 edges, and disabled-map 503.

The transaction took 35.201 seconds (36.997 seconds including setup/teardown).
These timings are neither an outage estimate nor a production performance test.

## Boundaries

Paired c5ea/Guide/Critic/tunnel/watchdog controls remained explicit test adapters;
provider/Guide/Critic/Creation dispatch was disabled in synthetic configuration.
Approvals and accepted-release records were fixtures. The real launcher and
production profile were executed, but not the production paired services.
V1 first installation and V1-to-V2 control-file transition retain their separate
fixture/fault-injection coverage; this application harness does not install them.
No production write, restart, installation, rollback, backup or acceptance was
performed. This change requires owner review and the normal reviewed release
artifact/approval binding before production use. The selected main-CI JAR is not
an invented `release`-workflow identity.
