from birdrat_proplogic.config import ArchiveConfig, EvolutionConfig, ProplogicConfig
from birdrat_proplogic.formula import pretty
from birdrat_proplogic.parse import parse_surface
from birdrat_proplogic.run import (
    _config_from_args,
    build_arg_parser,
    conjunction_commutativity_target,
    render_search_report,
    run_search,
)
from birdrat_proplogic.surface import desugar, surface_pretty


def small_config() -> ProplogicConfig:
    return ProplogicConfig(
        archive=ArchiveConfig(path=None),
        evolution=EvolutionConfig(
            population_size=4,
            max_generations=2,
            elite_count=1,
            tournament_size=2,
        ),
    )


def test_conjunction_commutativity_target_matches_section_19() -> None:
    target = conjunction_commutativity_target()

    assert surface_pretty(target) == "a ∧ b → b ∧ a"
    assert parse_surface(r"a \land b \to b \land a") == target
    assert pretty(desugar(target)) == "¬(a → ¬b) → ¬(b → ¬a)"


def test_run_search_returns_search_report() -> None:
    report = run_search(conjunction_commutativity_target(), small_config(), seed=1)

    assert report.result.target == conjunction_commutativity_target()
    assert len(report.result.history) == 2


def test_render_search_report_mentions_best_candidate_and_proof() -> None:
    report = run_search(conjunction_commutativity_target(), small_config(), seed=1)
    output = render_search_report(report)

    assert "surface target:\n  a ∧ b → b ∧ a" in output
    assert "active depth:" in output
    assert "best candidate:" in output
    assert "target similarity:" in output
    assert "best region similarity:" in output
    assert "proof:" in output


def test_config_from_args_applies_cli_overrides() -> None:
    parser = build_arg_parser()
    args = parser.parse_args(
        [
            "a -> a",
            "--population-size",
            "7",
            "--max-generations",
            "3",
            "--archive-path",
            "tmp/archive.json",
            "--no-load-archive",
        ]
    )

    config = _config_from_args(args)

    assert config.evolution.population_size == 7
    assert config.evolution.max_generations == 3
    assert config.archive.path == "tmp/archive.json"
    assert not config.archive.load_on_start
