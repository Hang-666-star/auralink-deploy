# c5ea early Web publication recovery (candidate; not installed)

A failed or interrupted Web publication can leave `DEPLOY_INTENT` or
`DEPLOY_FAILED_OR_UNCERTAIN` before the serializer binds a new selection. The
installed recovery entry then calls `Commit.finish`, which expects new-pair
hashes and raises `KeyError: new_selection_sha`. A subsequent deploy is blocked
by the unfinished transition even when the old release remains healthy.

This exact failure was reproduced using the installed generic selection helper
in an isolated filesystem. Its nonsecret source is retained only as the test
fixture `r25/fixtures/web_selection_commit_baseline.py`. No environment file,
selection, private approval, runtime asset or production record is committed.

## Narrow repair and refusal model

`r25/web_selection_recovery_overlay.py` is an **offline exact-hash renderer**.
It accepts only these observed installed sources:

| File under c5ea `bin/` | Before SHA-256 | After SHA-256 |
|---|---|---|
| selection_commit.py | `25fe045b7de4d99bbe6b004c3961e3af1154b0cc765225d1272a6538d9c97cd4` | `f96d2f885d1c099a20bdef031e03a3debc81ad01e0ae29e40066a0309dc7fd3d` |
| serialized_deploy_web.py | `1963c48dc821b5a771e2ce74dfdc1c3c445383da1a4a5b3d507a9caf6614f70b` | `d00cfd26d2f39b84cc944effdb1c35c3cd4823b3fa86cc54a37e4d9e167eb3a5` |
| deploy-web.sh | `d6e8e522b85106790da3b5537a86330b305feef8caa2a4ced1c22739d79b8cdd` | `ab1335aa5a655b4891f73fa5f2702af71bf50f7e6bb20ec7593ab01fe530d17e` |

The helper's early-state recovery validates stage ownership/mode, journal path
bindings, exact stage contents, saved old hashes/reference, and **unchanged live
old selection/reference**. It then calls the unchanged selector's owned-runtime
`status` under the serializer's existing shared exclusive lease. The selector
also validates the current link, release/build, supervisor state and actual
process identity. Only after all checks succeed does it write the journal's
terminal `BASELINE_RETAINED` state. Repetition repeats those checks without a
journal write. There is no selection/reference, PID, service, data or media write.

The serializer permits this new terminal state alongside `COMMITTED`. All other
serializer bytes remain unchanged, including its shared-lock behavior and hash
bound retained inner deployer. The entry shell's serializer digest is rebound.
The c5ea supervisor remains the sole Next owner. No second launcher is introduced.

`BASELINE_CAPTURED`, `DEPLOY_INTENT`, and `DEPLOY_FAILED_OR_UNCERTAIN` are eligible
only when the old runtime is still verified. The retained inner deployer's own
successful automatic rollback can satisfy this condition; its exit code alone
cannot. Missing/dead/foreign processes, a changed current link or live pair,
unbound new files, atomic-write remnants, invalid hashes, and unknown states
**refuse without repair or deploy replay**. PREPARED/CONFIG_INSTALLED/COMMITTED
continue through the existing new-pair path and its owned-new-runtime check.

If a candidate already owns the listener while no new pair was durably bound,
this repair deliberately does not infer success or select the old runtime. The
c5ea owner must reconcile that exact stage and identities through a separately
reviewed plan. An absent process is not permission to adopt an arbitrary PID.
This is not a generic application rollback command.

## Offline preparation (no production writes)

After source review, with read-only copies of the three exact installed files:

```bash
python3 -B r25/web_selection_recovery_overlay.py \
  --source-directory /absolute/private/observed-c5ea-bin \
  --output-directory /absolute/private/new-web-recovery-candidate
```

The output directory must be new. The renderer emits three scripts plus
`web-recovery-candidate.json`, recording every before/after digest and required
handoff binding. It neither executes nor installs them. It refuses unreviewed
bytes; there is no force/skip-hash option. Review the complete rendered diff.

## Coordinated installation boundary — NOT EXECUTED

This candidate needs owner review and separate installation authorization. It is
not part of the current 19-file Core controller ZIP; do not assume Core controller
installation applies it. The verified site has root:root0700 for these three
c5ea scripts and root:root0600 for the R25 handoff. Preserve those observed
identities; recheck them in the authorized window.

Order: **complete reviewed V1 first installation → install this separately
reviewed c5ea recovery patch under the same R25/c5ea lease → construct/approve V2
records from the resulting actual handoff → V2 upgrade → Core → c5ea Web**.

Do not apply the patch before V1: V1 bootstrap requires the exact old handoff
hash. Do not apply it after the Core application transaction: changing its
snapshotted handoff would invalidate Core recovery after-images. V1's normal
`core_release_guard.policy()` dynamically binds the policy SHA and application
configuration; the c5ea helper hash can change without changing that V1 policy.
The whole post-patch handoff SHA must be recorded for V2 approval; it is not
invented here because V1 is not yet installed.

The executable, separately authorized [four-file installation/recovery procedure](web-recovery-installation.md) acquires the existing
`/root/autodl-tmp/auralink-web-deploy/runtime/frontend-deployment.lock`, verify its
open inode, confirm no active Core/AI/controller/Web transaction, retain exact
backups of the **three files plus complete post-V1 handoff**, and bind all four
before/after hashes. Change only the handoff's existing
`R25_FRONTEND_COMMIT_HELPER_SHA256` from old to new helper SHA. Preserve every other
handoff byte and policy binding. Do not invent a production approval or run the
normal publication concurrently. No PID or process restart is required.

After installation, check all three script hashes/modes, the entry's serializer
binding, the handoff helper binding, unchanged Java/Next identities and owned
selector status. Stop on disagreement. No partial result may be called installed.
A partial four-file patch must be restored to its exact **post-V1** backups under
the same lease, accepting only the recorded before/after bytes and refusing
foreign drift, before any Core operation. If V1 itself later requires
`recover-install`, first restore this c5ea patch's post-V1 handoff baseline;
otherwise V1 correctly refuses a foreign handoff. Do not erase journals or
substitute a pre-V1 handoff into the installed V1 controller.

Only once installed and approved, the existing interface remains:

```bash
# NOT EXECUTED — actual c5ea stage and separate operator authorization required
/root/autodl-tmp/auralink-web-deploy/bin/deploy-web.sh recover-selection \
  /root/autodl-tmp/auralink-web-deploy/runtime/frontend-selection-transition-RECORDED_ID
```

A successful terminal journal must be `BASELINE_RETAINED` for the early path or
`COMMITTED` for the existing prepared path. The generic console word
`SELECTION_RECONCILED` alone is not production acceptance. Stop if the recorded
stage differs, the lock is owned, or status refuses. A normal committed Web
rollback uses a reviewed compatible source promotion through c5ea; it is not
performed by this helper.

## Validation and limits

- 13 focused tests: actual original missing-new-hash failure, early phases,
  repeated check/no-op, malformed/changed pairs, stage contamination, failed
  owned-runtime callback, prior prepared flow, exact renderer identity and
  byte preservation. CI uses real disposable files with synthetic UID/c5ea
  boundaries; those tests do not claim real process ownership.
- Separately executed isolated user/mount/network/PID namespace with the actual
  rendered helper, installed selector, installed diagnostics and unchanged c5ea
  supervisor. Real Node22.23.2 serves the selected production-API Web candidate,
  BUILD_ID `UFp1G1lBAeDa80YUnnakx`, on isolated19083. Three early phases and repeated
  recovery retained the same supervisor/Node PID/start-ticks and exact pair;
  stopped runtime refused with `owned_supervisor_status_75`, journal unchanged.
  Receipt: `web-selection-recovery-evidence.json`.
- Actual inner deployment/build/rollback was not replayed; three-file installation
  and four-file interruption recovery remain a separately reviewed installation
  plan. The namespace test does not establish production recovery or rollout. The separate one-off installation procedure has eight real-filesystem fixture tests (including injected partial installation and strict restoration); service/production records in those eight tests are synthetic.
- Related accepted UI: Web #15; Core #10 and Deploy #3 provide the existing
  no-map migration. This repair does not change application UI, API, data or
  deployment ownership. A concurrent Core launcher import fix is a separate PR.
