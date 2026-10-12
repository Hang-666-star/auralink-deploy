# Git-external Knowledge assets: approved poetry-only first release

The user approved a first release without the geographic map. Geographic
statistics, their sample definitions, painting charts and all poetry interactions
remain. The frontend makes no map request. This is an explicit two-file release
profile, not a waiver for missing required files.

The authoritative manifest and read-only tool live in [Core #10](https://github.com/Hang-666-star/auralink-core-api/pull/10):
`docs/knowledge-assets-manifest.json` and `scripts/verify-knowledge-assets.py`.
The manifest is schemaVersion2, releaseProfile `poetry-only`; SHA-256
`4a11c993bb55f4e2b8cbafc1b42e10a869bff4879ab0e3c110a8d324cbd863a5`. Real runtime data remains outside Git.

| Required file | Bytes | SHA-256 |
| --- | ---: | --- |
| poetry-graph.json | 528422 | `899511b6b7d02e6ba515986db651c67b3702497d2031bdbb75029c34491da2c0` |
| poetry-stats.json | 20130 | `27e91284d28c05c9b7dde9fcb4181c713761d3c2eebf84816b45c9f7d9af7501` |

Inherited Web source revision: `aa1da07086696835de7c361886115e602a88c471`,
`public/data/`. The graph has711 unique nodes and609 edges, no dangling endpoints;
stats agree. Original GraphML remains missing, upstream extraction accuracy is not
verified, and this file snapshot is not PostgreSQL graph persistence or an
automatic extension of painting imports.

## Bound configuration and installation

V2 private policy requires `upgrade.release_profile: poetry-only` and exactly:

```yaml
auralink.knowledge.snapshot-root: /operator-selected/immutable-version-root
auralink.knowledge.graph-sha256: 899511b6b7d02e6ba515986db651c67b3702497d2031bdbb75029c34491da2c0
auralink.knowledge.stats-sha256: 27e91284d28c05c9b7dde9fcb4181c713761d3c2eebf84816b45c9f7d9af7501
auralink.knowledge.map-enabled: false
```

The path above is an example, not a selected production root. No `china-sha256`
property or map-permission evidence belongs in this profile. Policy, complete
configuration before/after digests, manifest SHA and `releaseProfile`, directory
file set and runtime acceptance must agree. Extra map files in the selected
release asset root are refused; historical private maps elsewhere are untouched.
Core's disabled route will not open a map even if one remains on disk. It returns
an authenticated JSON503 `KNOWLEDGE_SNAPSHOT_UNAVAILABLE` with message
“此版本未启用地理底图；地域统计仍可读取。”; anonymous access remains401.
A generic missing-file503 or a map200 does not pass no-map acceptance.

The following procedure is for a future separately authorized asset administrator,
not a publisher fallback. No production installation was executed.

1. Select a new immutable version root and a durable two-file source bundle
   outside Git, application releases and the runtime mount. Bind the actual
   asset owner and service UID/GID/groups from the installation contract. Native
   PostgreSQL/pgpass has a separate installation account; never assume root:root
   or copy a historical UID. Do not modify existing Guide/source files.
2. Prepare a complete new version offline. For the observed root Java lifecycle,
   use the supported `readonly-filesystem-capdrop` contract: a dedicated tmpfs
   mounted exactly at the approved version root, filesystem root `/`, with
   `nosuid,nodev,noexec`. Copy only the two poetry files, verify hashes/lengths,
   approved owner/group, files0440 and directory0550, then remount the **whole
   filesystem** read-only. Both mount and superblock must show ro. Read-only bind
   mounts, writable backing filesystems, nested mounts and extra files refuse.
3. Run the reviewed Core tool against the exact schemaVersion2 manifest;
   `--check-environment` additionally requires root, graph SHA, stats SHA and
   `AURALINK_KNOWLEDGE_MAP_ENABLED=false`, with no china SHA. This validates the
   supplied environment only, not the effective Spring configuration. Bind the
   actual four dotted properties and full application after-image in V2 policy.
4. The Core tool's `--require-read-only` remains strict non-root POSIX verification
   and intentionally refuses UID0. V2 instead proves the globally readonly tmpfs
   for root mode and, after launch, all five capability sets zero/NoNewPrivs=1.
   No guessed service identity or fixture receipt substitutes that observation.
5. Use the reviewed V1 bootstrap→V2→Core transaction, then c5ea Web. Core acceptance
   requires stats/poetry200, graph IDs/endpoints/hashes, geographic field coverage,
   Gallery denominator, public projection, anonymous401 and exact disabled map503.
   Private acceptance sessions remain existing authorized inputs, never generated
   or printed by the publisher.

## Required-asset failure and recovery

A missing/corrupt/incorrectly hashed/unreadable required poetry file still refuses
V2 preflight or owned launch. Core's lazy loader independently returns safe
JSON503 without paths; painting statistics remain separate. Restore the exact
reviewed graph/stats pair and permissions before retrying. No-map mode does not
ignore required-asset validation or waive SHA/permission/identity/approval checks.

For bad delivery, leave the running complete volume intact. Provision a complete
verified version offline and approve its configuration before a coordinated
switch; never remount the active volume rw to patch individual files. Preserve
the prior complete pair/bundle. Tmpfs is lost on reboot/unmount: authorized
restoration copies both approved files from the durable bundle, rechecks bytes,
owner/readability and whole-filesystem ro before business startup. If assets
cannot be proven, refuse startup and use the journal's freshly rechecked compatible
baseline/configuration. Do not restore a database, remove media, discard tasks or
reimport huaniao to make a compatibility hash pass.

Previous three-file OS permission evidence remains historical proof of unchanged
sandbox mechanisms. The current two-file tests/real-process integration are
identified separately in [validation](validation.md); neither is production
activation or rollback acceptance.

## Future map-enabled release only

The map license issue is **deferred, not granted**. The inherited map matches the
[DataV export](https://geo.datav.aliyun.com/areas_v3/bound/100000_full.json) except
one terminal newline. [Aliyun documentation](https://help.aliyun.com/zh/datav/datav-7-0/user-guide/datav-geoatlas-widgets/)
attributes it to Gaode with learning/exchange language. Existing
[Gaode terms](https://lbs.amap.com/pages/terms/) and
[technical-service agreement](https://lbs.amap.com/pages/authorization/) do not
establish this project's independent hosting/authenticated API distribution
permission; ECharts licensing or download availability does not supply it.

A future map release requires a separately approved exact asset/use permission or
a licensed replacement. The retained V2 `map-enabled` profile still requires
literal true, the additional china SHA, exact three-file schemaVersion2 manifest,
map-permission evidence hash and authenticated map200/hash verification. No-map
approvals cannot select that profile or be relabeled as permission. This release
neither packages, installs nor serves the private map.
