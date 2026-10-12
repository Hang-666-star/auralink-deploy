# Coordinated Knowledge release instructions — NOT EXECUTED

This runbook is a review candidate. It grants no approval, changes no policy and
has not installed, started, stopped or published anything in production. Every
mutation below requires a separately authorized R25/c5ea window. Do not execute
examples with PR heads, synthetic approval records or guessed configuration.

## Observed starting state and mandatory decisions

The bounded 2026-10-12 observation found the original production lifecycle and
launcher, not an installed Core publisher. `operations/core_release_guard.py`,
`operations/r25-publisher/core_publish.py`, `POLICY.json` and `CURRENT.json` were
absent. Lifecycle/launcher hashes matched the first installer's exact V0 inputs;
paired JARs, MANIFEST and handoff also matched its accepted baseline. Therefore
**authorized V1 bootstrap must precede V1-to-V2 upgrade**. Do not fabricate an
empty CURRENT/POLICY to make the upgrade entrypoint run.

The Java service was root with capabilities, while native PostgreSQL/pgpass used
a separate installation account. These are different ownership contracts. Use
fresh account/UID/GID/group and configuration observations when binding policy;
never infer pgpass ownership from Java/root or copy a historical UID blindly.
The currently configured Guide graph/stats are not a read-only Knowledge asset
installation. The three matching source files in the historical frontend are
also not an approved runtime bundle or proof of map redistribution permission.

Before scheduling writes, the owner must resolve all of the following:

1. Required review and checks for Deploy #3, Core #10 and Web #14, then the normal
   separately approved main-to-release promotions. Main merge alone is not deploy.
2. Exact DataV/Gaode map hosting/API permission, or a separately reviewed scope
   change. Current V2 requires all three assets and a map-permission evidence
   digest. A map-unavailable release is **not** enabled by removing a file or
   inventing that digest; it needs an explicit contract/acceptance change.
3. Final Deploy/Core release identities, artifact run/attempt/hashes, the known
   reviewed compatible Web source commit, and independently reviewed private
   controller/policy/compatibility records. Web's later release merge SHA is
   recorded after Core acceptance; do not invent it in advance.
4. A real existing authorized acceptance session and its expiry window. The
   publisher only reads it; it cannot mint a token, log in or create an account.
5. Asset administrator, durable source bundle, approved new version root and
   reboot restoration procedure; observed root service requires the dedicated
   globally read-only tmpfs/capability-drop contract described in [assets](assets.md).
6. Bootstrap, actual legacy helper ownership and the complete coordinated
   integration findings must be closed on the final candidate. A successful
   source-only/unit test is not permission to bypass an installer refusal.

## Final artifacts: verify before any imported code

Perform these commands in an isolated release-review directory after authorized
release builds exist. Required variables are deliberately unset: no final release
SHA/run/approval has been invented. They must come from independently reviewed
release records, not from an uploaded manifest's self-declaration.

```bash
# NOT EXECUTED — local artifact verification only
set -Eeuo pipefail
: "${TRUSTED_DEPLOY_SOURCE:?reviewed exact Deploy release checkout}"
: "${DEPLOY_RELEASE_SHA:?approved final Deploy release SHA}"
: "${DEPLOY_RUN_ID:?verified release Actions run}"
: "${DEPLOY_RUN_ATTEMPT:?verified attempt}"
: "${DEPLOY_BUNDLE_DIR:?downloaded release artifact directory}"
: "${DEPLOY_ARCHIVE_SHA256:?independently approved ZIP digest}"
: "${DEPLOY_MANIFEST_SHA256:?independently approved manifest digest}"
test "$(git -C "$TRUSTED_DEPLOY_SOURCE" rev-parse HEAD)" = "$DEPLOY_RELEASE_SHA"
printf '%s  %s\n' "$DEPLOY_ARCHIVE_SHA256" "$DEPLOY_BUNDLE_DIR/r25-controller.zip" \
  "$DEPLOY_MANIFEST_SHA256" "$DEPLOY_BUNDLE_DIR/r25-controller-manifest.json" | sha256sum -c -
python3 -B "$TRUSTED_DEPLOY_SOURCE/scripts/package-r25-release.py" verify \
  --output "$DEPLOY_BUNDLE_DIR" --repository Hang-666-star/auralink-deploy \
  --ref refs/heads/release --commit "$DEPLOY_RELEASE_SHA" \
  --run-id "$DEPLOY_RUN_ID" --run-attempt "$DEPLOY_RUN_ATTEMPT"

: "${TRUSTED_CORE_SOURCE:?reviewed exact Core release checkout}"
: "${CORE_RELEASE_SHA:?approved final Core release SHA}"
: "${CORE_RUN_ID:?verified release Actions run}"
: "${CORE_RUN_ATTEMPT:?verified attempt}"
: "${CORE_CANDIDATE_DIR:?downloaded core-api-r25-staging artifact}"
: "${CORE_JAR_SHA256:?independently approved JAR digest}"
test "$(git -C "$TRUSTED_CORE_SOURCE" rev-parse HEAD)" = "$CORE_RELEASE_SHA"
printf '%s  %s\n' "$CORE_JAR_SHA256" \
  "$CORE_CANDIDATE_DIR/auralink-backend-0.0.1-SNAPSHOT.jar" | sha256sum -c -
python3 -B "$TRUSTED_CORE_SOURCE/scripts/core-release-candidate.py" verify \
  --manifest "$CORE_CANDIDATE_DIR/core-release-candidate.json" \
  --expected-commit "$CORE_RELEASE_SHA" --expected-run-id "$CORE_RUN_ID" \
  --expected-run-attempt "$CORE_RUN_ATTEMPT" \
  --jar "$CORE_CANDIDATE_DIR/auralink-backend-0.0.1-SNAPSHOT.jar" \
  --verification "$CORE_CANDIDATE_DIR/r25-artifact-verification.json"
```

Deploy's release workflow packages its fixed allowlist and does not connect to
production. Core's release workflow produces a different staging manifest from
the PR CI artifact. PR CI's synthetic merge SHA and the local preview JAR are not
release artifacts. Do not rebuild merely to change timestamps: retain existing
verified bytes when their exact source/run identity fits the approved contract.
If final merging/editing changes identity, obtain the normal release artifact,
rebind hashes/run/attempt/private review records, and repeat affected acceptance.

The reviewed administrator must extract only the verified Deploy archive's fixed
allowlist into a **new** private directory, refuse preexisting/unknown files,
verify extracted hashes, owner/mode and all ancestor paths, and exclude Python
bytecode caches before importing anything. The focused bootstrap/cache fixes do
not establish every legacy selector/tunnel helper cache condition. The bounded
production observation did not inspect those caches; the future authorized
preflight must check them without deleting unknown files to force acceptance. Never execute code from a Core upload.
Transfer uses the established SSH configuration with `StrictHostKeyChecking=yes`
and the independently verified known-host key; do not scan-and-trust or disable
host verification. Do not print keys, environment files or private records.

## Deliver assets and private records in the authorized preparation window

This is a separate asset-administrator operation, not a publisher fallback.
Follow [the asset installation/recovery procedure](assets.md). Copy the three
hash-bound files from the durable external bundle to a new offline version,
verify exact sizes/hashes and service traversal/read access, apply reviewed
owner/group with directory0550/files0440, and mount/remount the **whole dedicated
tmpfs** read-only with `nosuid,nodev,noexec`. Read-only bind mounts are insufficient.
Do not modify the existing Guide files or historical source directory in place.
Do not use a read-only filesystem as a reason to skip actual candidate process
capability/NoNewPrivs verification after launch.

The byte/config verifier can run before activation; it has no mutation capability:

```bash
# NOT EXECUTED — actual administrator selects these nonsecret approved values
: "${ASSET_ROOT:?approved complete version root, not the legacy source directory}"
: "${ASSET_MANIFEST:?reviewed Core knowledge-assets-manifest.json}"
: "${TRUSTED_CORE_SOURCE:?reviewed Core release checkout}"
python3 -B "$TRUSTED_CORE_SOURCE/scripts/verify-knowledge-assets.py" \
  --snapshot-root "$ASSET_ROOT" --manifest "$ASSET_MANIFEST"
```

This command only proves bytes. `--check-environment` verifies only an explicitly
supplied four-variable environment, not the effective running Spring properties.
The current root service must not be falsely passed through the non-root-only
`--require-read-only` flag. V2 separately verifies the globally ro tmpfs and, after
launch, the real process's five capability sets and NoNewPrivs. Application config
is installed only by the approved application transaction, not by an operator
editing YAML before publication. The policy binds these exact four values:

| Property | Required binding |
| --- | --- |
| `auralink.knowledge.snapshot-root` | approved new absolute version root |
| `auralink.knowledge.graph-sha256` | `899511b6b7d02e6ba515986db651c67b3702497d2031bdbb75029c34491da2c0` |
| `auralink.knowledge.stats-sha256` | `27e91284d28c05c9b7dde9fcb4181c713761d3c2eebf84816b45c9f7d9af7501` |
| `auralink.knowledge.china-sha256` | `206cf7fd5acba4bb08d9586899acc144cea2b29d9e93ff70f93895c5e5ffde77` |

Private delivery must include, after independent human review:

- V2 `POLICY.next.json`: exact original V1 policy bytes/digest; baseline release
  reference; Core release source/run/attempt/JAR/payload; a known reviewed
  compatible Web source commit in `upgrade.web_commit` (not a future merge SHA);
  full application before/after digests; twelve runtime module hashes;
  actual service/native PostgreSQL/credential/psql ownership, modes and hashes;
  external manifest and stable-window catalog/media retention evidence.
- `CONTROL_UPGRADE_APPROVAL.json`: reviewed Deploy release/run/attempt, exact
  old/new controllers/policy/modules/handoff, preserved CURRENT/JAR pair/MANIFEST/
  application hashes and approved evidence reference. Its approved SHA must be
  conveyed independently, not read from the untrusted record as its own authority.
- Exact private asset/retention/evidence documents at policy-bound paths. Map
  permission and compatibility evidence must be real, not fixture placeholders.
- `ACCEPTANCE_SESSION.json` in the fixed Core store, root-private0600, with the
  existing authorized `bearer` value. Never put the value in shell arguments,
  command output, Git or PRs. Absence/expiry blocks candidate acceptance.

Refresh the actual stable data window for the eleven retained catalog tables and
inventoried media before authorization. A later legitimate data change invalidates
that specific manifest; it is not a reason to overwrite production with old data.

## Bootstrap V1, then upgrade V2

All following server commands are **NOT EXECUTED** and require authorization.
The trusted interpreter and fixed roots are from the installation contract.
An administrator separately delivers reviewed publisher modules root-private0600
under `operations/r25-publisher` (directory0700), without overwriting an existing
installation. This delivery does not switch application JARs.

```bash
# NOT EXECUTED — on the authorized R25 host only
set -Eeuo pipefail
: "${APPROVED_RELEASE_WINDOW_REFERENCE:?separate owner authorization required}"
R25_ROOT=/root/autodl-tmp/artlive-r25-native-pg16/handoff-production-20260923T062101Z
R25_PYTHON=/root/miniconda3/bin/python3
PUBLISHER="$R25_ROOT/operations/r25-publisher/core_publish.py"
STORE="$R25_ROOT/runtime/core-publications"
# Before first installation, independently refresh fixed old identities/owners,
# paired service identities, lock state, legacy helpers and no bytecode caches.
"$R25_PYTHON" -B "$R25_ROOT/operations/r25-publisher/install_core_controller.py" install
"$R25_PYTHON" -B "$PUBLISHER" status
```

Require `CONTROLLER_INSTALLED` (or verified exact no-op), `java_restarted:false`,
V1 POLICY/CURRENT consistent with the unchanged running baseline, and restarted
owned watchdog. This is not a business deployment. Do not run a Knowledge JAR
through V1, which must still reject changed payloads. The first-install checks
are exact; drift requires review and cannot be accepted by editing fixed hashes.

Only after bootstrap succeeds can the private V2 records bind the actual new V1
policy/CURRENT and handoff identities. A bootstrap using this complete new Deploy
bundle already contains the new modules: bind their actual `before_sha256`; do
not copy fixture `null` values for files that now exist. Deliver the reviewed new modules plus
`POLICY.next.json` at the fixed candidate path; deliver the approval at the fixed
Core store path. Verify every delivered file/hash/private mode before execution.

```bash
# NOT EXECUTED — same authorized host/session; no fabricated approval
: "${DEPLOY_RELEASE_SHA:?approved final Deploy release commit}"
: "${CONTROL_APPROVAL_SHA256:?independently approved control plan digest}"
: "${V2_POLICY_SHA256:?independently approved POLICY.next.json digest}"
[[ "$DEPLOY_RELEASE_SHA" =~ ^[0-9a-f]{40}$ ]]
[[ "$CONTROL_APPROVAL_SHA256" =~ ^[0-9a-f]{64}$ ]]
CANDIDATE_CONTROLS="$R25_ROOT/operations/r25-controller-candidates/$DEPLOY_RELEASE_SHA"
printf '%s  %s\n' "$CONTROL_APPROVAL_SHA256" "$STORE/CONTROL_UPGRADE_APPROVAL.json" \
  "$V2_POLICY_SHA256" "$CANDIDATE_CONTROLS/POLICY.next.json" | sha256sum -c -
"$R25_PYTHON" -B "$CANDIDATE_CONTROLS/upgrade_core_controller.py" upgrade \
  --approval-sha256 "$CONTROL_APPROVAL_SHA256"
"$R25_PYTHON" -B "$PUBLISHER" status
```

Require `CONTROLLER_UPGRADED`/verified no-op, exact 17-file control plan and unchanged
application/CURRENT. It stops/restarts only the owned watchdog; Java/Next remain
unchanged. The shared R25/c5ea lock and Core/AI/unfinished-controller interlocks
must stay enforced. Do not hold a second external flock around these commands;
each operation acquires and validates the existing lock itself.

## Core artifact delivery and application activation

Choose one reviewed delivery method and retain its exact run/attempt identity:

- Existing Core workflow: `R25_DEPLOY_ENABLED=true` invokes the existing publisher
  after staging. This requires a **verified effective production approval gate**
  that keeps publication waiting while the actual run's artifact is reviewed and
  bound. Do not enable it if that gate/coordination is absent or not verified.
- Build-only release artifact while the flag remains disabled: after private V2
  approval, an authorized R25 operator can use the installed publisher's exact CLI
  below to deliver that same artifact/run/attempt. This is the same coordinator,
  not the historical independent deployment launcher or a new lifecycle owner.

A rerun increments run-attempt and can create different JAR bytes. Never approve
attempt1 then rerun publication as attempt2 against the old policy. Rebind a new
attempt/artifact through review. Do not change enable flags as an incidental
part of a code review; this needs explicit operational authorization.

```bash
# NOT EXECUTED — on R25, before transfer
: "${CORE_RELEASE_SHA:?approved final Core source SHA}"
: "${CORE_RUN_ID:?approved artifact run}"
: "${CORE_RUN_ATTEMPT:?approved artifact attempt}"
[[ "$CORE_RELEASE_SHA" =~ ^[0-9a-f]{40}$ ]]
[[ "$CORE_RUN_ID" =~ ^[1-9][0-9]{0,19}$ ]]
[[ "$CORE_RUN_ATTEMPT" =~ ^[1-9][0-9]{0,19}$ ]]
identity=(--commit "$CORE_RELEASE_SHA" --run-id "$CORE_RUN_ID" --run-attempt "$CORE_RUN_ATTEMPT")
"$R25_PYTHON" -B "$PUBLISHER" prepare-incoming "${identity[@]}"
```

`prepare-incoming` is a production directory write, **not** a read-only preflight.
Transfer only `auralink-backend-0.0.1-SNAPSHOT.jar`,
`r25-artifact-verification.json`, `core-release-candidate.json`, mode0600, to:
`/root/autodl-tmp/auralink-core-deploy/incoming/<CORE_SHA>-<RUN>-<ATTEMPT>/`.
Use the existing verified host-key SSH channel and compare transferred hashes.
Do not transfer candidate Python/scripts or real data into this directory.

```bash
# NOT EXECUTED — local approved delivery workstation; previously validated identities
: "${APPROVED_SSH_CONFIG:?existing host-key-verified SSH configuration}"
: "${R25_HOST_ALIAS:?approved existing SSH host alias}"
: "${CORE_CANDIDATE_DIR:?previously verified exact release files}"
chmod 600 "$CORE_CANDIDATE_DIR/auralink-backend-0.0.1-SNAPSHOT.jar" \
  "$CORE_CANDIDATE_DIR/r25-artifact-verification.json" "$CORE_CANDIDATE_DIR/core-release-candidate.json"
scp -F "$APPROVED_SSH_CONFIG" -o StrictHostKeyChecking=yes -o BatchMode=yes -p \
  "$CORE_CANDIDATE_DIR/auralink-backend-0.0.1-SNAPSHOT.jar" \
  "$CORE_CANDIDATE_DIR/r25-artifact-verification.json" \
  "$CORE_CANDIDATE_DIR/core-release-candidate.json" \
  "$R25_HOST_ALIAS:/root/autodl-tmp/auralink-core-deploy/incoming/$CORE_RELEASE_SHA-$CORE_RUN_ID-$CORE_RUN_ATTEMPT/"
```

```bash
# NOT EXECUTED — back on R25; exact identity array from above
"$R25_PYTHON" -B "$PUBLISHER" stage "${identity[@]}"
timeout --signal=TERM --kill-after=60 480 \
  "$R25_PYTHON" -B "$PUBLISHER" publish "${identity[@]}"
"$R25_PYTHON" -B "$PUBLISHER" status
```

`stage` writes the immutable approved registry; `publish` also stages internally,
then performs the application transaction. Record its transaction ID and every
outcome. Accept only verified `COMMITTED` (or verified exact no-op), never shell
exit alone. Require JAR pair/MANIFEST/handoff/config/CURRENT consistency, observed
owned PID/start-ticks/hash, readonly catalog/media compatibility, idle work,
zero candidate capabilities/NoNewPrivs, anonymous401, authenticated three GETs,
Gallery/statistics equality, public projection, graph/map hashes and media JSON
errors. The authenticated checks run through the actual installed publisher;
there is no separate fabricated HTTP success receipt.

## Only then publish Web through c5ea

Before Core approval, bind `upgrade.web_commit` to the **known, reviewed compatible
Web source commit**, normally the accepted main commit after Web PR review. The
current V2 schema records that compatibility identity; it does not require an
as-yet-unknown Web release merge SHA and does not prove runtime Web identity by
itself. Never put a guessed future merge SHA into the policy.

After Core acceptance, compare the Web main-to-release PR's complete resulting
application/configuration/dependency content with that bound source and authorize
promotion only if the intended contents still match. If main or the proposed
release tree has advanced materially, stop for compatibility review and rebind
the private candidate record through its supported reviewed procedure; do not
assume the earlier source approval covers new changes. Record both the bound
compatible source commit and the later actual release merge SHA, including the
source/tree comparison evidence.

Then use the repository's normal reviewed merge-commit process. The existing Web
release push automatically runs `deploy.yml`, which verifies the exact fetched
release and calls the existing `deploy-web.sh deploy <release SHA>`. No effective
Web production approval gate has been established by this review: **do not merge
Web release early expecting an unverified gate to hold deployment**. Do not run
that helper independently to bypass repository promotion/review, and do not start
Next from R25 or another session.

Record actual final Web release SHA/BUILD_ID and production API origin, then verify both
Knowledge views and existing Gallery/Studio/Guide/Critic read behavior. Do not
submit tasks or real providers to test availability. The local loopback preview
build is not the production bundle. If Core lacks new APIs, new Web shows
unavailable/retry; absent endpoints on the old baseline are not a baseline fault.

## Refusal, interruption and compatible rollback

- A lock/lifecycle-owner conflict is a refusal. Wait for its actual owner/recovery;
  never kill an unknown process, replace a lock inode or bypass the interlock.
- V1 first install: before live mutation, exact PREPARING/PREPARED can retry the
  same bundle. After watchdog/file mutation intent, use `recover-install` below;
  do not manually build POLICY or erase a bootstrap journal.
- V2 control install: PREPARING/PREPARED permits exact preparation retry. After
  mutation intent, use the same independently verified candidate bundle and the
  same approval digest with `recover`. INSTALLED is not a controller rollback
  command; controller recovery must not run after an application release.
- Application transaction: after failure/unknown interruption, inspect preserved
  journal/ACTIVE/identity safely and call `recover --transaction` for that journal.
  Do not blindly replay publish. Repeated recover returns a verified terminal
  no-op or a precise refusal. A COMMITTED release uses explicit `rollback`.

```bash
# NOT EXECUTED — one reviewed state-matching action, never all four
: "${RECOVERY_ACTION:?approved bootstrap, controller, recover or rollback action}"
case "$RECOVERY_ACTION" in
  bootstrap)
    "$R25_PYTHON" -B "$R25_ROOT/operations/r25-publisher/install_core_controller.py" recover-install
    ;;
  controller)
    : "${CONTROL_APPROVAL_SHA256:?same independently approved controller plan}"
    "$R25_PYTHON" -B "$CANDIDATE_CONTROLS/upgrade_core_controller.py" recover \
      --approval-sha256 "$CONTROL_APPROVAL_SHA256"
    ;;
  recover|rollback)
    : "${CORE_TRANSACTION_ID:?exact recorded transaction, never a guessed/latest ID}"
    [[ "$CORE_TRANSACTION_ID" =~ ^[0-9a-f]{32}$ ]]
    "$R25_PYTHON" -B "$PUBLISHER" "$RECOVERY_ACTION" --transaction "$CORE_TRANSACTION_ID"
    "$R25_PYTHON" -B "$PUBLISHER" status
    ;;
  *) echo 'Refusing unknown recovery action' >&2; exit 64 ;;
esac
```

These four recovery modes are alternatives, **not a sequential script**.
A failing status for a damaged Knowledge asset/session is not permission to edit
live files: explicit committed V2 rollback has an identity-only source gate while
retaining full target compatibility and restored-baseline acceptance. It still
requires an identifiable live owned Java process; complete process loss is not
covered by that allowance.

Prefer c5ea Web rollback first, then the Core transaction's exact compatible
baseline/configuration. The exact Web rollback subcommand has not been established
by this bounded read-only inspection; the c5ea owner must review its installed
helper and record that instruction before authorization. Do not invent a
`rollback` flag or substitute a second Next launcher. A normal reviewed Web revert
promotion is an alternative subject to normal rules and automatic release effects.

A changed catalog/media window refuses the old compatibility manifest. Obtain
reviewed updated compatibility evidence; never restore the old DB or delete new
records/media to make a digest match. Preserve completed huaniao imports, missing-
image rows, public/private projection, authentication, session-generation
protection, private media, configured-provider policy, user data, tasks and media.
Do not downgrade to an arbitrary historical JAR.

Retain durable complete asset versions outside the runtime tmpfs. After reboot or
loss, an authorized asset administrator restores the same approved complete bundle
and global-ro mount before the business start; publisher itself never repairs it.
Do not remount an active version writable or disable hash checks.

## Evidence reserved for actual production activation

Still required in the separately authorized window: fresh source/artifact/runtime
identity and lock checks; exact effective service/configuration and new mount
proof; real release-session GET acceptance; real Gallery/statistics field coverage
and data reconciliation; observed post-switch process capabilities; Web source/
BUILD_ID/API/UI verification; and a separately approved production recovery/rollback
exercise if requested. Isolated tests and this runbook do not establish production
rollout or rollback acceptance.
