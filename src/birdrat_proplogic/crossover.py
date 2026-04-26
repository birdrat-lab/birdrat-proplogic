from __future__ import annotations

from random import Random
from typing import Literal, TypeAlias

from birdrat_proplogic.formula import Atom, Formula, Imp, Meta, Not
from birdrat_proplogic.proof import Ax1, Ax2, Ax3, CD, Proof

ProofKind: TypeAlias = Literal["axiom", "cd"]
FormulaPath: TypeAlias = tuple[Literal["body", "left", "right"], ...]
ProofPath: TypeAlias = tuple[Literal["major", "minor"], ...]
FormulaSlot: TypeAlias = Literal["p", "q", "r"]
AxiomFormulaPath: TypeAlias = tuple[ProofPath, FormulaSlot, FormulaPath]


def crossover_proof(
    left: Proof,
    right: Proof,
    rng: Random | None = None,
    prefer_same_kind: bool = True,
) -> Proof:
    random = _rng(rng)
    if random.random() < 0.5:
        return proof_subtree_crossover(left, right, random, prefer_same_kind)
    return formula_subtree_crossover(left, right, random)


def proof_subtree_crossover(
    left: Proof,
    right: Proof,
    rng: Random | None = None,
    prefer_same_kind: bool = True,
) -> Proof:
    random = _rng(rng)
    left_paths = _proof_paths(left)
    left_path = random.choice(left_paths)
    left_kind = _proof_kind(_get_proof_subtree(left, left_path))
    right_paths = _proof_paths(right)
    compatible_right_paths = [
        path
        for path in right_paths
        if _proof_kind(_get_proof_subtree(right, path)) == left_kind
    ]
    if prefer_same_kind and compatible_right_paths:
        right_path = random.choice(compatible_right_paths)
    else:
        right_path = random.choice(right_paths)
    return _replace_proof_subtree(left, left_path, _get_proof_subtree(right, right_path))


def formula_subtree_crossover(
    left: Proof,
    right: Proof,
    rng: Random | None = None,
) -> Proof:
    random = _rng(rng)
    left_paths = _axiom_formula_paths(left)
    right_paths = _axiom_formula_paths(right)
    if not left_paths or not right_paths:
        return left
    left_path = random.choice(left_paths)
    right_path = random.choice(right_paths)
    return _replace_formula_in_proof(left, left_path, _get_formula_from_proof(right, right_path))


def crossover_formula(
    left: Formula,
    right: Formula,
    rng: Random | None = None,
) -> Formula:
    random = _rng(rng)
    left_path = random.choice(_formula_paths(left))
    right_path = random.choice(_formula_paths(right))
    return _replace_formula_subtree(left, left_path, _get_formula_subtree(right, right_path))


def _proof_paths(proof: Proof) -> tuple[ProofPath, ...]:
    paths: list[ProofPath] = [()]
    match proof:
        case Ax1() | Ax2() | Ax3():
            pass
        case CD(major, minor):
            paths.extend((("major",) + path for path in _proof_paths(major)))
            paths.extend((("minor",) + path for path in _proof_paths(minor)))
    return tuple(paths)


def _axiom_formula_paths(proof: Proof) -> tuple[AxiomFormulaPath, ...]:
    paths: list[AxiomFormulaPath] = []
    for proof_path in _proof_paths(proof):
        subtree = _get_proof_subtree(proof, proof_path)
        match subtree:
            case Ax1(p, q):
                paths.extend(
                    [
                        (proof_path, "p", path)
                        for path in _formula_paths(p)
                    ]
                )
                paths.extend(
                    [
                        (proof_path, "q", path)
                        for path in _formula_paths(q)
                    ]
                )
            case Ax2(p, q, r):
                paths.extend([(proof_path, "p", path) for path in _formula_paths(p)])
                paths.extend([(proof_path, "q", path) for path in _formula_paths(q)])
                paths.extend([(proof_path, "r", path) for path in _formula_paths(r)])
            case Ax3(p, q):
                paths.extend([(proof_path, "p", path) for path in _formula_paths(p)])
                paths.extend([(proof_path, "q", path) for path in _formula_paths(q)])
            case CD():
                pass
    return tuple(paths)


def _formula_paths(formula: Formula) -> tuple[FormulaPath, ...]:
    paths: list[FormulaPath] = [()]
    match formula:
        case Atom() | Meta():
            pass
        case Not(body):
            paths.extend((("body",) + path for path in _formula_paths(body)))
        case Imp(left, right):
            paths.extend((("left",) + path for path in _formula_paths(left)))
            paths.extend((("right",) + path for path in _formula_paths(right)))
    return tuple(paths)


def _get_proof_subtree(proof: Proof, path: ProofPath) -> Proof:
    if not path:
        return proof
    if not isinstance(proof, CD):
        raise ValueError("proof path descends through a non-CD node")
    head, *tail = path
    if head == "major":
        return _get_proof_subtree(proof.major, tuple(tail))
    return _get_proof_subtree(proof.minor, tuple(tail))


def _replace_proof_subtree(proof: Proof, path: ProofPath, replacement: Proof) -> Proof:
    if not path:
        return replacement
    if not isinstance(proof, CD):
        raise ValueError("proof path descends through a non-CD node")
    head, *tail = path
    if head == "major":
        return CD(_replace_proof_subtree(proof.major, tuple(tail), replacement), proof.minor)
    return CD(proof.major, _replace_proof_subtree(proof.minor, tuple(tail), replacement))


def _get_formula_from_proof(proof: Proof, path: AxiomFormulaPath) -> Formula:
    proof_path, slot, formula_path = path
    axiom = _get_proof_subtree(proof, proof_path)
    return _get_formula_subtree(_get_axiom_formula(axiom, slot), formula_path)


def _replace_formula_in_proof(proof: Proof, path: AxiomFormulaPath, replacement: Formula) -> Proof:
    proof_path, slot, formula_path = path
    axiom = _get_proof_subtree(proof, proof_path)
    formula = _get_axiom_formula(axiom, slot)
    changed_formula = _replace_formula_subtree(formula, formula_path, replacement)
    changed_axiom = _replace_axiom_formula(axiom, slot, changed_formula)
    return _replace_proof_subtree(proof, proof_path, changed_axiom)


def _get_axiom_formula(proof: Proof, slot: FormulaSlot) -> Formula:
    match proof:
        case Ax1(p, q) | Ax3(p, q):
            if slot == "p":
                return p
            if slot == "q":
                return q
        case Ax2(p, q, r):
            if slot == "p":
                return p
            if slot == "q":
                return q
            if slot == "r":
                return r
        case CD():
            pass
    raise ValueError(f"slot {slot} is not available on proof node")


def _replace_axiom_formula(proof: Proof, slot: FormulaSlot, replacement: Formula) -> Proof:
    match proof:
        case Ax1(p, q):
            if slot == "p":
                return Ax1(replacement, q)
            if slot == "q":
                return Ax1(p, replacement)
        case Ax2(p, q, r):
            if slot == "p":
                return Ax2(replacement, q, r)
            if slot == "q":
                return Ax2(p, replacement, r)
            if slot == "r":
                return Ax2(p, q, replacement)
        case Ax3(p, q):
            if slot == "p":
                return Ax3(replacement, q)
            if slot == "q":
                return Ax3(p, replacement)
        case CD():
            pass
    raise ValueError(f"slot {slot} is not available on proof node")


def _get_formula_subtree(formula: Formula, path: FormulaPath) -> Formula:
    if not path:
        return formula
    head, *tail = path
    match formula:
        case Not(body) if head == "body":
            return _get_formula_subtree(body, tuple(tail))
        case Imp(left, _) if head == "left":
            return _get_formula_subtree(left, tuple(tail))
        case Imp(_, right) if head == "right":
            return _get_formula_subtree(right, tuple(tail))
        case _:
            raise ValueError("formula path descends through an incompatible node")


def _replace_formula_subtree(formula: Formula, path: FormulaPath, replacement: Formula) -> Formula:
    if not path:
        return replacement
    head, *tail = path
    match formula:
        case Not(body) if head == "body":
            return Not(_replace_formula_subtree(body, tuple(tail), replacement))
        case Imp(left, right) if head == "left":
            return Imp(_replace_formula_subtree(left, tuple(tail), replacement), right)
        case Imp(left, right) if head == "right":
            return Imp(left, _replace_formula_subtree(right, tuple(tail), replacement))
        case _:
            raise ValueError("formula path descends through an incompatible node")


def _proof_kind(proof: Proof) -> ProofKind:
    if isinstance(proof, CD):
        return "cd"
    return "axiom"


def _rng(rng: Random | None) -> Random:
    if rng is None:
        return Random()
    return rng
