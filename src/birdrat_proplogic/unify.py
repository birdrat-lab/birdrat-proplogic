from __future__ import annotations

from dataclasses import dataclass
from typing import TypeAlias

from birdrat_proplogic.formula import Atom, Formula, Imp, Meta, Not


Substitution: TypeAlias = dict[str, Formula]


@dataclass(frozen=True)
class UnifyFailure:
    reason: str


UnifyResult: TypeAlias = Substitution | UnifyFailure


def unify(left: Formula, right: Formula) -> UnifyResult:
    return _unify(left, right, {})


def is_failure(result: UnifyResult) -> bool:
    return isinstance(result, UnifyFailure)


def apply_subst(formula: Formula, subst: Substitution) -> Formula:
    match formula:
        case Atom():
            return formula
        case Meta(name):
            replacement = subst.get(name)
            if replacement is None:
                return formula
            return apply_subst(replacement, subst)
        case Not(body):
            return Not(apply_subst(body, subst))
        case Imp(left, right):
            return Imp(apply_subst(left, subst), apply_subst(right, subst))


def _unify(left: Formula, right: Formula, subst: Substitution) -> UnifyResult:
    left = apply_subst(left, subst)
    right = apply_subst(right, subst)

    if left == right:
        return subst

    match left, right:
        case Meta(name), _:
            return _bind(name, right, subst)
        case _, Meta(name):
            return _bind(name, left, subst)
        case Atom(left_name), Atom(right_name):
            return UnifyFailure(f"atom mismatch: {left_name} != {right_name}")
        case Not(left_body), Not(right_body):
            return _unify(left_body, right_body, subst)
        case Imp(left_a, left_b), Imp(right_a, right_b):
            first = _unify(left_a, right_a, subst)
            if is_failure(first):
                return first
            return _unify(left_b, right_b, first)
        case _:
            return UnifyFailure("shape mismatch")


def _bind(name: str, formula: Formula, subst: Substitution) -> UnifyResult:
    if Meta(name) == formula:
        return subst
    if _occurs(name, formula, subst):
        return UnifyFailure(f"occurs check failed: {name}")

    extended = dict(subst)
    extended[name] = formula
    return {key: apply_subst(value, extended) for key, value in extended.items()}


def _occurs(name: str, formula: Formula, subst: Substitution) -> bool:
    formula = apply_subst(formula, subst)
    match formula:
        case Atom():
            return False
        case Meta(other):
            return name == other
        case Not(body):
            return _occurs(name, body, subst)
        case Imp(left, right):
            return _occurs(name, left, subst) or _occurs(name, right, subst)

