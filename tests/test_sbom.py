# SPDX-FileCopyrightText: 2026 Marcel Petrick
# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for release SBOM generation and consistency validation."""

from __future__ import annotations

import importlib.util
import io
import json
import tarfile
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
SPEC = importlib.util.spec_from_file_location("agent_while_true_sbom", ROOT / "scripts/sbom.py")
assert SPEC is not None
assert SPEC.loader is not None
sbom = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(sbom)


def _metadata(version: str, requirements: tuple[str, ...] = ()) -> bytes:
    requires = "".join(f"Requires-Dist: {requirement}\n" for requirement in requirements)
    return (
        "Metadata-Version: 2.4\n"
        "Name: agent-while-true\n"
        f"Version: {version}\n"
        "License-Expression: GPL-3.0-or-later\n"
        f"{requires}\n"
    ).encode()


def _artifacts(
    directory: Path,
    *,
    wheel_version: str = "1.2.3",
    sdist_version: str = "1.2.3",
    requirements: tuple[str, ...] = (),
) -> tuple[Path, Path]:
    wheel = directory / f"agent_while_true-{wheel_version}-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        info = zipfile.ZipInfo(f"agent_while_true-{wheel_version}.dist-info/METADATA")
        info.date_time = (2026, 1, 2, 3, 4, 6)
        archive.writestr(info, _metadata(wheel_version, requirements))
    sdist = directory / f"agent_while_true-{sdist_version}.tar.gz"
    with tarfile.open(sdist, "w:gz") as archive:
        payload = _metadata(sdist_version, requirements)
        info = tarfile.TarInfo(f"agent_while_true-{sdist_version}/PKG-INFO")
        info.size = len(payload)
        info.mtime = 1_767_326_646
        archive.addfile(info, io.BytesIO(payload))
    return wheel, sdist


def test_documents_inventory_release_artifacts_and_no_runtime_dependencies(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    wheel, sdist = _artifacts(
        tmp_path,
        requirements=("pytest==9.1.1; extra == 'dev'", "ruff==0.16.7; extra == 'dev'"),
    )
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1767326646")
    spdx, cyclonedx = sbom.make_documents(sbom.inspect_artifacts(wheel, sdist))

    sbom.validate_documents(spdx, cyclonedx)
    assert spdx["packages"][0]["versionInfo"] == "1.2.3"
    assert {entry["fileName"] for entry in spdx["files"]} == {
        f"./{wheel.name}",
        f"./{sdist.name}",
    }
    assert cyclonedx["dependencies"] == [
        {"ref": "pkg:pypi/agent-while-true@1.2.3", "dependsOn": []}
    ]
    assert "development" in spdx["annotations"][0]["comment"]


def test_documents_are_deterministic_for_same_artifacts(tmp_path: Path) -> None:
    wheel, sdist = _artifacts(tmp_path)
    provenance = sbom.inspect_artifacts(wheel, sdist)
    first = sbom.make_documents(provenance)
    second = sbom.make_documents(provenance)
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)


def test_rejects_mismatched_artifact_versions(tmp_path: Path) -> None:
    wheel, sdist = _artifacts(tmp_path, sdist_version="1.2.4")
    with pytest.raises(sbom.SbomError, match="versions do not match"):
        sbom.inspect_artifacts(wheel, sdist)


def test_rejects_missing_artifact(tmp_path: Path) -> None:
    wheel, _ = _artifacts(tmp_path)
    with pytest.raises(sbom.SbomError, match="missing release artifact"):
        sbom.inspect_artifacts(wheel, tmp_path / "missing.tar.gz")


def test_rejects_uninventoried_runtime_dependency(tmp_path: Path) -> None:
    wheel, sdist = _artifacts(tmp_path, requirements=("requests==2.32.5",))
    with pytest.raises(sbom.SbomError, match="unsupported runtime dependencies"):
        sbom.inspect_artifacts(wheel, sdist)


@pytest.mark.parametrize(
    "requirement",
    [
        "not a valid requirement",
        "not a valid requirement; extra == 'dev'",
        "foo; python_version >= '3.12' or extra == 'dev'",
        "foo; extra != 'dev'",
    ],
)
def test_rejects_nonexclusive_extra_markers(tmp_path: Path, requirement: str) -> None:
    wheel, sdist = _artifacts(tmp_path, requirements=(requirement,))
    with pytest.raises(sbom.SbomError, match="unsupported runtime dependencies"):
        sbom.inspect_artifacts(wheel, sdist)


def test_accepts_parenthesized_dev_only_marker(tmp_path: Path) -> None:
    wheel, sdist = _artifacts(
        tmp_path,
        requirements=(
            'pytest==9.1.1; ((extra == "dev"))',
            'cyclonedx-python-lib[validation]==11.12.0; extra == "dev"',
        ),
    )
    assert sbom.inspect_artifacts(wheel, sdist)["version"] == "1.2.3"


def test_rejects_unexpected_license_metadata(tmp_path: Path) -> None:
    wheel, sdist = _artifacts(tmp_path)
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr(
            "agent_while_true-1.2.3.dist-info/METADATA",
            _metadata("1.2.3").replace(b"GPL-3.0-or-later", b"MIT"),
        )
    with pytest.raises(sbom.SbomError, match="License-Expression"):
        sbom.inspect_artifacts(wheel, sdist)


def test_validation_rejects_malformed_and_inconsistent_documents(tmp_path: Path) -> None:
    wheel, sdist = _artifacts(tmp_path)
    spdx, cyclonedx = sbom.make_documents(sbom.inspect_artifacts(wheel, sdist))
    with pytest.raises(sbom.SbomError, match="malformed SPDX"):
        sbom.validate_documents({}, cyclonedx)

    cyclonedx["metadata"]["component"]["version"] = "9.9.9"
    with pytest.raises(sbom.SbomError, match="identities do not match"):
        sbom.validate_documents(spdx, cyclonedx)


def test_cli_generates_and_validates_both_formats(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    wheel, sdist = _artifacts(tmp_path)
    output = tmp_path / "sbom"
    assert (
        sbom.main(
            [
                "generate",
                "--wheel",
                str(wheel),
                "--sdist",
                str(sdist),
                "--output-dir",
                str(output),
            ]
        )
        == 0
    )
    standards_calls = []
    monkeypatch.setattr(
        sbom,
        "validate_with_standard_tools",
        lambda spdx_path, cdx_path: standards_calls.append((spdx_path, cdx_path)),
    )
    assert (
        sbom.main(
            [
                "validate",
                "--spdx",
                str(output / "agent-while-true.spdx.json"),
                "--cyclonedx",
                str(output / "agent-while-true.cdx.json"),
            ]
        )
        == 0
    )
    assert standards_calls == [
        (
            output / "agent-while-true.spdx.json",
            output / "agent-while-true.cdx.json",
        )
    ]


def test_maintained_standard_validators_accept_documents_and_reject_corruption(
    tmp_path: Path,
) -> None:
    wheel, sdist = _artifacts(tmp_path)
    spdx, cyclonedx = sbom.make_documents(sbom.inspect_artifacts(wheel, sdist))
    spdx_path = tmp_path / "release.spdx.json"
    cyclonedx_path = tmp_path / "release.cdx.json"
    spdx_path.write_text(json.dumps(spdx), encoding="utf-8")
    cyclonedx_path.write_text(json.dumps(cyclonedx), encoding="utf-8")

    sbom.validate_with_standard_tools(spdx_path, cyclonedx_path)

    broken_cyclonedx = {**cyclonedx, "version": "one"}
    cyclonedx_path.write_text(json.dumps(broken_cyclonedx), encoding="utf-8")
    with pytest.raises(sbom.SbomError, match="CycloneDX schema validation failed"):
        sbom.validate_with_standard_tools(spdx_path, cyclonedx_path)

    cyclonedx_path.write_text(json.dumps(cyclonedx), encoding="utf-8")
    broken_spdx = dict(spdx)
    del broken_spdx["creationInfo"]
    spdx_path.write_text(json.dumps(broken_spdx), encoding="utf-8")
    with pytest.raises(sbom.SbomError, match="SPDX standards validation failed"):
        sbom.validate_with_standard_tools(spdx_path, cyclonedx_path)
