from __future__ import annotations

from random import Random
from typing import Sequence

from birdrat_proplogic.config import DEFAULT_CONFIG, ProplogicConfig
from birdrat_proplogic.formula import Atom, Formula, Imp, Meta, Not, subformulas
from birdrat_proplogic.mutate import random_formula, random_proof
from birdrat_proplogic.proof import Ax1, Ax2, Ax3, CD, Invalid, Proof, conclusion


def formula_pool_from_target(
    target: Formula,
    region_targets: Sequence[Formula],
    *,
    max_implications: int = 200,
    include_negations: bool = True,
) -> tuple[Formula, ...]:
    pool: list[Formula] = []
    seen: set[Formula] = set()

    def add(formula: Formula) -> None:
        if formula in seen:
            return
        seen.add(formula)
        pool.append(formula)

    add(target)
    for region in region_targets:
        add(region)
    for formula in (target, *region_targets):
        for subformula in subformulas(formula):
            add(subformula)

    base = tuple(pool)
    if include_negations:
        for formula in base:
            add(Not(formula))

    implication_count = 0
    implication_inputs = tuple(pool)
    for left in implication_inputs:
        for right in implication_inputs:
            if implication_count >= max_implications:
                return tuple(pool)
            add(Imp(left, right))
            implication_count += 1
    return tuple(pool)


def random_seeded_axiom(
    rng: Random,
    formula_pool: Sequence[Formula],
    random_formula_rate: float = 0.10,
    max_formula_depth: int = 3,
) -> Proof:
    p = _seeded_formula(rng, formula_pool, random_formula_rate, max_formula_depth)
    q = _seeded_formula(rng, formula_pool, random_formula_rate, max_formula_depth)
    choice = rng.choice((1, 2, 3))
    if choice == 1:
        return Ax1(p, q)
    if choice == 2:
        return Ax2(p, q, _seeded_formula(rng, formula_pool, random_formula_rate, max_formula_depth))
    return Ax3(p, q)


def try_make_cd(major: Proof, minor: Proof) -> Proof | None:
    candidate = CD(major, minor)
    if isinstance(conclusion(candidate), Invalid):
        return None
    return candidate


def random_valid_cd(
    rng: Random,
    proof_pool: Sequence[Proof],
    max_attempts: int = 100,
) -> Proof | None:
    if len(proof_pool) < 2:
        return None
    for _ in range(max_attempts):
        major = rng.choice(proof_pool)
        minor = rng.choice(proof_pool)
        candidate = try_make_cd(major, minor)
        if candidate is not None:
            return candidate
    return None


def initialize_population_from_target(
    rng: Random,
    target: Formula,
    region_targets: Sequence[Formula],
    population_size: int,
    *,
    axiom_seed_count: int | None = None,
    cd_rounds: int = 2,
    noise_rate: float = 0.10,
    max_formula_depth: int = 3,
    config: ProplogicConfig = DEFAULT_CONFIG,
) -> list[Proof]:
    formula_pool = formula_pool_from_target(target, region_targets)
    seed_count = axiom_seed_count if axiom_seed_count is not None else max(population_size * 3, 12)
    proof_pool = [
        random_seeded_axiom(rng, formula_pool, max_formula_depth=max_formula_depth)
        for _ in range(seed_count)
    ]

    for _ in range(max(0, cd_rounds)):
        additions: list[Proof] = []
        attempts = max(seed_count, population_size)
        for _ in range(attempts):
            candidate = random_valid_cd(rng, proof_pool)
            if candidate is not None and candidate not in proof_pool and candidate not in additions:
                additions.append(candidate)
        proof_pool.extend(additions)

    population: list[Proof] = []
    while len(population) < population_size:
        if rng.random() < noise_rate or not proof_pool:
            population.append(random_proof(rng, config, depth=config.mutation.random_proof_depth))
        else:
            population.append(rng.choice(proof_pool))
    return population


def _seeded_formula(
    rng: Random,
    formula_pool: Sequence[Formula],
    random_formula_rate: float,
    max_formula_depth: int,
) -> Formula:
    if not formula_pool or rng.random() < random_formula_rate:
        return random_formula(rng, depth=max_formula_depth)
    return rng.choice(formula_pool)
