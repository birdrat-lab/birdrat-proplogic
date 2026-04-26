import json

import pytest

from birdrat_proplogic.archive import empty_archive, record_proof
from birdrat_proplogic.formula import Atom, Imp, Meta, Not
from birdrat_proplogic.lib.archive_json import load_archive_json, save_archive_json
from birdrat_proplogic.proof import Ax1, Ax2, CD


def test_archive_json_round_trips_formulas_and_proofs(tmp_path) -> None:
    path = tmp_path / "archive.json"
    formula = Imp(Not(Atom("a")), Imp(Atom("b"), Meta("?p")))
    proof = CD(
        Ax2(Atom("a"), Atom("b"), Atom("c")),
        Ax1(Not(Atom("a")), Meta("?q")),
    )
    archive = record_proof(empty_archive(), formula, proof)

    save_archive_json(archive, path)
    loaded = load_archive_json(path)

    assert loaded == archive


def test_load_archive_json_returns_empty_archive_for_missing_file(tmp_path) -> None:
    assert load_archive_json(tmp_path / "missing.json") == {}


def test_load_archive_json_rejects_unknown_version(tmp_path) -> None:
    path = tmp_path / "archive.json"
    path.write_text(json.dumps({"version": 999, "entries": []}), encoding="utf-8")

    with pytest.raises(ValueError, match="unsupported archive version"):
        load_archive_json(path)
