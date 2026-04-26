from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from math import exp

from birdrat_proplogic.config import DEFAULT_CONFIG, FitnessConfig, ProplogicConfig
from birdrat_proplogic.formula import Atom, Formula, Imp, Meta, Not, formula_size
from birdrat_proplogic.goals import Goal
from birdrat_proplogic.proof import Ax1, Ax2, Ax3, CD, Invalid, Proof, cd_depth, cd_steps, conclusion, proof_size
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
    target_similarity = formula_similarity(proof_conclusion, target)
    region_similarity = best_region_similarity(proof_conclusion, regions)
    similarity = max(target_similarity, region_similarity)

    if exact_target:
        score = fitness_config.exact_success_base + fitness_config.exact_target_bonus
    elif exact_region is not None:
        score = fitness_config.exact_region_bonus * exact_region.weight
        score += fitness_config.symbolic_similarity_weight * similarity
    elif steps == 0:
        score = fitness_config.axiom_only_similarity_cap * similarity
    else:
        score = 0.0
        score += fitness_config.symbolic_similarity_weight * similarity
        score += fitness_config.cd_existence_bonus
        score += fitness_config.cd_progress_bonus * cd_progress(proof, target, regions)

    score -= _complexity_penalty(steps, depth, nodes, formulas, fitness_config)

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
    targets = (target,) + tuple(region.core_theorem() for region in regions)
    return max(formula_similarity(candidate, item) for item in targets)


def best_region_similarity(candidate: Formula, regions: tuple[Goal, ...] = ()) -> float:
    if not regions:
        return 0.0
    return max(formula_similarity(candidate, region.core_theorem()) for region in regions)


def cd_progress(proof: Proof, target: Formula, regions: tuple[Goal, ...] = ()) -> float:
    if not isinstance(proof, CD):
        return 0.0

    proof_conclusion = conclusion(proof)
    major_conclusion = conclusion(proof.major)
    minor_conclusion = conclusion(proof.minor)
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
