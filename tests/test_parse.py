from birdrat_proplogic.parse import ParseError, parse_surface
from birdrat_proplogic.surface import SAnd, SAtom, SIff, SImp, SNot, SOr


def test_parse_latex_style_conjunction_commutativity() -> None:
    assert parse_surface(r"a \land b \to b \land a") == SImp(
        SAnd(SAtom("a"), SAtom("b")),
        SAnd(SAtom("b"), SAtom("a")),
    )


def test_parse_unicode_connectives() -> None:
    assert parse_surface("¬a ∨ b ↔ c") == SIff(
        SOr(SNot(SAtom("a")), SAtom("b")),
        SAtom("c"),
    )


def test_parse_implication_is_right_associative() -> None:
    assert parse_surface("a -> b -> c") == SImp(SAtom("a"), SImp(SAtom("b"), SAtom("c")))


def test_parse_sequent_surface_sugar() -> None:
    assert parse_surface("p -> q, r -> p, r |- q") == SImp(
        SImp(SAtom("p"), SAtom("q")),
        SImp(SImp(SAtom("r"), SAtom("p")), SImp(SAtom("r"), SAtom("q"))),
    )


def test_parse_unicode_turnstile_surface_sugar() -> None:
    assert parse_surface("a, b ⊢ c") == SImp(SAtom("a"), SImp(SAtom("b"), SAtom("c")))


def test_parse_parentheses_override_precedence() -> None:
    assert parse_surface("(a -> b) -> c") == SImp(SImp(SAtom("a"), SAtom("b")), SAtom("c"))


def test_parse_reports_invalid_input() -> None:
    result = parse_surface("a ->")

    assert isinstance(result, ParseError)
