# Deploy repository transfer and exact release identities

The Deploy repository was transferred from `Hang-666-star/auralink-deploy` to
`bailangguihun/auralink-deploy` (GitHub repository ID `1322538022`). A required
controller correction now needs a new formal build. The unchanged release
workflow passes the actual `GITHUB_REPOSITORY` to the packager; its previous
single-name check would reject that build after the transfer.

The packager now creates new artifacts only for the exact current repository
`bailangguihun/auralink-deploy`. Verification accepts the two explicitly named
repositories so that historical artifacts remain verifiable. It still compares
the manifest's repository, release ref, commit, run and attempt with independently
supplied expected values. The two names are **not aliases**: a historical manifest
does not verify against the new repository identity, or vice versa. No case
folding, redirect lookup, basename matching or arbitrary-owner fallback exists.

The V2 controller-upgrade approval schema accepts these same two explicit Deploy
repository names. The complete private plan remains bound to the independently
approved SHA-256, including its exact repository spelling, source commit, formal
run/attempt, modules, old/new policies and preserved application state. Changing
only the repository still invalidates an existing approval digest. The operator
must verify the formal bundle manifest against the independently selected build
identity before importing it, as required by the existing installation contract.

Keep the historical manifest bytes and their recorded provenance unchanged. A
new Deploy build requires its own manifest, artifact hash, module bindings and
reviewed V2 policy/control records. This change does not relabel or rebuild the
already selected Core JAR. Core's historical repository identity and verifier
are unchanged, as are V1 equivalent-payload restrictions, installation write
sets, recovery journals, the shared R25/c5ea lock and c5ea lifecycle ownership.

Repository ownership does not grant an environment-review exemption. Existing
CODEOWNERS, rulesets, environment reviewers and workflow triggers are unchanged.
No new deployment launcher, privileged bypass or automatic production activation
is introduced. A successful formal controller build still means `NOT_DEPLOYED`.

Focused tests cover both exact repository identities, refusal of cross-name
verification, foreign repositories and wrong release/commit/run/attempt values,
and new-build refusal before writing output for a historical or foreign name.
The transferred-identity controller fixture executes actual storage/lease/CAS
upgrade, injected post-write verification failure, recovery and repeat behavior;
it confirms unchanged synthetic database/media bytes. Its process, SQL, asset
and HTTP boundaries remain explicit fixtures, not production acceptance.
