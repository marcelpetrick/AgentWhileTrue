#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Marcel Petrick
# SPDX-License-Identifier: GPL-3.0-or-later
"""Generate deterministic release SBOMs from a wheel and source distribution.

The inventory covers the installable project's runtime dependency graph and the
two release artifacts. Build and development environments are outside its scope.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tarfile
import zipfile
from datetime import UTC, datetime
from email import policy
from email.parser import BytesParser
from pathlib import Path
from typing import Any

PROJECT_NAME = "agent-while-true"
LICENSE = "GPL-3.0-or-later"
SUPPLIER = "Person: Marcel Petrick"
REPOSITORY = "https://github.com/marcelpetrick/AgentWhileTrue"
HEX_256 = re.compile(r"^[0-9a-f]{64}$")
DEV_EXTRA_MARKER = re.compile(r"^(?P<open>\(*)extra==(?P<quote>['\"])dev(?P=quote)(?P<close>\)*)$")
EXACT_REQUIREMENT = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9._-]*"
    r"(?:\[[A-Za-z0-9._-]+(?:,[A-Za-z0-9._-]+)*\])?"
    r"==[A-Za-z0-9][A-Za-z0-9.*+!_-]*$"
)


class SbomError(ValueError):
    """Raised when artifacts or generated documents are inconsistent."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _sha1(path: Path) -> str:
    digest = hashlib.sha1()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _metadata(path: Path) -> tuple[Any, int]:
    try:
        if path.suffix == ".whl":
            with zipfile.ZipFile(path) as archive:
                names = [
                    name for name in archive.namelist() if name.endswith(".dist-info/METADATA")
                ]
                if len(names) != 1:
                    raise SbomError(f"{path}: expected exactly one wheel METADATA file")
                payload = archive.read(names[0])
                timestamps = [
                    int(datetime(*item.date_time, tzinfo=UTC).timestamp())
                    for item in archive.infolist()
                ]
                artifact_time = max(timestamps)
        elif path.name.endswith(".tar.gz"):
            with tarfile.open(path, "r:gz") as archive:
                members = [
                    item
                    for item in archive.getmembers()
                    if item.name.count("/") == 1 and item.name.endswith("/PKG-INFO")
                ]
                if len(members) != 1:
                    raise SbomError(f"{path}: expected exactly one top-level PKG-INFO file")
                extracted = archive.extractfile(members[0])
                if extracted is None:
                    raise SbomError(f"{path}: could not read PKG-INFO")
                payload = extracted.read()
                artifact_time = int(max(item.mtime for item in archive.getmembers()))
        else:
            raise SbomError(f"unsupported artifact type: {path}")
    except (OSError, tarfile.TarError, zipfile.BadZipFile) as error:
        raise SbomError(f"cannot read {path}: {error}") from error
    return BytesParser(policy=policy.default).parsebytes(payload), artifact_time


def _is_dev_extra_requirement(requirement: str) -> bool:
    """Accept only a dependency guarded solely by the project's dev extra."""
    package, separator, marker = requirement.partition(";")
    if not separator:
        return False
    match = DEV_EXTRA_MARKER.fullmatch("".join(marker.split()))
    return bool(
        EXACT_REQUIREMENT.fullmatch(package.strip())
        and match
        and len(match["open"]) == len(match["close"])
    )


def inspect_artifacts(wheel: Path, sdist: Path) -> dict[str, Any]:
    """Verify release artifacts and return normalized provenance."""
    if not wheel.is_file() or not sdist.is_file():
        missing = [str(path) for path in (wheel, sdist) if not path.is_file()]
        raise SbomError(f"missing release artifact(s): {', '.join(missing)}")
    inspected = []
    versions: set[str] = set()
    times = []
    for kind, path in (("wheel", wheel), ("sdist", sdist)):
        metadata, artifact_time = _metadata(path)
        name = str(metadata.get("Name", ""))
        version = str(metadata.get("Version", ""))
        if name.lower().replace("_", "-") != PROJECT_NAME:
            raise SbomError(f"{path}: unexpected project name {name!r}")
        if not version:
            raise SbomError(f"{path}: missing project version")
        license_expression = str(metadata.get("License-Expression", ""))
        if license_expression != LICENSE:
            raise SbomError(
                f"{path}: expected License-Expression {LICENSE!r}, got {license_expression!r}"
            )
        runtime = []
        for requirement in metadata.get_all("Requires-Dist", []):
            # Optional extras are deliberately not part of this runtime SBOM.
            if not _is_dev_extra_requirement(requirement):
                runtime.append(requirement)
        if runtime:
            raise SbomError(f"{path}: unsupported runtime dependencies: {', '.join(runtime)}")
        versions.add(version)
        times.append(artifact_time)
        inspected.append(
            {
                "kind": kind,
                "name": path.name,
                "path": path,
                "sha1": _sha1(path),
                "sha256": _sha256(path),
            }
        )
    if len(versions) != 1:
        raise SbomError(f"artifact versions do not match: {', '.join(sorted(versions))}")
    epoch_text = os.environ.get("SOURCE_DATE_EPOCH")
    created_epoch = int(epoch_text) if epoch_text is not None else max(times)
    created = datetime.fromtimestamp(created_epoch, UTC).replace(microsecond=0)
    return {"version": versions.pop(), "artifacts": inspected, "created": created}


def make_documents(provenance: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Create SPDX 2.3 and CycloneDX 1.6 JSON documents."""
    version = provenance["version"]
    artifacts = provenance["artifacts"]
    created = provenance["created"].isoformat().replace("+00:00", "Z")
    purl = f"pkg:pypi/{PROJECT_NAME}@{version}"
    sdist_name = next(item["name"] for item in artifacts if item["kind"] == "sdist")
    release_base = f"{REPOSITORY}/releases/download/agentwhiletrue-v{version}"
    fingerprint = hashlib.sha256("".join(item["sha256"] for item in artifacts).encode()).hexdigest()
    spdx_files = []
    relationships = [
        {
            "spdxElementId": "SPDXRef-DOCUMENT",
            "relationshipType": "DESCRIBES",
            "relatedSpdxElement": "SPDXRef-Package",
        }
    ]
    for item in artifacts:
        file_id = f"SPDXRef-Artifact-{item['kind']}"
        spdx_files.append(
            {
                "SPDXID": file_id,
                "fileName": f"./{item['name']}",
                "checksums": [
                    {"algorithm": "SHA1", "checksumValue": item["sha1"]},
                    {"algorithm": "SHA256", "checksumValue": item["sha256"]},
                ],
                "licenseConcluded": "NOASSERTION",
                "licenseInfoInFiles": ["NOASSERTION"],
                "copyrightText": "NOASSERTION",
            }
        )
        relationships.append(
            {
                "spdxElementId": "SPDXRef-DOCUMENT",
                "relationshipType": "DESCRIBES",
                "relatedSpdxElement": file_id,
            }
        )
    spdx = {
        "spdxVersion": "SPDX-2.3",
        "dataLicense": "CC0-1.0",
        "SPDXID": "SPDXRef-DOCUMENT",
        "name": f"{PROJECT_NAME}-{version}-release",
        "documentNamespace": f"{REPOSITORY}/sbom/{version}/{fingerprint}",
        "creationInfo": {"created": created, "creators": ["Tool: AgentWhileTrue scripts/sbom.py"]},
        "documentDescribes": ["SPDXRef-Package"],
        "packages": [
            {
                "name": PROJECT_NAME,
                "SPDXID": "SPDXRef-Package",
                "versionInfo": version,
                "downloadLocation": f"{release_base}/{sdist_name}",
                "filesAnalyzed": False,
                "licenseConcluded": LICENSE,
                "licenseDeclared": LICENSE,
                "copyrightText": "Copyright (C) Marcel Petrick",
                "supplier": SUPPLIER,
                "externalRefs": [
                    {
                        "referenceCategory": "PACKAGE-MANAGER",
                        "referenceType": "purl",
                        "referenceLocator": purl,
                    }
                ],
            }
        ],
        "files": spdx_files,
        "relationships": relationships,
        "annotations": [
            {
                "annotationDate": created,
                "annotationType": "OTHER",
                "annotator": "Tool: AgentWhileTrue scripts/sbom.py",
                "comment": (
                    "Scope: project runtime dependencies and built release artifacts; build and "
                    "development environments are excluded. No runtime dependencies are declared."
                ),
            }
        ],
    }
    references = [
        {
            "type": "distribution",
            "url": f"{release_base}/{item['name']}",
            "comment": f"Built {item['kind']} release artifact",
            "hashes": [{"alg": "SHA-256", "content": item["sha256"]}],
        }
        for item in artifacts
    ]
    cyclonedx = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.6",
        "serialNumber": (
            f"urn:uuid:{fingerprint[:8]}-{fingerprint[8:12]}-4{fingerprint[13:16]}-"
            f"a{fingerprint[17:20]}-{fingerprint[20:32]}"
        ),
        "version": 1,
        "metadata": {
            "timestamp": created,
            "tools": {
                "components": [
                    {
                        "type": "application",
                        "name": "AgentWhileTrue SBOM generator",
                        "version": version,
                    }
                ]
            },
            "component": {
                "type": "application",
                "bom-ref": purl,
                "name": PROJECT_NAME,
                "version": version,
                "purl": purl,
                "licenses": [{"license": {"id": LICENSE}}],
                "supplier": {"name": "Marcel Petrick"},
                "externalReferences": references,
                "properties": [
                    {
                        "name": "agentwhiletrue:sbom:scope",
                        "value": "runtime-dependencies-and-release-artifacts",
                    },
                    {
                        "name": "agentwhiletrue:sbom:excluded",
                        "value": "build-and-development-environments",
                    },
                ],
            },
        },
        "dependencies": [{"ref": purl, "dependsOn": []}],
    }
    return spdx, cyclonedx


def validate_documents(spdx: Any, cyclonedx: Any) -> None:
    """Check cross-document invariants before writing or accepting SBOMs."""
    if not isinstance(spdx, dict) or spdx.get("spdxVersion") != "SPDX-2.3":
        raise SbomError("malformed SPDX document")
    if (
        not isinstance(cyclonedx, dict)
        or cyclonedx.get("bomFormat") != "CycloneDX"
        or cyclonedx.get("specVersion") != "1.6"
    ):
        raise SbomError("malformed CycloneDX document")
    try:
        package = spdx["packages"][0]
        component = cyclonedx["metadata"]["component"]
        version = package["versionInfo"]
        if version != component["version"] or package["name"] != component["name"]:
            raise SbomError("SBOM project identities do not match")
        if (
            package["licenseDeclared"] != LICENSE
            or component["licenses"][0]["license"]["id"] != LICENSE
        ):
            raise SbomError("SBOM license is missing or incorrect")
        spdx_hashes = {
            entry["fileName"][2:]: next(
                check["checksumValue"]
                for check in entry["checksums"]
                if check["algorithm"] == "SHA256"
            )
            for entry in spdx["files"]
        }
        cdx_hashes = {
            Path(entry["url"]).name: entry["hashes"][0]["content"]
            for entry in component["externalReferences"]
            if entry["type"] == "distribution"
        }
    except (KeyError, IndexError, StopIteration, TypeError) as error:
        raise SbomError("malformed SBOM content") from error
    if (
        spdx_hashes != cdx_hashes
        or len(spdx_hashes) != 2
        or not all(HEX_256.fullmatch(value) for value in spdx_hashes.values())
    ):
        raise SbomError("artifact provenance is missing or inconsistent")


def validate_with_standard_tools(spdx_path: Path, cyclonedx_path: Path) -> None:
    """Validate with maintained implementations and their bundled schemas."""
    try:
        from cyclonedx.schema import SchemaVersion
        from cyclonedx.validation.json import JsonStrictValidator
        from spdx_tools.spdx.parser.parse_anything import parse_file
        from spdx_tools.spdx.validation.document_validator import validate_full_spdx_document
    except ImportError as error:
        raise SbomError(
            "standards validators are unavailable; install the pinned SBOM validation tools"
        ) from error

    try:
        spdx_document = parse_file(str(spdx_path))
    except Exception as error:  # Validator libraries expose several parse error types.
        raise SbomError(f"SPDX standards validation failed: {error}") from error
    messages = validate_full_spdx_document(spdx_document)
    if messages:
        details = "; ".join(message.validation_message for message in messages)
        raise SbomError(f"SPDX standards validation failed: {details}")

    validator = JsonStrictValidator(SchemaVersion.V1_6)
    try:
        errors = validator.validate_str(cyclonedx_path.read_text(encoding="utf-8"))
    except Exception as error:
        raise SbomError(f"CycloneDX schema validation failed: {error}") from error
    if errors:
        if isinstance(errors, (list, tuple, set)):
            details = "; ".join(str(error) for error in errors)
        else:
            details = str(errors)
        raise SbomError(f"CycloneDX schema validation failed: {details}")


def _load(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise SbomError(f"cannot read {path}: {error}") from error


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    generate = subparsers.add_parser("generate", help="generate SPDX and CycloneDX JSON")
    generate.add_argument("--wheel", type=Path, required=True)
    generate.add_argument("--sdist", type=Path, required=True)
    generate.add_argument("--output-dir", type=Path, required=True)
    validate = subparsers.add_parser("validate", help="validate generated cross-format invariants")
    validate.add_argument("--spdx", type=Path, required=True)
    validate.add_argument("--cyclonedx", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "generate":
            spdx, cyclonedx = make_documents(inspect_artifacts(args.wheel, args.sdist))
            validate_documents(spdx, cyclonedx)
            args.output_dir.mkdir(parents=True, exist_ok=True)
            (args.output_dir / "agent-while-true.spdx.json").write_text(
                json.dumps(spdx, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
            (args.output_dir / "agent-while-true.cdx.json").write_text(
                json.dumps(cyclonedx, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
        else:
            validate_documents(_load(args.spdx), _load(args.cyclonedx))
            validate_with_standard_tools(args.spdx, args.cyclonedx)
    except (OSError, SbomError, ValueError) as error:
        parser.exit(1, f"sbom: {error}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
