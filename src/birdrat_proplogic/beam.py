from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Iterable

from birdrat_proplogic.config import DEFAULT_CONFIG, ProplogicConfig
from birdrat_proplogic.dproof import DProofParseError, fresh_axiom
from birdrat_proplogic.fitness import (
    best_consequent_similarity,
    best_directed_similarity,
    implication_spine,
    total_fitness,
    total_formula_size,
)
from birdrat_proplogic.formula import Atom, Formula, Imp, Meta, Not, formula_size, is_closed_formula
from birdrat_proplogic.goals import Goal
from birdrat_proplogic.proof import (
    Ax1,
    Ax2,
    Ax3,
    Invalid,
    Proof,
    cd_depth,
    cd_steps,
    conclusion,
    is_vacuous_cd,
    proof_size,
)
from birdrat_proplogic.quality import behavior_descriptor, lemma_schema_score, novelty_score
from birdrat_proplogic.seed import try_make_cd
from birdrat_proplogic.unify import UnifyFailure, Substitution, unify


@dataclass(frozen=True)
class BeamLayerStats:
    depth: int
    pair_pool_size: int
    major_candidates: int
    compatible_minor_candidates: int
    pair_attempts: int
    valid_products: int
    closed_products: int
    schematic_products: int
    closed_survivors: int
    schematic_survivors: int


@dataclass(frozen=True)
class BeamDiagnostics:
    width: int
    max_depth: int
    pair_budget: int
    major_budget: int
    pair_attempts: int = 0
    valid_products: int = 0
    layer_counts: tuple[BeamLayerStats, ...] = ()


@dataclass(frozen=True)
class BeamSearchResult:
    proofs: tuple[Proof, ...]
    diagnostics: BeamDiagnostics


def cd_beam_search(
    target: Formula,
    regions: tuple[Goal, ...],
    formula_pool: tuple[Formula, ...],
    config: ProplogicConfig = DEFAULT_CONFIG,
) -> tuple[Proof, ...]:
    return cd_beam_search_result(target, regions, formula_pool, config).proofs


def cd_beam_search_result(
    target: Formula,
    regions: tuple[Goal, ...],
    formula_pool: tuple[Formula, ...],
    config: ProplogicConfig = DEFAULT_CONFIG,
) -> BeamSearchResult:
    evolution_config = config.evolution
    width = max(1, evolution_config.beam_width)
    max_depth = max(0, evolution_config.beam_max_depth)
    pair_budget = max(0, evolution_config.beam_pair_budget)
    major_budget = max(1, evolution_config.beam_major_budget)
    if not evolution_config.beam_enabled:
        return BeamSearchResult((), BeamDiagnostics(width, max_depth, pair_budget, major_budget))

    seeds = tuple(seeded_axiom_instances(formula_pool, width))
    known: list[Proof] = list(seeds)
    frontier: tuple[Proof, ...] = tuple(known)
    behavior_archive = tuple(behavior_descriptor(proof) for proof in known)
    layers: list[BeamLayerStats] = []

    for depth in range(max_depth):
        pair_pool = tuple(_dedupe(list(seeds) + list(known[-width:]) + list(frontier)))
        new: list[Proof] = []
        pairs, compatible_count = prioritized_candidate_pairs(
            pair_pool,
            target,
            regions,
            config,
            major_budget=major_budget,
            pair_budget=pair_budget,
        )

        for _, major, minor in pairs:
            candidate = try_make_cd(major, minor)
            if candidate is None or candidate in known or candidate in new:
                continue
            new.append(candidate)

        closed, schematic = _partition_valid(new)
        kept_closed = _rank_closed(closed, target, regions, config, width)
        kept_schematic = _rank_schematic(
            schematic,
            target,
            regions,
            behavior_archive,
            config,
            width,
        )
        layers.append(
            BeamLayerStats(
                depth=depth,
                pair_pool_size=len(pair_pool),
                major_candidates=min(major_budget, len([proof for proof in pair_pool if implication_major_parts(proof) is not None])),
                compatible_minor_candidates=compatible_count,
                pair_attempts=len(pairs),
                valid_products=len(new),
                closed_products=len(closed),
                schematic_products=len(schematic),
                closed_survivors=len(kept_closed),
                schematic_survivors=len(kept_schematic),
            )
        )
        if not new:
            break

        frontier = kept_closed + kept_schematic
        known.extend(frontier)
        behavior_archive = tuple(
            list(behavior_archive)
            + [behavior_descriptor(proof) for proof in frontier]
        )[-config.evolution.behavior_archive_size :]

    diagnostics = BeamDiagnostics(
        width=width,
        max_depth=max_depth,
        pair_budget=pair_budget,
        major_budget=major_budget,
        pair_attempts=sum(layer.pair_attempts for layer in layers),
        valid_products=sum(layer.valid_products for layer in layers),
        layer_counts=tuple(layers),
    )
    return BeamSearchResult(tuple(_dedupe(known)), diagnostics)


def implication_major_parts(proof: Proof) -> tuple[Formula, Formula] | None:
    proof_conclusion = conclusion(proof)
    if not isinstance(proof_conclusion, Imp):
        return None
    return (proof_conclusion.left, proof_conclusion.right)


def major_priority(major: Proof, target: Formula, regions: tuple[Goal, ...]) -> float:
    parts = implication_major_parts(major)
    if parts is None:
        return float("-inf")
    antecedent, consequent = parts
    targets = (target,) + tuple(region.core_theorem() for region in regions)
    exact = 1.0 if consequent in targets else 0.0
    unifies = 1.0 if _unifies_with_any(consequent, targets) else 0.0
    head_match = 1.0 if _same_final_head_as_any(consequent, targets) else 0.0
    vacuous = 1.0 if is_vacuous_cd(major) else 0.0
    return (
        2_000.0 * exact
        + 1_000.0 * best_consequent_similarity(consequent, target, regions)
        + 500.0 * unifies
        + 250.0 * best_directed_similarity(consequent, target, regions)
        + 100.0 * head_match
        - 2.0 * formula_size(antecedent)
        - 1.0 * proof_size(major)
        - 5.0 * cd_steps(major)
        - 0.2 * total_formula_size(major)
        - 250.0 * vacuous
    )


def pair_priority(major: Proof, minor: Proof, target: Formula, regions: tuple[Goal, ...]) -> float:
    parts = implication_major_parts(major)
    if parts is None:
        return float("-inf")
    antecedent, _ = parts
    minor_conclusion = conclusion(minor)
    if isinstance(minor_conclusion, Invalid):
        return float("-inf")
    subst = unify(antecedent, minor_conclusion)
    if isinstance(subst, UnifyFailure):
        return float("-inf")
    closed_minor_bonus = 25.0 if is_closed_formula(minor_conclusion) else 0.0
    return (
        major_priority(major, target, regions)
        - 1.0 * proof_size(minor)
        - 0.5 * substitution_size(subst)
        + closed_minor_bonus
    )


def prioritized_candidate_pairs(
    proof_pool: tuple[Proof, ...],
    target: Formula,
    regions: tuple[Goal, ...],
    config: ProplogicConfig,
    *,
    major_budget: int,
    pair_budget: int,
) -> tuple[tuple[tuple[float, Proof, Proof], ...], int]:
    index = build_minor_shape_index(proof_pool)
    majors = sorted(
        (proof for proof in proof_pool if implication_major_parts(proof) is not None),
        key=lambda proof: major_priority(proof, target, regions),
        reverse=True,
    )[:major_budget]

    pairs: list[tuple[float, Proof, Proof]] = []
    compatible_count = 0
    for major in majors:
        parts = implication_major_parts(major)
        if parts is None:
            continue
        antecedent, _ = parts
        minors = tuple(compatible_minor_candidates(antecedent, proof_pool, index))
        compatible_count += len(minors)
        for minor in minors:
            priority = pair_priority(major, minor, target, regions)
            if isfinite(priority):
                pairs.append((priority, major, minor))

    ranked = sorted(pairs, key=lambda item: item[0], reverse=True)
    if pair_budget <= 0:
        return ((), compatible_count)
    return (tuple(ranked[:pair_budget]), compatible_count)


def build_minor_shape_index(proof_pool: tuple[Proof, ...]) -> dict[str, tuple[Proof, ...]]:
    buckets: dict[str, list[Proof]] = {}
    for proof in proof_pool:
        proof_conclusion = conclusion(proof)
        key = _shape_key(proof_conclusion)
        buckets.setdefault(key, []).append(proof)
        if _is_schematic_or_meta_compatible(proof_conclusion):
            buckets.setdefault("schematic", []).append(proof)
    return {key: tuple(value) for key, value in buckets.items()}


def compatible_minor_candidates(
    antecedent: Formula,
    proof_pool: tuple[Proof, ...],
    index: dict[str, tuple[Proof, ...]],
) -> Iterable[Proof]:
    keys = {_shape_key(antecedent), "schematic"}
    if isinstance(antecedent, Meta):
        keys.update(index)
    selected: list[Proof] = []
    seen: set[Proof] = set()
    for key in keys:
        for proof in index.get(key, ()):
            if proof in seen:
                continue
            selected.append(proof)
            seen.add(proof)
    if not selected and isinstance(antecedent, Meta):
        return proof_pool
    return tuple(selected)


def substitution_size(subst: Substitution) -> int:
    return sum(formula_size(formula) for formula in subst.values())


def seeded_axiom_instances(formula_pool: tuple[Formula, ...], width: int) -> tuple[Proof, ...]:
    proofs: list[Proof] = []
    leaf_index = 0
    for _ in range(max(3, width // 3)):
        for axiom_number in ("1", "2", "3"):
            leaf_index += 1
            proof = fresh_axiom(axiom_number, leaf_index)
            if not isinstance(proof, DProofParseError):
                proofs.append(proof)
            if len(proofs) >= width:
                return tuple(_dedupe(proofs))

    limited_pool = formula_pool[: max(1, min(len(formula_pool), width))]
    for left in limited_pool:
        for right in limited_pool:
            proofs.append(Ax1(left, right))
            proofs.append(Ax3(left, right))
            if len(proofs) >= width:
                return tuple(_dedupe(proofs))
            for middle in limited_pool[:3]:
                proofs.append(Ax2(left, right, middle))
                if len(proofs) >= width:
                    return tuple(_dedupe(proofs))
    return tuple(_dedupe(proofs))


def _partition_valid(proofs: list[Proof]) -> tuple[tuple[Proof, ...], tuple[Proof, ...]]:
    closed = []
    schematic = []
    for proof in proofs:
        proof_conclusion = conclusion(proof)
        if isinstance(proof_conclusion, Invalid):
            continue
        if is_closed_formula(proof_conclusion):
            closed.append(proof)
        else:
            schematic.append(proof)
    return (tuple(closed), tuple(schematic))


def _rank_closed(
    proofs: tuple[Proof, ...],
    target: Formula,
    regions: tuple[Goal, ...],
    config: ProplogicConfig,
    width: int,
) -> tuple[Proof, ...]:
    return tuple(
        sorted(
            proofs,
            key=lambda proof: (
                total_fitness(proof, target, regions, config).score,
                -cd_depth(proof),
            ),
            reverse=True,
        )[:width]
    )


def _rank_schematic(
    proofs: tuple[Proof, ...],
    target: Formula,
    regions: tuple[Goal, ...],
    behavior_archive: tuple,
    config: ProplogicConfig,
    width: int,
) -> tuple[Proof, ...]:
    def score(proof: Proof) -> float:
        fitness = total_fitness(proof, target, regions, config)
        descriptor = behavior_descriptor(proof, fitness.conclusion)
        return lemma_schema_score(fitness, target, regions, descriptor, config) + 50.0 * novelty_score(
            descriptor,
            behavior_archive,
            k=config.evolution.novelty_k,
        )

    ranked = sorted(proofs, key=score, reverse=True)
    selected: list[Proof] = []
    seen_skeletons: set[str] = set()
    for proof in ranked:
        descriptor = behavior_descriptor(proof)
        if descriptor.normalized_skeleton in seen_skeletons:
            continue
        selected.append(proof)
        seen_skeletons.add(descriptor.normalized_skeleton)
        if len(selected) >= width:
            return tuple(selected)
    for proof in ranked:
        if proof in selected:
            continue
        selected.append(proof)
        if len(selected) >= width:
            break
    return tuple(selected)


def _shape_key(formula: Formula | Invalid) -> str:
    match formula:
        case Meta():
            return "meta"
        case Atom(name):
            return f"atom:{name}"
        case Not():
            return "not"
        case Imp():
            return "imp"
        case Invalid():
            return "invalid"


def _is_schematic_or_meta_compatible(formula: Formula | Invalid) -> bool:
    match formula:
        case Meta():
            return True
        case Not(body):
            return _is_schematic_or_meta_compatible(body)
        case Imp(left, right):
            return _is_schematic_or_meta_compatible(left) or _is_schematic_or_meta_compatible(right)
        case Atom() | Invalid():
            return False


def _unifies_with_any(formula: Formula, targets: tuple[Formula, ...]) -> bool:
    return any(not isinstance(unify(formula, target), UnifyFailure) for target in targets)


def _same_final_head_as_any(formula: Formula, targets: tuple[Formula, ...]) -> bool:
    _, head = implication_spine(formula)
    return any(head == implication_spine(target)[1] for target in targets)


def _dedupe(proofs: list[Proof]) -> list[Proof]:
    output = []
    seen = set()
    for proof in proofs:
        if proof in seen:
            continue
        output.append(proof)
        seen.add(proof)
    return output
