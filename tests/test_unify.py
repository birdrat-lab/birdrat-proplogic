from birdrat_proplogic.formula import Atom, Imp, Meta, Not
from birdrat_proplogic.unify import UnifyFailure, unify


def test_successful_unification_meta_with_atom() -> None:
    assert unify(Meta("?p"), Atom("a")) == {"?p": Atom("a")}


def test_successful_unification_compound_formula() -> None:
    result = unify(
        Imp(Meta("?p"), Meta("?q")),
        Imp(Atom("a"), Not(Atom("b"))),
    )
    assert result == {"?p": Atom("a"), "?q": Not(Atom("b"))}


def test_failed_unification() -> None:
    assert isinstance(unify(Atom("a"), Atom("b")), UnifyFailure)


def test_occurs_check_failure() -> None:
    assert isinstance(unify(Meta("?p"), Imp(Atom("a"), Meta("?p"))), UnifyFailure)

