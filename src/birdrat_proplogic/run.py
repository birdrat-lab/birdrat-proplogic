from __future__ import annotations

import argparse
from dataclasses import dataclass, replace

from birdrat_proplogic.archive import archive_size
from birdrat_proplogic.config import ArchiveConfig, EvolutionConfig, ProplogicConfig
from birdrat_proplogic.evolution import EvolutionResult, GenerationStats, evolve
from birdrat_proplogic.formula import pretty
from birdrat_proplogic.goals import Goal
from birdrat_proplogic.parse import ParseError, parse_surface
from birdrat_proplogic.proof import Invalid, proof_pretty
from birdrat_proplogic.profiling import RuntimeProfiler, compact_runtime_summary
from birdrat_proplogic.reporting import timestamp, write_report
from birdrat_proplogic.search import SearchResult, search_with_fallback
from birdrat_proplogic.surface import SAnd, SAtom, SImp, SurfaceFormula, desugar, surface_display, surface_pretty, surface_sequent_pretty


@dataclass(frozen=True)
class SearchReport:
    result: EvolutionResult
    search_result: SearchResult | None = None


def conjunction_commutativity_target() -> SurfaceFormula:
    a = SAtom("a")
    b = SAtom("b")
    return SImp(SAnd(a, b), SAnd(b, a))


def run_search(
    theorem: SurfaceFormula,
    config: ProplogicConfig,
    seed: int | None = None,
    progress_callback=None,
    profiler: RuntimeProfiler | None = None,
) -> SearchReport:
    search_result = search_with_fallback(
        theorem,
        config=config,
        seed=seed,
        progress_callback=progress_callback,
        profiler=profiler,
    )
    return SearchReport(result=search_result.result, search_result=search_result)


def render_search_report(report: SearchReport) -> str:
    result = report.result
    best = result.best
    best_fitness = best.fitness
    display_regions = _unique_regions_by_theorem(result.regions)
    conclusion = best_fitness.conclusion
    if isinstance(conclusion, Invalid):
        conclusion_text = f"invalid: {conclusion.reason}"
    else:
        conclusion_text = pretty(conclusion)

    lines = [
        "surface target:",
        *[f"  {line}" for line in surface_display(result.target).splitlines()],
        "",
        "core target:",
        f"  {pretty(desugar(result.target))}",
        "",
        "generated regions:",
    ]
    lines.extend(f"  {surface_pretty(region.theorem())}" for region in display_regions)
    lines.extend(
        [
            "",
            "search:",
            f"  generations: {len(result.history)}",
            f"  solved in phase: {report.search_result.solved_in_phase if report.search_result else 'n/a'}",
            f"  active depth: {_depth_summary(result)}",
            f"  archive formulas: {len(result.archive)}",
            f"  archive proofs: {archive_size(result.archive)}",
            "",
            "diagnostics:",
            *_diagnostic_lines(result),
            "",
            "best candidate:",
            f"  exact target: {_found_text(best_fitness.exact_target)}",
            f"  valid: {best_fitness.valid}",
            f"  score: {best_fitness.score:.6f}",
            f"  target similarity: {best_fitness.target_similarity:.6f}",
            f"  best region similarity: {best_fitness.region_similarity:.6f}",
            f"  region: {surface_pretty(best_fitness.exact_region.theorem()) if best_fitness.exact_region else 'none'}",
            f"  conclusion: {conclusion_text}",
            f"  cd_steps: {best_fitness.cd_steps}",
            f"  cd_depth: {best_fitness.cd_depth}",
            f"  proof_size: {best_fitness.proof_size}",
            f"  formula_size: {best_fitness.formula_size}",
            "",
            "proof:",
        ]
    )
    lines.extend(f"  {line}" for line in proof_pretty(best.proof).splitlines())
    return "\n".join(lines)


def _depth_summary(result: EvolutionResult) -> str:
    if not result.history:
        return "none"
    depths = tuple(item.active_proof_depth for item in result.history)
    if min(depths) == max(depths):
        return str(depths[0])
    return f"{min(depths)}..{max(depths)}"


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="birdrat-proplogic")
    parser.add_argument("theorem", help="surface theorem, e.g. 'a \\land b -> b \\land a'")
    parser.add_argument("--seed", type=int)
    parser.add_argument("--population-size", type=int)
    parser.add_argument("--max-generations", type=int)
    parser.add_argument("--elite-count", type=int)
    parser.add_argument("--tournament-size", type=int)
    parser.add_argument("--initial-proof-depth", type=int)
    parser.add_argument("--max-proof-depth", type=int)
    parser.add_argument("--iterative-deepening-budget", type=int)
    parser.add_argument("--iterative-deepening-scale", type=float)
    parser.add_argument("--diagnostics-interval", type=int)
    parser.add_argument("--beam-width", type=int)
    parser.add_argument("--beam-max-depth", type=int)
    parser.add_argument("--beam-major-budget", type=int)
    parser.add_argument("--beam-pair-budget", type=int)
    parser.add_argument("--no-beam", action="store_true")
    parser.add_argument("--archive-path")
    parser.add_argument("--no-archive", action="store_true")
    parser.add_argument("--no-load-archive", action="store_true")
    parser.add_argument("--no-save-archive", action="store_true")
    parser.add_argument("--keep-going", action="store_true", help="continue through max generations after exact success")
    parser.add_argument("--progress-interval", type=int, default=10)
    parser.add_argument("--report-dir", default="reports/runs")
    parser.add_argument("--report-format", choices=("json", "md", "both"), default="json")
    parser.add_argument("--no-report", action="store_true")
    parser.add_argument("--profile", action="store_true")
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    profiler = RuntimeProfiler(enabled=True)
    with profiler.section("parse_surface"):
        parsed = parse_surface(args.theorem)
    if isinstance(parsed, ParseError):
        parser.error(parsed.message)

    config = _config_from_args(args)
    if not args.quiet:
        print(f"target: {surface_sequent_pretty(parsed)}")
        print(f"core target: {pretty(desugar(parsed))}")
    report = run_search(
        parsed,
        config,
        args.seed,
        progress_callback=_progress_printer(args.progress_interval, args.quiet),
        profiler=profiler,
    )
    search = report.search_result
    assert search is not None
    if args.verbose:
        print(render_search_report(report))
    else:
        print(render_compact_search_summary(report))
    if args.profile and not args.quiet:
        _print_runtime_summary(search)
    if not args.no_report:
        with profiler.section("report_writing"):
            paths = write_report(
                _run_report_payload(report, args.seed, config),
                report_dir=args.report_dir,
                stem=f"run-{timestamp()}",
                report_format=args.report_format,
            )
        if not args.quiet:
            print(f"full report: {', '.join(str(path) for path in paths)}")
    return 0


def render_compact_search_summary(report: SearchReport) -> str:
    search = report.search_result
    result = report.result
    best = result.best.fitness
    lines = [
        "",
        "summary:",
        f"  found: {'yes' if search and search.found else 'no'}",
        f"  phase: {search.solved_in_phase if search and search.solved_in_phase else 'none'}",
        f"  best similarity: {best.target_similarity:.3f}",
        f"  cd: {best.cd_steps}",
        f"  depth: {best.cd_depth}",
        f"  size: {best.proof_size}",
        f"  runtime: {search.total_runtime_seconds:.3f}s" if search else "  runtime: n/a",
    ]
    if not best.exact_target:
        conclusion = best.conclusion
        lines.append(f"  best conclusion: {'invalid' if isinstance(conclusion, Invalid) else pretty(conclusion)}")
    return "\n".join(lines)


def _progress_printer(interval: int, quiet: bool):
    interval = max(1, interval)
    printed: set[tuple[str, int]] = set()

    def callback(phase: str, stats: GenerationStats, elapsed: float) -> None:
        if quiet:
            return
        should_print = stats.generation == 0 or stats.best_exact or stats.generation % interval == 0
        if not should_print or (phase, stats.generation) in printed:
            return
        printed.add((phase, stats.generation))
        if stats.best_exact:
            print(
                f"gen {stats.generation}: phase={phase} FOUND exact proof "
                f"cd={stats.mean_cd_steps:.1f} depth={stats.active_proof_depth} time={elapsed:.1f}s"
            )
            return
        print(
            f"gen {stats.generation}: phase={phase} best={stats.best_score:.1f} "
            f"sim={stats.best_target_similarity:.2f} exact={stats.exact_target_count} valid={stats.valid_fraction:.2f} "
            f"closed={stats.closed_fraction:.2f} beam={stats.beam_valid_products} time={elapsed:.1f}s"
        )

    return callback


def _print_runtime_summary(search: SearchResult) -> None:
    lines = compact_runtime_summary(search.runtime_profile)
    if not lines:
        return
    print("runtime summary:")
    print("\n".join(lines))


def _run_report_payload(report: SearchReport, seed: int | None, config: ProplogicConfig) -> dict:
    search = report.search_result
    result = report.result
    best = result.best
    return {
        "title": "birdrat-proplogic run",
        "summary": {
            "surface_target": surface_pretty(result.target),
            "surface_sequent": surface_sequent_pretty(result.target),
            "surface_display": surface_display(result.target),
            "core_target": pretty(desugar(result.target)),
            "found": search.found if search else False,
            "solved_in_phase": search.solved_in_phase if search else None,
            "runtime_seconds": search.total_runtime_seconds if search else None,
            "best_score": best.fitness.score,
            "target_similarity": best.fitness.target_similarity,
            "cd_steps": best.fitness.cd_steps,
            "cd_depth": best.fitness.cd_depth,
            "proof_size": best.fitness.proof_size,
        },
        "seed": seed,
        "config": config,
        "target": result.target,
        "target_display": surface_display(result.target),
        "core_target": desugar(result.target),
        "regions": tuple(region.theorem() for region in result.regions),
        "search_result": search,
        "history": result.history,
        "beam_diagnostics": result.beam_diagnostics,
        "best_proof": proof_pretty(best.proof),
        "runtime_profile": search.runtime_profile if search else None,
    }


def _config_from_args(args: argparse.Namespace) -> ProplogicConfig:
    config = ProplogicConfig()
    evolution = config.evolution
    for arg_name, field_name in (
        ("population_size", "population_size"),
        ("max_generations", "max_generations"),
        ("elite_count", "elite_count"),
        ("tournament_size", "tournament_size"),
        ("initial_proof_depth", "initial_proof_depth"),
        ("max_proof_depth", "max_proof_depth"),
        ("iterative_deepening_budget", "iterative_deepening_budget"),
        ("iterative_deepening_scale", "iterative_deepening_scale"),
        ("diagnostics_interval", "diagnostics_interval"),
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

    archive = config.archive
    if args.no_archive:
        archive = ArchiveConfig(path=None)
    else:
        if args.archive_path is not None:
            archive = replace(archive, path=args.archive_path)
        if args.no_load_archive:
            archive = replace(archive, load_on_start=False)
        if args.no_save_archive:
            archive = replace(archive, save_on_finish=False)

    return replace(config, evolution=evolution, archive=archive)


def _unique_regions_by_theorem(regions: tuple[Goal, ...]) -> tuple[Goal, ...]:
    seen: set[SurfaceFormula] = set()
    unique: list[Goal] = []
    for region in regions:
        theorem = region.theorem()
        if theorem in seen:
            continue
        seen.add(theorem)
        unique.append(region)
    return tuple(unique)


def _diagnostic_lines(result: EvolutionResult) -> list[str]:
    if not result.history:
        return ["  none"]
    interval = max(1, result.diagnostics_interval)
    selected = [result.history[0]]
    selected.extend(item for item in result.history[1:-1] if item.generation % interval == 0)
    if result.history[-1] not in selected:
        selected.append(result.history[-1])
    return [
        (
            f"  gen {item.generation}: depth={item.active_proof_depth}, "
            f"valid={item.valid_fraction:.2f}, exact_target={item.exact_target_count}, "
            f"exact_region={item.exact_region_count}, best={item.best_score:.3f}, "
            f"closed={item.closed_fraction:.2f}, schematic={item.schematic_fraction:.2f}, "
            f"behaviors={item.unique_behavior_count}, behavior_archive={item.behavior_archive_size}, "
            f"schema_archive={item.schema_archive_size}, immigrants={item.random_immigrant_count}, "
            f"schema_instantiations={item.instantiated_schema_products}, "
            f"beam={item.beam_pool_size}, beam_pairs={item.beam_pair_attempts}/{item.beam_pair_budget}, "
            f"beam_valid={item.beam_valid_products}, "
            f"mean_cd={item.mean_cd_steps:.2f}, mean_substantive_cd={item.mean_substantive_cd_steps:.2f}, "
            f"mean_size={item.mean_proof_size:.2f}, mean_formula={item.mean_formula_size:.2f}, "
            f"best_conclusion={item.best_conclusion}, "
            f"beam_layers={';'.join(item.beam_layer_counts) if item.beam_layer_counts else 'none'}"
        )
        for item in selected
    ]


def _found_text(found: bool) -> str:
    if found:
        return "found"
    return "not found"


if __name__ == "__main__":
    raise SystemExit(main())
