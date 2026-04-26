from __future__ import annotations

from dataclasses import dataclass
from typing import TypeAlias

from birdrat_proplogic.formula import Formula, Imp, Not, pretty
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


@dataclass(frozen=True)
class ProofStep:
    index: int
    rule: str
    conclusion: Conclusion
    detail: str
    premises: tuple[int, ...] = ()


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


def proof_pretty(proof: Proof) -> str:
    return "\n".join(proof_pretty_lines(proof))


def proof_pretty_lines(proof: Proof) -> tuple[str, ...]:
    return tuple(_format_step(step) for step in linearize_proof(proof))


def linearize_proof(proof: Proof) -> tuple[ProofStep, ...]:
    steps, _ = _linearize_proof(proof, 1)
    return tuple(steps)


def _linearize_proof(proof: Proof, next_index: int) -> tuple[list[ProofStep], int]:
    match proof:
        case Ax1(p, q):
            return (
                [
                    ProofStep(
                        index=next_index,
                        rule="Ax1",
                        conclusion=conclusion(proof),
                        detail=f"p := {pretty(p)}, q := {pretty(q)}",
                    )
                ],
                next_index + 1,
            )
        case Ax2(p, q, r):
            return (
                [
                    ProofStep(
                        index=next_index,
                        rule="Ax2",
                        conclusion=conclusion(proof),
                        detail=f"p := {pretty(p)}, q := {pretty(q)}, r := {pretty(r)}",
                    )
                ],
                next_index + 1,
            )
        case Ax3(p, q):
            return (
                [
                    ProofStep(
                        index=next_index,
                        rule="Ax3",
                        conclusion=conclusion(proof),
                        detail=f"p := {pretty(p)}, q := {pretty(q)}",
                    )
                ],
                next_index + 1,
            )
        case CD(major, minor):
            major_steps, after_major = _linearize_proof(major, next_index)
            minor_steps, after_minor = _linearize_proof(minor, after_major)
            major_index = major_steps[-1].index
            minor_index = minor_steps[-1].index
            step = ProofStep(
                index=after_minor,
                rule="CD",
                conclusion=conclusion(proof),
                detail=f"condensed detachment from steps {major_index} and {minor_index}",
                premises=(major_index, minor_index),
            )
            return (major_steps + minor_steps + [step], after_minor + 1)


def _format_step(step: ProofStep) -> str:
    if isinstance(step.conclusion, Invalid):
        conclusion_text = f"invalid: {step.conclusion.reason}"
    else:
        conclusion_text = pretty(step.conclusion)
    return f"{step.index}. {step.rule} ({step.detail}) proves {conclusion_text}"
