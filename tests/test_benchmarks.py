from birdrat_proplogic.benchmarks import small_target_benchmarks
from birdrat_proplogic.run_benchmarks import build_arg_parser, render_benchmark_result
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


def test_run_benchmarks_parser_accepts_small_targets_and_overrides() -> None:
    parser = build_arg_parser()
    args = parser.parse_args(
        [
            "--small-targets",
            "--seed",
            "3",
            "--beam-pair-budget",
            "123",
            "--beam-major-budget",
            "17",
        ]
    )

    assert args.small_targets
    assert args.seed == 3
    assert args.beam_pair_budget == 123
    assert args.beam_major_budget == 17


def test_render_benchmark_result_runs_search_and_reports_required_fields() -> None:
    benchmark = small_target_benchmarks()[0]

    output = render_benchmark_result(benchmark, seed=1)

    assert "name: identity" in output
    assert "found exact proof:" in output
    assert "best closed candidate:" in output
    assert "best schematic candidate:" in output
    assert "beam pair attempts:" in output
    assert "beam valid products:" in output
