from birdrat_proplogic.beam import (
    candidate_pairs,
    cd_beam_search,
    cd_beam_search_result,
    exploratory_pairs,
    implication_major_parts,
    implication_spine_suffixes,
    pair_priority,
    prioritized_candidate_pairs,
    prioritized_pairs,
    seeded_axiom_instances,
    suffix_pairs,
    suffix_priority,
)
from birdrat_proplogic.config import ArchiveConfig, EvolutionConfig, ProplogicConfig
from birdrat_proplogic.dproof import proves_identity_up_to_renaming
from birdrat_proplogic.evolution import evolve
from birdrat_proplogic.formula import Atom, Imp, Meta
from birdrat_proplogic.proof import Ax1, Ax2
from birdrat_proplogic.seed import formula_pool_from_target
from birdrat_proplogic.surface import SAtom, SImp


def test_cd_beam_rediscovers_identity_shape_without_hardcoded_proof() -> None:
    target = Imp(Meta("?x"), Meta("?x"))
    config = ProplogicConfig(
        archive=ArchiveConfig(path=None),
        evolution=EvolutionConfig(beam_width=18, beam_max_depth=2),
    )

    proofs = cd_beam_search(target, (), (target,), config)

    assert any(proves_identity_up_to_renaming(proof) for proof in proofs)


def test_beam_mixed_evolution_finds_closed_identity_target() -> None:
    config = ProplogicConfig(
        archive=ArchiveConfig(path=None),
        evolution=EvolutionConfig(
            population_size=6,
            max_generations=3,
            beam_width=12,
            beam_max_depth=2,
        ),
    )

    result = evolve(SImp(SAtom("a"), SAtom("a")), config, seed=1)

    assert result.best.fitness.exact_target
    assert result.history[-1].beam_pool_size > 0


def test_implication_major_parts_extracts_antecedent_and_consequent() -> None:
    proof = Ax1(Atom("p"), Atom("q"))

    assert implication_major_parts(proof) == (Atom("p"), Imp(Atom("q"), Atom("p")))


def test_implication_spine_suffixes_returns_right_associated_suffixes() -> None:
    p = Atom("p")
    q = Atom("q")
    r = Atom("r")
    target = Imp(Imp(p, q), Imp(Imp(p, Imp(q, r)), Imp(p, r)))

    assert implication_spine_suffixes(target) == (
        r,
        Imp(p, r),
        Imp(Imp(p, Imp(q, r)), Imp(p, r)),
        target,
    )


def test_suffix_priority_rewards_suffix_unification_without_axiom_bonus() -> None:
    p = Atom("p")
    q = Atom("q")
    target = Imp(p, Imp(q, p))

    assert suffix_priority(Imp(q, p), target, ()) == 1.0
    assert suffix_priority(Meta("?x"), target, ()) == 0.85


def test_pair_priority_requires_unifiable_minor() -> None:
    p = Atom("p")
    q = Atom("q")
    target = Imp(p, p)
    major = Ax2(Meta("?p"), Meta("?q"), Meta("?r"))
    minor = Ax1(p, q)

    assert pair_priority(major, minor, target, ()) > float("-inf")


def test_cd_beam_search_result_respects_pair_budget_and_reports_diagnostics() -> None:
    target = Imp(Meta("?x"), Meta("?x"))
    config = ProplogicConfig(
        archive=ArchiveConfig(path=None),
        evolution=EvolutionConfig(beam_width=12, beam_max_depth=2, beam_pair_budget=5),
    )

    result = cd_beam_search_result(target, (), (target,), config)

    assert result.diagnostics.pair_budget == 5
    assert all(layer.pair_attempts <= 5 for layer in result.diagnostics.layer_counts)
    assert result.diagnostics.pair_attempts <= 10
    assert all(0.0 <= layer.generated_ax1_fraction <= 1.0 for layer in result.diagnostics.layer_counts)
    assert all(0.0 <= layer.kept_ax3_fraction <= 1.0 for layer in result.diagnostics.layer_counts)


def test_beam_reports_suffix_retention_and_schema_instantiation() -> None:
    target = Imp(Atom("a"), Atom("a"))
    config = ProplogicConfig(
        archive=ArchiveConfig(path=None),
        evolution=EvolutionConfig(beam_width=12, beam_max_depth=2, beam_pair_budget=500),
    )

    result = cd_beam_search_result(target, (), (target,), config)

    assert any(layer.schema_instantiation_attempts > 0 for layer in result.diagnostics.layer_counts)
    assert any(layer.schema_instantiation_valid > 0 for layer in result.diagnostics.layer_counts)
    assert any(layer.schema_instantiation_exact_target > 0 for layer in result.diagnostics.layer_counts)
    assert all(layer.suffix_candidates_seen_by_suffix for layer in result.diagnostics.layer_counts)
    assert any(
        any(count > 0 for _suffix, count in layer.suffix_survivors_by_suffix)
        for layer in result.diagnostics.layer_counts
    )


def test_prioritized_candidate_pairs_filters_to_budgeted_unifiable_pairs() -> None:
    p = Atom("p")
    q = Atom("q")
    target = Imp(p, p)
    pool = (Ax2(Meta("?p"), Meta("?q"), Meta("?r")), Ax1(p, q), Ax1(q, p))
    config = ProplogicConfig(archive=ArchiveConfig(path=None))

    pairs, compatible = prioritized_candidate_pairs(
        pool,
        target,
        (),
        config,
        major_budget=3,
        pair_budget=2,
    )

    assert compatible > 0
    assert 0 < len(pairs) <= 2


def test_hybrid_candidate_pairs_add_non_strict_channels() -> None:
    p = Atom("p")
    q = Atom("q")
    r = Atom("r")
    target = Imp(Imp(p, q), Imp(Imp(r, p), Imp(r, q)))
    formula_pool = formula_pool_from_target(target, ())
    pool = seeded_axiom_instances(formula_pool, 40)
    config = ProplogicConfig(
        archive=ArchiveConfig(path=None),
        evolution=EvolutionConfig(
            beam_width=40,
            beam_pair_budget=100,
            beam_prioritized_fraction=1.0,
            beam_suffix_fraction=0.20,
            beam_exploratory_fraction=0.10,
        ),
    )

    selection = candidate_pairs(
        pool,
        target,
        (),
        config,
        major_budget=200,
        pair_budget=100,
    )

    assert selection.strict_pairs_attempted == 100
    assert selection.suffix_pairs_attempted > 0
    assert selection.exploratory_pairs_attempted > 0
    assert len(selection.pairs) > selection.strict_pairs_attempted


def test_pair_channels_are_separate_entry_points() -> None:
    p = Atom("p")
    q = Atom("q")
    target = Imp(p, p)
    pool = (Ax2(Meta("?p"), Meta("?q"), Meta("?r")), Ax1(p, q), Ax1(q, p))
    config = ProplogicConfig(archive=ArchiveConfig(path=None))

    strict = prioritized_pairs(pool, target, (), config, major_budget=3, pair_budget=2)
    suffix = suffix_pairs(pool, target, (), config, major_budget=3, pair_budget=2)
    exploratory = exploratory_pairs(pool, target, (), config, major_budget=3, pair_budget=2)

    assert len(strict.pairs) <= 2
    assert len(suffix.pairs) <= 2
    assert len(exploratory.pairs) <= 2
