from random import Random

from birdrat_proplogic.crossover import crossover_formula, formula_subtree_crossover, proof_subtree_crossover
from birdrat_proplogic.formula import Atom, Imp, Not
from birdrat_proplogic.proof import Ax1, Ax2, Ax3, CD, proof_size


def test_crossover_formula_replaces_a_subformula() -> None:
    left = Imp(Atom("a"), Atom("b"))
    right = Not(Atom("c"))

    child = crossover_formula(left, right, Random(0))

    assert child != left


def test_proof_subtree_crossover_returns_proof_with_bounded_size() -> None:
    left = CD(Ax1(Atom("a"), Atom("b")), Ax3(Atom("b"), Atom("c")))
    right = CD(Ax2(Atom("c"), Atom("a"), Atom("b")), Ax1(Atom("c"), Atom("c")))

    child = proof_subtree_crossover(left, right, Random(1))

    assert proof_size(child) <= proof_size(left) + proof_size(right)


def test_proof_subtree_crossover_can_replace_root() -> None:
    left = Ax1(Atom("a"), Atom("b"))
    right = Ax3(Atom("c"), Atom("d"))

    child = proof_subtree_crossover(left, right, Random(0))

    assert child == right


def test_proof_subtree_crossover_prefers_axiom_for_axiom() -> None:
    left = Ax1(Atom("a"), Atom("b"))
    right = CD(Ax2(Atom("c"), Atom("d"), Atom("e")), Ax3(Atom("f"), Atom("g")))

    child = proof_subtree_crossover(left, right, Random(0), prefer_same_kind=True)

    assert isinstance(child, Ax2 | Ax3)


def test_proof_subtree_crossover_can_prefer_cd_for_cd() -> None:
    left = CD(Ax1(Atom("a"), Atom("b")), Ax1(Atom("b"), Atom("a")))
    right = CD(CD(Ax2(Atom("c"), Atom("d"), Atom("e")), Ax3(Atom("f"), Atom("g"))), Ax1(Atom("h"), Atom("i")))

    child = proof_subtree_crossover(left, right, Random(2), prefer_same_kind=True)

    assert isinstance(child, CD)


def test_formula_subtree_crossover_changes_axiom_argument() -> None:
    left = Ax1(Imp(Atom("a"), Atom("b")), Atom("c"))
    right = Ax3(Not(Atom("d")), Atom("e"))

    child = formula_subtree_crossover(left, right, Random(4))

    assert child != left
    assert isinstance(child, Ax1)
