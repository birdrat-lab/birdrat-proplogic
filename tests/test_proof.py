from birdrat_proplogic.formula import Atom, Imp, Meta, Not
from birdrat_proplogic.proof import (
    Ax1,
    Ax2,
    Ax3,
    CD,
    Invalid,
    cd_depth,
    cd_steps,
    conclusion,
    is_weakening_cd,
    is_vacuous_cd,
    proof_pretty,
    proof_size,
    strip_vacuous_weakening,
    substantive_cd_steps,
)


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


def test_vacuous_weakening_detection_strips_ax1_cd_wrapper() -> None:
    a = Atom("a")
    b = Atom("b")
    h = Not(Imp(a, Not(b)))
    k = Not(Imp(b, Not(a)))
    ax1 = Ax1(Meta("?p"), h)
    ax3 = Ax3(Not(Imp(a, Not(k))), a)
    proof = CD(ax1, ax3)

    stripped_conclusion, wrappers = strip_vacuous_weakening(proof)

    assert is_weakening_cd(proof)
    assert stripped_conclusion == conclusion(ax3)
    assert wrappers == 1
    assert substantive_cd_steps(proof) == 0


def test_vacuous_cd_detection_catches_ax1_wrap_then_unwrap_detour() -> None:
    a = Atom("a")
    b = Atom("b")
    h = Not(Imp(a, Not(b)))
    base = Ax1(h, a)
    wrapper = CD(Ax1(Meta("?r"), Meta("?q")), base)
    detour = CD(wrapper, Ax1(b, a))

    stripped_conclusion, wrappers = strip_vacuous_weakening(detour)

    assert not is_weakening_cd(detour)
    assert is_vacuous_cd(detour)
    assert stripped_conclusion == conclusion(base)
    assert wrappers == 2
    assert substantive_cd_steps(detour) == 0


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
