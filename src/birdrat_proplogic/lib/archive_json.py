from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from birdrat_proplogic.archive import ProofArchive, empty_archive, record_proof
from birdrat_proplogic.config import DEFAULT_CONFIG, ProplogicConfig
from birdrat_proplogic.formula import Atom, Formula, Imp, Meta, Not
from birdrat_proplogic.proof import Ax1, Ax2, Ax3, CD, Proof

ARCHIVE_JSON_VERSION = 1


def load_archive_json(
    path: str | Path,
    config: ProplogicConfig = DEFAULT_CONFIG,
) -> ProofArchive:
    archive_path = Path(path)
    if not archive_path.exists():
        return empty_archive()

    with archive_path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)

    if data.get("version") != ARCHIVE_JSON_VERSION:
        raise ValueError(f"unsupported archive version: {data.get('version')}")

    archive = empty_archive()
    for entry in data.get("entries", ()):
        formula = _decode_formula(entry["formula"])
        for proof_data in entry.get("proofs", ()):
            archive = record_proof(archive, formula, _decode_proof(proof_data), config)
    return archive


def save_archive_json(archive: ProofArchive, path: str | Path) -> None:
    archive_path = Path(path)
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": ARCHIVE_JSON_VERSION,
        "entries": [
            {
                "formula": _encode_formula(formula),
                "proofs": [_encode_proof(proof) for proof in proofs],
            }
            for formula, proofs in sorted(archive.items(), key=lambda item: repr(item[0]))
        ],
    }
    temp_path = archive_path.with_suffix(f"{archive_path.suffix}.tmp")
    with temp_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
    temp_path.replace(archive_path)


def _encode_formula(formula: Formula) -> dict[str, Any]:
    match formula:
        case Atom(name):
            return {"type": "Atom", "name": name}
        case Meta(name):
            return {"type": "Meta", "name": name}
        case Not(body):
            return {"type": "Not", "body": _encode_formula(body)}
        case Imp(left, right):
            return {
                "type": "Imp",
                "left": _encode_formula(left),
                "right": _encode_formula(right),
            }


def _decode_formula(data: dict[str, Any]) -> Formula:
    match data.get("type"):
        case "Atom":
            return Atom(_expect_str(data, "name"))
        case "Meta":
            return Meta(_expect_str(data, "name"))
        case "Not":
            return Not(_decode_formula(_expect_dict(data, "body")))
        case "Imp":
            return Imp(
                _decode_formula(_expect_dict(data, "left")),
                _decode_formula(_expect_dict(data, "right")),
            )
        case other:
            raise ValueError(f"unknown formula type: {other}")


def _encode_proof(proof: Proof) -> dict[str, Any]:
    match proof:
        case Ax1(p, q):
            return {"type": "Ax1", "p": _encode_formula(p), "q": _encode_formula(q)}
        case Ax2(p, q, r):
            return {
                "type": "Ax2",
                "p": _encode_formula(p),
                "q": _encode_formula(q),
                "r": _encode_formula(r),
            }
        case Ax3(p, q):
            return {"type": "Ax3", "p": _encode_formula(p), "q": _encode_formula(q)}
        case CD(major, minor):
            return {
                "type": "CD",
                "major": _encode_proof(major),
                "minor": _encode_proof(minor),
            }


def _decode_proof(data: dict[str, Any]) -> Proof:
    match data.get("type"):
        case "Ax1":
            return Ax1(
                _decode_formula(_expect_dict(data, "p")),
                _decode_formula(_expect_dict(data, "q")),
            )
        case "Ax2":
            return Ax2(
                _decode_formula(_expect_dict(data, "p")),
                _decode_formula(_expect_dict(data, "q")),
                _decode_formula(_expect_dict(data, "r")),
            )
        case "Ax3":
            return Ax3(
                _decode_formula(_expect_dict(data, "p")),
                _decode_formula(_expect_dict(data, "q")),
            )
        case "CD":
            return CD(
                _decode_proof(_expect_dict(data, "major")),
                _decode_proof(_expect_dict(data, "minor")),
            )
        case other:
            raise ValueError(f"unknown proof type: {other}")


def _expect_dict(data: dict[str, Any], key: str) -> dict[str, Any]:
    value = data.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"expected object at key: {key}")
    return value


def _expect_str(data: dict[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str):
        raise ValueError(f"expected string at key: {key}")
    return value
