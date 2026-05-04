from __future__ import annotations

import argparse
from dataclasses import replace
from time import perf_counter

from birdrat_proplogic.benchmarks import SearchBenchmark, small_target_benchmarks
from birdrat_proplogic.evolution import evolve
from birdrat_proplogic.fitness import total_fitness
from birdrat_proplogic.formula import is_closed_formula, pretty
from birdrat_proplogic.proof import Invalid
from birdrat_proplogic.quality import behavior_descriptor, novelty_score
from birdrat_proplogic.surface import desugar, surface_pretty


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m birdrat_proplogic.run_benchmarks")
    parser.add_argument("--small-targets", action="store_true", help="run the five small target-only benchmarks")
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--max-generations", type=int)
    parser.add_argument("--population-size", type=int)
    parser.add_argument("--beam-width", type=int)
    parser.add_argument("--beam-max-depth", type=int)
    parser.add_argument("--beam-major-budget", type=int)
    parser.add_argument("--beam-pair-budget", type=int)
    parser.add_argument("--keep-going", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    if not args.small_targets:
        parser.error("choose a benchmark suite, e.g. --small-targets")

    benchmarks = tuple(_override_config(benchmark, args) for benchmark in small_target_benchmarks())
    for index, benchmark in enumerate(benchmarks):
        if index:
            print()
        print(render_benchmark_result(benchmark, args.seed))
    return 0


def render_benchmark_result(benchmark: SearchBenchmark, seed: int | None = None) -> str:
    started = perf_counter()
    result = evolve(benchmark.target, benchmark.config, seed=seed)
    runtime = perf_counter() - started
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
        f"target: {surface_pretty(benchmark.target)}",
        f"core target: {pretty(desugar(benchmark.target))}",
        f"expected status: {benchmark.expected_status}",
        f"found exact proof: {best.exact_target}",
        f"best closed candidate: {_candidate_text(best_closed)}",
        f"best schematic candidate: {_candidate_text(best_schema)}",
        f"best novelty candidate: {_candidate_text(best_novelty)}",
        f"best score: {best.score:.6f}",
        f"target similarity: {best.target_similarity:.6f}",
        f"proof CD steps: {best.cd_steps}",
        f"proof CD depth: {best.cd_depth}",
        f"proof size: {best.proof_size}",
        f"formula size: {best.formula_size}",
        f"runtime: {runtime:.3f}s",
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
    ]
    return "\n".join(lines)


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


if __name__ == "__main__":
    raise SystemExit(main())
