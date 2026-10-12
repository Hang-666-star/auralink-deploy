# Poetry transport without mount privileges

This correction is a review candidate, **not an installed production policy**.
It addresses a container where the operator and root Java share a mount namespace,
but `CAP_SYS_ADMIN` is absent from permitted/effective/bounding sets. A mount
command there returns permission denied; chmod is not a read-only filesystem.
The old `readonly-filesystem-capdrop` mode and its dedicated globally read-only
tmpfs requirements remain intact. There is no automatic fallback.

## Explicit coupled Core / Deploy contract

Core must include the `sealed-memfd-v1` adapter in `KnowledgeSnapshotService`.
An old JAR cannot be selected for this transport. The new JAR, payload, formal
release run/attempt and controller module bytes require their ordinary independent
review/binding; the previous accepted JAR must not be relabeled as the new build.

V2 retains its schema and `knowledge-read-v1` capability, but explicitly selects:

```json
{
  "installation.service.isolation": "sealed-memfd-capdrop",
  "upgrade.release_profile": "poetry-only",
  "upgrade.assets.sealed_owner": {
    "account": "ACTUAL_REVIEWED_EXISTING_NONROOT_ACCOUNT",
    "uid": "ACTUAL_NUMERIC_UID",
    "gid": "ACTUAL_SERVICE_GID"
  },
  "upgrade.configuration.knowledge.snapshot-transport": "sealed-memfd-v1"
}
```

This dotted presentation is explanatory, not executable policy. UID/GID must be
integers in the nested policy. The existing account must resolve to that nonzero
UID; do not create an account or copy a historical numeric UID to satisfy it.
The inode group is deliberately the service's observed GID, not an invented
primary group for the custodian. The asset custodian is a filesystem principal,
not a new human approval role. Its trust/descriptor-access assumptions must be
reviewed. `nobody` is not an automatic production choice.

The exact five configuration properties are the existing four poetry-only keys
plus `auralink.knowledge.snapshot-transport: sealed-memfd-v1`. `snapshot-root`
is the approved durable source root. Only the two existing graph/stats files,
manifest SHA, hashes, lengths, directory0550/file0440, declared ownership, no
symlinks/hardlinks/ACLs and traversal checks pass. No china file, extra descriptor
configuration, map-enabled combination or unknown transport is allowed. Hashes
and the full before/after configuration remain bound to the candidate.

The existing launcher, in its existing PID immediately before Java exec:

1. Validates the installed policy, candidate and complete durable pair. It reads
   each file through the existing descriptor-bound reader and verifies its SHA.
2. Requires descriptor slots198/199 to be unused, then creates two anonymous
   memfds. It copies only those verified bytes; no helper service is introduced.
3. Sets the explicitly bound different inode owner, service group and0440, then
   installs all four kernel seals: WRITE, GROW, SHRINK and SEAL. The anonymous
   objects are inherited as graph FD198 and statistics FD199.
4. Uses the original capability transition: all five capability sets zero,
   locked NOROOT securebit and NoNewPrivs=1. Any error terminates this launcher;
   there is no ordinary-directory fallback. Same PID/start ticks are retained.
5. Core opens only `/proc/self/fd/198` and `/proc/self/fd/199`, and applies its
   original byte limits, SHA and strict JSON/graph checks. It does not reread
   durable files or interpret arbitrary descriptor URLs. Core's anonymous-file
   shape check is not a claim to verify seals; that proof belongs to Deploy.

The coordinator independently opens the actual live process descriptors and
checks F_GET_SEALS, distinct anonymous regular inodes, declared UID/GID/0440,
lengths and complete hashes. It combines this with the existing process,
configuration, UID/groups, start ticks, zero-capability and NoNewPrivs checks.
A launcher message or JSON receipt cannot substitute the real kernel objects.

## Exact protection and limits

| Property | Sealed mode |
| --- | --- |
| Overwrite, truncate, grow, shared writable mmap, proc-fd alias write | Kernel content seals reject, even through an inherited writable descriptor. |
| Service chmod/chown to add write/execute permission | Different inode owner plus zero FOWNER/CHOWN capabilities rejects. The service group has read only. |
| Direct exec of those descriptors by the service | No execute bits, and service cannot add them. |
| Later durable-source replacement | Cannot change already sealed bytes; a restart revalidates source and rejects wrong hashes. |
| Global read-only or noexec filesystem | **Not provided or claimed.** There is no new mount. |
| Executable private mmap / trusted inode owner or privileged administrator changing metadata | Not a global prohibition. Known immutable JSON bytes are the protected object; this is not a general code-execution sandbox. |

The older tmpfs mount's `noexec` property is broader than this object transport.
In particular, content seals do not forbid `MAP_PRIVATE(PROT_EXEC)`. The JVM
already executes code; this proposal protects approved JSON byte identity and
prevents the Java service from editing/replacing or chmod-promoting these objects.
Do not advertise the two modes as identical filesystem isolation. A trusted
privileged administrator or a separately authorized custodian with a descriptor
remains outside the service's authority boundary. Do not expose/send the inherited
descriptors to an untrusted custodian process.

## Upgrade, restart and recovery

Review/merge both scoped source PRs through normal main rules, then use normal
Core/Deploy main-to-release promotion and non-deploying formal builds. Keep the
independent Core automatic publisher disabled. Bind the **new** exact bytes and
source identities; source-level unchanged-statistics evidence can be reused,
but old9e02 JAR integration is not evidence for a byte-different JAR.

Keep the completed V1 installation and pending four-file c5ea plan. This change
does not edit that plan or authorize its installation. The existing CODEOWNER
must still review its actual private before/after digest. Following that step,
prepare and independently review the V2 policy/control plan for the new modules,
new JAR, actual durable root, actual custodian and the five configuration keys.
Do not copy a synthetic test policy into production.

The same V2 upgrade and Core Publisher/Runtime activate the candidate. No mount
or platform privilege grant is needed for this mode. Missing/corrupt/unreadable
source, occupied FD slots, incomplete seals, wrong owner, privilege-transition
failure or bad actual runtime identity refuse before acceptance. A launch error
after application writes uses the existing transaction's recovery. The compatible
baseline continues its original launcher and filesystem configuration; it does
not need the new descriptors. No database restore/media deletion is involved.

On restart, the same launcher recreates and validates the sealed pair from the
approved durable files before exec. No tmpfs restoration is needed for this mode.
Loss/corruption of durable files still refuses launch and requires restoring the
exact externally retained pair under the original approval, not accepting new
hashes. Repeat/recovery decisions remain journal-based, not blind replay.

Core acceptance still checks authenticated statistics/Gallery eligibility,
711 unique nodes/609 relations, source hashes, no-map503, authentication and
media/public projection. Only after Core is accepted may the existing queued Web
run be approved by its real production environment reviewer. No duplicate Web
workflow or Next lifecycle owner is introduced.

## Evidence boundaries

`test_core_asset_sandbox.py` executes real Linux memfd operations and cross-exec
checks, while synthetic proc fixtures separately cover rejection branches.
`test_sealed_business.py` covers policy/config/source-binding and attestation
routing; CI traversal mocks are explicitly labeled. `test_business_transaction.py`
runs the real Publisher/CoreRuntime fixture state machine in the new mode,
including failure/recovery/repeat/rollback with synthetic DB state and stubbed
lifecycle/HTTP. Actual Java17/selected-JAR/PG integration is recorded separately;
none of these tests establish production activation or rollback acceptance.

Primary platform references:
[memfd and sealing](https://man7.org/linux/man-pages/man2/memfd_create.2.html),
[capabilities](https://man7.org/linux/man-pages/man7/capabilities.7.html),
[Landlock ABI limitations](https://www.kernel.org/doc/html/v6.6/userspace-api/landlock.html),
[memfd execution flags](https://www.kernel.org/doc/html/latest/userspace-api/mfd_noexec.html).
The actual target exposes Landlock ABI1, so a Landlock-only substitute cannot
supply the required truncate protection. Public AutoDL documentation does not
establish a supported live privileged tmpfs operation for this instance; that
remains an alternative provider inquiry, not assumed platform support.

Two additional isolated executions on 2026-10-12 used the exact local Core JAR
`a799f4af9d2b5702a732de1745d561b72c76288765fd89425e470e1eae5d07b8`
(69,633,154 bytes). This is a review-candidate artifact, not a formal release or
approval. The executed deployment source was bound to these byte identities:

| Module | SHA-256 |
| --- | --- |
| `core_business.py` | `79b4b4d81b59c98cade36dcf3cf28d39564a8a1627ce0eed90b84e4f7b0f5789` |
| `core_asset_sandbox.py` | `5acc36de303ea653e5394148a890986c3a722d19a24ddc32fcfcbd8b01957958` |
| `core_release_guard.py` | `31ca0d83f86fa7f1644b4f93cca2d1d5fab453a16dcb10bc69733a2e3c90175d` |
| `core_runtime.py` | `3e26b83fecb52f6b7f79116d47afbe58be6cda2f9627fcb51e559578e26269ec` |
| `publisher_transaction.py` | `ba94dafd94cb96e37bf79a7004ed3de00732136f6e586c14d63eef0b057cbe1d` |
| `r25_storage.py` | `c0eb0f7c07f725b7218782f20e5e68768e39bf971f654bdd632f4b681085332c` |

- **Root launcher / actual Java exec:** actual `prepare_sealed` passed two sealed
  objects to Java17 while retaining the same PID/start ticks. The exact JAR's
  snapshot implementation read the real 711-node/609-edge pair; the coordinator
  independently opened its live descriptors and verified seals, exact hashes,
  ownership, all capability sets zero and NNP=1. An isolated verifier restricted
  to the observed production capability mask `0xa80425fb` also succeeded, without
  `CAP_SYS_PTRACE`. After the service privilege drop, fchmod, fchown, pwrite,
  truncate and shared writable mmap returned EPERM; direct exec returned EACCES.
  Changing only the disposable durable copy did not change the live sealed data.
- **Actual Publisher / CoreRuntime / production Java launcher / PostgreSQL16:**
  disposable mount/network/PID namespaces exercised successful COMMITTED,
  repeated no-op, application RESTORED, shared-lock and foreign-PID refusals,
  and fresh-coordinator recovery after an abrupt exit immediately following the
  first real JAR replacement. Authenticated Knowledge acceptance observed six
  eligible synthetic paintings, two author names, the real 711/609 snapshot,
  correct hashes, one public-projection sample and authenticated disabled-map503.
  Tampered or missing durable assets refused preflight; restoring the complete
  approved pair permitted continuation. The before/after digests of **all 44
  fixture database tables** matched, including two users, two creations, one
  critic task, one workflow and private-media records. Four media files and all
  five application installation objects were preserved/restored. No model or
  Creation request was made.

The second run still used explicit paired c5ea/Guide/Critic/Tunnel/watchdog
adapters and synthetic approval/provenance records; it did not replay controller
installation or exercise production service peers. The separate Java exec run
does not establish HTTP authentication by itself; that was exercised by the
isolated transaction run. Neither execution is production activation or rollback
acceptance, and the synthetic UID is not a production ownership decision.

Git-external commands and receipts are retained under the existing workspace
`/home/bailangguihun/artlive-database-migration/evidence/release-install-20261012/`:
`sealed-root-java/{run.py,execution.json,result.json}`,
`sealed-pg-integration/{run.py,execution.json,result.json}`, and
`sealed-integration-summary.json`. Real snapshots, private runtime/configuration
and database contents are not committed. The required Core Maven build reported
34 cases: **27 executed, seven PostgreSQL tests skipped**, zero failures/errors;
the separate real PostgreSQL transaction above does not relabel those seven cases
as executed. Future byte-different JARs or controller modules require truthful
artifact rebinding and checks appropriate to their differences.
