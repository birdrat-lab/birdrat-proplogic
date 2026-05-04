from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from birdrat_proplogic.formula import Atom, Formula, Imp, Meta, Not, pretty
from birdrat_proplogic.proof import Ax1, Ax2, Ax3, CD, Invalid, Proof, cd_depth, cd_steps, conclusion, proof_size
from birdrat_proplogic.unify import Substitution, UnifyFailure, apply_subst, unify


@dataclass(frozen=True)
class LeanCheckResult:
    checked: bool
    returncode: int | None
    command: tuple[str, ...] | None
    stdout: str
    stderr: str
    skipped_reason: str | None = None


@dataclass(frozen=True)
class LeanProofExport:
    theorem_name: str
    target: Formula
    proof: Proof
    lean_source: str
    output_path: Path


@dataclass(frozen=True)
class LeanTheoremSpec:
    theorem_name: str
    target: Formula
    proof: Proof
    surface_target: str = ""
    found_by: str | None = None
    found_phase: str | None = None


@dataclass(frozen=True)
class _LeanStep:
    name: str
    formula: Formula
    expr: str


@dataclass(frozen=True)
class _LeanNameEnv:
    names: dict[tuple[str, str], str]
    target_atoms: tuple[Atom, ...]
    local_names: tuple[str, ...]
    local_default: str
    renamed: tuple[tuple[str, str], ...]


LEAN_RESERVED = {
    "axiom",
    "by",
    "classical",
    "def",
    "end",
    "exact",
    "fun",
    "have",
    "import",
    "intro",
    "let",
    "namespace",
    "theorem",
}


def formula_to_lean(formula: Formula, env: _LeanNameEnv) -> str:
    match formula:
        case Atom(name):
            return env.names[("Atom", name)]
        case Meta(name):
            return env.names[("Meta", name)]
        case Not(body):
            return f"(¬ {formula_to_lean(body, env)})"
        case Imp(left, right):
            return f"({formula_to_lean(left, env)} → {formula_to_lean(right, env)})"


def collect_target_atoms(formula: Formula) -> tuple[Atom, ...]:
    seen: set[str] = set()
    atoms: list[Atom] = []

    def visit(item: Formula) -> None:
        match item:
            case Atom(name):
                if name not in seen:
                    seen.add(name)
                    atoms.append(item)
            case Meta():
                return
            case Not(body):
                visit(body)
            case Imp(left, right):
                visit(left)
                visit(right)

    visit(formula)
    return tuple(atoms)


def collect_proof_atoms_and_metas(proof: Proof) -> tuple[Formula, ...]:
    seen: set[tuple[str, str]] = set()
    items: list[Formula] = []

    def add_formula(formula: Formula) -> None:
        match formula:
            case Atom(name):
                key = ("Atom", name)
                if key not in seen:
                    seen.add(key)
                    items.append(formula)
            case Meta(name):
                key = ("Meta", name)
                if key not in seen:
                    seen.add(key)
                    items.append(formula)
            case Not(body):
                add_formula(body)
            case Imp(left, right):
                add_formula(left)
                add_formula(right)

    for formula in _proof_formulas(proof):
        add_formula(formula)
    return tuple(items)


def sanitize_lean_name(name: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in name.replace("?", "M_"))
    if not cleaned:
        cleaned = "v"
    if cleaned[0].isdigit():
        cleaned = f"v_{cleaned}"
    if cleaned in LEAN_RESERVED:
        cleaned = f"{cleaned}_"
    return cleaned


def proof_to_lean_steps(proof: Proof, target: Formula, theorem_name: str = "output", output_path: Path | str = "OUTPUT.lean") -> LeanProofExport:
    return export_lean_proof(proof, target, theorem_name=theorem_name, output_path=Path(output_path))


def export_lean_proof(
    proof: Proof,
    target: Formula,
    *,
    theorem_name: str = "output",
    output_path: Path | str = "OUTPUT.lean",
    surface_target: str = "",
    found_by: str | None = None,
    found_phase: str | None = None,
) -> LeanProofExport:
    spec = LeanTheoremSpec(theorem_name, target, proof, surface_target, found_by, found_phase)
    source = _file_source((spec,), suite_name=None)
    return LeanProofExport(theorem_name=theorem_name, target=target, proof=proof, lean_source=source, output_path=Path(output_path))


def export_lean_suite(
    specs: Iterable[LeanTheoremSpec],
    *,
    output_path: Path | str = "OUTPUT.lean",
    suite_name: str = "small-targets",
) -> LeanProofExport:
    specs_tuple = tuple(specs)
    if not specs_tuple:
        raise ValueError("cannot export empty Lean theorem suite")
    source = _file_source(specs_tuple, suite_name=suite_name)
    first = specs_tuple[0]
    return LeanProofExport(first.theorem_name, first.target, first.proof, source, Path(output_path))


def write_lean_file(export: LeanProofExport, path: Path | None = None) -> None:
    output_path = path or export.output_path
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(export.lean_source, encoding="utf-8")


def check_lean_file(
    path: Path,
    *,
    use_lake: bool | None = None,
    lean_command: str = "lean",
) -> LeanCheckResult:
    command = _lean_command(path, use_lake=use_lake, lean_command=lean_command)
    if command is None:
        return LeanCheckResult(False, None, None, "", "", skipped_reason="lean executable unavailable")
    completed = subprocess.run(command, check=False, capture_output=True, text=True)
    return LeanCheckResult(
        checked=completed.returncode == 0,
        returncode=completed.returncode,
        command=command,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


def _lean_command(path: Path, *, use_lake: bool | None, lean_command: str) -> tuple[str, ...] | None:
    if use_lake is None:
        use_lake = Path("lakefile.lean").exists() or Path("lakefile.toml").exists()
    if use_lake:
        if shutil.which("lake") is None:
            return None
        return ("lake", "env", lean_command, str(path))
    if shutil.which(lean_command) is None:
        return None
    return (lean_command, str(path))


def _file_source(specs: tuple[LeanTheoremSpec, ...], suite_name: str | None) -> str:
    blocks: list[str] = []
    checks: list[str] = []
    for spec in specs:
        block, check = _theorem_block(spec)
        blocks.append(block)
        checks.append(check)
    header_subject = f"Benchmark suite: {suite_name}" if suite_name else f"Theorem: {specs[0].theorem_name}"
    return "\n".join(
        [
            "/-",
            "Generated by birdrat-proplogic.",
            header_subject,
            "",
            "Lean checks this proof as a certificate for the internally generated P2 + CD proof.",
            "Lean was not used to search for the proof.",
            "-/",
            "",
            "namespace BirdratOutput",
            "",
            _p2_axioms_source(),
            "",
            "\n\n".join(blocks),
            "",
            "\n".join(checks),
            "",
            "end BirdratOutput",
            "",
        ]
    )


def _p2_axioms_source() -> str:
    return "\n".join(
        [
            "theorem p2_ax1 (P Q : Prop) : P → Q → P :=",
            "  fun hp _ => hp",
            "",
            "theorem p2_ax2 (P Q R : Prop) :",
            "    (P → Q → R) → (P → Q) → P → R :=",
            "  fun hpqr hpq hp => hpqr hp (hpq hp)",
            "",
            "theorem p2_ax3 (P Q : Prop) : (¬ P → ¬ Q) → Q → P := by",
            "  classical",
            "  intro h hq",
            "  by_cases hp : P",
            "  · exact hp",
            "  · exact False.elim ((h hp) hq)",
        ]
    )


def _theorem_block(spec: LeanTheoremSpec) -> tuple[str, str]:
    proof = _alpha_rename_axiom_metas(spec.proof)
    steps: list[_LeanStep] = []
    final_name = _emit_steps(proof, {}, steps)
    env = _name_env(spec.target, tuple(step.formula for step in steps))
    params = " ".join(f"({env.names[('Atom', atom.name)]} : Prop)" for atom in env.target_atoms)
    theorem_name = sanitize_lean_name(spec.theorem_name)
    theorem_head = f"theorem {theorem_name} {params} : {formula_to_lean(spec.target, env)} := by" if params else f"theorem {theorem_name} : {formula_to_lean(spec.target, env)} := by"
    lines = [
        "/-",
        f"Theorem: {theorem_name}",
        f"Surface target: {spec.surface_target or pretty(spec.target)}",
        f"Core target: {pretty(spec.target)}",
        f"Found by: {spec.found_by or 'unknown'}",
        f"Phase: {spec.found_phase or 'unknown'}",
        f"CD steps: {cd_steps(proof)}",
        f"CD depth: {cd_depth(proof)}",
        f"Proof size: {proof_size(proof)}",
        "-/",
        theorem_head,
    ]
    for local_name in env.local_names:
        lines.append(f"  let {local_name} : Prop := {env.local_default}")
    if env.renamed:
        lines.append("  -- sanitized generated proposition names")
        for original, renamed in env.renamed:
            lines.append(f"  -- {original} -> {renamed}")
    for step in steps:
        lines.append(f"  have {step.name} : {formula_to_lean(step.formula, env)} := {step.expr}")
    lines.append(f"  exact {final_name}")
    return ("\n".join(lines), f"#check {theorem_name}")


def _alpha_rename_axiom_metas(proof: Proof) -> Proof:
    counter = 0

    def rename_formula(formula: Formula, mapping: dict[str, str]) -> Formula:
        match formula:
            case Atom():
                return formula
            case Meta(name):
                renamed = mapping.setdefault(name, f"{name}_leaf{counter}")
                return Meta(renamed)
            case Not(body):
                return Not(rename_formula(body, mapping))
            case Imp(left, right):
                return Imp(rename_formula(left, mapping), rename_formula(right, mapping))

    def visit(item: Proof) -> Proof:
        nonlocal counter
        match item:
            case Ax1(p, q):
                counter += 1
                mapping: dict[str, str] = {}
                return Ax1(rename_formula(p, mapping), rename_formula(q, mapping))
            case Ax2(p, q, r):
                counter += 1
                mapping = {}
                return Ax2(rename_formula(p, mapping), rename_formula(q, mapping), rename_formula(r, mapping))
            case Ax3(p, q):
                counter += 1
                mapping = {}
                return Ax3(rename_formula(p, mapping), rename_formula(q, mapping))
            case CD(major, minor):
                return CD(visit(major), visit(minor))

    renamed = visit(proof)
    return renamed


def _emit_steps(proof: Proof, subst: Substitution, steps: list[_LeanStep]) -> str:
    match proof:
        case Ax1(p, q):
            step_name = f"h{len(steps) + 1}"
            p_sub = apply_subst(p, subst)
            q_sub = apply_subst(q, subst)
            formula = _expect_formula(apply_subst(conclusion(proof), subst))
            steps.append(_LeanStep(step_name, formula, f"p2_ax1 {_formula_expr(p_sub)} {_formula_expr(q_sub)}"))
            return step_name
        case Ax2(p, q, r):
            step_name = f"h{len(steps) + 1}"
            p_sub = apply_subst(p, subst)
            q_sub = apply_subst(q, subst)
            r_sub = apply_subst(r, subst)
            formula = _expect_formula(apply_subst(conclusion(proof), subst))
            steps.append(_LeanStep(step_name, formula, f"p2_ax2 {_formula_expr(p_sub)} {_formula_expr(q_sub)} {_formula_expr(r_sub)}"))
            return step_name
        case Ax3(p, q):
            step_name = f"h{len(steps) + 1}"
            p_sub = apply_subst(p, subst)
            q_sub = apply_subst(q, subst)
            formula = _expect_formula(apply_subst(conclusion(proof), subst))
            steps.append(_LeanStep(step_name, formula, f"p2_ax3 {_formula_expr(p_sub)} {_formula_expr(q_sub)}"))
            return step_name
        case CD(major, minor):
            major_conclusion = _expect_formula(apply_subst(conclusion(major), subst))
            minor_conclusion = _expect_formula(apply_subst(conclusion(minor), subst))
            if not isinstance(major_conclusion, Imp):
                raise ValueError("cannot export invalid CD: major is not implication")
            local_subst = unify(major_conclusion.left, minor_conclusion)
            if isinstance(local_subst, UnifyFailure):
                raise ValueError(f"cannot export invalid CD: {local_subst.reason}")
            combined = _compose_subst(subst, local_subst)
            major_name = _emit_steps(major, combined, steps)
            minor_name = _emit_steps(minor, combined, steps)
            step_name = f"h{len(steps) + 1}"
            formula = apply_subst(major_conclusion.right, local_subst)
            steps.append(_LeanStep(step_name, formula, f"{major_name} {minor_name}"))
            return step_name


def _formula_expr(formula: Formula) -> str:
    match formula:
        case Atom(name):
            return sanitize_lean_name(name)
        case Meta(name):
            return sanitize_lean_name(name)
        case Not() | Imp():
            return f"({formula_to_lean(formula, _transient_env(formula))})"


def _compose_subst(base: Substitution, update: Substitution) -> Substitution:
    combined = {name: apply_subst(value, update) for name, value in base.items()}
    combined.update(update)
    return combined


def _name_env(target: Formula, formulas: tuple[Formula, ...]) -> _LeanNameEnv:
    target_atoms = collect_target_atoms(target)
    target_atom_names = {atom.name for atom in target_atoms}
    used: set[str] = set()
    names: dict[tuple[str, str], str] = {}
    renamed: list[tuple[str, str]] = []
    for atom in target_atoms:
        sanitized = _unique_name(sanitize_lean_name(atom.name), used)
        names[("Atom", atom.name)] = sanitized
        if sanitized != atom.name:
            renamed.append((atom.name, sanitized))
    for formula in formulas:
        for item in _formula_vars(formula):
            match item:
                case Atom(name):
                    key = ("Atom", name)
                    if key in names:
                        continue
                    base = sanitize_lean_name(name)
                    if name in target_atom_names:
                        base = f"A_{base}"
                    names[key] = _unique_name(base, used)
                case Meta(name):
                    key = ("Meta", name)
                    if key not in names:
                        names[key] = _unique_name(sanitize_lean_name(name), used)
    local_names = tuple(name for key, name in names.items() if key[0] == "Meta" or key[1] not in target_atom_names)
    local_default = names[("Atom", target_atoms[0].name)] if target_atoms else "True"
    return _LeanNameEnv(names, target_atoms, local_names, local_default, tuple(renamed))


def _transient_env(formula: Formula) -> _LeanNameEnv:
    names: dict[tuple[str, str], str] = {}
    used: set[str] = set()
    for item in _formula_vars(formula):
        match item:
            case Atom(name):
                names[("Atom", name)] = _unique_name(sanitize_lean_name(name), used)
            case Meta(name):
                names[("Meta", name)] = _unique_name(sanitize_lean_name(name), used)
    return _LeanNameEnv(names, (), (), "True", ())


def _unique_name(base: str, used: set[str]) -> str:
    candidate = base
    index = 1
    while candidate in used or candidate in LEAN_RESERVED:
        index += 1
        candidate = f"{base}_{index}"
    used.add(candidate)
    return candidate


def _formula_vars(formula: Formula) -> tuple[Formula, ...]:
    seen: set[tuple[str, str]] = set()
    output: list[Formula] = []

    def visit(item: Formula) -> None:
        match item:
            case Atom(name):
                key = ("Atom", name)
                if key not in seen:
                    seen.add(key)
                    output.append(item)
            case Meta(name):
                key = ("Meta", name)
                if key not in seen:
                    seen.add(key)
                    output.append(item)
            case Not(body):
                visit(body)
            case Imp(left, right):
                visit(left)
                visit(right)

    visit(formula)
    return tuple(output)


def _proof_formulas(proof: Proof) -> tuple[Formula, ...]:
    formulas: list[Formula] = []

    def visit(item: Proof) -> None:
        item_conclusion = conclusion(item)
        if not isinstance(item_conclusion, Invalid):
            formulas.append(item_conclusion)
        match item:
            case Ax1(p, q):
                formulas.extend((p, q))
            case Ax2(p, q, r):
                formulas.extend((p, q, r))
            case Ax3(p, q):
                formulas.extend((p, q))
            case CD(major, minor):
                visit(major)
                visit(minor)

    visit(proof)
    return tuple(formulas)


def _expect_formula(value: Formula | Invalid) -> Formula:
    if isinstance(value, Invalid):
        raise ValueError(value.reason)
    return value
