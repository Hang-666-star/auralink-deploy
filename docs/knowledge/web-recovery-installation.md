# Four-file c5ea recovery patch execution — NOT EXECUTED

This document is a reviewable **one-off administrative procedure**, not a new
application deployment owner or installed controller framework. The executable
companion is [web_recovery_installation.py](web_recovery_installation.py). It never
starts/stops services, writes PID records, touches application JARs, calls a model,
or reads/writes the database. Its only live write allowlist is three c5ea scripts
plus the R25 handoff's one existing helper-hash binding.

This source PR and the rendered three-file patch must be owner-approved first.
Production execution and delivering these private files remain separately
authorized operations. All commands below are **NOT EXECUTED**.

## Exact phase, files and interruption model

Execute **after successful V1 bootstrap, before any V2 controller upgrade or Core
application transaction**. The script requires bootstrap journal `INSTALLED`,
V1 equivalent-payload policy, matching policy binding, no V2 active marker, no
unfinished Core/AI transaction and no unfinished Web transition. It captures and
later rechecks POLICY, CURRENT, bootstrap journal, frontend selection/reference
and c5ea process-state file hashes. Advancing these identities refuses recovery.

Fixed site locations:

- R25: `/root/autodl-tmp/artlive-r25-native-pg16/handoff-production-20260923T062101Z`
- c5ea: `/root/autodl-tmp/auralink-web-deploy`
- Delivered candidate: `$R25/operations/c5ea-recovery-candidate-20261012`
- Private before/after images and plan: `$R25/operations/c5ea-recovery-installation-20261012`
- Exactly three live scripts: `$WEB/bin/{selection_commit.py,serialized_deploy_web.py,deploy-web.sh}`, observed root:root0700.
- Exactly one live config file: `$R25/runtime/handoff-control.env`, observed root:root0600. Only `R25_FRONTEND_COMMIT_HELPER_SHA256` changes; every other byte is retained.

The shared lease is `$WEB/runtime/frontend-deployment.lock`; the same inode must
be held exclusively. A busy lock refuses without replacing it. The actual
hash-bound R25 selector verifies c5ea's owned Next before and after the four-file
operation using the inherited lease. Its site script identity remains the
observed numeric1000:1000/0700 contract; a changed site must stop for review.

Existing reviewed `r25_storage.py` source hash must be
`c0eb0f7c07f725b7218782f20e5e68768e39bf971f654bdd632f4b681085332c`.
The script compiles those verified source bytes directly, not a `.pyc`. Existing
R25Storage supplies private modes, no-symlink traversal, durable fsync and
expected-existing-hash atomic compare-and-swap. There is no force option.

## 1. Deliver reviewed files and prepare private images

An authorized administrator delivers the **exact rendered** three scripts into
the fixed new candidate directory, root:root0700 directory/files. The companion
procedure itself must be delivered as a reviewed, hash-verified root-private
file (for example `$R25/operations/c5ea-recovery-installation.py`); record its
actual reviewed commit/hash in the execution record. Do not execute a script
from an unverified upload. No installation or delivery happened in this review.

Expected candidate hashes:

```text
f96d2f885d1c099a20bdef031e03a3debc81ad01e0ae29e40066a0309dc7fd3d  selection_commit.py
d00cfd26d2f39b84cc944effdb1c35c3cd4823b3fa86cc54a37e4d9e167eb3a5  serialized_deploy_web.py
ab1335aa5a655b4891f73fa5f2702af71bf50f7e6bb20ec7593ab01fe530d17e  deploy-web.sh
```

```bash
# NOT EXECUTED — authorized R25 administration session only
set -Eeuo pipefail
R25=/root/autodl-tmp/artlive-r25-native-pg16/handoff-production-20260923T062101Z
PROCEDURE="$R25/operations/c5ea-recovery-installation.py"
/root/miniconda3/bin/python3 -B "$PROCEDURE" prepare
```

Expected `PREPARED_PENDING_INDEPENDENT_APPROVAL` and a `plan_sha256`. Prepare
creates only the private stage: four complete before-images, four after-images,
plan and PREPARED journal. It does **not** change live targets. Handoff rendering
requires the actual post-V1 bootstrap digest and exactly one old helper-hash
line. The printed plan digest is a review object, **not approval**. The full
handoff bytes stay private; do not paste them into an issue, log or PR.

The owner reviews private before/after images, the exact four targets/modes,
context and generated post-V1 handoff hash, then conveys the approved plan SHA
independently. Its value cannot be fixed in this pre-bootstrap document.

If preparation is interrupted before a complete plan/journal exists, no live
write could have started. Stop, retain the private incomplete directory and
verify the three original script hashes plus bootstrap's exact post-V1 handoff.
An administrator may then archive that incomplete stage for evidence and repeat
preparation into the fixed fresh path. Do not run install or restore against
an incomplete/unapproved plan; no automatic deletion/cleanup is provided.

## 2. Apply exactly the independently approved plan

```bash
# NOT EXECUTED — never fill this by reading the plan's own digest as authority
: "${APPROVED_C5EA_PLAN_SHA256:?independently reviewed owner-approved plan SHA required}"
/root/miniconda3/bin/python3 -B "$PROCEDURE" install \
  --approved-plan-sha256 "$APPROVED_C5EA_PLAN_SHA256"
```

All four before-images and context must still match before the INSTALLING journal
is durably written. Each atomic copy accepts only its observed old SHA and fixed
owner/mode. The entry shell's hash check remains fail-closed while bindings are
partially installed. Success means `INSTALLED`, `services_restarted:false`, all
four after-images agree and owned Next/context checks passed. Repeating a
completed install checks the same state and returns `INSTALLED_VERIFIED_NOOP`.
No service interruption is intended; concurrent controlled publication is
excluded by the shared lease. A watchdog/probe may observe lock busy during this
short file operation. An interruption does not imply recovery succeeded.

Record the complete new handoff hash from the approved plan. **Only then** generate
and independently approve V2 policy/control records from those actual bytes.
Do not use the pre-patch handoff in V2 approval. Do not rerun V1 install/recovery
against a changed handoff and assume it is equivalent.

## 3. Restore a failed/partial patch before progressing

```bash
# NOT EXECUTED — same approved plan, same stage, before V2/Core progression
/root/miniconda3/bin/python3 -B "$PROCEDURE" restore \
  --approved-plan-sha256 "$APPROVED_C5EA_PLAN_SHA256"
```

INSTALLING cannot be blindly resumed with `install`; it explicitly requires
restore. Restore checks the same plan/context/lease and accepts each live file
only if it has that plan's known before or after hash, then restores the exact
four post-V1 before-images with compare-and-swap. Foreign bytes, an advanced Core
CURRENT, changed frontend state, or any begun V2 upgrade cause refusal without
fallback writes. Successful `RESTORED` verifies all before-images and owned Next;
repetition is `RESTORED_VERIFIED_NOOP`. PREPARED restore verifies the unchanged
baseline and closes only the private journal. Recovery never restores a database.

After restoring this separate patch, V1 `recover-install` may be considered only
under its own state-specific contract and authorization; the restored handoff is
exactly the post-V1 value expected by V1 recovery. Do not invoke the four-file
restore after V2 or Core application activation. At that phase use their
independently bound state models, not a historical handoff overwrite.

## Evidence and limits

Eight focused tests execute prepare, install/repeat, partial first-file failure,
restore/repeat, invalid approval, foreign drift, changed CURRENT, missing V1/V2
progress and a real flock conflict using disposable files and real R25Storage.
V1 metadata, owner IDs and Next status are explicit fixtures in these tests.
Separate c5ea recovery evidence executes real Node/selector/supervisor in a
namespace. No production installation, interrupted installation or rollback has
been accepted by these tests. This does not authorize executing the procedure.
