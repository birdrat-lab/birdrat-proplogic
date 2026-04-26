from random import Random

from birdrat_proplogic.config import MutationConfig, ProplogicConfig
from birdrat_proplogic.formula import Atom, Imp, Meta, Not, formula_size
from birdrat_proplogic.mutate import (
    mutate_axiom_formula_argument,
    mutate_formula,
    mutate_proof,
    random_formula,
    random_proof,
    replace_cd_child,
    replace_subtree,
    swap_cd_children,
    wrap_cd,
)
from birdrat_proplogic.proof import Ax1, CD, Proof, proof_size


def test_mutate_formula_respects_size_limit() -> None:
    config = ProplogicConfig(mutation=MutationConfig(max_formula_size=2))
    formula = Atom("a")

    mutated = mutate_formula(formula, Random(0), config)

    assert formula_size(mutated) <= 2


def test_mutate_formula_can_mutate_inside_implication() -> None:
    formula = Imp(Atom("a"), Atom("b"))

    mutated = mutate_formula(formula, Random(1))

    assert mutated != formula


def test_random_formula_respects_depth_zero_leaf() -> None:
    formula = random_formula(Random(0), depth=0)

    assert isinstance(formula, Atom | Meta)


def test_random_proof_builds_proof_tree() -> None:
    proof = random_proof(Random(2), depth=2)

    assert isinstance(proof, Proof)


def test_mutate_axiom_formula_argument_changes_axiom_arguments() -> None:
    proof = Ax1(Atom("a"), Atom("b"))

    mutated = mutate_axiom_formula_argument(proof, Random(3))

    assert isinstance(mutated, Ax1)
    assert mutated != proof


def test_wrap_cd_adds_condensed_detachment_node() -> None:
    proof = Ax1(Atom("a"), Atom("b"))

    mutated = wrap_cd(proof, Random(4))

    assert isinstance(mutated, CD)
    assert proof_size(mutated) > proof_size(proof)


def test_swap_cd_children_swaps_major_and_minor() -> None:
    major = Ax1(Atom("a"), Atom("b"))
    minor = Ax1(Atom("b"), Atom("a"))
    proof = CD(major, minor)

    assert swap_cd_children(proof) == CD(minor, major)


def test_replace_cd_child_replaces_one_child() -> None:
    major = Ax1(Atom("a"), Atom("b"))
    minor = Ax1(Atom("b"), Atom("a"))
    proof = CD(major, minor)

    mutated = replace_cd_child(proof, Random(5))

    assert isinstance(mutated, CD)
    assert mutated.major != major or mutated.minor != minor


def test_replace_subtree_can_replace_root() -> None:
    proof = CD(Ax1(Atom("a"), Atom("b")), Ax1(Atom("b"), Atom("a")))

    mutated = replace_subtree(proof, Random(1))

    assert mutated != proof


def test_mutate_proof_returns_proof() -> None:
    proof = CD(Ax1(Atom("a"), Atom("b")), Ax1(Atom("b"), Atom("a")))

    mutated = mutate_proof(proof, Random(6))

    assert isinstance(mutated, Proof)


def test_formula_mutation_can_wrap_with_negation_or_implication() -> None:
    mutated = mutate_formula(Atom("a"), Random(2))

    assert isinstance(mutated, Atom | Not | Imp)
