from birdrat_proplogic.formula import Atom, Imp, Meta, Not
from birdrat_proplogic.proof import Ax1, Ax2, Ax3, CD, Invalid, cd_depth, cd_steps, conclusion, proof_pretty, proof_size


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


def test_proof_pretty_includes_axiom_and_conclusion() -> None:
    proof = Ax1(Atom("a"), Atom("b"))

    assert proof_pretty(proof) == "1. Ax1 (p := a, q := b) proves a → b → a"


def test_proof_pretty_linearizes_cd_steps() -> None:
    proof = CD(Ax1(Meta("?p"), Meta("?q")), Ax1(Atom("a"), Atom("b")))

    lines = proof_pretty(proof).splitlines()

    assert lines[0].startswith("1. Ax1")
    assert lines[1].startswith("2. Ax1")
    assert lines[2].startswith("3. CD")
    assert "steps 1 and 2" in lines[2]
