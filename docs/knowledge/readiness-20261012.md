# Knowledge readiness decision — 2026-10-12

The three unmerged PR candidates are ready for owner review; the current complete
feature release is **not authorized or ready for production activation**. This
round performed one bounded read-only production observation and focused isolated
integration. It did not install controllers/assets, deploy, restart production,
change data, create accounts or submit provider/task/upload requests.

Related PRs: [Web #14](https://github.com/Hang-666-star/auralink-web/pull/14),
[Core #10](https://github.com/Hang-666-star/auralink-core-api/pull/10),
[Deploy #3](https://github.com/Hang-666-star/auralink-deploy/pull/3).
Web head remains `675d96d875000bb557772236ddedd6863df2f464`; Core head remains
`e65847f507e73dd6857e9c497861c647a8b2af9b`. Deploy started this review at
`4baca34735e2e690960e9170dbd9e850b0c8bfb3`; the PR's subsequent scoped fix contains
this report. See the PR checks for its exact current head and required CI.

## Review rules and concrete fixes

All three base branches were unchanged from the recorded starting commits. The
initial inspection found no reviews, comments or unresolved threads; absence of
feedback is not approval. Active rulesets require one Code Owner approval from
`Hang-666-star`, latest-push approval, dismissal of stale approvals, resolved
threads and strict required CI. Owner decisions remain pending. Feature pushes
and main-PR events do not deploy or invoke providers. Web release push deploys;
that event has not been triggered. No workflows/policies were changed.

The observed production registry is absent, exposing a concrete first-install
regression: `CoreRuntime.query` required POLICY before the first installer wrote
it. `BootstrapRuntime` now allows only the exact original handoff and paired
baseline JARs to enter the existing legacy query path before registration.
Registered installs still use strict policy dispatch; missing/corrupt policy does
not become a normal publisher fallback. Five focused tests cover valid bootstrap,
foreign handoff/JAR refusal, registered-policy refusal/dispatch and ordinary
runtime refusal.

A separate first-import guard refuses sibling bytecode before imports and legacy
PG helper caches before live/saved-engine loading. Three focused tests use real
stale bytecode and direct CLI invocation, including `-B`, prefix and symlink cases;
no marker code executes and unknown caches are retained. All eight pass. The
existing 14 CoreRuntime and four installer-fault tests also pass. These tests use
explicit lease/metadata/DB boundary mocks and are not real V1-install acceptance.

## New integration and reused PostgreSQL evidence

[Real integration](readiness-integration.md) and its
[sanitized receipt](readiness-integration-evidence.json) close the principal
artifact/process/filesystem/PG/HTTP gaps: actual60c5→550d upgrade, real lock and
foreign-process refusals, COMMITTED/no-op/rollback, abrupt exit after first JAR
replacement, fresh-coordinator recovery and repeated recovery. Five application
files, all44 public-table signatures, eleven retained tables and three media
files are preserved. The paired-service interfaces and production launcher/profile
remain explicit adapters; synthetic approvals are not authorization. User/task
fixture tables are empty. Actual controller install remains covered by separate
fault tests, not this Java harness. No production rollback is claimed.

Core CI run38206922984 executed17 Maven tests and skipped7 PostgreSQL tests under
its existing opt-in condition. Each skipped method has earlier actual isolated PG
execution at application source `a6875b63fafd4c8658d79f6ec040d08b7cad04ad`:

| PaintingStatisticsPostgresTest method | Actual prior duration | Scope |
| --- | ---: | --- |
| emptyCatalogStillReturnsEveryMetric | 0.188s | Empty population and unavailable metrics |
| matchesGalleryExactlyAndDeduplicatesCurrentRevisions | 0.612s | Gallery eligibility, current revision and deduplication |
| outputIsBoundedAndReportsTruncationWithoutChangingDenominator | 1.511s | Bounded50 output, full denominator65 |
| missingPendingAndConflictingAliasesAreNotCounted | 0.156s | Field-level missing/pending/alias conflicts |
| tenThousandSyntheticRecordsKeepExactCountsAndBoundedPublicProjection | 12.332s | 10000 paintings/266000 annotations; 7000 eligible/50 names |
| neverAggregatesHiddenFieldsOrLiteralZeroAndTracksCoverage | 0.527s | Private projection, literal0, coverage and mutation isolation |
| explicitUnknownsAreUnavailableAndUnmatchedSamplesStayVisible | 0.095s | Unknown/unmatched/unavailable rules |

Current Core head's421 Java/SQL/test/pom files match that source exactly. Original
Surefire XML SHA256 is
`256073750db779a03ddf7a05ec47486399e38e7b110bc74b4d199c16db876e96`;
original build-log SHA256 is
`bab3d574475ea2e3746159acb58bf83b9f2d10486272460ff72f07dbfa640cae`.
Each XML testcase has no skip/failure/error. Tests used independent temporary
schemas in the isolated PG; none needed a new run. The 10k method used jit=off;
prior1.585s warm-cache/single-concurrency HTTP timing is not production acceptance.

## Existing artifact identities

| Artifact | Identity | Evidence boundary |
| --- | --- | --- |
| Local Knowledge JAR | SHA256 `550d1bb9e71717226d5fc7645c94b6cb21234ecbfff44aa3fdae4f1f9c1a84d8`, 69632545bytes | Actual isolated PG/HTTP/browser and this real Java integration; app sourcea687 is unchanged in Core PR |
| Core CI JAR | SHA256 `d0e1e52200868fee41e6e5fef148b787c4b384b75f2a9183536c566d0bd9ea4f`, run38206922984/attempt1 | Distinct bytes;17 Maven/7PG skips and packaged verifier, not the local JAR's live integration |
| Core CI ZIP | artifact11727108903, SHA256 `e8870e8ed598204e950d5162968213e078b59cf4ea642f5e15789997ad3b1ff9` | API metadata confirms available; not redownloaded; PR synthetic merge tree equals Core head, not release identity |
| Web preview | BUILD_ID `ZTBFk3sN5MNNwckmM-GNR`; sourcea5e5 application unchanged in675d |83 tests, desktop/narrow UI; loopback API build, not production bundle |

All are PR candidates. Final source/run/attempt/artifact identities and private
approvals must be rebound after normal reviewed release promotion. This report
creates no signed release manifest and does not rebuild for timestamps.

## One bounded production observation

The reviewed probe used existing host-key-verified SSH, file/proc/listener reads,
four anonymous GETs and one BEGIN READ ONLY/ROLLBACK SELECT. No controller was
imported/called, no lock acquired, and no remote files/stages/configs were created.

- Running Java's open JAR and both installed copies matched `60c5b955…`; current
  Next release directory was `7ddeae4a2b21` and BUILD_ID `2Zes3anpWQ2FWv3_7E1ca`.
  The c5ea controller and existing shared lock selection were unchanged.
- Active PostgreSQL reported16.15 and V001–V013. The exact Gallery predicate was
  verified in the running JAR, and read-only SQL and actual GET both counted9553.
  Legitimate future changes must be preserved;9553 is not a fixed acceptance rule.
- Java uses root with capabilities. Native PostgreSQL configuration and credential
  ownership resolve to its separate installation account; never infer root:root
  pgpass ownership. PG listener did not disclose PID, so current PG OS UID was
  not independently attested. Critic policy file remains configured-provider;
  no provider was invoked.
- Original lifecycle/launcher/handoff/MANIFEST match V1 bootstrap inputs, but the
  Core publisher, release guard, POLICY and CURRENT do not exist. **V1 bootstrap
  is required before V2 upgrade.** Knowledge config is absent and the new class
  is absent from the current JAR;401 on anonymous new URLs is not baseline failure.
- Guide has the exact graph/stats but no map on writable XFS. Historical source has
  all three exact files with writable permissions. Neither is an approved V2
  asset installation. New durable bundle/version root/readonly tmpfs is required.

Full frontend sourceSHA, actual PG PID/UID, all legacy-helper caches, installation
space, complete retention/media window, acceptance session and production rollback
were not established. They belong to the explicitly authorized preparation/
activation window, not to a claim of completed production acceptance here.

## Explicit decisions and next actions

1. **Review owner — Hang-666-star:** review each latest PR head and CI. No agent can
   substitute approval or merge under this task.
2. **Authorized project/release operator — map decision:** the exact DataV/Gaode
   export remains permission-unresolved. [Aliyun](https://help.aliyun.com/zh/datav/datav-7-0/user-guide/datav-geoatlas-widgets/)
   describes learning/exchange and points rights questions to Gaode.
   [Gaode terms](https://lbs.amap.com/pages/terms/)3.3/3.5/4.12/7 and
   [service licensing](https://lbs.amap.com/pages/authorization/) do not establish
   this project's server hosting/authenticated GeoJSON redistribution permission.
   Use the official3.5 work-order channel or an existing applicable agreement for
   the exact hash, entity/audience, storage/API/display, term and attribution.
   Alternatively explicitly approve a licensed replacement, or statistics+graph
   with map unavailable. The latter requires a separately reviewed reduced
   capability/two-file manifest/expected503/no-map-bytes acceptance and UI reason;
   current V2 requires all three files and map200 and must not be bypassed.
3. **Asset administrator and R25:** review [assets.md](assets.md), choose a new
   durable source/version root, bind observed service/nativePG contracts and
   readonly tmpfs/capabilities, and record authorized reboot restoration. Files
   exist but are not installed for Knowledge; this round installs nothing.
4. **Release owner with R25/c5ea:** review the exact
   [NOT EXECUTED instructions](release-instructions.md), approve final identities,
   compatibility window and private evidence, then schedule V1 bootstrap→V2→Core
   acceptance→c5ea Web. Record actual Web releaseSHA/BUILD_ID separately from its
   previously reviewed compatible source. Refresh unresolved installation facts.
5. **c5ea owner:** identify the installed supported Web rollback command before
   authorization; it was not inspected here and no flag is invented. Application
   recovery uses the exact recorded Core transaction, compatible data window and
   baseline. No arbitrary old JAR, old DB restore, data/media deletion or huaniao
   reimport is permitted.

The local preview remains available and unchanged. Technical review preparation
is complete with explicit integration boundaries; map permission, human approval,
final release identities, asset delivery and production-stage checks remain
specific decisions/actions, not reasons to repeat migration implementation.
