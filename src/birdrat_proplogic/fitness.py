from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from math import exp

from birdrat_proplogic.config import DEFAULT_CONFIG, FitnessConfig, ProplogicConfig
from birdrat_proplogic.formula import Atom, Formula, Imp, Meta, Not, formula_size
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
    proof_size,
    strip_vacuous_weakening,
    substantive_cd_steps,
)
from birdrat_proplogic.unify import UnifyFailure, unify


@dataclass(frozen=True)
class FitnessResult:
    score: float
    conclusion: Formula | Invalid
    exact_target: bool
    exact_region: Goal | None
    similarity: float
    target_similarity: float
    region_similarity: float
    cd_steps: int
    cd_depth: int
    proof_size: int
    formula_size: int
    valid: bool


def total_fitness(
    proof: Proof,
    target: Formula,
    regions: tuple[Goal, ...] = (),
    config: ProplogicConfig = DEFAULT_CONFIG,
) -> FitnessResult:
    fitness_config = config.fitness
    proof_conclusion = conclusion(proof)
    steps = cd_steps(proof)
    depth = cd_depth(proof)
    nodes = proof_size(proof)
    formulas = total_formula_size(proof)

    if isinstance(proof_conclusion, Invalid):
        score = -_complexity_penalty(steps, depth, nodes, formulas, fitness_config)
        score -= fitness_config.invalid_proof_penalty
        return FitnessResult(
            score=score,
            conclusion=proof_conclusion,
            exact_target=False,
            exact_region=None,
            similarity=0.0,
            target_similarity=0.0,
            region_similarity=0.0,
            cd_steps=steps,
            cd_depth=depth,
            proof_size=nodes,
            formula_size=formulas,
            valid=False,
        )

    exact_target = proof_conclusion == target
    exact_region = _matching_region(proof_conclusion, regions)
    scoring_conclusion, weakening_wrappers = strip_vacuous_weakening(proof)
    if isinstance(scoring_conclusion, Invalid):
        scoring_conclusion = proof_conclusion
        weakening_wrappers = 0

    target_similarity = directed_similarity(scoring_conclusion, target, fitness_config)
    region_similarity = best_region_similarity(scoring_conclusion, regions, fitness_config)
    directed = best_directed_similarity(scoring_conclusion, target, regions)
    old = best_old_formula_similarity(scoring_conclusion, target, regions)
    debt = min_assumption_debt(scoring_conclusion, target, regions, fitness_config)
    similarity = _combined_similarity(directed, old, fitness_config)
    substantive_steps = substantive_cd_steps(proof)
    projection = is_projection_formula(scoring_conclusion)
    consequent_similarity = best_consequent_similarity(scoring_conclusion, target, regions)
    consequent_matches = consequent_similarity >= fitness_config.consequent_match_threshold
    if not exact_target and exact_region is None and projection:
        similarity = min(similarity, fitness_config.projection_similarity_cap)
    if not exact_target and exact_region is None and not consequent_matches:
        similarity = min(similarity, fitness_config.consequent_mismatch_similarity_cap)

    if exact_target:
        score = fitness_config.exact_success_base + fitness_config.exact_target_bonus
    elif exact_region is not None:
        score = fitness_config.exact_region_bonus * exact_region.weight
        score += fitness_config.symbolic_similarity_weight * similarity
    elif substantive_steps == 0:
        score = fitness_config.axiom_only_similarity_cap * similarity
    else:
        score = 0.0
        score += fitness_config.symbolic_similarity_weight * similarity
        if consequent_matches:
            score += fitness_config.cd_existence_bonus
            score += fitness_config.cd_progress_bonus * cd_progress(proof, target, regions)
    if not exact_target and exact_region is None:
        score -= fitness_config.assumption_debt_penalty * debt
        score -= fitness_config.weakening_wrapper_penalty * weakening_wrappers

    score -= _complexity_penalty(steps, depth, nodes, formulas, fitness_config)
    if not exact_target and exact_region is None and projection:
        score -= fitness_config.projection_penalty

    return FitnessResult(
        score=score,
        conclusion=proof_conclusion,
        exact_target=exact_target,
        exact_region=exact_region,
        similarity=similarity,
        target_similarity=target_similarity,
        region_similarity=region_similarity,
        cd_steps=steps,
        cd_depth=depth,
        proof_size=nodes,
        formula_size=formulas,
        valid=True,
    )


def best_similarity(candidate: Formula, target: Formula, regions: tuple[Goal, ...] = ()) -> float:
    return best_directed_similarity(candidate, target, regions)


def best_directed_similarity(candidate: Formula, target: Formula, regions: tuple[Goal, ...] = ()) -> float:
    targets = (target,) + tuple(region.core_theorem() for region in regions)
    return max(implication_spine_similarity(candidate, item) for item in targets)


def best_old_formula_similarity(candidate: Formula, target: Formula, regions: tuple[Goal, ...] = ()) -> float:
    targets = (target,) + tuple(region.core_theorem() for region in regions)
    return max(formula_similarity(candidate, item) for item in targets)


def best_consequent_similarity(candidate: Formula, target: Formula, regions: tuple[Goal, ...] = ()) -> float:
    _, candidate_consequent = implication_spine(candidate)
    targets = (target,) + tuple(region.core_theorem() for region in regions)
    return max(_consequent_similarity(candidate_consequent, implication_spine(item)[1]) for item in targets)


def best_region_similarity(
    candidate: Formula,
    regions: tuple[Goal, ...] = (),
    config: FitnessConfig = DEFAULT_CONFIG.fitness,
) -> float:
    if not regions:
        return 0.0
    return max(directed_similarity(candidate, region.core_theorem(), config) for region in regions)


def directed_similarity(
    candidate: Formula,
    target: Formula,
    config: FitnessConfig = DEFAULT_CONFIG.fitness,
) -> float:
    return _combined_similarity(
        implication_spine_similarity(candidate, target),
        formula_similarity(candidate, target),
        config,
    )


def implication_spine(formula: Formula) -> tuple[tuple[Formula, ...], Formula]:
    antecedents: list[Formula] = []
    current = formula
    while isinstance(current, Imp):
        antecedents.append(current.left)
        current = current.right
    return (tuple(antecedents), current)


@lru_cache(maxsize=None)
def implication_spine_similarity(candidate: Formula, target: Formula) -> float:
    if candidate == target:
        return 1.0

    candidate_antecedents, candidate_consequent = implication_spine(candidate)
    target_antecedents, target_consequent = implication_spine(target)

    antecedent_score = _antecedent_similarity(candidate_antecedents, target_antecedents)
    coverage_score = antecedent_coverage_score(candidate, target)
    consequent_score = _consequent_similarity(candidate_consequent, target_consequent)
    assumption_score = _assumption_count_score(candidate_antecedents, target_antecedents)
    debt = assumption_debt(candidate, target)

    score = 0.15 * antecedent_score + 0.05 * coverage_score + 0.65 * consequent_score + 0.15 * assumption_score
    score -= min(0.75, 0.20 * debt)
    return max(0.0, min(1.0, score))


def antecedent_coverage_score(candidate: Formula, target: Formula) -> float:
    candidate_antecedents, _ = implication_spine(candidate)
    target_antecedents, _ = implication_spine(target)
    if not target_antecedents:
        return 1.0
    unmatched = list(candidate_antecedents)
    matched = 0
    for target_antecedent in target_antecedents:
        best_index = None
        best_score = 0.0
        for index, candidate_antecedent in enumerate(unmatched):
            score = _antecedent_match_score(candidate_antecedent, target_antecedent)
            if score > best_score:
                best_score = score
                best_index = index
        if best_index is not None and best_score >= 0.70:
            matched += 1
            unmatched.pop(best_index)
    return matched / len(target_antecedents)


def extra_assumptions(candidate: Formula, target: Formula) -> tuple[Formula, ...]:
    candidate_antecedents, _ = implication_spine(candidate)
    target_antecedents, _ = implication_spine(target)
    if _starts_with(candidate_antecedents, target_antecedents):
        return candidate_antecedents[len(target_antecedents) :]
    return tuple(
        antecedent
        for index, antecedent in enumerate(candidate_antecedents)
        if index >= len(target_antecedents) or antecedent != target_antecedents[index]
    )


def assumption_debt(
    candidate: Formula,
    target: Formula,
    config: FitnessConfig = DEFAULT_CONFIG.fitness,
) -> float:
    candidate_antecedents, candidate_head = implication_spine(candidate)
    _, target_head = implication_spine(target)
    extra = extra_assumptions(candidate, target)
    debt = config.extra_antecedent_penalty * len(extra)
    debt += config.extra_antecedent_size_penalty * sum(formula_size(item) for item in extra)

    if target_head in candidate_antecedents:
        debt += config.extra_antecedent_penalty * 2.0
    if candidate_head == target_head and extra:
        debt += config.extra_antecedent_penalty * len(extra)
    return debt


def min_assumption_debt(
    candidate: Formula,
    target: Formula,
    regions: tuple[Goal, ...] = (),
    config: FitnessConfig = DEFAULT_CONFIG.fitness,
) -> float:
    targets = (target,) + tuple(region.core_theorem() for region in regions)
    return min(assumption_debt(candidate, item, config) for item in targets)


def best_antecedent_coverage(candidate: Formula, target: Formula, regions: tuple[Goal, ...] = ()) -> float:
    targets = (target,) + tuple(region.core_theorem() for region in regions)
    return max(antecedent_coverage_score(candidate, item) for item in targets)


def is_projection_formula(formula: Formula) -> bool:
    antecedents, consequent = implication_spine(formula)
    return consequent in antecedents


def cd_progress(proof: Proof, target: Formula, regions: tuple[Goal, ...] = ()) -> float:
    if not isinstance(proof, CD) or substantive_cd_steps(proof) == 0:
        return 0.0

    proof_conclusion, _ = strip_vacuous_weakening(proof)
    major_conclusion, _ = strip_vacuous_weakening(proof.major)
    minor_conclusion, _ = strip_vacuous_weakening(proof.minor)
    if isinstance(proof_conclusion, Invalid):
        return 0.0

    child_similarity = best_similarity(proof_conclusion, target, regions)
    parent_similarities = [
        best_similarity(item, target, regions)
        for item in (major_conclusion, minor_conclusion)
        if not isinstance(item, Invalid)
    ]
    if not parent_similarities:
        return child_similarity
    return max(0.0, child_similarity - max(parent_similarities))


@lru_cache(maxsize=None)
def formula_similarity(left: Formula, right: Formula) -> float:
    if left == right:
        return 1.0

    scores = [
        0.25 * _root_similarity(left, right),
        0.25 * _skeleton_similarity(left, right),
        0.20 * _atom_similarity(left, right),
        0.20 * _subformula_similarity(left, right),
        0.10 * _unification_similarity(left, right),
    ]
    return sum(scores)


def depth_penalty(
    depth: int,
    threshold: int,
    lam: float = 100.0,
    k: float = 1.5,
) -> float:
    excess = max(0, depth - threshold)
    if excess == 0:
        return 0.0
    return lam * (2.0 / (1.0 + exp(-k * excess)) - 1.0)


@lru_cache(maxsize=None)
def total_formula_size(proof: Proof) -> int:
    match proof:
        case Ax1(p, q):
            return formula_size(p) + formula_size(q)
        case Ax2(p, q, r):
            return formula_size(p) + formula_size(q) + formula_size(r)
        case Ax3(p, q):
            return formula_size(p) + formula_size(q)
        case CD(major, minor):
            return total_formula_size(major) + total_formula_size(minor)


def _matching_region(candidate: Formula, regions: tuple[Goal, ...]) -> Goal | None:
    return next((region for region in regions if candidate == region.core_theorem()), None)


def _complexity_penalty(
    steps: int,
    depth: int,
    nodes: int,
    formulas: int,
    config: FitnessConfig,
) -> float:
    return (
        config.cd_step_penalty * steps
        + config.proof_size_penalty * nodes
        + config.formula_size_penalty * formulas
        + depth_penalty(
            depth,
            config.adaptive_cd_depth_threshold,
            config.depth_penalty_limit,
            config.depth_penalty_steepness,
        )
    )


def _combined_similarity(directed: float, old: float, config: FitnessConfig) -> float:
    total_weight = config.directed_similarity_weight + config.auxiliary_similarity_weight
    if total_weight <= 0:
        return 0.0
    return (
        config.directed_similarity_weight * directed
        + config.auxiliary_similarity_weight * old
    ) / total_weight


def _starts_with(candidate: tuple[Formula, ...], prefix: tuple[Formula, ...]) -> bool:
    if len(candidate) < len(prefix):
        return False
    return candidate[: len(prefix)] == prefix


def _antecedent_similarity(candidate: tuple[Formula, ...], target: tuple[Formula, ...]) -> float:
    if not candidate and not target:
        return 1.0
    if not candidate and target:
        return 0.85
    shared = min(len(candidate), len(target))
    if shared == 0:
        return 0.0
    return sum(formula_similarity(candidate[index], target[index]) for index in range(shared)) / max(len(target), shared)


def _assumption_count_score(candidate: tuple[Formula, ...], target: tuple[Formula, ...]) -> float:
    if len(candidate) <= len(target):
        return 1.0
    return 1.0 / (1.0 + len(candidate) - len(target))


def _antecedent_match_score(candidate: Formula, target: Formula) -> float:
    if candidate == target:
        return 1.0
    if not isinstance(unify(candidate, target), UnifyFailure):
        return 0.90
    return formula_similarity(candidate, target)


def _consequent_similarity(candidate: Formula, target: Formula) -> float:
    if candidate == target:
        return 1.0
    if not isinstance(unify(candidate, target), UnifyFailure):
        return 0.85
    return 0.15 * formula_similarity(candidate, target)


def _root_similarity(left: Formula, right: Formula) -> float:
    if type(left) is type(right):
        return 1.0
    return 0.0


def _skeleton_similarity(left: Formula, right: Formula) -> float:
    match left, right:
        case (Atom() | Meta()), (Atom() | Meta()):
            return 1.0
        case Not(left_body), Not(right_body):
            return 0.5 + 0.5 * _skeleton_similarity(left_body, right_body)
        case Imp(left_a, left_b), Imp(right_a, right_b):
            left_score = _skeleton_similarity(left_a, right_a)
            right_score = _skeleton_similarity(left_b, right_b)
            return 0.5 + 0.25 * left_score + 0.25 * right_score
        case _:
            return 0.0


def _atom_similarity(left: Formula, right: Formula) -> float:
    left_atoms = _atoms(left)
    right_atoms = _atoms(right)
    if not left_atoms and not right_atoms:
        return 1.0
    return len(left_atoms & right_atoms) / len(left_atoms | right_atoms)


def _subformula_similarity(left: Formula, right: Formula) -> float:
    left_subformulas = _subformulas(left)
    right_subformulas = _subformulas(right)
    return len(left_subformulas & right_subformulas) / len(left_subformulas | right_subformulas)


def _unification_similarity(left: Formula, right: Formula) -> float:
    if isinstance(unify(left, right), UnifyFailure):
        return 0.0
    return 1.0


def _atoms(formula: Formula) -> frozenset[str]:
    match formula:
        case Atom(name):
            return frozenset((name,))
        case Meta():
            return frozenset()
        case Not(body):
            return _atoms(body)
        case Imp(left, right):
            return _atoms(left) | _atoms(right)


def _subformulas(formula: Formula) -> frozenset[Formula]:
    match formula:
        case Atom() | Meta():
            return frozenset((formula,))
        case Not(body):
            return frozenset((formula,)) | _subformulas(body)
        case Imp(left, right):
            return frozenset((formula,)) | _subformulas(left) | _subformulas(right)
