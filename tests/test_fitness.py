from birdrat_proplogic.config import ProplogicConfig
from birdrat_proplogic.fitness import (
    assumption_debt,
    best_region_similarity,
    cd_progress,
    depth_penalty,
    directed_similarity,
    extra_assumptions,
    formula_similarity,
    implication_spine,
    implication_spine_similarity,
    is_projection_formula,
    total_fitness,
    total_formula_size,
)
from birdrat_proplogic.formula import Atom, Imp, Meta, Not
from birdrat_proplogic.goals import extract_goals
from birdrat_proplogic.proof import Ax1, CD, Invalid, conclusion
from birdrat_proplogic.surface import SAtom, SImp


def test_formula_similarity_rewards_exact_match() -> None:
    formula = Imp(Atom("a"), Atom("b"))

    assert formula_similarity(formula, formula) == 1.0


def test_formula_similarity_rewards_shared_implication_skeleton() -> None:
    close = formula_similarity(Imp(Atom("a"), Atom("b")), Imp(Atom("a"), Atom("c")))
    far = formula_similarity(Imp(Atom("a"), Atom("b")), Not(Imp(Atom("a"), Atom("c"))))

    assert close > far


def test_implication_spine_extracts_antecedents_and_final_consequent() -> None:
    formula = Imp(Atom("a"), Imp(Atom("b"), Atom("c")))

    assert implication_spine(formula) == ((Atom("a"), Atom("b")), Atom("c"))


def test_implication_spine_similarity_penalizes_projection_artifact() -> None:
    a = Atom("a")
    b = Atom("b")
    h = Not(Imp(a, Not(b)))
    k = Not(Imp(b, Not(a)))
    target = Imp(h, k)
    bad_candidate = Imp(h, Imp(b, Imp(k, b)))

    assert implication_spine_similarity(target, target) == 1.0
    assert implication_spine_similarity(bad_candidate, target) < 0.25


def test_assumption_debt_tracks_extra_candidate_antecedents() -> None:
    a = Atom("a")
    b = Atom("b")
    h = Not(Imp(a, Not(b)))
    e1 = Imp(Not(a), Not(Not(a)))
    e2 = Not(a)
    target = Imp(h, a)
    bad = Imp(h, Imp(e1, Imp(e2, a)))

    assert extra_assumptions(bad, target) == (e1, e2)
    assert assumption_debt(bad, target) > assumption_debt(target, target)


def test_directed_similarity_prefers_exact_and_stronger_over_extra_assumptions() -> None:
    a = Atom("a")
    b = Atom("b")
    h = Not(Imp(a, Not(b)))
    e1 = Imp(Not(a), Not(Not(a)))
    e2 = Not(a)
    target = Imp(h, a)
    bad = Imp(h, Imp(e1, Imp(e2, a)))
    stronger = a

    assert directed_similarity(target, target) == 1.0
    assert directed_similarity(stronger, target) > 0.75
    assert directed_similarity(bad, target) < 0.35
    assert directed_similarity(stronger, target) > directed_similarity(bad, target)


def test_full_target_projection_artifact_has_low_directed_similarity_and_debt() -> None:
    a = Atom("a")
    b = Atom("b")
    h = Not(Imp(a, Not(b)))
    k = Not(Imp(b, Not(a)))
    target = Imp(h, k)
    bad = Imp(h, Imp(b, Imp(k, b)))

    assert directed_similarity(bad, target) < 0.25
    assert assumption_debt(bad, target) > 0.0


def test_is_projection_formula_detects_final_consequent_projection() -> None:
    a = Atom("a")
    b = Atom("b")
    h = Not(Imp(a, Not(b)))
    k = Not(Imp(b, Not(a)))

    assert is_projection_formula(Imp(h, Imp(b, Imp(k, b))))
    assert not is_projection_formula(Imp(h, k))


def test_total_fitness_penalizes_extra_assumption_debt() -> None:
    a = Atom("a")
    b = Atom("b")
    x = Atom("x")
    h = Not(Imp(a, Not(b)))
    e1 = Imp(Not(a), Not(Not(a)))
    target = Imp(h, h)
    bad = Ax1(h, e1)
    lighter_extra = Ax1(h, x)

    assert assumption_debt(conclusion(lighter_extra), target) < assumption_debt(conclusion(bad), target)
    assert total_fitness(lighter_extra, target).score > total_fitness(bad, target).score


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
    assert result.region_similarity == 1.0
    assert result.target_similarity < 1.0


def test_best_region_similarity_is_zero_without_regions() -> None:
    assert best_region_similarity(Atom("a"), ()) == 0.0


def test_total_fitness_penalizes_invalid_proof() -> None:
    a = Atom("a")
    b = Atom("b")
    proof = CD(Ax1(a, b), Ax1(a, b))
    result = total_fitness(proof, Imp(a, b))

    assert not result.valid
    assert result.score < 0


def test_axiom_only_similarity_is_capped_below_valid_cd_candidate() -> None:
    a = Atom("a")
    b = Atom("b")
    target = Imp(Not(Imp(a, Not(b))), Not(Imp(b, Not(a))))
    similar_axiom = Ax1(Not(Imp(b, Not(a))), Not(Imp(a, Not(b))))
    valid_cd = CD(Ax1(Meta("?p"), Meta("?q")), Ax1(a, b))

    axiom_result = total_fitness(similar_axiom, target)
    cd_result = total_fitness(valid_cd, target)

    assert axiom_result.cd_steps == 0
    assert axiom_result.similarity > 0.2
    assert cd_result.cd_steps > 0
    assert cd_result.score > axiom_result.score


def test_exact_region_still_beats_non_exact_cd() -> None:
    a = Atom("a")
    b = Atom("b")
    region_proof = Ax1(a, b)
    valid_cd = CD(Ax1(Meta("?p"), Meta("?q")), Ax1(a, b))
    target = Imp(b, b)
    regions = extract_goals(SImp(SAtom("a"), SImp(SAtom("b"), SAtom("a"))))

    region_result = total_fitness(region_proof, target, regions)
    cd_result = total_fitness(valid_cd, target, regions)

    assert region_result.exact_region is not None
    assert not cd_result.exact_target
    assert cd_result.exact_region is None
    assert region_result.score > cd_result.score


def test_cd_progress_is_positive_when_cd_conclusion_is_closer_than_parents() -> None:
    a = Atom("a")
    b = Atom("b")
    proof = CD(Ax1(Meta("?p"), Meta("?q")), Ax1(a, b))
    target = conclusion(proof)

    assert not isinstance(target, Invalid)
    assert cd_progress(proof, target) > 0.0


def test_cd_progress_is_zero_when_cd_does_not_improve_similarity() -> None:
    a = Atom("a")
    b = Atom("b")
    proof = CD(Ax1(Meta("?p"), Meta("?q")), Ax1(a, b))
    target = Imp(Not(Imp(a, Not(b))), Not(Imp(b, Not(a))))

    assert cd_progress(proof, target) == 0.0


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
