from birdrat_proplogic.config import ProplogicConfig
from birdrat_proplogic.fitness import depth_penalty, formula_similarity, total_fitness, total_formula_size
from birdrat_proplogic.formula import Atom, Imp, Meta, Not
from birdrat_proplogic.goals import extract_goals
from birdrat_proplogic.proof import Ax1, CD
from birdrat_proplogic.surface import SAtom, SImp


def test_formula_similarity_rewards_exact_match() -> None:
    formula = Imp(Atom("a"), Atom("b"))

    assert formula_similarity(formula, formula) == 1.0


def test_formula_similarity_rewards_shared_implication_skeleton() -> None:
    close = formula_similarity(Imp(Atom("a"), Atom("b")), Imp(Atom("a"), Atom("c")))
    far = formula_similarity(Imp(Atom("a"), Atom("b")), Not(Imp(Atom("a"), Atom("c"))))

    assert close > far


def test_depth_penalty_starts_after_threshold() -> None:
    assert depth_penalty(2, 2) == 0.0
    assert depth_penalty(3, 2) > 0.0


def test_total_fitness_prioritizes_exact_target_over_region_match() -> None:
    a = Atom("a")
    b = Atom("b")
    target = Imp(a, Imp(b, a))
    target_proof = Ax1(a, b)
    region_proof = Ax1(a, a)

    target_result = total_fitness(target_proof, target)
    region_result = total_fitness(
        region_proof,
        Imp(b, b),
        extract_goals(SImp(SAtom("a"), SImp(SAtom("a"), SAtom("a")))),
    )

    assert target_result.exact_target
    assert region_result.exact_region is not None
    assert target_result.score > region_result.score


def test_total_fitness_detects_region_match() -> None:
    a = Atom("a")
    b = Atom("b")
    target = Imp(b, b)
    proof = Ax1(a, a)
    regions = extract_goals(SImp(SAtom("a"), SImp(SAtom("a"), SAtom("a"))))

    result = total_fitness(proof, target, regions)

    assert result.exact_region is not None
    assert result.valid


def test_total_fitness_penalizes_invalid_proof() -> None:
    a = Atom("a")
    b = Atom("b")
    proof = CD(Ax1(a, b), Ax1(a, b))
    result = total_fitness(proof, Imp(a, b))

    assert not result.valid
    assert result.score < 0


def test_total_formula_size_counts_axiom_arguments() -> None:
    proof = Ax1(Imp(Atom("a"), Atom("b")), Meta("?q"))

    assert total_formula_size(proof) == 4


def test_fitness_uses_configured_penalties() -> None:
    a = Atom("a")
    b = Atom("b")
    proof = Ax1(a, b)
    target = Imp(a, Imp(b, a))

    default_score = total_fitness(proof, target).score
    expensive_config = ProplogicConfig()
    expensive_config = ProplogicConfig(
        regions=expensive_config.regions,
        fitness=type(expensive_config.fitness)(
            exact_success_base=expensive_config.fitness.exact_success_base,
            proof_size_penalty=100.0,
        ),
    )

    assert total_fitness(proof, target, config=expensive_config).score < default_score
