from __future__ import annotations

from random import Random
from typing import Sequence

from birdrat_proplogic.config import DEFAULT_CONFIG, MutationConfig, ProplogicConfig
from birdrat_proplogic.formula import Atom, Formula, Imp, Meta, Not, formula_size, metas
from birdrat_proplogic.proof import Ax1, Ax2, Ax3, CD, Proof
from birdrat_proplogic.unify import apply_subst


def mutate_formula(
    formula: Formula,
    rng: Random | None = None,
    config: ProplogicConfig = DEFAULT_CONFIG,
    formula_pool: Sequence[Formula] = (),
) -> Formula:
    random = _rng(rng)
    mutation_config = config.mutation
    candidates = _formula_mutation_candidates(formula, random, mutation_config, formula_pool)
    bounded = tuple(item for item in candidates if formula_size(item) <= mutation_config.max_formula_size)
    if not bounded:
        return formula
    return random.choice(bounded)


def random_formula(
    rng: Random | None = None,
    config: ProplogicConfig = DEFAULT_CONFIG,
    depth: int | None = None,
) -> Formula:
    random = _rng(rng)
    mutation_config = config.mutation
    remaining_depth = mutation_config.random_formula_depth if depth is None else depth
    if remaining_depth <= 0:
        return _random_leaf_formula(random, mutation_config)

    constructors = ("leaf", "not", "imp")
    choice = random.choice(constructors)
    if choice == "leaf":
        return _random_leaf_formula(random, mutation_config)
    if choice == "not":
        return Not(random_formula(random, config, remaining_depth - 1))
    return Imp(
        random_formula(random, config, remaining_depth - 1),
        random_formula(random, config, remaining_depth - 1),
    )


def mutate_proof(
    proof: Proof,
    rng: Random | None = None,
    config: ProplogicConfig = DEFAULT_CONFIG,
    formula_pool: Sequence[Formula] = (),
) -> Proof:
    random = _rng(rng)
    operations = [
        replace_axiom_node,
        mutate_axiom_formula_argument,
        replace_subtree,
        wrap_cd,
    ]
    if formula_pool and _proof_metas(proof):
        operations.append(instantiate_meta_from_pool)
    if isinstance(proof, CD):
        operations.extend([replace_cd_child, swap_cd_children])
    return random.choice(operations)(proof, random, config, formula_pool)


def random_proof(
    rng: Random | None = None,
    config: ProplogicConfig = DEFAULT_CONFIG,
    depth: int | None = None,
) -> Proof:
    random = _rng(rng)
    remaining_depth = config.mutation.random_proof_depth if depth is None else depth
    if remaining_depth <= 0:
        return _random_axiom(random, config)
    if random.random() < 0.5:
        return _random_axiom(random, config)
    return CD(
        random_proof(random, config, remaining_depth - 1),
        random_proof(random, config, remaining_depth - 1),
    )


def replace_axiom_node(
    proof: Proof,
    rng: Random | None = None,
    config: ProplogicConfig = DEFAULT_CONFIG,
    formula_pool: Sequence[Formula] = (),
) -> Proof:
    random = _rng(rng)
    match proof:
        case Ax1(p, q):
            return random.choice((Ax1(p, q), Ax2(p, q, _random_or_seeded_formula(random, config, formula_pool)), Ax3(p, q)))
        case Ax2(p, q, r):
            return random.choice((Ax1(p, q), Ax2(p, q, r), Ax3(p, q)))
        case Ax3(p, q):
            return random.choice((Ax1(p, q), Ax2(p, q, _random_or_seeded_formula(random, config, formula_pool)), Ax3(p, q)))
        case CD(major, minor):
            if random.random() < 0.5:
                return CD(replace_axiom_node(major, random, config, formula_pool), minor)
            return CD(major, replace_axiom_node(minor, random, config, formula_pool))


def mutate_axiom_formula_argument(
    proof: Proof,
    rng: Random | None = None,
    config: ProplogicConfig = DEFAULT_CONFIG,
    formula_pool: Sequence[Formula] = (),
) -> Proof:
    random = _rng(rng)
    match proof:
        case Ax1(p, q):
            if random.random() < 0.5:
                return Ax1(mutate_formula(p, random, config, formula_pool), q)
            return Ax1(p, mutate_formula(q, random, config, formula_pool))
        case Ax2(p, q, r):
            index = random.randrange(3)
            if index == 0:
                return Ax2(mutate_formula(p, random, config, formula_pool), q, r)
            if index == 1:
                return Ax2(p, mutate_formula(q, random, config, formula_pool), r)
            return Ax2(p, q, mutate_formula(r, random, config, formula_pool))
        case Ax3(p, q):
            if random.random() < 0.5:
                return Ax3(mutate_formula(p, random, config, formula_pool), q)
            return Ax3(p, mutate_formula(q, random, config, formula_pool))
        case CD(major, minor):
            if random.random() < 0.5:
                return CD(mutate_axiom_formula_argument(major, random, config, formula_pool), minor)
            return CD(major, mutate_axiom_formula_argument(minor, random, config, formula_pool))


def replace_subtree(
    proof: Proof,
    rng: Random | None = None,
    config: ProplogicConfig = DEFAULT_CONFIG,
    formula_pool: Sequence[Formula] = (),
) -> Proof:
    random = _rng(rng)
    if not isinstance(proof, CD) or random.random() < 0.33:
        if formula_pool:
            from birdrat_proplogic.seed import random_seeded_axiom

            return random_seeded_axiom(random, formula_pool, max_formula_depth=config.mutation.random_formula_depth)
        return random_proof(random, config)
    if random.random() < 0.5:
        return CD(replace_subtree(proof.major, random, config, formula_pool), proof.minor)
    return CD(proof.major, replace_subtree(proof.minor, random, config, formula_pool))


def wrap_cd(
    proof: Proof,
    rng: Random | None = None,
    config: ProplogicConfig = DEFAULT_CONFIG,
    formula_pool: Sequence[Formula] = (),
) -> Proof:
    random = _rng(rng)
    other = random_proof(random, config, max(0, config.mutation.random_proof_depth - 1))
    if random.random() < 0.5:
        return CD(proof, other)
    return CD(other, proof)


def replace_cd_child(
    proof: Proof,
    rng: Random | None = None,
    config: ProplogicConfig = DEFAULT_CONFIG,
    formula_pool: Sequence[Formula] = (),
) -> Proof:
    random = _rng(rng)
    if not isinstance(proof, CD):
        return proof
    if formula_pool:
        from birdrat_proplogic.seed import random_seeded_axiom

        child = random_seeded_axiom(random, formula_pool, max_formula_depth=config.mutation.random_formula_depth)
    else:
        child = random_proof(random, config)
    if random.random() < 0.5:
        return CD(child, proof.minor)
    return CD(proof.major, child)


def swap_cd_children(
    proof: Proof,
    rng: Random | None = None,
    config: ProplogicConfig = DEFAULT_CONFIG,
    formula_pool: Sequence[Formula] = (),
) -> Proof:
    if not isinstance(proof, CD):
        return proof
    return CD(proof.minor, proof.major)


def instantiate_meta_from_pool(
    proof: Proof,
    rng: Random | None = None,
    config: ProplogicConfig = DEFAULT_CONFIG,
    formula_pool: Sequence[Formula] = (),
) -> Proof:
    random = _rng(rng)
    proof_metas = tuple(_proof_metas(proof))
    if not proof_metas or not formula_pool:
        return proof
    meta = random.choice(proof_metas)
    replacement = random.choice(tuple(formula_pool))
    return _apply_proof_subst(proof, {meta.name: replacement})


def _formula_mutation_candidates(
    formula: Formula,
    rng: Random,
    config: MutationConfig,
    formula_pool: Sequence[Formula],
) -> tuple[Formula, ...]:
    match formula:
        case Atom():
            replacement = Atom(rng.choice(config.atom_names))
            random_leaf = _random_or_seeded_formula(rng, ProplogicConfig(mutation=config), formula_pool)
            return (
                replacement,
                random_leaf,
                Not(formula),
                Imp(formula, random_leaf),
                Imp(random_leaf, formula),
            )
        case Meta():
            replacement = Meta(rng.choice(config.meta_names))
            random_leaf = _random_or_seeded_formula(rng, ProplogicConfig(mutation=config), formula_pool)
            return (
                replacement,
                random_leaf,
                Not(formula),
                Imp(formula, random_leaf),
                Imp(random_leaf, formula),
            )
        case Not(body):
            return (
                Not(mutate_formula(body, rng, ProplogicConfig(mutation=config), formula_pool)),
                body,
                Imp(formula, _random_or_seeded_formula(rng, ProplogicConfig(mutation=config), formula_pool)),
                Imp(_random_or_seeded_formula(rng, ProplogicConfig(mutation=config), formula_pool), formula),
            )
        case Imp(left, right):
            return (
                Imp(mutate_formula(left, rng, ProplogicConfig(mutation=config), formula_pool), right),
                Imp(left, mutate_formula(right, rng, ProplogicConfig(mutation=config), formula_pool)),
                Not(formula),
                left,
                right,
            )


def _random_axiom(rng: Random, config: ProplogicConfig) -> Proof:
    p = random_formula(rng, config)
    q = random_formula(rng, config)
    choice = rng.choice((1, 2, 3))
    if choice == 1:
        return Ax1(p, q)
    if choice == 2:
        return Ax2(p, q, random_formula(rng, config))
    return Ax3(p, q)


def _random_leaf_formula(rng: Random, config: MutationConfig) -> Formula:
    if rng.random() < 0.75:
        return Atom(rng.choice(config.atom_names))
    return Meta(rng.choice(config.meta_names))


def _random_or_seeded_formula(rng: Random, config: ProplogicConfig, formula_pool: Sequence[Formula]) -> Formula:
    if formula_pool and rng.random() < 0.9:
        return rng.choice(formula_pool)
    return random_formula(rng, config)


def _proof_metas(proof: Proof) -> frozenset[Meta]:
    match proof:
        case Ax1(p, q):
            return metas(p) | metas(q)
        case Ax2(p, q, r):
            return metas(p) | metas(q) | metas(r)
        case Ax3(p, q):
            return metas(p) | metas(q)
        case CD(major, minor):
            return _proof_metas(major) | _proof_metas(minor)


def _apply_proof_subst(proof: Proof, subst: dict[str, Formula]) -> Proof:
    match proof:
        case Ax1(p, q):
            return Ax1(apply_subst(p, subst), apply_subst(q, subst))
        case Ax2(p, q, r):
            return Ax2(apply_subst(p, subst), apply_subst(q, subst), apply_subst(r, subst))
        case Ax3(p, q):
            return Ax3(apply_subst(p, subst), apply_subst(q, subst))
        case CD(major, minor):
            return CD(_apply_proof_subst(major, subst), _apply_proof_subst(minor, subst))


def _rng(rng: Random | None) -> Random:
    if rng is None:
        return Random()
    return rng
