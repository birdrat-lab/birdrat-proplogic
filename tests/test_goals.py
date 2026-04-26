from birdrat_proplogic.config import ProplogicConfig, RegionConfig
from birdrat_proplogic.formula import Atom, Imp, Not
from birdrat_proplogic.goals import Goal, extract_goals
from birdrat_proplogic.surface import SAnd, SAtom, SIff, SImp, desugar


def theorem_set(goals: tuple[Goal, ...]) -> set[object]:
    return {goal.theorem() for goal in goals}


def test_region_extraction_for_conjunction_commutativity() -> None:
    a = SAtom("a")
    b = SAtom("b")
    target = SImp(SAnd(a, b), SAnd(b, a))
    goals = extract_goals(target)
    theorems = theorem_set(goals)

    assert target in theorems
    assert SImp(SAnd(a, b), b) in theorems
    assert SImp(SAnd(a, b), a) in theorems
    assert all(goal.core_theorem() == desugar(goal.theorem()) for goal in goals)


def test_region_extraction_for_biconditional() -> None:
    a = SAtom("A")
    b = SAtom("B")
    target = SIff(a, b)
    theorems = theorem_set(extract_goals(target))

    assert target in theorems
    assert SImp(a, b) in theorems
    assert SImp(b, a) in theorems


def test_goal_conversion_back_to_theorem_form() -> None:
    a = SAtom("a")
    b = SAtom("b")
    c = SAtom("c")
    goal = Goal((a, b), c, "example", 1.0)

    assert goal.theorem() == SImp(a, SImp(b, c))
    assert goal.core_theorem() == Imp(Atom("a"), Imp(Atom("b"), Atom("c")))


def test_context_conjunction_regions() -> None:
    a = SAtom("a")
    b = SAtom("b")
    c = SAtom("c")
    goals = extract_goals(SImp(SAnd(a, b), c))
    theorems = theorem_set(goals)

    assert SImp(SAnd(a, b), a) in theorems
    assert SImp(SAnd(a, b), b) in theorems
    assert SImp(SAnd(a, b), c) in theorems
    assert SImp(a, SImp(b, c)) not in theorems


def test_context_conjunction_split_is_experimental_flag() -> None:
    a = SAtom("a")
    b = SAtom("b")
    c = SAtom("c")
    config = ProplogicConfig(regions=RegionConfig(enable_context_conjunction_split=True))
    theorems = theorem_set(extract_goals(SImp(SAnd(a, b), c), config))

    assert SImp(a, SImp(b, c)) in theorems


def test_goal_core_theorem_desugars_context() -> None:
    a = SAtom("a")
    b = SAtom("b")
    goal = Goal((SAnd(a, b),), a)

    assert goal.core_theorem() == Imp(Not(Imp(Atom("a"), Not(Atom("b")))), Atom("a"))


def test_region_extraction_uses_configured_weights() -> None:
    a = SAtom("a")
    b = SAtom("b")
    config = ProplogicConfig(
        regions=RegionConfig(
            whole_goal_weight=2.0,
            implication_target_weight=0.25,
        )
    )

    goals = extract_goals(SImp(a, b), config)
    weights_by_name = {goal.name: goal.weight for goal in goals}

    assert weights_by_name["whole"] == 2.0
    assert weights_by_name["whole:imp"] == 0.5
