from random import Random

from birdrat_proplogic.config import ArchiveConfig, EvolutionConfig, ProplogicConfig
from birdrat_proplogic.formula import Atom, Formula, Imp, Meta, Not, subformulas
from birdrat_proplogic.mutate import random_proof
from birdrat_proplogic.proof import Ax1, Ax2, Ax3, CD, Invalid, Proof, conclusion
from birdrat_proplogic.seed import (
    formula_pool_from_target,
    initialize_population_from_target,
    random_seeded_axiom,
    random_valid_cd,
    try_make_cd,
)


def test_subformulas_returns_formula_and_children_in_order() -> None:
    formula = Imp(Not(Atom("a")), Atom("b"))

    assert subformulas(formula) == (formula, Not(Atom("a")), Atom("a"), Atom("b"))


def test_formula_pool_from_target_includes_target_region_subformulas_and_negations() -> None:
    target = Imp(Not(Atom("a")), Atom("b"))
    region = Imp(Atom("a"), Atom("a"))
    pool = formula_pool_from_target(target, (region,), max_implications=0)

    assert target in pool
    assert region in pool
    assert Atom("a") in pool
    assert Atom("b") in pool
    assert Not(region) in pool


def test_formula_pool_from_target_deduplicates_formulas() -> None:
    target = Imp(Atom("a"), Atom("a"))
    pool = formula_pool_from_target(target, (target,), max_implications=0, include_negations=False)

    assert len(pool) == len(set(pool))


def test_formula_pool_from_target_caps_implications() -> None:
    target = Imp(Atom("a"), Atom("b"))
    pool_without_implications = formula_pool_from_target(target, (), max_implications=0, include_negations=False)
    pool_with_implications = formula_pool_from_target(target, (), max_implications=2, include_negations=False)

    assert len(pool_with_implications) <= len(pool_without_implications) + 2


def test_random_seeded_axiom_uses_formula_pool_when_random_rate_zero() -> None:
    pool = (Atom("a"), Atom("b"))
    proof = random_seeded_axiom(Random(0), pool, random_formula_rate=0.0)

    assert all(argument in pool for argument in _axiom_arguments(proof))


def test_try_make_cd_returns_valid_cd_when_possible() -> None:
    proof = try_make_cd(Ax1(Meta("?p"), Meta("?q")), Ax1(Atom("a"), Atom("b")))

    assert isinstance(proof, CD)
    assert not isinstance(conclusion(proof), Invalid)


def test_try_make_cd_returns_none_when_invalid() -> None:
    assert try_make_cd(Ax1(Atom("a"), Atom("b")), Ax1(Atom("x"), Atom("y"))) is None


def test_random_valid_cd_finds_valid_candidate_from_pool() -> None:
    major = Ax1(Meta("?p"), Meta("?q"))
    minor = Ax1(Atom("a"), Atom("b"))

    proof = random_valid_cd(Random(0), (major, minor), max_attempts=20)

    assert isinstance(proof, CD)
    assert not isinstance(conclusion(proof), Invalid)


def test_initialize_population_from_target_returns_requested_size() -> None:
    target = Imp(Atom("a"), Atom("a"))
    population = initialize_population_from_target(Random(1), target, (), 12)

    assert len(population) == 12
    assert all(isinstance(proof, Proof) for proof in population)


def test_initialize_population_from_target_improves_valid_fraction_over_random() -> None:
    target = Imp(Atom("a"), Atom("a"))
    config = ProplogicConfig(
        archive=ArchiveConfig(path=None),
        evolution=EvolutionConfig(population_size=30),
    )
    seeded = initialize_population_from_target(Random(2), target, (), 30, noise_rate=0.0, config=config)
    random_population = tuple(random_proof(Random(index), config, depth=2) for index in range(30))

    assert _valid_fraction(seeded) > _valid_fraction(random_population)


def _axiom_arguments(proof: Proof) -> tuple[Formula, ...]:
    match proof:
        case Ax1(p, q) | Ax3(p, q):
            return (p, q)
        case Ax2(p, q, r):
            return (p, q, r)
        case CD():
            return ()


def _valid_fraction(population) -> float:
    return sum(not isinstance(conclusion(proof), Invalid) for proof in population) / len(population)
