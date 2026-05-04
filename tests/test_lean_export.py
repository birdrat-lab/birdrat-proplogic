from __future__ import annotations

import shutil
from dataclasses import replace

import pytest

from birdrat_proplogic.benchmarks import small_target_benchmarks
from birdrat_proplogic.config import EvolutionConfig
from birdrat_proplogic.formula import Atom, Imp, Meta, Not
from birdrat_proplogic.lean_export import (
    LeanTheoremSpec,
    check_lean_file,
    export_lean_proof,
    export_lean_suite,
    formula_to_lean,
    sanitize_lean_name,
    write_lean_file,
)
from birdrat_proplogic.search import search_with_fallback
from birdrat_proplogic.surface import desugar, surface_pretty


DISALLOWED = ("sorry", "admit", "simp", "tauto", "aesop", "omega", "exact?")


def _identity_search():
    benchmark = small_target_benchmarks()[0]
    benchmark = replace(
        benchmark,
        config=replace(
            benchmark.config,
            evolution=EvolutionConfig(
                population_size=6,
                max_generations=2,
                beam_width=12,
                beam_max_depth=2,
                beam_pair_budget=100,
            ),
        ),
    )
    result = search_with_fallback(benchmark.target, benchmark.config, seed=1)
    assert result.found
    assert result.proof is not None
    return benchmark, result


def test_formula_to_lean() -> None:
    formula = Imp(Atom("p"), Imp(Not(Atom("q")), Meta("?m1")))
    export = export_lean_proof(
        proof=_identity_search()[1].proof,
        target=Imp(Atom("p"), Atom("p")),
        theorem_name="identity",
    )

    assert formula_to_lean(formula, _name_env_from_export(export.lean_source)) == "(p → ((¬ q) → M_m1))"


def test_sanitize_lean_name() -> None:
    assert sanitize_lean_name("x-1") == "x_1"
    assert sanitize_lean_name("p'") == "p_"
    assert sanitize_lean_name("1p") == "v_1p"


def test_export_contains_no_disallowed_terms() -> None:
    _benchmark, result = _identity_search()
    export = export_lean_proof(result.proof, Imp(Atom("p"), Atom("p")))

    for token in DISALLOWED:
        assert token not in export.lean_source


def test_export_contains_p2_axioms() -> None:
    _benchmark, result = _identity_search()
    export = export_lean_proof(result.proof, Imp(Atom("p"), Atom("p")))

    assert "theorem p2_ax1" in export.lean_source
    assert "theorem p2_ax2" in export.lean_source
    assert "theorem p2_ax3" in export.lean_source
    assert "axiom p2_ax" not in export.lean_source


def test_export_identity_file_shape() -> None:
    benchmark, result = _identity_search()
    export = export_lean_proof(
        result.proof,
        desugar(benchmark.target),
        theorem_name="identity",
        surface_target=surface_pretty(benchmark.target),
        found_by=result.found_by,
        found_phase=result.solved_in_phase,
    )

    assert "theorem identity (p : Prop) : (p → p) := by" in export.lean_source
    assert "Found by:" in export.lean_source
    assert "have h" in export.lean_source
    assert "exact h" in export.lean_source
    assert "#check identity" in export.lean_source


def test_export_small_targets_file_shape() -> None:
    benchmark, result = _identity_search()
    specs = tuple(
        LeanTheoremSpec(
            theorem_name=name,
            target=desugar(benchmark.target),
            proof=result.proof,
            surface_target=surface_pretty(benchmark.target),
        )
        for name in (
            "identity",
            "syllogism",
            "classical_negation",
            "contraction",
            "distribution_application",
        )
    )
    export = export_lean_suite(specs, suite_name="small-targets")

    assert "Benchmark suite: small-targets" in export.lean_source
    assert export.lean_source.count("theorem identity") == 1
    assert "theorem distribution_application" in export.lean_source
    assert "#check classical_negation" in export.lean_source


def test_export_distribution_file_shape() -> None:
    benchmark, result = _identity_search()
    export = export_lean_proof(
        result.proof,
        desugar(benchmark.target),
        theorem_name="distribution_application",
    )

    assert "theorem distribution_application" in export.lean_source
    assert "namespace BirdratOutput" in export.lean_source
    assert "end BirdratOutput" in export.lean_source


def test_identity_export_checks_with_lean_when_available(tmp_path) -> None:
    if shutil.which("lean") is None:
        pytest.skip("Lean not installed")
    benchmark, result = _identity_search()
    export = export_lean_proof(result.proof, desugar(benchmark.target), theorem_name="identity", output_path=tmp_path / "OUTPUT.lean")
    write_lean_file(export)

    checked = check_lean_file(export.output_path)

    assert checked.checked, checked.stderr


def _name_env_from_export(_source: str):
    from birdrat_proplogic.lean_export import _transient_env

    return _transient_env(Imp(Atom("p"), Imp(Not(Atom("q")), Meta("?m1"))))
