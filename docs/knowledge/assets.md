# Git-external Knowledge assets and recovery

Authoritative manifest and validator are in reviewed [Core #10](https://github.com/Hang-666-star/auralink-core-api/pull/10),
head `e65847f507e73dd6857e9c497861c647a8b2af9b`:
[manifest](https://github.com/Hang-666-star/auralink-core-api/blob/e65847f507e73dd6857e9c497861c647a8b2af9b/docs/knowledge-assets-manifest.json),
[verification tool](https://github.com/Hang-666-star/auralink-core-api/blob/e65847f507e73dd6857e9c497861c647a8b2af9b/scripts/verify-knowledge-assets.py),
[provenance](https://github.com/Hang-666-star/auralink-core-api/blob/e65847f507e73dd6857e9c497861c647a8b2af9b/docs/knowledge-map-provenance.md).
The manifest SHA-256 is `f8892ca72c911ec074f87346fb2ffea696895ba10aad999adff2d88503cc5674`.
Only this metadata belongs in Git; the real bundle does not.

| File | Bytes | SHA-256 |
| --- | ---: | --- |
| poetry-graph.json | 528422 | `899511b6b7d02e6ba515986db651c67b3702497d2031bdbb75029c34491da2c0` |
| poetry-stats.json | 20130 | `27e91284d28c05c9b7dde9fcb4181c713761d3c2eebf84816b45c9f7d9af7501` |
| china.json | 582521 | `206cf7fd5acba4bb08d9586899acc144cea2b29d9e93ff70f93895c5e5ffde77` |

Inherited Web source revision: `aa1da07086696835de7c361886115e602a88c471`,
`public/data/`. Graph: 711 unique nodes/609 edges, no dangling endpoints;
map: 35 features. The original GraphML is still missing. This snapshot is not
PostgreSQL graph storage, verified extraction knowledge, or an automatic extension
of the completed painting imports.

## Installation inputs and procedure

This is a procedure for a future separately authorized asset administrator.
The publisher checks and selects files; it does not create mounts, copy assets,
remount writable, download data, or repair files. No production command was run.

1. Resolve the map permission condition below. Select a new immutable version
   root from the actual installation contract, outside Git and release artifacts.
   Record actual asset owner, application account/UID/GID/groups, native DB
   credential owner, mount capabilities and effective JVM configuration. Do not
   infer pgpass ownership from root or from the asset owner.
2. Retain a durable verified three-file source bundle outside the runtime mount,
   with administrator-controlled access. Prepare a complete new version; never
   overwrite an online graph/stats pair. For the existing root Java lifecycle,
   the supported mode is `readonly-filesystem-capdrop`: mount a dedicated tmpfs
   exactly at the approved version root, with `nosuid,nodev,noexec`. Copy the three
   files while offline, verify their hashes/lengths, set approved owner/group,
   files `0440` and directory `0550`, then remount the **entire filesystem** `ro`.
   Ordinary read-only bind mounts and image/disk-backed filesystems are refused
   by this initial contract. Mountinfo must show root `/`, filesystem `tmpfs`,
   and both mount/superblock `ro` flags. Reject nested mounts or extra files.
3. Bind the root and the three SHA-256 values to the four exact Knowledge
   properties in the private policy/application after-image. Bind the manifest
   itself by SHA. Verify the original Core tool with `--check-environment` for
   bytes/configuration; check only the selected environment keys, never print
   secrets or source a production env into a development shell.
4. For a non-root compatible installation, the original tool's
   `--require-read-only` checks service read/traverse without write, including
   ancestors. **That flag intentionally rejects UID0 and is not weakened.** For
   the explicit root mode, the new Deploy asset/sandbox checks instead require
   the globally read-only tmpfs and then observe the actual launched Java with
   all five capability sets zero and NoNewPrivs=1. A preflight filesystem result
   alone does not claim the candidate process has already dropped capabilities.
5. Use the approved Core transaction to switch JAR/configuration; require real
   authenticated HTTP acceptance before CURRENT. The publisher's private session
   is separately provisioned; no login/token issuance occurs in the publisher.

The isolated procedure exercised actual Linux mounts, OS ownership, service
readability and kernel write refusals, plus same-JVM restore behavior. Its chosen
fixture accounts/UIDs are not production configuration recommendations.

## Failure and recovery

Application loaders return JSON503 `KNOWLEDGE_SNAPSHOT_UNAVAILABLE` for absent,
unconfigured, corrupt, inconsistent or unreadable assets without internal paths.
The graph and map fail independently and remain retryable. The release acceptance
must refuse an unavailable required asset rather than describe partial readiness
as a complete Knowledge release. Unexpected configuration parameters remain400;
anonymous Knowledge requests remain401.

For a bad delivery, leave the running complete volume intact. Provision a new
complete, verified version offline and obtain approval for its configuration
identity before a coordinated switch. Never remount an active asset volume rw to
patch files one by one. Retain the prior complete volume/bundle for recovery.

Tmpfs contents disappear on reboot/unmount. Re-provision the same approved bytes
from the durable external bundle, verify the manifest, ownership and global ro
mount before starting the business candidate. If that cannot be proven, startup
refuses; recover using the journal's freshly rechecked compatible baseline. Do
not disable hashes or restore/delete database/media data to make recovery pass.

## Exact map permission remains unresolved

The inherited map matches the official
[DataV export](https://geo.datav.aliyun.com/areas_v3/bound/100000_full.json)
except for one terminal newline. Download availability is not a redistribution
license. [Aliyun GeoAtlas documentation](https://help.aliyun.com/zh/datav/datav-7-0/user-guide/datav-geoatlas-widgets/)
attributes the data to Gaode and limits the stated use to learning/exchange.
The current [Gaode terms](https://lbs.amap.com/pages/terms/) and
[technical-service licensing agreement](https://lbs.amap.com/pages/authorization/)
do not establish ArtLIVE's permission to store and rehost these exact bytes via
an authenticated GeoJSON API. An ECharts license or ordinary API purchase does
not establish that permission either.

An authorized owner must provide an applicable existing agreement or obtain
rights-holder confirmation covering the exact SHA, deployment entity/audience,
server storage, API redistribution, geography display, term and attribution/map
review requirements. Store the actual agreement privately and bind its approved
reference. If permission cannot be obtained, a separately approved licensed-map
migration is an option. This PR neither removes/replaces the map nor publishes it.
