# Assistant launcher import failure and bounded controller correction

The first production AI publication of the Assistant source reached
`START_INTENT`. Its controlled Java subprocess failed before starting the JVM:
the source-bound `core_business.assistant_module()` loader executed
`assistant_release.py`, whose top-level import of `publisher_transaction.Refused`
required a sibling directory absent from the launcher's deliberately closed
Python search path. The same import prevented restarting the unchanged Core
during automatic AI recovery. This was a controller import defect, not a model,
database migration, application JAR, or attachment failure.

The AI transaction restored the previous source and started the owned Critic,
but remained `RECOVERY_REQUIRED`; it must not be described as restored. Core
publication and V014–V016 migration had not started. The previous Core JAR and
all production data remain the recovery baseline. The already installed
Assistant controller must not be relabeled as partially installed or V1.

## Source correction

`assistant_release.Refused` is now a local `RuntimeError` subclass, following
the existing standalone `core_business` validator. The module no longer needs
an ambient sibling import to reject invalid input. Validation conditions,
migration hashes, SQL, permissions, and database behavior are unchanged. A
fresh `python -I -B` regression exercises the real bound-source loader without
the publisher search path, including a poisoned ambient module, wrong source
hash, and incorrect permissions. No `PYTHONPATH`, cache injection, or permissive
import fallback is used.

## Recovery boundary

The ordinary successor installer deliberately refuses an unfinished AI
transaction, and its `recover` operation does not uninstall an `INSTALLED`
controller. Neither command is an authorization to rewrite the completed
installation journal. The narrowly scoped correction in the same reviewed
upgrader changes only the validator and its POLICY/HANDOFF hash bindings.

It requires a separately reviewed formal Deploy bundle and exact private
correction record. Existing owner/delegated review rules apply; this document
does not create approval or substitute CI for approval. The correction holds
the same R25/c5ea lock, checks the original installed-controller record and
current Core/AI transaction, proves that old AI source is restored and Java and
watchdog are absent, and preserves the owned Guide/Critic/Next processes.
Foreign changes, wrong phases, differing source, lost ownership, or a different
current release are refusals. Before-images and partial progress are retained;
the correction does not edit application transaction journals or launch any
service, execute SQL, change credentials, or touch data/media.

After the correction is verified, recovery still uses the existing command:

```bash
"$PY" -B "$R/operations/r25-publisher/ai_publish.py" recover \
  --transaction "$EXACT_FAILED_AI_TRANSACTION"
```

The executor must inspect that transaction's real phase and all correction
results first. This command restores the prior accepted AI/Core behavior and
supervision; publication is a separate subsequent action. An interrupted or
foreign correction is not a reason to replay AI publication or to restore an
old database. No Web environment approval is appropriate until AI and Core
acceptance has subsequently passed.

## Evidence limits

Temporary-filesystem tests exercise hashes, compare-and-swap writes, locking,
partial correction, and refusal cases. OS service observations in these tests
are explicit fixtures. Fresh-process import checks execute the real validator
loader, but are not a claim of production JVM recovery. Production recovery,
service interruption duration, and public acceptance must be recorded by the
release executor against the installed formal bytes.

The repair does not call the lifecycle's full `load()` while POLICY/HANDOFF may
be partially copied. It initializes only that loader's existing fixed frontend
selector, selection-reference, selection-hash and shared-lock bindings, then
delegates read-only status to the existing `Engine.frontend`. A regression uses
the retained lifecycle fixture's real initially unloaded Engine; selector
process observations and diagnostics remain explicit fixtures. This closes the
uninitialized-selector test gap, without claiming a real c5ea process ran in
that unit test.

## Exact repair record and commands

`R25_ASSISTANT_LAUNCHER_IMPORT_REPAIR_V1` is an incident-specific record, not a
new general installation capability. Prepare its private JSON without secrets
and review the actual diff under the existing owner/delegated process. Its
fields are closed and are validated by `validate_launcher_repair`:

- `deploy`: repository `bailangguihun/auralink-deploy`, ref
  `refs/heads/release`, the formal commit, run ID/attempt, ZIP hash, manifest
  hash and `upgrade_assistant_controller.py` hash. The formal ZIP must contain
  exactly the existing 25 controller files in the canonical packaging format.
- `installed_control`: original approval SHA-256 and exact `INSTALLED` journal
  SHA-256. Its approval, journal and active pointer remain unchanged.
- `current_release`: accepted Core commit, JAR and accepted-record hashes.
  `preserved` independently binds `release-jar`, `preview-jar`, `manifest` and
  `application`; the two live JARs must equal the accepted Core JAR.
- `ai`: the exact failed transaction
  `a540f3f722f13acaaebceb0c785af083` and hashes of its active pointer, journal,
  snapshot, current pointer and restored old source tree. The phase must remain
  `RECOVERY_REQUIRED` after the documented old-source restoration attempt.
- `services`: current owned Guide and Critic PID/start-tick pairs;
  `next_owner` is `c5ea`. Java and the watchdog must be absent. The before/after
  checks do not use historical PIDs as evidence of current ownership.
- `controller_owner`, `private_owner`: the existing installation's numeric
  owner pairs. They must match the installed contract; they are not permission
  to change service identities or file ownership.
- `files`: exactly `assistant_release.py`, `policy`, `handoff`, each with an
  exact `before_sha256` and `after_sha256`.
- `review_evidence_sha256`: the private evidence hash for this particular
  correction. A computed digest alone is not evidence of human approval.

The live targets, all using the existing private owner and mode `0600`, are:

1. `operations/r25-publisher/assistant_release.py`: only replace its single
   sibling `Refused` import with the standalone local exception definition.
2. `runtime/core-publications/POLICY.json`: change only the runtime hash for
   `assistant_release.py`, `upgrade.assistant.artifacts.deploy` (new formal
   repository/commit/ZIP identity), and
   `upgrade.assistant.review_evidence_sha256`. Every other value remains equal
   to the installed policy, including the accepted Core baseline and its
   recovery compatibility identity.
3. `runtime/handoff-control.env`: change only
   `R25_CORE_RELEASE_POLICY_SHA256` to the resulting policy hash.

This installs one corrected helper plus its metadata bindings. It does **not**
claim that the entire new controller bundle replaced the installed controller.
The existing accepted Core record and completed controller installation remain
historical, immutable evidence. The new formal upgrader executes from its
candidate bundle; this operation does not replace the live upgrader.

Place the reviewed plan and private review evidence at
`runtime/core-publications/LAUNCHER_IMPORT_REPAIR_APPROVAL.json` and
`runtime/core-publications/LAUNCHER_IMPORT_REPAIR_REVIEW.json`. They must use the
existing private owner and `0600`. Preserve all previous records. Place the
formal 25-file bundle, its ZIP/manifest, and the exact `POLICY.next.json` and
`HANDOFF.next.env` under
`operations/r25-controller-candidates/<formal-release-commit>/`.

The following commands are **NOT EXECUTED by this document**. Set
`REPAIR_DEPLOY_COMMIT` and `REPAIR_APPROVAL_SHA256` from the genuine reviewed
record and verified formal build; missing values are a stop condition.

```bash
R=/root/autodl-tmp/artlive-r25-native-pg16/handoff-production-20260923T062101Z
PY=/root/miniconda3/bin/python3.10
: "${REPAIR_DEPLOY_COMMIT:?verified formal release commit required}"
: "${REPAIR_APPROVAL_SHA256:?reviewed repair approval digest required}"
REPAIR_TOOL="$R/operations/r25-controller-candidates/$REPAIR_DEPLOY_COMMIT/upgrade_assistant_controller.py"
"$PY" -B "$REPAIR_TOOL" repair-launcher-import \
  --approval-sha256 "$REPAIR_APPROVAL_SHA256"
```

Expected result is `LAUNCHER_IMPORT_REPAIR_INSTALLED` and a new repair journal
at `runtime/core-publications/launcher-import-repairs/<approval-sha256>/journal.json`
with phase `INSTALLED`. The result reports no application restart, database
writes or AI transaction replay. Inspect the actual three after-hashes and
current process/transaction state before the subsequent AI recovery.

If copying began and failed, inspect that repair journal first. Only the
following command restores the correction's three metadata/code preimages;
it does not restore application data, start services, or resolve the AI
transaction:

```bash
"$PY" -B "$REPAIR_TOOL" recover-launcher-import \
  --approval-sha256 "$REPAIR_APPROVAL_SHA256"
```

`NOT_STARTED` recovery is refused. Foreign metadata or context drift is also a
refusal, never permission to overwrite it. Immutable before-images allow
interrupted pre-journal preparation to resume without replacing evidence.
Partial live installation requires explicit recovery. After `RESTORED`, the
same reviewed `repair-launcher-import` command can explicitly attempt the
correction again if its original context still matches. Repeating an already
verified `INSTALLED` correction is a checked no-op.

## Fresh launcher-policy read before application recovery

After the correction journal is `INSTALLED`, run a fresh isolated Python
process that verifies the unchanged launcher's guard identity, loads it from
those exact bytes, and invokes only its read-only `policy()` validation. Obtain
`INSTALLED_GUARD_SHA256`, `CONTROLLER_UID` and `CONTROLLER_GID` from the reviewed
installed policy; do not substitute the new bundle's identity or guessed owner.
The command deliberately excludes the publisher directory from `sys.path` and
does not launch Java, query SQL, invoke AI recovery, or contact any provider.

```bash
: "${INSTALLED_GUARD_SHA256:?installed guard hash required}"
: "${CONTROLLER_UID:?installed controller UID required}"
: "${CONTROLLER_GID:?installed controller GID required}"
"$PY" -I -B - "$R" "$INSTALLED_GUARD_SHA256" "$CONTROLLER_UID" "$CONTROLLER_GID" <<'PY'
import hashlib, os, pathlib, re, stat, sys, types
root = pathlib.Path(sys.argv[1])
expected = sys.argv[2]
assert re.fullmatch('[0-9a-f]{64}', expected)
path = root / 'operations/core_release_guard.py'
parent = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
try:
    for part in path.parts[1:-1]:
        child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
        os.close(parent)
        parent = child
    fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
    try:
        before = os.fstat(fd)
        assert stat.S_ISREG(before.st_mode) and before.st_nlink == 1
        assert (before.st_uid, before.st_gid, stat.S_IMODE(before.st_mode)) == (int(sys.argv[3]), int(sys.argv[4]), 0o700)
        assert before.st_size <= 1024 * 1024
        with os.fdopen(os.dup(fd), 'rb') as stream:
            raw = stream.read(1024 * 1024 + 1)
        after = os.fstat(fd)
        assert (before.st_size, before.st_mtime_ns, before.st_ctime_ns) == (after.st_size, after.st_mtime_ns, after.st_ctime_ns)
        assert len(raw) == before.st_size and hashlib.sha256(raw).hexdigest() == expected
    finally:
        os.close(fd)
finally:
    os.close(parent)
assert str(root / 'operations/r25-publisher') not in sys.path
assert 'publisher_transaction' not in sys.modules
module = types.ModuleType('core_release_guard')
module.__file__ = str(path)
sys.modules[module.__name__] = module
exec(compile(raw, str(path), 'exec'), module.__dict__)
policy = module.policy()
assert policy['upgrade']['capability'] == 'assistant-v1'
assert 'publisher_transaction' not in sys.modules
print('LAUNCHER_BOUND_POLICY_READONLY=PASS')
PY
```

A failure is a stop condition; record the exact error without adding import
paths or weakening hashes. A pass establishes that this bound policy/import
path works in a fresh interpreter, not that the JVM or public API has recovered.
Only then use the existing `ai_publish.py recover` for the exact failed
transaction, and record its real outcome before considering another publish.
