from birdrat_proplogic.formula import Atom, Imp, Meta, Not, formula_size, is_closed_formula, metas, pretty
from birdrat_proplogic.surface import (
    SAnd,
    SAtom,
    SIff,
    SImp,
    SOr,
    desugar,
    surface_display,
    surface_implication_spine,
    surface_pretty,
    surface_sequent_pretty,
)


def test_formula_equality() -> None:
    assert Imp(Atom("a"), Not(Atom("b"))) == Imp(Atom("a"), Not(Atom("b")))
    assert Atom("a") != Atom("b")


def test_formula_pretty_printing() -> None:
    assert pretty(Atom("a")) == "a"
    assert pretty(Not(Atom("a"))) == "¬a"
    assert pretty(Imp(Atom("a"), Imp(Atom("b"), Atom("a")))) == "a → b → a"
    assert pretty(Imp(Imp(Atom("a"), Atom("b")), Atom("c"))) == "(a → b) → c"


def test_formula_size() -> None:
    assert formula_size(Atom("a")) == 1
    assert formula_size(Not(Atom("a"))) == 2
    assert formula_size(Imp(Atom("a"), Atom("b"))) == 3


def test_metas_and_closed_formula_detection() -> None:
    formula = Imp(Atom("a"), Not(Meta("?p")))

    assert metas(formula) == frozenset((Meta("?p"),))
    assert not is_closed_formula(formula)
    assert is_closed_formula(Imp(Atom("a"), Not(Atom("b"))))


def test_desugaring_and_or_iff() -> None:
    a = SAtom("a")
    b = SAtom("b")

    assert desugar(SOr(a, b)) == Imp(Not(Atom("a")), Atom("b"))
    assert desugar(SAnd(a, b)) == Not(Imp(Atom("a"), Not(Atom("b"))))
    assert desugar(SIff(a, b)) == Not(
        Imp(Imp(Atom("a"), Atom("b")), Not(Imp(Atom("b"), Atom("a"))))
    )


def test_desugaring_spec_example() -> None:
    a = SAtom("a")
    b = SAtom("b")
    assert desugar(SImp(SAnd(a, b), SAnd(b, a))) == Imp(
        Not(Imp(Atom("a"), Not(Atom("b")))),
        Not(Imp(Atom("b"), Not(Atom("a")))),
    )


def test_surface_pretty_printing() -> None:
    assert surface_pretty(SImp(SAnd(SAtom("a"), SAtom("b")), SAtom("c"))) == "a ∧ b → c"


def test_surface_sequent_display_for_implication_spine() -> None:
    formula = SImp(
        SImp(SAtom("p"), SAtom("q")),
        SImp(SImp(SAtom("r"), SAtom("p")), SImp(SAtom("r"), SAtom("q"))),
    )

    assert surface_implication_spine(formula) == (
        (SImp(SAtom("p"), SAtom("q")), SImp(SAtom("r"), SAtom("p")), SAtom("r")),
        SAtom("q"),
    )
    assert surface_sequent_pretty(formula) == "p → q, r → p, r |- q"
    assert surface_display(formula) == "\n".join(
        (
            "assumptions:",
            "  1. p → q",
            "  2. r → p",
            "  3. r",
            "conclusion:",
            "  q",
        )
    )
