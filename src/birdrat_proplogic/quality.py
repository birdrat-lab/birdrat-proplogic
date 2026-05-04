from __future__ import annotations

from dataclasses import dataclass
from random import Random

from birdrat_proplogic.config import DEFAULT_CONFIG, ProplogicConfig
from birdrat_proplogic.fitness import FitnessResult, total_fitness
from birdrat_proplogic.formula import Atom, Formula, Imp, Meta, Not, is_closed_formula, metas
from birdrat_proplogic.goals import Goal
from birdrat_proplogic.proof import (
    Ax1,
    Ax2,
    Ax3,
    CD,
    Invalid,
    Proof,
    cd_depth,
    cd_steps,
    conclusion,
    substantive_cd_steps,
)
from birdrat_proplogic.seed import random_seeded_axiom
from birdrat_proplogic.unify import UnifyFailure, apply_subst, unify


@dataclass(frozen=True)
class BehaviorDescriptor:
    closed: bool
    root_symbol: str
    implication_spine_length: int
    final_head_shape: str
    atom_set: frozenset[str]
    meta_count: int
    cd_steps: int
    substantive_cd_steps: int
    proof_depth: int
    axiom_counts: tuple[int, int, int]
    normalized_skeleton: str


@dataclass(frozen=True)
class QualityArchives:
    schema_archive: tuple[Proof, ...] = ()
    behavior_archive: tuple[BehaviorDescriptor, ...] = ()


@dataclass(frozen=True)
class QualitySelectionResult:
    population: tuple[Proof, ...]
    target_elites: tuple[Proof, ...]
    region_elites: tuple[Proof, ...]
    novelty_elites: tuple[Proof, ...]
    schema_elites: tuple[Proof, ...]
    random_immigrants: tuple[Proof, ...]
    promoted: tuple[Proof, ...]


def behavior_descriptor(proof: Proof, proof_conclusion: Formula | Invalid | None = None) -> BehaviorDescriptor:
    if proof_conclusion is None:
        proof_conclusion = conclusion(proof)
    if isinstance(proof_conclusion, Invalid):
        return BehaviorDescriptor(
            closed=False,
            root_symbol="invalid",
            implication_spine_length=0,
            final_head_shape="invalid",
            atom_set=frozenset(),
            meta_count=0,
            cd_steps=cd_steps(proof),
            substantive_cd_steps=substantive_cd_steps(proof),
            proof_depth=cd_depth(proof),
            axiom_counts=axiom_counts(proof),
            normalized_skeleton="invalid",
        )

    antecedents, final_head = implication_spine(proof_conclusion)
    return BehaviorDescriptor(
        closed=is_closed_formula(proof_conclusion),
        root_symbol=root_symbol(proof_conclusion),
        implication_spine_length=len(antecedents),
        final_head_shape=normalized_skeleton(final_head),
        atom_set=atoms(proof_conclusion),
        meta_count=len(metas(proof_conclusion)),
        cd_steps=cd_steps(proof),
        substantive_cd_steps=substantive_cd_steps(proof),
        proof_depth=cd_depth(proof),
        axiom_counts=axiom_counts(proof),
        normalized_skeleton=normalized_skeleton(proof_conclusion),
    )


def novelty_score(
    descriptor: BehaviorDescriptor,
    archive: tuple[BehaviorDescriptor, ...],
    *,
    k: int = 5,
) -> float:
    if not archive:
        return 1.0
    nearest_count = min(max(1, k), len(archive))
    distances = sorted(behavior_distance(descriptor, archived) for archived in archive)
    return sum(distances[:nearest_count]) / nearest_count


def behavior_distance(left: BehaviorDescriptor, right: BehaviorDescriptor) -> float:
    distance = 0.0
    if left.closed != right.closed:
        distance += 1.0
    distance += min(1.0, abs(left.implication_spine_length - right.implication_spine_length) / 4.0)
    distance += min(1.0, abs(left.meta_count - right.meta_count) / 3.0)
    distance += min(1.0, abs(left.cd_steps - right.cd_steps) / 8.0)
    distance += min(1.0, abs(left.substantive_cd_steps - right.substantive_cd_steps) / 8.0)
    distance += min(1.0, abs(left.proof_depth - right.proof_depth) / 6.0)
    if left.root_symbol != right.root_symbol:
        distance += 0.5
    if left.final_head_shape != right.final_head_shape:
        distance += 0.75
    if left.normalized_skeleton != right.normalized_skeleton:
        distance += 1.0
    distance += jaccard_distance(left.atom_set, right.atom_set)
    return distance


def select_quality_diverse_population(
    scored: tuple,
    target: Formula,
    regions: tuple[Goal, ...],
    archives: QualityArchives,
    config: ProplogicConfig,
    rng: Random,
    formula_pool: tuple[Formula, ...],
) -> QualitySelectionResult:
    evolution_config = config.evolution
    population_size = evolution_config.population_size
    promoted = promote_schematic_candidates(scored, target, regions, config)
    pool = scored + promoted

    descriptors = {
        item.proof: behavior_descriptor(item.proof, item.fitness.conclusion)
        for item in pool
    }
    closed = tuple(
        item for item in pool
        if item.fitness.valid
        and not isinstance(item.fitness.conclusion, Invalid)
        and descriptors[item.proof].closed
    )
    schematic = tuple(
        item for item in pool
        if item.fitness.valid
        and not isinstance(item.fitness.conclusion, Invalid)
        and not descriptors[item.proof].closed
    )

    counts = channel_counts(population_size)
    target_elites = tuple(item.proof for item in _top_unique(closed, counts[0], key=_target_score))
    region_elites = tuple(item.proof for item in _top_unique(closed, counts[1], key=_region_score))
    novelty_elites = tuple(
        item.proof
        for item in _top_unique(
            pool,
            counts[2],
            key=lambda item: novelty_score(
                descriptors[item.proof],
                archives.behavior_archive,
                k=evolution_config.novelty_k,
            ),
        )
    )
    schema_elites = tuple(
        item.proof
        for item in _top_unique(
            schematic,
            counts[3],
            key=lambda item: lemma_schema_score(item.fitness, target, regions, descriptors[item.proof], config),
        )
    )
    random_immigrants = random_immigrant_proofs(rng, counts[4], formula_pool, config)

    selected: list[Proof] = []
    for channel in (target_elites, region_elites, novelty_elites, schema_elites, random_immigrants):
        _extend_unique(selected, channel, population_size)
    if len(selected) < population_size:
        fill = _top_unique(pool, population_size - len(selected), key=lambda item: item.fitness.score)
        _extend_unique(selected, tuple(item.proof for item in fill), population_size)
    while len(selected) < population_size:
        selected.extend(random_immigrant_proofs(rng, 1, formula_pool, config))

    return QualitySelectionResult(
        population=tuple(selected[:population_size]),
        target_elites=target_elites,
        region_elites=region_elites,
        novelty_elites=novelty_elites,
        schema_elites=schema_elites,
        random_immigrants=random_immigrants,
        promoted=tuple(item.proof for item in promoted),
    )


def update_quality_archives(
    archives: QualityArchives,
    scored: tuple,
    selected: QualitySelectionResult,
    target: Formula,
    regions: tuple[Goal, ...],
    config: ProplogicConfig = DEFAULT_CONFIG,
) -> QualityArchives:
    selected_set = set(
        selected.target_elites
        + selected.region_elites
        + selected.novelty_elites
        + selected.schema_elites
        + selected.promoted
    )
    descriptor_inputs = tuple(item for item in scored if item.proof in selected_set)
    new_descriptors = tuple(
        behavior_descriptor(item.proof, item.fitness.conclusion)
        for item in descriptor_inputs
    )
    behavior_limit = max(1, config.evolution.behavior_archive_size)
    behavior_archive = _append_limited_unique(
        archives.behavior_archive,
        new_descriptors,
        behavior_limit,
    )

    schematic = tuple(
        item for item in scored
        if item.proof in selected.schema_elites
        and item.fitness.valid
        and not isinstance(item.fitness.conclusion, Invalid)
    )
    ranked_schemas = tuple(
        item.proof
        for item in sorted(
            schematic,
            key=lambda item: lemma_schema_score(
                item.fitness,
                target,
                regions,
                behavior_descriptor(item.proof, item.fitness.conclusion),
                config,
            ),
            reverse=True,
        )
    )
    schema_archive = _append_limited_unique(
        archives.schema_archive,
        ranked_schemas,
        config.evolution.schema_archive_size,
    )
    return QualityArchives(schema_archive=schema_archive, behavior_archive=behavior_archive)


def promote_schematic_candidates(
    scored: tuple,
    target: Formula,
    regions: tuple[Goal, ...],
    config: ProplogicConfig,
) -> tuple:
    targets = (target,) + tuple(region.core_theorem() for region in regions)
    promoted = []
    for item in scored:
        proof_conclusion = item.fitness.conclusion
        if isinstance(proof_conclusion, Invalid) or is_closed_formula(proof_conclusion):
            continue
        for target_formula in targets:
            subst = unify(proof_conclusion, target_formula)
            if isinstance(subst, UnifyFailure):
                continue
            proof = apply_proof_subst(item.proof, subst)
            fitness = total_fitness(proof, target, regions, config)
            if fitness.valid and not isinstance(fitness.conclusion, Invalid) and is_closed_formula(fitness.conclusion):
                promoted.append(type(item)(proof=proof, fitness=fitness))
                break
    return tuple(promoted)


def lemma_schema_score(
    fitness: FitnessResult,
    target: Formula | None,
    regions: tuple[Goal, ...],
    descriptor: BehaviorDescriptor,
    config: ProplogicConfig = DEFAULT_CONFIG,
) -> float:
    if not fitness.valid or isinstance(fitness.conclusion, Invalid) or descriptor.closed:
        return float("-inf")
    compactness = 1000.0 / (1.0 + fitness.proof_size + 0.1 * fitness.formula_size)
    substantive_bonus = 25.0 * fitness.cd_steps
    if target is None:
        instantiable = 0.0
    else:
        targets = (target,) + tuple(region.core_theorem() for region in regions)
        instantiable = max(
            1.0 if not isinstance(unify(fitness.conclusion, item), UnifyFailure) else 0.0
            for item in targets
        )
    return compactness + substantive_bonus + 250.0 * instantiable + 10.0 * descriptor.meta_count


def random_immigrant_proofs(
    rng: Random,
    count: int,
    formula_pool: tuple[Formula, ...],
    config: ProplogicConfig,
) -> tuple[Proof, ...]:
    return tuple(
        random_seeded_axiom(
            rng,
            formula_pool,
            max_formula_depth=config.mutation.random_formula_depth,
        )
        for _ in range(max(0, count))
    )


def channel_counts(population_size: int) -> tuple[int, int, int, int, int]:
    if population_size <= 0:
        return (0, 0, 0, 0, 0)
    base = population_size // 5
    counts = [base, base, base, base, base]
    for index in range(population_size - sum(counts)):
        counts[index] += 1
    return tuple(counts)  # type: ignore[return-value]


def apply_proof_subst(proof: Proof, subst: dict[str, Formula]) -> Proof:
    match proof:
        case Ax1(p, q):
            return Ax1(apply_subst(p, subst), apply_subst(q, subst))
        case Ax2(p, q, r):
            return Ax2(apply_subst(p, subst), apply_subst(q, subst), apply_subst(r, subst))
        case Ax3(p, q):
            return Ax3(apply_subst(p, subst), apply_subst(q, subst))
        case CD(major, minor):
            return CD(apply_proof_subst(major, subst), apply_proof_subst(minor, subst))


def apply_substitution_to_proof(proof: Proof, subst: dict[str, Formula]) -> Proof:
    return apply_proof_subst(proof, subst)


def implication_spine(formula: Formula) -> tuple[tuple[Formula, ...], Formula]:
    antecedents: list[Formula] = []
    current = formula
    while isinstance(current, Imp):
        antecedents.append(current.left)
        current = current.right
    return (tuple(antecedents), current)


def root_symbol(formula: Formula) -> str:
    match formula:
        case Atom():
            return "atom"
        case Meta():
            return "meta"
        case Not():
            return "not"
        case Imp():
            return "imp"


def atoms(formula: Formula) -> frozenset[str]:
    match formula:
        case Atom(name):
            return frozenset((name,))
        case Meta():
            return frozenset()
        case Not(body):
            return atoms(body)
        case Imp(left, right):
            return atoms(left) | atoms(right)


def normalized_skeleton(formula: Formula) -> str:
    match formula:
        case Atom():
            return "A"
        case Meta():
            return "M"
        case Not(body):
            return f"not({normalized_skeleton(body)})"
        case Imp(left, right):
            return f"imp({normalized_skeleton(left)},{normalized_skeleton(right)})"


def axiom_counts(proof: Proof) -> tuple[int, int, int]:
    match proof:
        case Ax1():
            return (1, 0, 0)
        case Ax2():
            return (0, 1, 0)
        case Ax3():
            return (0, 0, 1)
        case CD(major, minor):
            left = axiom_counts(major)
            right = axiom_counts(minor)
            return tuple(a + b for a, b in zip(left, right))  # type: ignore[return-value]


def uses_ax1(proof: Proof) -> bool:
    return axiom_counts(proof)[0] > 0


def uses_ax2(proof: Proof) -> bool:
    return axiom_counts(proof)[1] > 0


def uses_ax3(proof: Proof) -> bool:
    return axiom_counts(proof)[2] > 0


def jaccard_distance(left: frozenset[str], right: frozenset[str]) -> float:
    if not left and not right:
        return 0.0
    return 1.0 - (len(left & right) / len(left | right))


def _target_score(item) -> float:
    return item.fitness.score + 10_000.0 * item.fitness.target_similarity


def _region_score(item) -> float:
    exact = 1.0 if item.fitness.exact_region is not None else 0.0
    return 50_000.0 * exact + 10_000.0 * item.fitness.region_similarity + item.fitness.score


def _top_unique(items: tuple, count: int, *, key) -> tuple:
    if count <= 0:
        return ()
    selected = []
    seen = set()
    for item in sorted(items, key=key, reverse=True):
        if item.proof in seen:
            continue
        seen.add(item.proof)
        selected.append(item)
        if len(selected) >= count:
            break
    return tuple(selected)


def _extend_unique(selected: list[Proof], proofs: tuple[Proof, ...], limit: int) -> None:
    seen = set(selected)
    for proof in proofs:
        if proof in seen:
            continue
        selected.append(proof)
        seen.add(proof)
        if len(selected) >= limit:
            break


def _append_limited_unique(existing: tuple, additions: tuple, limit: int) -> tuple:
    output = list(existing)
    seen = set(output)
    for item in additions:
        if item in seen:
            continue
        output.append(item)
        seen.add(item)
    return tuple(output[-max(1, limit):])
