from dataclasses import replace

from birdrat_proplogic.benchmarks import expanded_target_benchmarks, regression_benchmarks, small_target_benchmarks
from birdrat_proplogic.config import EvolutionConfig
from birdrat_proplogic.run_benchmarks import build_arg_parser, main, render_benchmark_result
from birdrat_proplogic.search import make_default_search_phases, make_exhaustive_search_phases
from birdrat_proplogic.surface import surface_pretty


def test_small_target_benchmarks_are_target_only_definitions() -> None:
    benchmarks = small_target_benchmarks()

    assert tuple(benchmark.name for benchmark in benchmarks) == (
        "identity",
        "syllogism",
        "classical-negation",
        "contraction",
        "distribution-application",
    )
    assert surface_pretty(benchmarks[0].target) == "p → p"
    assert all("DD211" not in benchmark.notes for benchmark in benchmarks)


def test_expanded_target_benchmarks_are_separate_diagnostic_suite() -> None:
    benchmarks = expanded_target_benchmarks()

    assert tuple(benchmark.name for benchmark in benchmarks) == (
        "double-negation-intro",
        "contrapositive",
    )
    assert surface_pretty(benchmarks[0].target) == "p → ¬¬p"
    assert surface_pretty(benchmarks[1].target) == "(p → q) → ¬q → ¬p"
    assert benchmarks[0].config.evolution.population_size == 80
    assert benchmarks[0].config.evolution.max_generations == 150
    assert benchmarks[0].config.evolution.diagnostics_interval == 1
    assert benchmarks[0].config.evolution.beam_width == 240
    assert benchmarks[0].config.evolution.beam_max_depth == 7
    assert benchmarks[0].config.evolution.beam_major_budget == 10_000
    assert benchmarks[0].config.evolution.beam_pair_budget == 100_000
    assert benchmarks[1].config.evolution.population_size == 100
    assert benchmarks[1].config.evolution.max_generations == 250
    assert benchmarks[1].config.evolution.diagnostics_interval == 1
    assert benchmarks[1].config.evolution.beam_width == 320
    assert benchmarks[1].config.evolution.beam_max_depth == 8
    assert benchmarks[1].config.evolution.beam_major_budget == 20_000
    assert benchmarks[1].config.evolution.beam_pair_budget == 200_000
    assert all("known proof" not in benchmark.notes.lower() for benchmark in benchmarks)


def test_default_regression_benchmarks_are_required_success_targets() -> None:
    benchmarks = regression_benchmarks()

    assert tuple(benchmark.name for benchmark in benchmarks) == (
        "identity",
        "syllogism",
        "classical-negation",
        "contraction",
        "distribution-application",
    )


def test_run_benchmarks_parser_accepts_suite_flags_and_overrides() -> None:
    parser = build_arg_parser()
    args = parser.parse_args(
        [
            "--suite",
            "expanded",
            "--seed",
            "3",
            "--beam-pair-budget",
            "123",
            "--beam-major-budget",
            "17",
            "--beam-only",
            "--strict",
        ]
    )

    assert args.suite == "expanded"
    assert args.seed == 3
    assert args.beam_pair_budget == 123
    assert args.beam_major_budget == 17
    assert args.beam_only
    assert args.strict


def test_small_target_benchmarks_use_bounded_regression_settings() -> None:
    for benchmark in small_target_benchmarks():
        assert benchmark.config.evolution.population_size <= 40
        assert benchmark.config.evolution.max_generations <= 40


def test_render_benchmark_result_runs_search_and_reports_required_fields() -> None:
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

    output = render_benchmark_result(benchmark, seed=1)

    assert "name: identity" in output
    assert "found exact proof:" in output
    assert "found by:" in output
    assert "found generation:" in output
    assert "best closed candidate:" in output
    assert "best schematic candidate:" in output
    assert "beam pair attempts:" in output
    assert "beam valid products:" in output
    assert "schema instantiation products:" in output
    assert "solved in phase:" in output
    assert "phase results:" in output


def test_default_search_phases_are_monotone() -> None:
    benchmark = small_target_benchmarks()[1]
    phases = make_default_search_phases(benchmark.config)

    assert tuple(phase.name for phase in phases) == (
        "strict-preselected",
        "hybrid",
        "expanded-hybrid",
    )
    assert phases[0].prioritized_fraction == 1.0
    assert phases[0].suffix_fraction == 0.0
    assert phases[1].prioritized_fraction == 1.0
    assert phases[1].suffix_fraction > 0.0
    assert phases[1].exploratory_fraction > 0.0
    assert phases[2].beam_pair_budget > phases[1].beam_pair_budget
    assert phases[2].beam_max_depth == phases[1].beam_max_depth + 1


def test_expanded_search_phase_is_single_exhaustive_beam_phase() -> None:
    benchmark = expanded_target_benchmarks()[0]
    phases = make_exhaustive_search_phases(benchmark.config)

    assert tuple(phase.name for phase in phases) == ("exhaustive-beam",)
    assert phases[0].prioritized_fraction == 0.0
    assert phases[0].suffix_fraction == 0.0
    assert phases[0].exploratory_fraction == 1.0
    assert phases[0].beam_width == benchmark.config.evolution.beam_width
    assert phases[0].beam_max_depth == benchmark.config.evolution.beam_max_depth
    assert phases[0].beam_pair_budget == benchmark.config.evolution.beam_pair_budget


def test_expanded_benchmark_cli_prints_generation_progress_with_total(capsys) -> None:
    exit_code = main(
        [
            "--expanded-targets",
            "--no-report",
            "--max-generations",
            "1",
            "--population-size",
            "2",
            "--beam-width",
            "2",
            "--beam-max-depth",
            "0",
            "--beam-major-budget",
            "2",
            "--beam-pair-budget",
            "1",
        ]
    )

    output = capsys.readouterr().out

    assert exit_code == 0
    assert "gen 0/1: exhaustive-beam starting" in output
    assert "gen 0/1: exhaustive-beam best=" in output
