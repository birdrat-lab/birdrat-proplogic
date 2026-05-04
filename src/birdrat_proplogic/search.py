from __future__ import annotations

from dataclasses import dataclass, replace
from math import ceil
from time import perf_counter
from typing import Callable

from birdrat_proplogic.config import ProplogicConfig
from birdrat_proplogic.evolution import EvolutionResult, GenerationStats, evolve
from birdrat_proplogic.fitness import FitnessResult, total_fitness
from birdrat_proplogic.formula import is_closed_formula
from birdrat_proplogic.proof import Invalid, Proof
from birdrat_proplogic.profiling import RuntimeProfile, RuntimeProfiler
from birdrat_proplogic.quality import behavior_descriptor, novelty_score
from birdrat_proplogic.surface import SurfaceFormula, desugar


@dataclass(frozen=True)
class SearchPhase:
    name: str
    beam_width: int
    beam_max_depth: int
    beam_pair_budget: int
    prioritized_fraction: float
    suffix_fraction: float
    exploratory_fraction: float
    population_size: int
    generations: int


@dataclass(frozen=True)
class PhaseReport:
    phase_name: str
    found_exact: bool
    best_exact_proof: Proof | None
    best_closed_candidate: Proof | None
    best_schematic_candidate: Proof | None
    best_novelty_candidate: Proof | None
    best_score: float
    target_similarity: float
    runtime_seconds: float
    beam_pair_attempts: int
    beam_valid_products: int
    beam_layer_counts: tuple
    population_size: int
    generations: int
    result: EvolutionResult


@dataclass(frozen=True)
class SearchResult:
    found: bool
    proof: Proof | None
    solved_in_phase: str | None
    phase_reports: tuple[PhaseReport, ...]
    best_closed_candidate: Proof | None
    best_schematic_candidate: Proof | None
    best_novelty_candidate: Proof | None
    total_runtime_seconds: float
    result: EvolutionResult
    runtime_profile: RuntimeProfile


def make_default_search_phases(base_config: ProplogicConfig) -> tuple[SearchPhase, ...]:
    evolution = base_config.evolution
    return (
        SearchPhase(
            name="strict-preselected",
            beam_width=evolution.beam_width,
            beam_max_depth=evolution.beam_max_depth,
            beam_pair_budget=evolution.beam_pair_budget,
            prioritized_fraction=1.0,
            suffix_fraction=0.0,
            exploratory_fraction=0.0,
            population_size=evolution.population_size,
            generations=evolution.max_generations,
        ),
        SearchPhase(
            name="hybrid",
            beam_width=evolution.beam_width,
            beam_max_depth=evolution.beam_max_depth,
            beam_pair_budget=evolution.beam_pair_budget,
            prioritized_fraction=1.0,
            suffix_fraction=0.20,
            exploratory_fraction=0.10,
            population_size=evolution.population_size,
            generations=evolution.max_generations,
        ),
        SearchPhase(
            name="expanded-hybrid",
            beam_width=max(evolution.beam_width, ceil(1.5 * evolution.beam_width)),
            beam_max_depth=evolution.beam_max_depth + 1,
            beam_pair_budget=2 * evolution.beam_pair_budget,
            prioritized_fraction=1.0,
            suffix_fraction=0.25,
            exploratory_fraction=0.15,
            population_size=evolution.population_size,
            generations=evolution.max_generations,
        ),
    )


def search_with_fallback(
    target: SurfaceFormula,
    config: ProplogicConfig,
    seed: int | None = None,
    progress_callback: Callable[[str, GenerationStats, float], None] | None = None,
    profiler: RuntimeProfiler | None = None,
) -> SearchResult:
    started = perf_counter()
    profiler = profiler or RuntimeProfiler(enabled=False)
    reports: list[PhaseReport] = []
    for index, phase in enumerate(make_default_search_phases(config)):
        phase_seed = None if seed is None else seed + index * 1_000_003
        phase_config = _config_for_phase(config, phase)
        phase_started = perf_counter()
        result = evolve(
            target,
            phase_config,
            seed=phase_seed,
            progress_callback=(
                None
                if progress_callback is None
                else lambda stats, elapsed, phase_name=phase.name: progress_callback(phase_name, stats, elapsed)
            ),
            profiler=profiler,
        )
        runtime = perf_counter() - phase_started
        report = _phase_report(phase.name, result, phase_config, runtime)
        reports.append(report)
        if report.found_exact:
            runtime_total = perf_counter() - started
            profiler.add_time("total", runtime_total)
            return _search_result(tuple(reports), runtime_total, profiler.snapshot())
    runtime_total = perf_counter() - started
    profiler.add_time("total", runtime_total)
    return _search_result(tuple(reports), runtime_total, profiler.snapshot())


def _config_for_phase(config: ProplogicConfig, phase: SearchPhase) -> ProplogicConfig:
    _validate_phase(phase)
    evolution = replace(
        config.evolution,
        beam_width=phase.beam_width,
        beam_max_depth=phase.beam_max_depth,
        beam_pair_budget=phase.beam_pair_budget,
        beam_prioritized_fraction=phase.prioritized_fraction,
        beam_suffix_fraction=phase.suffix_fraction,
        beam_exploratory_fraction=phase.exploratory_fraction,
        population_size=phase.population_size,
        max_generations=phase.generations,
    )
    return replace(config, evolution=evolution)


def _validate_phase(phase: SearchPhase) -> None:
    fractions = (phase.prioritized_fraction, phase.suffix_fraction, phase.exploratory_fraction)
    if any(item < 0 for item in fractions):
        raise ValueError(f"negative search phase fraction: {phase.name}")
    if sum(fractions) <= 0:
        raise ValueError(f"search phase fractions sum to zero: {phase.name}")


def _phase_report(
    phase_name: str,
    result: EvolutionResult,
    config: ProplogicConfig,
    runtime_seconds: float,
) -> PhaseReport:
    target = desugar(result.target)
    fitnesses = tuple(total_fitness(proof, target, result.regions, config) for proof in result.population)
    best_closed = _best_closed_candidate(result.population, fitnesses)
    best_schema = _best_schema_candidate(result.population, fitnesses)
    best_novelty = _best_novelty_candidate(result.population, fitnesses)
    best = result.best.fitness
    return PhaseReport(
        phase_name=phase_name,
        found_exact=best.exact_target,
        best_exact_proof=result.best.proof if best.exact_target else None,
        best_closed_candidate=best_closed,
        best_schematic_candidate=best_schema,
        best_novelty_candidate=best_novelty,
        best_score=best.score,
        target_similarity=best.target_similarity,
        runtime_seconds=runtime_seconds,
        beam_pair_attempts=result.beam_diagnostics.pair_attempts,
        beam_valid_products=result.beam_diagnostics.valid_products,
        beam_layer_counts=result.beam_diagnostics.layer_counts,
        population_size=config.evolution.population_size,
        generations=len(result.history),
        result=result,
    )


def _search_result(reports: tuple[PhaseReport, ...], runtime_seconds: float, runtime_profile: RuntimeProfile) -> SearchResult:
    solved = next((report for report in reports if report.found_exact), None)
    final_report = solved if solved is not None else max(reports, key=lambda report: report.best_score)
    return SearchResult(
        found=solved is not None,
        proof=solved.best_exact_proof if solved is not None else None,
        solved_in_phase=solved.phase_name if solved is not None else None,
        phase_reports=reports,
        best_closed_candidate=_best_report_candidate(reports, "best_closed_candidate"),
        best_schematic_candidate=_best_report_candidate(reports, "best_schematic_candidate"),
        best_novelty_candidate=_best_report_candidate(reports, "best_novelty_candidate"),
        total_runtime_seconds=runtime_seconds,
        result=final_report.result,
        runtime_profile=runtime_profile,
    )


def _best_report_candidate(reports: tuple[PhaseReport, ...], field_name: str) -> Proof | None:
    candidates = [getattr(report, field_name) for report in reports if getattr(report, field_name) is not None]
    if not candidates:
        return None
    return candidates[0]


def _best_closed_candidate(proofs: tuple[Proof, ...], fitnesses: tuple[FitnessResult, ...]) -> Proof | None:
    candidates = [
        (proof, fitness)
        for proof, fitness in zip(proofs, fitnesses)
        if fitness.valid and not isinstance(fitness.conclusion, Invalid) and is_closed_formula(fitness.conclusion)
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda item: item[1].score)[0]


def _best_schema_candidate(proofs: tuple[Proof, ...], fitnesses: tuple[FitnessResult, ...]) -> Proof | None:
    candidates = [
        (proof, fitness)
        for proof, fitness in zip(proofs, fitnesses)
        if fitness.valid and not isinstance(fitness.conclusion, Invalid) and not is_closed_formula(fitness.conclusion)
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda item: item[1].score)[0]


def _best_novelty_candidate(proofs: tuple[Proof, ...], fitnesses: tuple[FitnessResult, ...]) -> Proof | None:
    descriptors = tuple(
        behavior_descriptor(proof, fitness.conclusion)
        for proof, fitness in zip(proofs, fitnesses)
    )
    if not descriptors:
        return None
    archive = descriptors[: max(1, len(descriptors) // 2)]
    index = max(range(len(descriptors)), key=lambda item: novelty_score(descriptors[item], archive))
    return proofs[index]
