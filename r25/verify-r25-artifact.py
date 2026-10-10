#!/usr/bin/env python3
"""Fail CI if a build loses accepted packaged R25 resources/security guards."""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile

PROFILE_HASHES = {
    "application-catalog-postgres-real-r24-rehearsal.yml": "08cb1a2466cc730f4784fe534866fa4a88b6f01da81be3ab99cd1638808f978e",
    "application-catalog-postgres-restore-rehearsal.yml": "958bbbfeae839c7b69e94b17d76e9603f7711bb3e56d1fa880f52d6107757ec4",
    "application-catalog-postgres-user-favorites-integration.yml": "1ddda0ef1ea5f20fbd8a1c37b6c84cbad38cac11ca28894b418d38dff1b577cf",
    "application-catalog-postgres-creation-integration.yml": "864a17b98639883ea15bdec28ef125e822ae2aa2fe7c88725b2ed5427ef4a712",
    "application-catalog-postgres-critic-assets-integration.yml": "0882869c9c6751a5bbf293eb98fbd41c7470d7a772634e76436ce62397d3261b",
    "application-catalog-postgres-cutover-readonly.yml": "8628d30326738d71853791ea12fc3bbe22a6e0459aa7be2ecbf4f4f3cee4e866",
    "application-catalog-postgres-integration.yml": "8dbab037b6ad74c014e29b9796e4ae381bf87cfa799dbc3d78290f9264543639",
    "application-catalog-postgres-guide-integration.yml": "7475790d4f5ce7be81fa33eb5b7592e3c16c552cb44b34c1dffb6641ccd3fea0",
    "application-catalog-postgres-restore-rehearsal-v2.yml": "841f5b9e056e3440f75052df7fe88383a732b66ada0341b972660cc6d7c3abce",
    "application-catalog-postgres-real-r24-restore.yml": "0c4469ab9b7ceef8fecf8e939b4cd973fa0ea0310b37fd538d6d4f46c91b1331",
    "application-catalog-postgres-production.yml": "ce7cb06da572f6ea47e3aaa8496db34f0a1a10ae776327677914fb3d1438b838",
}

def verify(jar):
    with zipfile.ZipFile(jar) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise ValueError("duplicate archive members")
        for name in names:
            if name.startswith("/") or ".." in Path(name).parts:
                raise ValueError("unsafe archive member")
        profiles = {}
        for name, expected in PROFILE_HASHES.items():
            actual = hashlib.sha256(archive.read("BOOT-INF/classes/" + name)).hexdigest()
            if actual != expected:
                raise ValueError("production profile identity mismatch: " + name)
            profiles[name] = actual
        requirements = {
            "com/auralink/security/SecurityConfig.class": [b"dispatcherTypeMatchers", b"jakarta/servlet/DispatcherType", b"ERROR"],
            "com/auralink/api/v1/error/ApiV1ExceptionHandler.class": [b"APPLICATION_JSON", b"contentType"],
            "com/auralink/service/painting/PaintingQueryService.class": [b"explicitlyNonPublic", b"source.original_sequence", b"source.original_image_reference"],
        }
        for path, constants in requirements.items():
            contents = archive.read("BOOT-INF/classes/" + path)
            if any(value not in contents for value in constants):
                raise ValueError("accepted class contract missing: " + path)
        if not any(name.startswith("BOOT-INF/lib/postgresql-") and name.endswith(".jar") for name in names):
            raise ValueError("PostgreSQL runtime driver missing")
    result = hashlib.sha256()
    with jar.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
    digest = result.hexdigest()
    return {"status": "PASS", "jar_sha256": digest, "jar_bytes": jar.stat().st_size,
            "profile_count": len(profiles), "profiles": profiles,
            "scope": "packaged resource and bytecode contracts; not an HTTP/PG acceptance claim"}

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("jar", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = json.dumps(verify(args.jar), ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.write_text(report, encoding="utf-8")
    print(report, end="")

