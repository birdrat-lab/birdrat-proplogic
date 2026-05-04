from __future__ import annotations

import argparse
from dataclasses import replace

from birdrat_proplogic.benchmarks import SearchBenchmark, regression_benchmarks, small_target_benchmarks
from birdrat_proplogic.fitness import total_fitness
from birdrat_proplogic.formula import is_closed_formula, pretty
from birdrat_proplogic.proof import Invalid
from birdrat_proplogic.proof import proof_pretty
from birdrat_proplogic.profiling import RuntimeProfile, RuntimeProfiler, compact_runtime_summary
from birdrat_proplogic.quality import behavior_descriptor, novelty_score
from birdrat_proplogic.reporting import timestamp, write_report
from birdrat_proplogic.search import PhaseReport, search_with_fallback
from birdrat_proplogic.surface import desugar, surface_display, surface_pretty, surface_sequent_pretty


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m birdrat_proplogic.run_benchmarks")
    parser.add_argument("--small-targets", action="store_true", help="run all five small target-only benchmarks")
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--max-generations", type=int)
    parser.add_argument("--population-size", type=int)
    parser.add_argument("--beam-width", type=int)
    parser.add_argument("--beam-max-depth", type=int)
    parser.add_argument("--beam-major-budget", type=int)
    parser.add_argument("--beam-pair-budget", type=int)
    parser.add_argument("--keep-going", action="store_true")
    parser.add_argument("--progress-interval", type=int, default=10)
    parser.add_argument("--report-dir", default="reports/benchmarks")
    parser.add_argument("--report-format", choices=("json", "md", "both"), default="json")
    parser.add_argument("--no-report", action="store_true")
    parser.add_argument("--profile", action="store_true", default=True)
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    suite = small_target_benchmarks() if args.small_targets else regression_benchmarks()
    benchmarks = tuple(_override_config(benchmark, args) for benchmark in suite)
    suite_name = "small-targets" if args.small_targets else "regression"
    results = []
    for index, benchmark in enumerate(benchmarks):
        if not args.quiet:
            if index:
                print()
                print()
            print(f"[{index + 1}/{len(benchmarks)}] {benchmark.name}")
            print("  proving:")
            for line in surface_display(benchmark.target).splitlines():
                print(f"    {line}")
            print(f"  core: {pretty(desugar(benchmark.target))}")
        profiler = RuntimeProfiler(enabled=True)
        search = search_with_fallback(
            benchmark.target,
            benchmark.config,
            seed=args.seed,
            profiler=profiler,
            progress_callback=_benchmark_progress_printer(args.progress_interval, args.quiet),
        )
        results.append((benchmark, search))
        if args.verbose:
            print(render_benchmark_search_result(benchmark, search))
        elif not args.quiet:
            print(f"  {_benchmark_status_line(search)}")
    if not args.quiet:
        print()
        print(_summary_table(results))
        if args.profile:
            profile_lines = _aggregate_runtime_summary(results)
            if profile_lines:
                print()
                print("runtime summary:")
                print("\n".join(profile_lines))
    report_paths = ()
    if not args.no_report:
        profiler = RuntimeProfiler(enabled=True)
        with profiler.section("report_writing"):
            report_paths = write_report(
                _benchmark_report_payload(suite_name, results, args.seed),
                report_dir=args.report_dir,
                stem=f"{suite_name}-{timestamp()}",
                report_format=args.report_format,
            )
        if not args.quiet:
            print(f"full report: {', '.join(str(path) for path in report_paths)}")
    return 0


def render_benchmark_result(benchmark: SearchBenchmark, seed: int | None = None) -> str:
    search = search_with_fallback(benchmark.target, benchmark.config, seed=seed)
    return render_benchmark_search_result(benchmark, search)


def render_benchmark_search_result(benchmark: SearchBenchmark, search) -> str:
    result = search.result
    best = result.best.fitness
    final_scored = tuple(
        total_fitness(proof, desugar(benchmark.target), result.regions, benchmark.config)
        for proof in result.population
    )
    best_closed = _best_closed_candidate(final_scored)
    best_schema = _best_schema_candidate(final_scored)
    best_novelty = _best_novelty_candidate(result.population, final_scored)
    diagnostics = result.beam_diagnostics
    lines = [
        f"name: {benchmark.name}",
        f"target: {surface_sequent_pretty(benchmark.target)}",
        "target display:",
        *[f"  {line}" for line in surface_display(benchmark.target).splitlines()],
        f"core target: {pretty(desugar(benchmark.target))}",
        f"expected status: {benchmark.expected_status}",
        f"found exact proof: {search.found}",
        f"solved in phase: {search.solved_in_phase or 'none'}",
        f"best closed candidate: {_candidate_text(best_closed)}",
        f"best schematic candidate: {_candidate_text(best_schema)}",
        f"best novelty candidate: {_candidate_text(best_novelty)}",
        f"best score: {best.score:.6f}",
        f"target similarity: {best.target_similarity:.6f}",
        f"proof CD steps: {best.cd_steps}",
        f"proof CD depth: {best.cd_depth}",
        f"proof size: {best.proof_size}",
        f"formula size: {best.formula_size}",
        f"total runtime: {search.total_runtime_seconds:.3f}s",
        f"beam width: {benchmark.config.evolution.beam_width}",
        f"beam max depth: {benchmark.config.evolution.beam_max_depth}",
        f"beam pair budget: {diagnostics.pair_budget}",
        f"beam pair attempts: {diagnostics.pair_attempts}",
        f"beam valid products: {diagnostics.valid_products}",
        f"beam layer counts: {_beam_layer_text(result.history[-1].beam_layer_counts if result.history else ())}",
        f"schema instantiation products: {result.history[-1].instantiated_schema_products if result.history else 0}",
        f"population size: {benchmark.config.evolution.population_size}",
        f"generations: {len(result.history)}",
        f"notes: {benchmark.notes}",
        "phase results:",
        *_phase_lines(search.phase_reports),
    ]
    return "\n".join(lines)


def _benchmark_status_line(search) -> str:
    best = search.result.best.fitness
    if search.found:
        return (
            f"{search.solved_in_phase}: FOUND cd={best.cd_steps} "
            f"depth={best.cd_depth} size={best.proof_size} time={search.total_runtime_seconds:.1f}s"
        )
    return (
        f"not found phase=none best_sim={best.target_similarity:.2f} "
        f"time={search.total_runtime_seconds:.1f}s"
    )


def _benchmark_progress_printer(interval: int, quiet: bool):
    interval = max(1, interval)
    printed: set[tuple[str, int]] = set()

    def callback(phase: str, stats, elapsed: float) -> None:
        if quiet:
            return
        should_print = stats.generation == 0 or stats.best_exact or stats.generation % interval == 0
        if not should_print or (phase, stats.generation) in printed:
            return
        printed.add((phase, stats.generation))
        if stats.best_exact:
            print(
                f"  gen {stats.generation}: {phase} FOUND "
                f"best={stats.best_score:.1f} sim={stats.best_target_similarity:.2f} "
                f"exact={stats.exact_target_count} beam={stats.beam_valid_products} time={elapsed:.1f}s"
            )
            return
        print(
            f"  gen {stats.generation}: {phase} "
            f"best={stats.best_score:.1f} sim={stats.best_target_similarity:.2f} "
            f"exact={stats.exact_target_count} valid={stats.valid_fraction:.2f} "
            f"closed={stats.closed_fraction:.2f} beam={stats.beam_valid_products} time={elapsed:.1f}s"
        )

    return callback


def _summary_table(results) -> str:
    lines = [
        "summary",
        f"{'name':25} {'found':5} {'phase':18} {'cd':>3} {'depth':>5} {'size':>5} {'runtime':>8}",
    ]
    for benchmark, search in results:
        best = search.result.best.fitness
        found = "yes" if search.found else "no"
        phase = search.solved_in_phase or "none"
        cd = str(best.cd_steps) if search.found else "-"
        depth = str(best.cd_depth) if search.found else "-"
        size = str(best.proof_size) if search.found else "-"
        lines.append(
            f"{benchmark.name:25} {found:5} {phase:18} {cd:>3} {depth:>5} {size:>5} {search.total_runtime_seconds:>7.1f}s"
        )
        if not search.found:
            lines.append(f"  best similarity: {best.target_similarity:.3f}")
    return "\n".join(lines)


def _benchmark_report_payload(suite_name: str, results, seed: int | None) -> dict:
    return {
        "title": f"birdrat-proplogic benchmark: {suite_name}",
        "summary": [
            {
                "name": benchmark.name,
                "found": search.found,
                "solved_in_phase": search.solved_in_phase,
                "runtime_seconds": search.total_runtime_seconds,
                "cd_steps": search.result.best.fitness.cd_steps,
                "cd_depth": search.result.best.fitness.cd_depth,
                "proof_size": search.result.best.fitness.proof_size,
                "target_similarity": search.result.best.fitness.target_similarity,
            }
            for benchmark, search in results
        ],
        "suite": suite_name,
        "seed": seed,
        "results": [
            {
                "benchmark": benchmark,
                "surface_target": surface_pretty(benchmark.target),
                "surface_sequent": surface_sequent_pretty(benchmark.target),
                "surface_display": surface_display(benchmark.target),
                "core_target": pretty(desugar(benchmark.target)),
                "search_result": search,
                "history": search.result.history,
                "beam_diagnostics": search.result.beam_diagnostics,
                "best_proof": proof_pretty(search.result.best.proof),
                "runtime_profile": search.runtime_profile,
            }
            for benchmark, search in results
        ],
    }


def _aggregate_runtime_summary(results) -> list[str]:
    sections: dict[str, float] = {}
    counters: dict[str, int] = {}
    for _benchmark, search in results:
        for key, value in search.runtime_profile.sections.items():
            sections[key] = sections.get(key, 0.0) + value
        for key, value in search.runtime_profile.counters.items():
            counters[key] = counters.get(key, 0) + value
    return compact_runtime_summary(RuntimeProfile(sections=sections, counters=counters))


def _override_config(benchmark: SearchBenchmark, args: argparse.Namespace) -> SearchBenchmark:
    evolution = benchmark.config.evolution
    for arg_name, field_name in (
        ("max_generations", "max_generations"),
        ("population_size", "population_size"),
        ("beam_width", "beam_width"),
        ("beam_max_depth", "beam_max_depth"),
        ("beam_major_budget", "beam_major_budget"),
        ("beam_pair_budget", "beam_pair_budget"),
    ):
        value = getattr(args, arg_name)
        if value is not None:
            evolution = replace(evolution, **{field_name: value})
    if args.keep_going:
        evolution = replace(evolution, stop_on_exact=False)
    return replace(benchmark, config=replace(benchmark.config, evolution=evolution))


def _best_closed_candidate(fitnesses):
    closed = [
        fitness
        for fitness in fitnesses
        if fitness.valid and not isinstance(fitness.conclusion, Invalid) and is_closed_formula(fitness.conclusion)
    ]
    if not closed:
        return None
    return max(closed, key=lambda fitness: fitness.score)


def _best_schema_candidate(fitnesses):
    schematic = [
        fitness
        for fitness in fitnesses
        if fitness.valid and not isinstance(fitness.conclusion, Invalid) and not is_closed_formula(fitness.conclusion)
    ]
    if not schematic:
        return None
    return max(schematic, key=lambda fitness: fitness.score)


def _best_novelty_candidate(proofs, fitnesses):
    descriptors = tuple(
        behavior_descriptor(proof, fitness.conclusion)
        for proof, fitness in zip(proofs, fitnesses)
    )
    if not descriptors:
        return None
    archive = descriptors[: max(1, len(descriptors) // 2)]
    index = max(
        range(len(descriptors)),
        key=lambda item: novelty_score(descriptors[item], archive),
    )
    return fitnesses[index]


def _candidate_text(fitness) -> str:
    if fitness is None:
        return "none"
    if isinstance(fitness.conclusion, Invalid):
        conclusion = f"invalid: {fitness.conclusion.reason}"
    else:
        conclusion = pretty(fitness.conclusion)
    return f"{conclusion} (score={fitness.score:.3f}, target_similarity={fitness.target_similarity:.3f})"


def _beam_layer_text(layers: tuple[str, ...]) -> str:
    if not layers:
        return "none"
    return " | ".join(layers)


def _phase_lines(reports: tuple[PhaseReport, ...]) -> list[str]:
    lines: list[str] = []
    for report in reports:
        lines.extend(
            [
                f"  {report.phase_name}:",
                f"    found: {report.found_exact}",
                f"    best closed: {_proof_text(report.best_closed_candidate, report)}",
                f"    best schematic: {_proof_text(report.best_schematic_candidate, report)}",
                f"    best novelty: {_proof_text(report.best_novelty_candidate, report)}",
                f"    runtime: {report.runtime_seconds:.3f}s",
                f"    beam pair attempts: {report.beam_pair_attempts}",
                f"    beam valid products: {report.beam_valid_products}",
                f"    beam layer counts: {_raw_beam_layer_text(report.beam_layer_counts)}",
            ]
        )
    return lines


def _proof_text(proof, report: PhaseReport) -> str:
    if proof is None:
        return "none"
    fitness = total_fitness(proof, desugar(report.result.target), report.result.regions)
    return _candidate_text(fitness)


def _raw_beam_layer_text(layers: tuple) -> str:
    if not layers:
        return "none"
    return " | ".join(
        (
            f"d{layer.depth}:attempts={layer.pair_attempts},valid={layer.valid_products},"
            f"strict={layer.strict_pairs_attempted},suffix={layer.suffix_pairs_attempted},"
            f"explore={layer.exploratory_pairs_attempted},dupes={layer.duplicate_pairs_removed},"
            f"closed={layer.closed_products},schematic={layer.schematic_products},"
            f"suffix_seen={_suffix_survivor_text(layer.suffix_candidates_seen_by_suffix)},"
            f"suffix_closed_seen={_suffix_survivor_text(layer.suffix_closed_candidates_seen_by_suffix)},"
            f"suffix_schematic_seen={_suffix_survivor_text(layer.suffix_schematic_candidates_seen_by_suffix)},"
            f"suffix_survivors={_suffix_survivor_text(layer.suffix_survivors_by_suffix)},"
            f"best_by_suffix={_suffix_survivor_text(layer.best_candidate_by_suffix)},"
            f"schema_attempts={layer.schema_instantiation_attempts},"
            f"schema_valid={layer.schema_instantiation_valid},"
            f"schema_closed={layer.schema_instantiation_closed},"
            f"schema_schematic={layer.schema_instantiation_schematic},"
            f"schema_exact_target={layer.schema_instantiation_exact_target},"
            f"schema_exact_region={layer.schema_instantiation_exact_region},"
            f"schema_exact_suffix={layer.schema_instantiation_exact_suffix},"
            f"best_instantiated={layer.best_instantiated_candidate or 'none'},"
            f"exact_generated={layer.exact_target_generated_in_beam},"
            f"exact_survived={layer.exact_target_survived_to_population}"
        )
        for layer in layers
    )


def _suffix_survivor_text(items: tuple[tuple[str, int], ...]) -> str:
    if not items:
        return "none"
    return "[" + ", ".join(f"{suffix}:{count}" for suffix, count in items) + "]"


if __name__ == "__main__":
    raise SystemExit(main())
