from __future__ import annotations

from dataclasses import dataclass, replace
from random import Random

from birdrat_proplogic.archive import ProofArchive, empty_archive, update_archive
from birdrat_proplogic.config import DEFAULT_CONFIG, ProplogicConfig
from birdrat_proplogic.crossover import crossover_proof
from birdrat_proplogic.fitness import FitnessResult, total_fitness
from birdrat_proplogic.formula import Formula, pretty
from birdrat_proplogic.goals import Goal, extract_goals
from birdrat_proplogic.lib.archive_json import load_archive_json, save_archive_json
from birdrat_proplogic.mutate import mutate_proof
from birdrat_proplogic.proof import Invalid, Proof
from birdrat_proplogic.seed import formula_pool_from_target, initialize_population_from_target
from birdrat_proplogic.surface import SurfaceFormula, desugar


@dataclass(frozen=True)
class ScoredProof:
    proof: Proof
    fitness: FitnessResult


@dataclass(frozen=True)
class GenerationStats:
    generation: int
    active_proof_depth: int
    best_score: float
    best_conclusion: str
    best_exact: bool
    best_valid: bool
    valid_fraction: float
    exact_target_count: int
    exact_region_count: int
    mean_cd_steps: float
    mean_cd_depth: float
    mean_proof_size: float
    mean_formula_size: float


@dataclass(frozen=True)
class EvolutionResult:
    target: SurfaceFormula
    regions: tuple[Goal, ...]
    archive: ProofArchive
    population: tuple[Proof, ...]
    best: ScoredProof
    history: tuple[GenerationStats, ...]
    diagnostics_interval: int


def evolve(
    target: SurfaceFormula,
    config: ProplogicConfig = DEFAULT_CONFIG,
    rng: Random | None = None,
    seed: int | None = None,
) -> EvolutionResult:
    random = _make_rng(rng, seed)
    evolution_config = config.evolution
    regions = extract_goals(target, config)
    core_target = desugar(target)
    active_depth = _active_depth(0, config)
    active_config = _config_for_depth(config, active_depth)
    region_targets = tuple(region.core_theorem() for region in regions)
    formula_pool = formula_pool_from_target(core_target, region_targets)
    population = tuple(
        initialize_population_from_target(
            random,
            core_target,
            region_targets,
            evolution_config.population_size,
            max_formula_depth=active_config.mutation.random_formula_depth,
            config=active_config,
        )
    )
    history: list[GenerationStats] = []
    archive = _load_archive(config)

    scored = _score_population(population, core_target, regions, active_config)
    best = scored[0]

    for generation in range(evolution_config.max_generations):
        active_depth = _active_depth(generation, config)
        active_config = _config_for_depth(config, active_depth)
        scored = _score_population(population, core_target, regions, active_config)
        archive = update_archive(archive, _archive_items(scored), active_config)
        best = max(best, scored[0], key=lambda item: item.fitness.score)
        history.append(_generation_stats(generation, active_depth, scored))

        if evolution_config.stop_on_exact and scored[0].fitness.exact_target:
            break

        elite_count = min(evolution_config.elite_count, evolution_config.population_size)
        elites = tuple(item.proof for item in scored[:elite_count])
        children = _make_children(scored, active_config, random, formula_pool)
        population = (elites + children)[: evolution_config.population_size]

    final_scored = _score_population(population, core_target, regions, _config_for_depth(config, active_depth))
    archive = update_archive(archive, _archive_items(final_scored), _config_for_depth(config, active_depth))
    best = max(best, final_scored[0], key=lambda item: item.fitness.score)
    _save_archive(archive, config)
    return EvolutionResult(
        target=target,
        regions=regions,
        archive=archive,
        population=population,
        best=best,
        history=tuple(history),
        diagnostics_interval=evolution_config.diagnostics_interval,
    )


def _make_children(
    scored: tuple[ScoredProof, ...],
    config: ProplogicConfig,
    rng: Random,
    formula_pool: tuple[Formula, ...],
) -> tuple[Proof, ...]:
    evolution_config = config.evolution
    child_count = max(0, evolution_config.population_size - evolution_config.elite_count)
    children: list[Proof] = []
    while len(children) < child_count:
        parent1 = _tournament(scored, evolution_config.tournament_size, rng).proof
        parent2 = _tournament(scored, evolution_config.tournament_size, rng).proof
        if rng.random() < evolution_config.crossover_rate:
            child = crossover_proof(parent1, parent2, rng)
        else:
            child = parent1
        if rng.random() < evolution_config.mutation_rate:
            child = mutate_proof(child, rng, config, formula_pool)
        children.append(child)
    return tuple(children)


def _score_population(
    population: tuple[Proof, ...],
    target: Formula,
    regions: tuple[Goal, ...],
    config: ProplogicConfig,
) -> tuple[ScoredProof, ...]:
    scored = tuple(
        ScoredProof(proof=proof, fitness=total_fitness(proof, target, regions, config))
        for proof in population
    )
    return tuple(sorted(scored, key=lambda item: item.fitness.score, reverse=True))


def _archive_items(scored: tuple[ScoredProof, ...]) -> tuple[tuple[Proof, FitnessResult], ...]:
    return tuple((item.proof, item.fitness) for item in scored)


def _tournament(scored: tuple[ScoredProof, ...], size: int, rng: Random) -> ScoredProof:
    sample_size = min(size, len(scored))
    contestants = rng.sample(scored, sample_size)
    return max(contestants, key=lambda item: item.fitness.score)


def _active_depth(generation: int, config: ProplogicConfig) -> int:
    evolution_config = config.evolution
    depth = evolution_config.initial_proof_depth
    spent = 0
    while depth < evolution_config.max_proof_depth:
        next_spent = spent + _depth_budget(depth, evolution_config.initial_proof_depth, config)
        if generation < next_spent:
            return depth
        spent = next_spent
        depth += 1
    return evolution_config.max_proof_depth


def _depth_budget(depth: int, initial_depth: int, config: ProplogicConfig) -> int:
    evolution_config = config.evolution
    base_budget = max(1, evolution_config.iterative_deepening_budget)
    scale = max(1.0, evolution_config.iterative_deepening_scale)
    depth_offset = max(0, depth - initial_depth)
    return max(1, round(base_budget * (scale**depth_offset)))


def _config_for_depth(config: ProplogicConfig, depth: int) -> ProplogicConfig:
    return replace(
        config,
        fitness=replace(config.fitness, adaptive_cd_depth_threshold=depth),
        mutation=replace(config.mutation, random_proof_depth=depth),
    )


def _generation_stats(generation: int, active_depth: int, scored: tuple[ScoredProof, ...]) -> GenerationStats:
    best = scored[0]
    best_conclusion = best.fitness.conclusion
    if isinstance(best_conclusion, Invalid):
        best_conclusion_text = f"invalid: {best_conclusion.reason}"
    else:
        best_conclusion_text = pretty(best_conclusion)
    count = len(scored)
    return GenerationStats(
        generation=generation,
        active_proof_depth=active_depth,
        best_score=best.fitness.score,
        best_conclusion=best_conclusion_text,
        best_exact=best.fitness.exact_target,
        best_valid=best.fitness.valid,
        valid_fraction=sum(1 for item in scored if item.fitness.valid) / count,
        exact_target_count=sum(1 for item in scored if item.fitness.exact_target),
        exact_region_count=sum(1 for item in scored if item.fitness.exact_region is not None),
        mean_cd_steps=sum(item.fitness.cd_steps for item in scored) / count,
        mean_cd_depth=sum(item.fitness.cd_depth for item in scored) / count,
        mean_proof_size=sum(item.fitness.proof_size for item in scored) / count,
        mean_formula_size=sum(item.fitness.formula_size for item in scored) / count,
    )


def _make_rng(rng: Random | None, seed: int | None) -> Random:
    if rng is not None:
        return rng
    return Random(seed)


def _load_archive(config: ProplogicConfig) -> ProofArchive:
    archive_config = config.archive
    if not archive_config.path or not archive_config.load_on_start:
        return empty_archive()
    return load_archive_json(archive_config.path, config)


def _save_archive(archive: ProofArchive, config: ProplogicConfig) -> None:
    archive_config = config.archive
    if not archive_config.path or not archive_config.save_on_finish:
        return
    save_archive_json(archive, archive_config.path)
