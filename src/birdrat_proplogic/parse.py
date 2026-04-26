from __future__ import annotations

from dataclasses import dataclass

from birdrat_proplogic.surface import SAnd, SAtom, SIff, SImp, SNot, SOr, SurfaceFormula


@dataclass(frozen=True)
class ParseError:
    message: str


ParseResult = SurfaceFormula | ParseError


def parse_surface(text: str) -> ParseResult:
    tokens = _tokenize(text)
    if isinstance(tokens, ParseError):
        return tokens
    parser = _Parser(tokens)
    formula = parser.parse_iff()
    if isinstance(formula, ParseError):
        return formula
    if parser.current() is not None:
        return ParseError(f"unexpected token: {parser.current()}")
    return formula


def _tokenize(text: str) -> tuple[str, ...] | ParseError:
    tokens: list[str] = []
    index = 0
    operators = (
        "\\leftrightarrow",
        "\\rightarrow",
        "\\land",
        "\\wedge",
        "\\iff",
        "\\to",
        "\\lor",
        "\\vee",
        "\\not",
        "<->",
        "->",
        "↔",
        "→",
        "∧",
        "∨",
        "¬",
        "~",
        "!",
        "&",
        "|",
        "(",
        ")",
    )
    while index < len(text):
        char = text[index]
        if char.isspace():
            index += 1
            continue

        matched = next((operator for operator in operators if text.startswith(operator, index)), None)
        if matched is not None:
            tokens.append(_normalize_token(matched))
            index += len(matched)
            continue

        if char.isalpha() or char == "_":
            start = index
            index += 1
            while index < len(text) and (text[index].isalnum() or text[index] == "_"):
                index += 1
            tokens.append(text[start:index])
            continue

        return ParseError(f"unexpected character: {char}")
    return tuple(tokens)


def _normalize_token(token: str) -> str:
    if token in ("\\leftrightarrow", "\\iff", "<->", "↔"):
        return "IFF"
    if token in ("\\rightarrow", "\\to", "->", "→"):
        return "IMP"
    if token in ("\\land", "\\wedge", "∧", "&"):
        return "AND"
    if token in ("\\lor", "\\vee", "∨", "|"):
        return "OR"
    if token in ("\\not", "¬", "~", "!"):
        return "NOT"
    return token


class _Parser:
    def __init__(self, tokens: tuple[str, ...]) -> None:
        self.tokens = tokens
        self.index = 0

    def current(self) -> str | None:
        if self.index >= len(self.tokens):
            return None
        return self.tokens[self.index]

    def advance(self) -> str | None:
        token = self.current()
        if token is not None:
            self.index += 1
        return token

    def parse_iff(self) -> ParseResult:
        left = self.parse_imp()
        if isinstance(left, ParseError):
            return left
        if self.current() == "IFF":
            self.advance()
            right = self.parse_iff()
            if isinstance(right, ParseError):
                return right
            return SIff(left, right)
        return left

    def parse_imp(self) -> ParseResult:
        left = self.parse_or()
        if isinstance(left, ParseError):
            return left
        if self.current() == "IMP":
            self.advance()
            right = self.parse_imp()
            if isinstance(right, ParseError):
                return right
            return SImp(left, right)
        return left

    def parse_or(self) -> ParseResult:
        left = self.parse_and()
        if isinstance(left, ParseError):
            return left
        while self.current() == "OR":
            self.advance()
            right = self.parse_and()
            if isinstance(right, ParseError):
                return right
            left = SOr(left, right)
        return left

    def parse_and(self) -> ParseResult:
        left = self.parse_not()
        if isinstance(left, ParseError):
            return left
        while self.current() == "AND":
            self.advance()
            right = self.parse_not()
            if isinstance(right, ParseError):
                return right
            left = SAnd(left, right)
        return left

    def parse_not(self) -> ParseResult:
        if self.current() == "NOT":
            self.advance()
            body = self.parse_not()
            if isinstance(body, ParseError):
                return body
            return SNot(body)
        return self.parse_atom()

    def parse_atom(self) -> ParseResult:
        token = self.current()
        if token is None:
            return ParseError("expected formula")
        if token == "(":
            self.advance()
            formula = self.parse_iff()
            if isinstance(formula, ParseError):
                return formula
            if self.current() != ")":
                return ParseError("expected closing parenthesis")
            self.advance()
            return formula
        if token in ("IFF", "IMP", "OR", "AND", "NOT", ")"):
            return ParseError(f"expected atom, got: {token}")
        self.advance()
        return SAtom(token)
