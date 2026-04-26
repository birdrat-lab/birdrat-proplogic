from __future__ import annotations

from dataclasses import dataclass
from typing import TypeAlias

from birdrat_proplogic.formula import Atom, Formula, Imp, Not


@dataclass(frozen=True)
class SAtom:
    name: str


@dataclass(frozen=True)
class SNot:
    body: SurfaceFormula


@dataclass(frozen=True)
class SImp:
    left: SurfaceFormula
    right: SurfaceFormula


@dataclass(frozen=True)
class SAnd:
    left: SurfaceFormula
    right: SurfaceFormula


@dataclass(frozen=True)
class SOr:
    left: SurfaceFormula
    right: SurfaceFormula


@dataclass(frozen=True)
class SIff:
    left: SurfaceFormula
    right: SurfaceFormula


SurfaceFormula: TypeAlias = SAtom | SNot | SImp | SAnd | SOr | SIff


def desugar(formula: SurfaceFormula) -> Formula:
    match formula:
        case SAtom(name):
            return Atom(name)
        case SNot(body):
            return Not(desugar(body))
        case SImp(left, right):
            return Imp(desugar(left), desugar(right))
        case SOr(left, right):
            return Imp(Not(desugar(left)), desugar(right))
        case SAnd(left, right):
            return Not(Imp(desugar(left), Not(desugar(right))))
        case SIff(left, right):
            a = desugar(left)
            b = desugar(right)
            return Not(Imp(Imp(a, b), Not(Imp(b, a))))


def surface_pretty(formula: SurfaceFormula) -> str:
    return _surface_pretty(formula, 0)


def _surface_pretty(formula: SurfaceFormula, parent_prec: int) -> str:
    match formula:
        case SAtom(name):
            text = name
            prec = 5
        case SNot(body):
            text = f"¬{_surface_pretty(body, 4)}"
            prec = 4
        case SAnd(left, right):
            text = f"{_surface_pretty(left, 3)} ∧ {_surface_pretty(right, 3)}"
            prec = 3
        case SOr(left, right):
            text = f"{_surface_pretty(left, 2)} ∨ {_surface_pretty(right, 2)}"
            prec = 2
        case SImp(left, right):
            text = f"{_surface_pretty(left, 2)} → {_surface_pretty(right, 1)}"
            prec = 1
        case SIff(left, right):
            text = f"{_surface_pretty(left, 1)} ↔ {_surface_pretty(right, 1)}"
            prec = 0

    if prec < parent_prec:
        return f"({text})"
    return text

