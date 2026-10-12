# Explicit Knowledge Core upgrade — review candidate, not production authorization

This change adds a candidate-specific V2 path to the existing R25 publisher.
It does not turn equivalent repackaging into permission to change executable
payloads. V1 still compares every effective class, resource, library and launcher
attribute. The current application changes require V2:

- [Core #10](https://github.com/Hang-666-star/auralink-core-api/pull/10): authenticated
  GET `/api/v1/knowledge/painting-statistics`, `/poetry-graph`, `/china-map`.
- [Web #14](https://github.com/Hang-666-star/auralink-web/pull/14): Knowledge views.

Nothing in this document approves a production candidate, installs a controller,
changes an enable flag, or authorizes release promotion. Owner review, actual
release artifact identities, installation preflight and a separately authorized
window remain necessary. Do not use synthetic test approval records operationally.

## What is bound

`core_business.py` validates `R25_CORE_BUSINESS_POLICY_V2`, installed through the
separate controller upgrade transaction. It contains the exact original V1 policy
and its byte digest, its one verified current/rollback release reference, the
new candidate's repository, source commit, Actions run/attempt, JAR SHA/size and
independently computed complete payload fingerprint. The public candidate JSON
cannot install or update approval. The existing trusted artifact verifier still
runs before staging; no uploaded script is executed.

The private policy also binds all twelve Core publisher/validator/installer
modules, the exact lifecycle/launcher/guard sources, the paired Web commit,
review/evidence digests, asset manifest and permission evidence, the application
configuration before/after digests, and the native PostgreSQL installation.
`upgrade.evidence.map_permission_sha256` is a required private approval reference,
not a claim that permission has been obtained for this candidate.

There is no approval generator or auto-discovery of acceptable hashes. The
operator must deliver separately reviewed private records and pass the approved
controller plan digest out of band. Before first executing the upgrade entrypoint,
independently verify the entire reviewed Deploy bundle against its release Actions
manifest and approval hashes. Its later internal checks cannot establish trust in
modules already imported from that bundle. A Core upload cannot select this bundle.
The final release merge commits and Actions
JARs do not exist yet; feature heads and the local preview JAR are not substitutes.

## Configuration, data and runtime

Only four `auralink.knowledge.*` properties are added: `snapshot-root`,
`graph-sha256`, `stats-sha256`, `china-sha256`. The transformer preserves every
original configuration byte and verifies the complete approved after digest.
Ambiguous/preexisting Knowledge configuration fails closed. Spring YAML binding
of these dotted properties was checked with the actual candidate dependencies.
Environment/JVM overrides are refused when the actual running process is attested.
Authentication, database/media paths and `configured-provider` are not changed.

V2 uses an independent read-only PostgreSQL adapter; it never passes the changed
JAR as the historical 60c5 baseline to the old guard. `psql`, native configuration,
loopback database identity and the pgpass owner are bound to the installation
contract and the OS account database. There is no root:root pgpass assumption.
The executable has explicit approved ownership/mode and is copied into a sealed
memfd after digest verification, then executed by descriptor to prevent a path
replacement between verification and exec. Its ELF interpreter/shared libraries
remain part of the trusted host installation. Only the fixed retention, idle-work
and public-projection sample queries can run;
all use read-only transactions, bounded timeouts and a minimal environment.

The approved retention manifest binds PostgreSQL 16, V001–V013, complete row
signatures of the eleven catalog tables named in `core_business.TABLES` (including
current-revision selectors, missing-image/source rows, fields and annotations),
three kinds of active work, and explicitly inventoried media bytes. This is a
strict stable-window contract. Any changed catalog row, including an addition,
refuses the old manifest. Later rollback requires separately reviewed refreshed
compatibility evidence; it never restores a database to make an old hash pass.
These checks do not pretend to fingerprint every user/task table. The publisher's
fixed write set excludes databases, credentials, user assets, tasks and media;
existing application integration evidence remains part of the required review.

The shared R25/c5ea lock and Core/AI recovery interlocks remain. An unfinished
controller upgrade also blocks normal Core publication. c5ea remains the only
Next lifecycle owner. The reviewed business overlay changes only the Java
launcher hook and its lifecycle digest; no alternate launch service is created.

## Root service and read-only assets

The historical launcher runs Java with root identity. Inventing a non-root UID
in policy cannot satisfy its process contract. The explicit
`readonly-filesystem-capdrop` installation mode retains that verified UID/PID and
existing application-file access while dropping all capability sets and setting
`NoNewPrivs` in the owned launcher immediately before exec of the business JAR.
Only a new V2 business record invokes this hook; V1 and rollback baseline starts
keep their existing behavior. The coordinator keeps its normal authority and can
stop/recover its owned child using the existing identity checks.

This mode requires an independently provisioned **dedicated tmpfs filesystem**
mounted exactly at the approved snapshot root, filesystem root `/`, with both
mount and superblock read-only flags. A read-only bind mount alone is insufficient:
other namespaces can expose its writable backing filesystem. Other filesystem
backing types are deliberately unsupported in this first contract. The publisher
never mounts, copies or repairs data assets. If the kernel cannot enforce the
capability/no-new-privileges transition, launch fails and the normal recovery
transaction remains responsible for the application.

Actual process verification checks UID/GID/groups, PID start ticks, the effective
configuration argument and absence of overrides; for the business candidate it
also checks zero effective/permitted/inheritable/bounding/ambient capabilities,
NoNewPrivs and the actual read-only filesystem view. A fabricated account or
synthetic permission receipt cannot replace this observation. The alternative
non-root POSIX mode retains its strict separate-owner/read-only checks and only
applies to an independently compatible reviewed installation.

The persistent source bundle remains outside Git; a tmpfs mount is lost on
reboot/unmount. Authorized asset provisioning must restore a complete version,
verify all bytes and remount the whole filesystem read-only before restarting the
business application. Missing/unmounted assets cause preflight/start refusal;
application requests otherwise retain the safe 503/retry contract. This is an
explicit operational prerequisite, not a production mount performed by this PR.

## Controller transaction and application transaction

The reviewed Deploy bundle is staged privately at the fixed
`operations/r25-controller-candidates/<reviewed-release-commit>/` location.
`upgrade_core_controller.py upgrade --approval-sha256 <reviewed-digest>` reads
`CONTROL_UPGRADE_APPROVAL.json` from the fixed Core store. It binds exact old/new
policies, publisher modules, control overlays and three handoff hash updates,
plus unchanged CURRENT, JAR pair, MANIFEST and application configuration.
The overlay renderer accepts only the exact audited V1 source pair. Unknown
controller drift is not absorbed. Existing V1 first installation remains separate.

PREPARING/PREPARED allow exact preparation retry. After watchdog stop or file
replacement intent, repeat upgrade refuses; use the same reviewed candidate
bundle's `recover --approval-sha256 <same-digest>`. Recovery validates the fixed
lock and complete before/after identities without first requiring a partially
installed policy to load. It restores the previous controller/policy pair only
while the application/CURRENT remain unchanged. It never stops Java or Next.
Private journals and the active marker survive errors. Unknown files/ownership,
foreign CURRENT or drift refuse with a fixed reason code; no automatic cleanup.

Normal application delivery continues through `core_publish.py prepare-incoming`,
`stage`, `publish`, `status`, `recover --transaction ...`, and `rollback
--transaction ...`. The fixed existing snapshot now includes the approved
configuration after-image. CURRENT is committed only after process, PostgreSQL,
anonymous/media and authenticated Knowledge acceptance. Recovery accepts only the
journal's exact before/after file/config states, including interrupted partial
installation. A repeated committed operation verifies and returns a no-op.

Explicit rollback of a committed V2 release verifies the transaction, CURRENT,
exact accepted payload, five live after-images, controls and owned live Java PID
without requiring healthy Knowledge endpoints/assets or an unexpired acceptance
session. It then applies the unchanged baseline compatibility/idle-work gates and
full restored-baseline acceptance. This allows recovery from asset/session failure
without accepting a foreign JAR or unknown process. The path still requires an
identifiable live Java process; total process loss is not covered by this new
rollback allowance. V1 retains its existing source health checks.

`ACCEPTANCE_SESSION.json` is a private existing-session input containing a `bearer`
value. The publisher does not log in, mint JWTs, create accounts, or print the
session. Missing/expired sessions or unavailable graph/map endpoints prevent
acceptance. Read-only acceptance verifies Gallery/statistics denominator equality,
field coverage, author-name bounds, graph hashes/IDs/endpoints, map identity,
anonymous 401, authenticated public-field samples and media JSON errors. Earlier
isolated private-field mutation evidence is reused, not reproduced in production.

## Release and rollback sequence

1. Review Deploy/Core/Web PRs and required CI. Merging main does not deploy.
   The 2026-10-12 bounded observation found the original lifecycle/launcher and
   no Core publisher registry. This installation therefore needs the reviewed V1
   first-install step before V2 upgrade. Use the [unexecuted release instructions](release-instructions.md);
   do not invoke the V2 upgrader directly against absent POLICY/CURRENT.
2. In a separately authorized preparation window, refresh actual controller,
   JAR/Web/configuration identities, locks/recovery state, service credentials,
   ownership, native PostgreSQL and source-module cache state. Bind final reviewed
   release Actions artifacts and private acceptance/retention evidence.
3. Resolve exact map redistribution permission. Deliver all three Git-external
   files, verified manifest and a complete dedicated read-only asset filesystem.
   Verify actual service identity, effective JVM configuration and reboot recovery.
4. Install/upgrade the reviewed Deploy controller under the same R25 coordination;
   verify its recovery contract. Publish Core/configuration/assets first. Require
   actual authenticated acceptance and later production data reconciliation.
5. Only after Core acceptance, explicitly authorize Web main→release promotion
   through c5ea/R25. Web release has automatic deployment effects. Verify final
   source SHA/BUILD_ID/API base and both Knowledge views.
6. Prefer Web rollback first, then the current Core transaction's verified,
   still-compatible baseline/configuration. New Web with old Core displays
   unavailable/retry for absent Knowledge APIs. Do not restore an arbitrary old
   JAR, restore a DB, delete media, re-import or republish the 486 huaniao records.
   A changed data window or failed recovery remains a refusal requiring review.

Production rollout, reconciliation, controller installation and production
rollback acceptance have **not** been executed. See [asset delivery](assets.md) and [validation](validation.md)
for exactly which boundaries were exercised with real processes, PostgreSQL and
HTTP, and which coordinator tests use fixtures/stubs.
