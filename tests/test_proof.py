from birdrat_proplogic.formula import Atom, Imp, Meta, Not
from birdrat_proplogic.proof import Ax1, Ax2, Ax3, CD, Invalid, cd_depth, cd_steps, conclusion, proof_size


def test_p2_axiom_conclusions() -> None:
    p = Atom("p")
    q = Atom("q")
    r = Atom("r")

    assert conclusion(Ax1(p, q)) == Imp(p, Imp(q, p))
    assert conclusion(Ax2(p, q, r)) == Imp(Imp(p, Imp(q, r)), Imp(Imp(p, q), Imp(p, r)))
    assert conclusion(Ax3(p, q)) == Imp(Imp(Not(p), Not(q)), Imp(q, p))


def test_valid_cd() -> None:
    proof = CD(Ax1(Meta("?p"), Meta("?q")), Ax1(Atom("a"), Atom("b")))
    minor_conclusion = Imp(Atom("a"), Imp(Atom("b"), Atom("a")))

    assert conclusion(proof) == Imp(Meta("?q"), minor_conclusion)


def test_invalid_cd_when_antecedent_does_not_unify() -> None:
    proof = CD(Ax1(Atom("a"), Atom("b")), Ax1(Atom("x"), Atom("y")))
    assert isinstance(conclusion(proof), Invalid)


def test_invalid_cd_propagates_from_subproof() -> None:
    invalid_minor = CD(Ax1(Atom("a"), Atom("b")), Ax1(Atom("x"), Atom("y")))
    proof = CD(Ax1(Meta("?p"), Meta("?q")), invalid_minor)

    assert isinstance(conclusion(proof), Invalid)


def test_proof_metrics() -> None:
    proof = CD(CD(Ax1(Meta("?p"), Meta("?q")), Ax1(Atom("a"), Atom("b"))), Ax1(Atom("x"), Atom("y")))

    assert cd_steps(proof) == 2
    assert cd_depth(proof) == 2
    assert proof_size(proof) == 5
