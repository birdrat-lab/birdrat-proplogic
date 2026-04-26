from __future__ import annotations

import argparse
from dataclasses import dataclass, replace

from birdrat_proplogic.archive import archive_size
from birdrat_proplogic.config import ArchiveConfig, EvolutionConfig, ProplogicConfig
from birdrat_proplogic.evolution import EvolutionResult, evolve
from birdrat_proplogic.formula import pretty
from birdrat_proplogic.goals import Goal
from birdrat_proplogic.parse import ParseError, parse_surface
from birdrat_proplogic.proof import Invalid, proof_pretty
from birdrat_proplogic.surface import SAnd, SAtom, SImp, SurfaceFormula, desugar, surface_pretty


@dataclass(frozen=True)
class SearchReport:
    result: EvolutionResult


def conjunction_commutativity_target() -> SurfaceFormula:
    a = SAtom("a")
    b = SAtom("b")
    return SImp(SAnd(a, b), SAnd(b, a))


def run_search(
    theorem: SurfaceFormula,
    config: ProplogicConfig,
    seed: int | None = None,
) -> SearchReport:
    return SearchReport(result=evolve(theorem, config=config, seed=seed))


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
        f"  {surface_pretty(result.target)}",
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
            f"  active depth: {_depth_summary(result)}",
            f"  archive formulas: {len(result.archive)}",
            f"  archive proofs: {archive_size(result.archive)}",
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
    parser.add_argument("--archive-path")
    parser.add_argument("--no-archive", action="store_true")
    parser.add_argument("--no-load-archive", action="store_true")
    parser.add_argument("--no-save-archive", action="store_true")
    parser.add_argument("--keep-going", action="store_true", help="continue through max generations after exact success")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    parsed = parse_surface(args.theorem)
    if isinstance(parsed, ParseError):
        parser.error(parsed.message)

    config = _config_from_args(args)
    report = run_search(parsed, config, args.seed)
    print(render_search_report(report))
    return 0


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
    ):
        value = getattr(args, arg_name)
        if value is not None:
            evolution = replace(evolution, **{field_name: value})
    if args.keep_going:
        evolution = replace(evolution, stop_on_exact=False)

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


def _found_text(found: bool) -> str:
    if found:
        return "found"
    return "not found"


if __name__ == "__main__":
    raise SystemExit(main())
