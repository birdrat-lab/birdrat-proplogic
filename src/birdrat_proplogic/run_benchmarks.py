from __future__ import annotations

import argparse
from dataclasses import replace
from pathlib import Path

from birdrat_proplogic.benchmarks import (
    SearchBenchmark,
    expanded_target_benchmarks,
    regression_benchmarks,
    small_target_benchmarks,
)
from birdrat_proplogic.fitness import total_fitness
from birdrat_proplogic.formula import is_closed_formula, pretty
from birdrat_proplogic.lean_export import LeanCheckResult, LeanTheoremSpec, check_lean_file, export_lean_suite, write_lean_file
from birdrat_proplogic.proof import Invalid
from birdrat_proplogic.proof import proof_pretty
from birdrat_proplogic.profiling import RuntimeProfile, RuntimeProfiler, compact_runtime_summary
from birdrat_proplogic.quality import behavior_descriptor, novelty_score
from birdrat_proplogic.reporting import timestamp, write_report
from birdrat_proplogic.search import PhaseReport, make_exhaustive_search_phases, search_beam_only, search_with_fallback
from birdrat_proplogic.surface import desugar, surface_display, surface_pretty, surface_sequent_pretty


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m birdrat_proplogic.run_benchmarks")
    parser.add_argument("--suite", choices=("regression", "small", "expanded"), help="benchmark suite to run")
    parser.add_argument("--small-targets", action="store_true", help="run all five small target-only benchmarks")
    parser.add_argument("--expanded-targets", action="store_true", help="run the expanded diagnostic target-only benchmarks")
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--max-generations", type=int)
    parser.add_argument("--population-size", type=int)
    parser.add_argument("--beam-width", type=int)
    parser.add_argument("--beam-max-depth", type=int)
    parser.add_argument("--beam-major-budget", type=int)
    parser.add_argument("--beam-pair-budget", type=int)
    parser.add_argument("--beam-only", action="store_true", help="run only the cascading beam search phases")
    parser.add_argument("--no-beam", action="store_true", help="disable beam seeding and run evolution only")
    parser.add_argument("--beam-progress-interval", type=float, default=5.0)
    parser.add_argument("--no-beam-stop-on-exact", action="store_true")
    parser.add_argument("--export-lean", action="store_true")
    parser.add_argument("--lean-output", default="OUTPUT.lean")
    parser.add_argument("--no-lean-check", action="store_true")
    parser.add_argument("--lean-command", default="lean")
    parser.add_argument("--keep-going", action="store_true")
    parser.add_argument("--strict", action="store_true", help="return a failing exit code if any selected benchmark is not solved")
    parser.add_argument("--progress-interval", type=int)
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

    if args.beam_only and args.no_beam:
        parser.error("--beam-only and --no-beam are mutually exclusive")
    suite_name, suite = _selected_suite(args)
    benchmarks = tuple(_override_config(benchmark, args) for benchmark in suite)
    progress_interval = args.progress_interval or (1 if suite_name == "expanded-targets" else 10)
    results = []
    for index, benchmark in enumerate(benchmarks):
        if not args.quiet:
            if index:
                print(flush=True)
                print(flush=True)
            print(f"[{index + 1}/{len(benchmarks)}] {benchmark.name}", flush=True)
            print("  proving:", flush=True)
            for line in surface_display(benchmark.target).splitlines():
                print(f"    {line}", flush=True)
            print(f"  core: {pretty(desugar(benchmark.target))}", flush=True)
        profiler = RuntimeProfiler(enabled=True)
        phases = _search_phases_for_benchmark(suite_name, benchmark)
        beam_progress_enabled = suite_name == "expanded-targets" and benchmark.config.evolution.beam_enabled and not args.quiet
        beam_progress = _beam_progress_printer() if beam_progress_enabled else None
        beam_start = _beam_start_printer() if beam_progress_enabled else None
        if args.beam_only:
            search = search_beam_only(
                benchmark.target,
                benchmark.config,
                seed=args.seed,
                profiler=profiler,
                beam_start_callback=beam_start,
                beam_progress_callback=beam_progress,
                beam_progress_interval_seconds=args.beam_progress_interval,
                phases=phases,
            )
        else:
            search = search_with_fallback(
                benchmark.target,
                benchmark.config,
                seed=args.seed,
                profiler=profiler,
                progress_callback=_benchmark_progress_printer(
                    progress_interval,
                    args.quiet,
                    total_generations=benchmark.config.evolution.max_generations
                    if suite_name == "expanded-targets"
                    else None,
                ),
                beam_start_callback=beam_start,
                beam_progress_callback=beam_progress,
                beam_progress_interval_seconds=args.beam_progress_interval,
                phases=phases,
            )
        results.append((benchmark, search))
        if args.verbose:
            print(render_benchmark_search_result(benchmark, search), flush=True)
        elif not args.quiet:
            print(f"  {_benchmark_status_line(search)}", flush=True)
    if not args.quiet:
        print()
        print(_summary_table(results))
        if args.profile:
            profile_lines = _aggregate_runtime_summary(results)
            if profile_lines:
                print()
                print("runtime summary:")
                print("\n".join(profile_lines))
    lean_export_path = None
    lean_check_result = None
    lean_theorems_exported = 0
    lean_theorems_skipped: tuple[str, ...] = ()
    if args.export_lean:
        lean_export_path, lean_check_result, lean_theorems_exported, lean_theorems_skipped = _export_benchmark_lean(
            suite_name,
            results,
            Path(args.lean_output),
            no_check=args.no_lean_check,
            lean_command=args.lean_command,
            quiet=args.quiet,
        )
    report_paths = ()
    if not args.no_report:
        profiler = RuntimeProfiler(enabled=True)
        with profiler.section("report_writing"):
            report_paths = write_report(
                _benchmark_report_payload(
                    suite_name,
                    results,
                    args.seed,
                    lean_export_path=lean_export_path,
                    lean_check_result=lean_check_result,
                    lean_theorems_exported=lean_theorems_exported,
                    lean_theorems_skipped=lean_theorems_skipped,
                ),
                report_dir=args.report_dir,
                stem=f"{suite_name}-{timestamp()}",
                report_format=args.report_format,
            )
        if not args.quiet:
            print(f"full report: {', '.join(str(path) for path in report_paths)}")
    if args.strict and any(not search.found for _benchmark, search in results):
        return 1
    if args.export_lean and suite_name == "small-targets" and (lean_theorems_exported != len(results) or (lean_check_result is not None and lean_check_result.returncode not in (None, 0))):
        return 1
    return 0


def _export_benchmark_lean(
    suite_name: str,
    results,
    output_path: Path,
    *,
    no_check: bool,
    lean_command: str,
    quiet: bool,
) -> tuple[Path | None, LeanCheckResult | None, int, tuple[str, ...]]:
    if suite_name != "small-targets":
        if not quiet:
            print("lean: skipped, benchmark Lean export is currently supported for --small-targets")
        return (None, None, 0, tuple(benchmark.name for benchmark, _search in results))
    failed = tuple(benchmark.name for benchmark, search in results if not search.found or search.proof is None)
    if failed:
        if not quiet:
            print(f"lean: skipped, missing proofs for {', '.join(failed)}")
        return (None, None, 0, failed)
    specs = tuple(
        LeanTheoremSpec(
            theorem_name=benchmark.name.replace("-", "_"),
            target=desugar(benchmark.target),
            proof=search.proof,
            surface_target=surface_pretty(benchmark.target),
            found_by=search.found_by,
            found_phase=search.solved_in_phase,
        )
        for benchmark, search in results
        if search.proof is not None
    )
    export = export_lean_suite(specs, output_path=output_path, suite_name=suite_name)
    write_lean_file(export)
    if not quiet:
        print("lean:")
        print(f"  wrote: {output_path}")
    if no_check:
        check_result = LeanCheckResult(False, None, None, "", "", skipped_reason="disabled by --no-lean-check")
    else:
        check_result = check_lean_file(output_path, lean_command=lean_command)
    if not quiet:
        if check_result.checked:
            print("  checked: yes")
        elif check_result.skipped_reason:
            print(f"  checked: skipped ({check_result.skipped_reason})")
        else:
            print("  checked: no")
            if check_result.stderr:
                print(check_result.stderr.strip())
        print(f"  theorems: {len(specs)}/{len(results)}")
    return (output_path, check_result, len(specs), ())


def _search_phases_for_benchmark(suite_name: str, benchmark: SearchBenchmark):
    if suite_name == "expanded-targets":
        return make_exhaustive_search_phases(benchmark.config)
    return None


def _selected_suite(args: argparse.Namespace) -> tuple[str, tuple[SearchBenchmark, ...]]:
    if args.suite == "expanded" or args.expanded_targets:
        return "expanded-targets", expanded_target_benchmarks()
    if args.suite == "small" or args.small_targets:
        return "small-targets", small_target_benchmarks()
    return "regression", regression_benchmarks()


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
        f"found by: {search.found_by or 'none'}",
        f"found generation: {_optional_number(search.found_generation)}",
        f"found beam layer: {_optional_number(search.found_beam_layer)}",
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
        provenance = search.found_by or "unknown"
        generation = _optional_number(search.found_generation)
        layer = _optional_number(search.found_beam_layer)
        return (
            f"{search.solved_in_phase}: FOUND by={provenance} gen={generation} beam_layer={layer} cd={best.cd_steps} "
            f"depth={best.cd_depth} size={best.proof_size} time={search.total_runtime_seconds:.1f}s"
        )
    best_closed = _candidate_summary_from_proof(search.best_closed_candidate, search)
    best_schematic = _candidate_summary_from_proof(search.best_schematic_candidate, search)
    return (
        f"not found phase=none best_sim={best.target_similarity:.2f} "
        f"best_closed={best_closed} best_schematic={best_schematic} "
        f"time={search.total_runtime_seconds:.1f}s"
    )


def _beam_start_printer():
    def callback(phase) -> None:
        print(
            f"  {phase.name}: building beam width={phase.beam_width} "
            f"depth={phase.beam_max_depth} pair_budget={phase.beam_pair_budget}",
            flush=True,
        )

    return callback


def _beam_progress_printer():
    def callback(phase: str, event) -> None:
        print(
            f"  beam d{event.depth}/{event.max_depth}: pool={event.pool_size} "
            f"pairs={event.pair_attempts}/{event.pair_budget} valid={event.valid_products} "
            f"closed={event.closed_products} schematic={event.schematic_products} "
            f"kept={event.kept_products} max_depth={event.max_cd_depth} "
            f"max_cd={event.max_cd_steps} time={event.elapsed_seconds:.1f}s",
            flush=True,
        )

    return callback


def _benchmark_progress_printer(interval: int, quiet: bool, total_generations: int | None = None):
    interval = max(1, interval)
    printed: set[tuple[str, int]] = set()

    def callback(phase: str, stats, elapsed: float) -> None:
        if quiet:
            return
        should_print = stats.generation == 0 or stats.best_exact or stats.generation % interval == 0
        if not should_print or (phase, stats.generation) in printed:
            return
        printed.add((phase, stats.generation))
        generation = _generation_progress_label(stats.generation, total_generations)
        if stats.best_exact:
            print(
                f"  gen {generation}: {phase} FOUND "
                f"best={stats.best_score:.1f} sim={stats.best_target_similarity:.2f} "
                f"exact={stats.exact_target_count} beam={stats.beam_valid_products} time={elapsed:.1f}s",
                flush=True,
            )
            return
        print(
            f"  gen {generation}: {phase} "
            f"best={stats.best_score:.1f} sim={stats.best_target_similarity:.2f} "
            f"exact={stats.exact_target_count} valid={stats.valid_fraction:.2f} "
            f"closed={stats.closed_fraction:.2f} beam={stats.beam_valid_products} time={elapsed:.1f}s",
            flush=True,
        )

    return callback


def _generation_progress_label(generation: int, total_generations: int | None) -> str:
    if total_generations is None:
        return str(generation)
    return f"{generation}/{total_generations}"


def _summary_table(results) -> str:
    lines = [
        "summary",
        f"{'name':38} {'found':5} {'phase':18} {'by':22} {'gen':>4} {'cd':>3} {'depth':>5} {'size':>5} {'runtime':>8}",
    ]
    for benchmark, search in results:
        best = search.result.best.fitness
        found = "yes" if search.found else "no"
        phase = search.solved_in_phase or "none"
        found_by = search.found_by or "-"
        generation = _optional_number(search.found_generation) if search.found else "-"
        cd = str(best.cd_steps) if search.found else "-"
        depth = str(best.cd_depth) if search.found else "-"
        size = str(best.proof_size) if search.found else "-"
        lines.append(
            f"{benchmark.name:38} {found:5} {phase:18} {found_by:22} {generation:>4} {cd:>3} {depth:>5} {size:>5} {search.total_runtime_seconds:>7.1f}s"
        )
        if not search.found:
            lines.append(f"  best similarity: {best.target_similarity:.3f}")
            lines.append(f"  best closed candidate: {_candidate_summary_from_proof(search.best_closed_candidate, search)}")
            lines.append(f"  best schematic candidate: {_candidate_summary_from_proof(search.best_schematic_candidate, search)}")
    return "\n".join(lines)


def _benchmark_report_payload(
    suite_name: str,
    results,
    seed: int | None,
    *,
    lean_export_path: Path | None = None,
    lean_check_result: LeanCheckResult | None = None,
    lean_theorems_exported: int = 0,
    lean_theorems_skipped: tuple[str, ...] = (),
) -> dict:
    return {
        "title": f"birdrat-proplogic benchmark: {suite_name}",
        "summary": [
            {
                "name": benchmark.name,
                "found": search.found,
                "solved_in_phase": search.solved_in_phase,
                "found_by": search.found_by,
                "found_generation": search.found_generation,
                "found_beam_layer": search.found_beam_layer,
                "runtime_seconds": search.total_runtime_seconds,
                "cd_steps": search.result.best.fitness.cd_steps,
                "cd_depth": search.result.best.fitness.cd_depth,
                "proof_size": search.result.best.fitness.proof_size,
                "target_similarity": search.result.best.fitness.target_similarity,
                "lean_export_path": lean_export_path,
                "lean_checked": lean_check_result.checked if lean_check_result else None,
                "lean_check_command": lean_check_result.command if lean_check_result else None,
                "lean_check_stdout": lean_check_result.stdout if lean_check_result else None,
                "lean_check_stderr": lean_check_result.stderr if lean_check_result else None,
                "lean_theorems_exported": lean_theorems_exported,
                "lean_theorems_skipped": lean_theorems_skipped,
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
                "found_by": search.found_by,
                "found_generation": search.found_generation,
                "found_beam_layer": search.found_beam_layer,
                "history": search.result.history,
                "beam_diagnostics": search.result.beam_diagnostics,
                "best_proof": proof_pretty(search.result.best.proof),
                "runtime_profile": search.runtime_profile,
            }
            for benchmark, search in results
        ],
        "lean_export_path": lean_export_path,
        "lean_checked": lean_check_result.checked if lean_check_result else None,
        "lean_check_command": lean_check_result.command if lean_check_result else None,
        "lean_check_stdout": lean_check_result.stdout if lean_check_result else None,
        "lean_check_stderr": lean_check_result.stderr if lean_check_result else None,
        "lean_theorems_exported": lean_theorems_exported,
        "lean_theorems_skipped": lean_theorems_skipped,
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
    if args.no_beam:
        evolution = replace(evolution, beam_enabled=False)
    if args.no_beam_stop_on_exact:
        evolution = replace(evolution, beam_stop_on_exact=False)
    return replace(benchmark, config=replace(benchmark.config, evolution=evolution))


def _optional_number(value: int | None) -> str:
    return "none" if value is None else str(value)


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


def _candidate_summary_from_proof(proof, search) -> str:
    if proof is None:
        return "none"
    fitness = total_fitness(proof, desugar(search.result.target), search.result.regions)
    return _candidate_text(fitness)


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
                f"    found by: {report.found_by or 'none'}",
                f"    found generation: {_optional_number(report.found_generation)}",
                f"    found beam layer: {_optional_number(report.found_beam_layer)}",
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
