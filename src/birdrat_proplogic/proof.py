from __future__ import annotations

from dataclasses import dataclass
from typing import TypeAlias

from birdrat_proplogic.formula import Formula, Imp, Not
from birdrat_proplogic.unify import UnifyFailure, apply_subst, unify


@dataclass(frozen=True)
class Ax1:
    p: Formula
    q: Formula


@dataclass(frozen=True)
class Ax2:
    p: Formula
    q: Formula
    r: Formula


@dataclass(frozen=True)
class Ax3:
    p: Formula
    q: Formula


@dataclass(frozen=True)
class CD:
    major: Proof
    minor: Proof


Proof: TypeAlias = Ax1 | Ax2 | Ax3 | CD


@dataclass(frozen=True)
class Invalid:
    reason: str


Conclusion: TypeAlias = Formula | Invalid


def conclusion(proof: Proof) -> Conclusion:
    match proof:
        case Ax1(p, q):
            return Imp(p, Imp(q, p))
        case Ax2(p, q, r):
            return Imp(Imp(p, Imp(q, r)), Imp(Imp(p, q), Imp(p, r)))
        case Ax3(p, q):
            return Imp(Imp(Not(p), Not(q)), Imp(q, p))
        case CD(major, minor):
            major_conclusion = conclusion(major)
            if isinstance(major_conclusion, Invalid):
                return Invalid(f"invalid major: {major_conclusion.reason}")
            minor_conclusion = conclusion(minor)
            if isinstance(minor_conclusion, Invalid):
                return Invalid(f"invalid minor: {minor_conclusion.reason}")
            if not isinstance(major_conclusion, Imp):
                return Invalid("major conclusion is not an implication")

            subst = unify(major_conclusion.left, minor_conclusion)
            if isinstance(subst, UnifyFailure):
                return Invalid(f"antecedent does not unify with minor: {subst.reason}")
            return apply_subst(major_conclusion.right, subst)


def is_valid(proof: Proof) -> bool:
    return not isinstance(conclusion(proof), Invalid)


def cd_steps(proof: Proof) -> int:
    match proof:
        case Ax1() | Ax2() | Ax3():
            return 0
        case CD(major, minor):
            return 1 + cd_steps(major) + cd_steps(minor)


def cd_depth(proof: Proof) -> int:
    match proof:
        case Ax1() | Ax2() | Ax3():
            return 0
        case CD(major, minor):
            return 1 + max(cd_depth(major), cd_depth(minor))


def proof_size(proof: Proof) -> int:
    match proof:
        case Ax1() | Ax2() | Ax3():
            return 1
        case CD(major, minor):
            return 1 + proof_size(major) + proof_size(minor)

