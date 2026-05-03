from __future__ import annotations

from dataclasses import dataclass

from birdrat_proplogic.formula import Formula, Imp, Meta, pretty
from birdrat_proplogic.proof import Ax1, Ax2, Ax3, CD, Invalid, Proof, conclusion


@dataclass(frozen=True)
class DProofParseError:
    message: str


DProofParseResult = Proof | DProofParseError


def parse_dproof(text: str) -> DProofParseResult:
    parser = _DProofParser("".join(text.split()))
    proof = parser.parse()
    if isinstance(proof, DProofParseError):
        return proof
    if parser.current() is not None:
        return DProofParseError(f"unexpected token: {parser.current()}")
    return proof


def fresh_axiom(number: str, leaf_index: int) -> Proof | DProofParseError:
    p = Meta(f"?p{leaf_index}")
    q = Meta(f"?q{leaf_index}")
    r = Meta(f"?r{leaf_index}")
    if number == "1":
        return Ax1(p, q)
    if number == "2":
        return Ax2(p, q, r)
    if number == "3":
        return Ax3(p, q)
    return DProofParseError(f"unknown axiom: {number}")


def proves_identity_up_to_renaming(proof: Proof) -> bool:
    proof_conclusion = conclusion(proof)
    if isinstance(proof_conclusion, Invalid):
        return False
    return canonicalize_metas(proof_conclusion) == Imp(Meta("?m0"), Meta("?m0"))


def canonicalize_metas(formula: Formula) -> Formula:
    names: dict[str, str] = {}

    def visit(item: Formula) -> Formula:
        match item:
            case Meta(name):
                if name not in names:
                    names[name] = f"?m{len(names)}"
                return Meta(names[name])
            case Imp(left, right):
                return Imp(visit(left), visit(right))
            case _:
                from birdrat_proplogic.formula import Atom, Not

                match item:
                    case Atom():
                        return item
                    case Not(body):
                        return Not(visit(body))

    return visit(formula)


def render_dproof_verification(text: str) -> str:
    proof = parse_dproof(text)
    if isinstance(proof, DProofParseError):
        return f"invalid D-proof: {proof.message}"
    proof_conclusion = conclusion(proof)
    if isinstance(proof_conclusion, Invalid):
        conclusion_text = f"invalid: {proof_conclusion.reason}"
    else:
        conclusion_text = pretty(proof_conclusion)
    identity = "yes" if proves_identity_up_to_renaming(proof) else "no"
    return "\n".join(
        [
            f"D-proof: {''.join(text.split())}",
            f"conclusion: {conclusion_text}",
            f"derives p -> p up to metavariable renaming: {identity}",
        ]
    )


class _DProofParser:
    def __init__(self, text: str) -> None:
        self.text = text
        self.index = 0
        self.leaf_count = 0

    def current(self) -> str | None:
        if self.index >= len(self.text):
            return None
        return self.text[self.index]

    def advance(self) -> str | None:
        token = self.current()
        if token is not None:
            self.index += 1
        return token

    def parse(self) -> DProofParseResult:
        token = self.advance()
        if token is None:
            return DProofParseError("expected D, 1, 2, or 3")
        if token == "D":
            major = self.parse()
            if isinstance(major, DProofParseError):
                return major
            minor = self.parse()
            if isinstance(minor, DProofParseError):
                return minor
            return CD(major, minor)
        if token in ("1", "2", "3"):
            self.leaf_count += 1
            return fresh_axiom(token, self.leaf_count)
        return DProofParseError(f"unexpected token: {token}")
