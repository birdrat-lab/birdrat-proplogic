from __future__ import annotations

from dataclasses import dataclass
from typing import TypeAlias


@dataclass(frozen=True)
class Atom:
    name: str


@dataclass(frozen=True)
class Meta:
    name: str


@dataclass(frozen=True)
class Not:
    body: Formula


@dataclass(frozen=True)
class Imp:
    left: Formula
    right: Formula


Formula: TypeAlias = Atom | Meta | Not | Imp


def formula_size(formula: Formula) -> int:
    match formula:
        case Atom() | Meta():
            return 1
        case Not(body):
            return 1 + formula_size(body)
        case Imp(left, right):
            return 1 + formula_size(left) + formula_size(right)


def pretty(formula: Formula) -> str:
    return _pretty(formula, 0)


def _pretty(formula: Formula, parent_prec: int) -> str:
    match formula:
        case Atom(name) | Meta(name):
            text = name
            prec = 3
        case Not(body):
            text = f"¬{_pretty(body, 2)}"
            prec = 2
        case Imp(left, right):
            text = f"{_pretty(left, 2)} → {_pretty(right, 1)}"
            prec = 1

    if prec < parent_prec:
        return f"({text})"
    return text


def contains_meta(formula: Formula) -> bool:
    match formula:
        case Meta():
            return True
        case Atom():
            return False
        case Not(body):
            return contains_meta(body)
        case Imp(left, right):
            return contains_meta(left) or contains_meta(right)

