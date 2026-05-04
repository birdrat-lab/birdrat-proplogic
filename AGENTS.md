# AGENTS.md — birdrat-proplogic: Expanded Benchmark Suite and Solver Provenance

## Project purpose

`birdrat-proplogic` is a prototype proof-search system for classical propositional logic.

The project searches for Hilbert-style proofs over the Łukasiewicz/Church `P₂` axiom schemata using condensed detachment (`CD`) as the internal inference rule. The long-term goal is to build a Lean-facing theorem generator whose proof search is restricted to an explicitly chosen set of valid logical moves.

Lean integration is a future milestone, but **not the current milestone**.

The current priority is:

```text
1. freeze the current five-target benchmark suite as regression coverage,
2. add a slightly expanded target-only benchmark suite,
3. make solver provenance explicit,
4. distinguish beam-driven success from evolutionary/GP-driven success,
5. preserve concise terminal output and archived detailed reports,
6. use runtime analysis to understand where the next bottlenecks are.
```

Do not add Lean integration yet.

---

## Core logical system

The internal proof language is:

```text
Proof =
    Ax1(p, q)
  | Ax2(p, q, r)
  | Ax3(p, q)
  | CD(major, minor)
```

The three axiom schemata are:

```text
Ax1: p → (q → p)

Ax2: (p → (q → r)) → ((p → q) → (p → r))

Ax3: (¬p → ¬q) → (q → p)
```

`CD(major, minor)` is condensed detachment.

If:

```text
conclusion(major) = A → B
```

and `A` unifies with `conclusion(minor)` under most-general unifier `σ`, then:

```text
conclusion(CD(major, minor)) = σ(B)
```

Otherwise the `CD` node is invalid.

`CD` nodes contain proof subtrees, not formulas.

---

## Formula language

The core formula language is:

```text
Formula =
    Atom(name)
  | Meta(name)
  | Not(A)
  | Imp(A, B)
```

Surface syntax may include:

```text
And
Or
Iff
```

but proof search should reduce surface syntax to the core language.

Current desugaring conventions:

```text
A ∨ B := ¬A → B

A ∧ B := ¬(A → ¬B)

A ↔ B := (A → B) ∧ (B → A)
```

Important consequence:

```text
p ∧ q → p
```

is not a primitive projection rule.

It desugars to:

```text
¬(p → ¬q) → p
```

This is a nontrivial theorem in the `P₂ + CD` system. Do not treat surface conjunction elimination as a primitive proof rule.

---

## Benchmark policy

Do **not** hardcode known proofs.

Do **not** build benchmarks around replaying known proof strings.

Do **not** seed the search with external proof strings.

The benchmark suite should consist of theorem targets only. The search system must attempt to find proofs of those targets using the internal proof-search machinery.

It is acceptable that benchmark targets were selected because they are externally known to be reasonable small propositional theorems. But the implementation should not use known proofs during search, scoring, initialization, benchmarking, or verification.

The benchmark question is:

```text
Given only the theorem target, can the tool find a proof?
```

not:

```text
Can the tool replay a known proof?
```

---

# Current solver architecture

The solver is now best understood as a hybrid proof-search system:

```text
target-directed P₂ + CD beam search
+ schema instantiation
+ quality-diverse/evolutionary selection layer
```

It is not currently a pure genetic-programming theorem prover.

For the current small benchmark suite, most successful work appears to happen in the beam before the evolutionary loop has many generations to operate. That is acceptable, but the reports should be explicit about proof provenance.

Use this framing in comments, documentation, and reports:

```text
The current solver is hybrid.
The small benchmark suite currently validates the beam-driven proof-search core.
The evolutionary machinery remains available as a fallback/exploration layer and may matter more on harder targets.
```

Do not remove the evolutionary layer. Do not remove quality-diverse selection. But do not overstate its role when a proof was found by the beam.

---

# Baseline benchmark suite

The current five-target suite is now a regression suite.

It should remain available as:

```bash
PYTHONPATH=src python -m birdrat_proplogic.run_benchmarks --small-targets
```

Baseline targets:

```text
1. identity:
   p ⊢ p
   core: p → p

2. syllogism / functoriality:
   p → q, r → p, r ⊢ q
   core: (p → q) → (r → p) → r → q

3. classical-negation:
   ¬p, p ⊢ q
   core: ¬p → p → q

4. contraction:
   p → p → q, p ⊢ q
   core: (p → p → q) → p → q

5. distribution/application:
   p → q, p → q → r, p ⊢ r
   core: (p → q) → (p → q → r) → p → r
```

Expected behavior:

```text
identity:                  must pass
syllogism:                 must pass
classical-negation:         must pass
contraction:               must pass
distribution/application:   must pass
```

Each benchmark should require exact proof discovery, not merely high target similarity.

Use loose upper bounds for proof metrics initially:

```text
CD steps: bounded generously
CD depth: bounded generously
proof size: bounded generously
runtime: reported, not initially enforced
```

Do not use strict proof-size equality because the search may find different valid proofs after refactors.

---

# New expanded benchmark suite

Add a second benchmark suite, separate from `--small-targets`.

Suggested flag:

```bash
PYTHONPATH=src python -m birdrat_proplogic.run_benchmarks --expanded-targets
```

or:

```bash
PYTHONPATH=src python -m birdrat_proplogic.run_benchmarks --suite expanded
```

The expanded suite should remain target-only. It should not include hardcoded proofs.

The expanded suite should be attempted only after the small suite passes.

---

## Expanded benchmark design goals

The expanded targets should test the next layer of difficulty without jumping directly into encoded conjunction as the only objective.

The suite should probe:

```text
1. double negation behavior,
2. contraposition-style behavior,
3. permutation/exchange of assumptions,
4. composition of implications,
5. simple encoded-connective projection,
6. simple encoded-connective symmetry.
```

Use target formulas that are readable in sequent display form.

---

## Expanded benchmark candidates

### Expanded 1: double-negation introduction

Display:

```text
p ⊢ ¬¬p
```

Core:

```text
p → ¬¬p
```

Purpose:

```text
Tests classical/negation machinery in a small closed theorem.
Should be easier than encoded conjunction but less trivial than identity.
```

Expected status:

```text
May pass with current strict beam.
If not, should expose whether schema instantiation handles negated targets.
```

---

### Expanded 2: contraposition-like theorem

Display:

```text
p → q, ¬q ⊢ ¬p
```

Core:

```text
(p → q) → ¬q → ¬p
```

Purpose:

```text
Tests classical contrapositive behavior without using encoded conjunction.
Useful bridge between classical-negation and encoded connective examples.
```

Expected status:

```text
May require fallback phases or stronger schema instantiation.
```

---

### Expanded 3: permutation / exchange

Display:

```text
p → q → r, q, p ⊢ r
```

Core:

```text
(p → q → r) → q → p → r
```

Purpose:

```text
Tests reordering of assumptions. This is important because Hilbert implication spines encode context order explicitly, and exchange is not a primitive inference rule.
```

Expected status:

```text
May be harder than distribution/application depending on current suffix retention.
```

---

### Expanded 4: composition

Display:

```text
q → r, p → q, p ⊢ r
```

Core:

```text
(q → r) → (p → q) → p → r
```

Purpose:

```text
Tests ordinary composition of implications. Similar to syllogism but with a different target spine.
```

Expected status:

```text
Should be a plausible next success after the five-target suite.
```

---

### Expanded 5: encoded conjunction left projection

Display:

```text
p ∧ q ⊢ p
```

Core:

```text
¬(p → ¬q) → p
```

Purpose:

```text
First encoded conjunction target. Important because surface syntax looks simple, but the core theorem is nontrivial under the project’s encoding.
```

Expected status:

```text
May fail initially. Failure should be reported cleanly.
Do not add primitive conjunction elimination.
```

---

### Expanded 6: encoded conjunction right projection

Display:

```text
p ∧ q ⊢ q
```

Core:

```text
¬(p → ¬q) → q
```

Purpose:

```text
Second encoded conjunction projection. It should be compared against left projection to see whether one direction is substantially easier for the current search.
```

Expected status:

```text
May fail initially. Failure should be reported cleanly.
Do not add primitive conjunction elimination.
```

---

### Expanded 7: encoded conjunction commutativity

Display:

```text
p ∧ q ⊢ q ∧ p
```

Core:

```text
¬(p → ¬q) → ¬(q → ¬p)
```

Purpose:

```text
First larger encoded-connective theorem. This was one of the original motivating examples and should remain a milestone target, not a baseline requirement.
```

Expected status:

```text
Likely harder. Do not require it to pass initially.
Use it to inspect failure modes after projection benchmarks are attempted.
```

---

## Expanded suite expected behavior

Do not initially require all expanded targets to pass.

Recommended expectation categories:

```text
must-pass:
  small-target suite only

expected-plausible:
  double-negation introduction
  composition

expected-diagnostic:
  contraposition
  permutation
  encoded conjunction left projection
  encoded conjunction right projection
  encoded conjunction commutativity
```

The expanded suite should report:

```text
found exact proof: yes/no
solved phase
found_by provenance
CD steps
CD depth
proof size
runtime
best closed candidate
best schematic candidate
best similarity
report path
```

A failing expanded benchmark should not fail the entire command unless an explicit `--strict` flag is used.

Add:

```text
--strict
```

Meaning:

```text
exit nonzero if any selected benchmark target fails
```

Default:

```text
do not exit nonzero for expanded-suite failures
```

For the small suite, `--strict` may be enabled by default in CI/regression contexts.

---

# Sequent-style display

The demos and reports should prefer sequent-style display over raw parenthesized implication chains.

For any formula:

```text
A1 → A2 → ... → An → H
```

display:

```text
assumptions:
  1. A1
  2. A2
  ...
  n. An

conclusion:
  H
```

Also show the core formula when useful:

```text
core: A1 → A2 → ... → An → H
```

Examples:

```text
p → q, p → q → r, p ⊢ r
```

should be printed as:

```text
proving:
  assumptions:
    1. p → q
    2. p → q → r
    3. p
  conclusion:
    r
core: (p → q) → (p → q → r) → p → r
```

For encoded conjunction:

```text
p ∧ q ⊢ p
core: ¬(p → ¬q) → p
```

This makes it clear that the user-facing theorem is surface-level, while the proof search target is the encoded core formula.

This is display/parsing sugar only. It does not add natural-deduction rules.

---

# Solver provenance

Reports should distinguish where an exact proof first appeared.

Add fields such as:

```python
found_by: Literal[
    "beam",
    "schema-instantiation",
    "initial-population",
    "mutation",
    "crossover",
    "selection",
    "unknown",
]

found_phase: str
found_generation: int | None
found_beam_layer: int | None
surfaced_generation: int | None
```

Use whatever subset is currently feasible, but at minimum report:

```text
solved in phase
found generation
found by beam vs evolution if known
```

Purpose:

```text
If a theorem is solved at generation 1 because the beam already produced the proof, the report should not imply that mutation/crossover evolved the proof in one generation.
```

Benchmark line example:

```text
distribution/application
  strict-preselected: FOUND by beam, surfaced gen=1, cd=6 depth=4 size=13 time=72.4s
```

If provenance is uncertain:

```text
found_by: unknown
```

Do not fake provenance.

---

# Beam-only and no-beam diagnostic controls

Add diagnostic flags:

```text
--beam-only
--no-beam
```

These are diagnostic controls, not the main interface.

## `--beam-only`

Behavior:

```text
run beam search and schema instantiation
skip mutation/crossover/evolution
report whether exact proof was found
```

Purpose:

```text
Determine whether a benchmark is solved entirely by the beam/search substrate.
```

If all five small targets pass under `--beam-only`, then the current small suite is validating the beam prover rather than the evolutionary layer.

## `--no-beam`

Behavior:

```text
run population initialization, mutation, crossover, quality-diverse selection
do not include beam-generated proof pool
```

Purpose:

```text
Measure whether the GP/evolutionary layer can solve anything independently.
```

Expected:

```text
The no-beam mode may fail on most nontrivial targets.
That is useful diagnostic information, not a bug.
```

Do not make these flags the default. The default solver should remain the full hybrid pipeline.

---

# Reporting requirements

Terminal output should remain concise.

For benchmarks, use compact per-target progress:

```text
[1/5] identity
  strict-preselected: FOUND cd=2 depth=2 size=5 time=0.7s
```

With progress enabled:

```text
proving:
  assumptions:
    1. p → q
    2. p → q → r
    3. p
  conclusion:
    r
core: (p → q) → (p → q → r) → p → r
gen 0: strict-preselected best=-215.9 sim=0.31 exact=0 valid=0.97 closed=0.65 beam=16018 time=72.1s
gen 1: strict-preselected FOUND best=10999857.5 sim=1.00 exact=1 beam=16018 time=72.4s
```

At the end, print a compact table:

```text
summary
name                      found phase               by     cd depth size runtime
identity                  yes   strict-preselected  beam   2  2     5    0.7s
distribution/application  yes   strict-preselected  beam   6  4     13   76.2s
```

Full details belong in archived reports.

---

# Full report archival

By default, both `run` and `run_benchmarks` should save a full report to disk.

Suggested directories:

```text
reports/runs/
reports/benchmarks/
```

Suggested filenames:

```text
reports/runs/run-YYYYMMDD-HHMMSS.json
reports/benchmarks/small-targets-YYYYMMDD-HHMMSS.json
reports/benchmarks/expanded-targets-YYYYMMDD-HHMMSS.json
```

Full reports should include:

```text
target surface formula
core target formula
sequent display
configuration
random seed
phases attempted
phase reports
provenance fields
progress snapshots
final result
best proof if found
best closed candidate
best schematic candidate
best novelty candidate
beam diagnostics
suffix diagnostics
schema-instantiation diagnostics
axiom-family diagnostics
runtime profile
```

Do not feed archived proofs back into future searches unless explicitly requested.

Reports are for inspection and regression analysis, not proof seeding.

---

# Runtime analysis

Keep runtime profiling instrumentation.

At minimum, continue reporting:

```text
total
beam
schema instantiation
fitness
selection
```

Prefer to include more detail in archived reports:

```text
unification
conclusion computation
formula similarity
candidate deduplication
beam pair generation
beam candidate ranking
suffix retention
schema instantiation
mutation
crossover
report writing
```

Before optimizing, inspect profiling data.

Likely future optimization targets:

```text
conclusion(proof)
formula_size(formula)
implication_spine(formula)
implication_spine_suffixes(formula)
formula_similarity(a, b)
unify(a, b)
proof metrics:
  cd_steps
  cd_depth
  proof_size
```

Do not blindly optimize before profiling.

---

# Regression expectations

## Small suite

The small suite should be treated as regression coverage.

Expected:

```text
identity: found
syllogism: found
classical-negation: found
contraction: found
distribution/application: found
```

## Expanded suite

The expanded suite is diagnostic at first.

Expected:

```text
double-negation introduction:
  plausible

composition:
  plausible

contraposition:
  diagnostic

permutation:
  diagnostic

encoded conjunction left projection:
  diagnostic

encoded conjunction right projection:
  diagnostic

encoded conjunction commutativity:
  diagnostic/milestone
```

Do not fail the whole run if expanded targets fail unless `--strict` is specified.

---

# Implementation order

Recommended order:

```text
1. Preserve current small-target benchmark behavior.
2. Add provenance fields to results and reports.
3. Add --beam-only and --no-beam diagnostic flags.
4. Add expanded benchmark suite definitions.
5. Add compact summary output for expanded benchmarks.
6. Add archived report support for expanded benchmarks.
7. Run small suite in default, beam-only, and no-beam modes.
8. Run expanded suite in default mode.
9. Use runtime profile and failure reports to choose the next structural improvement.
```

---

# Non-goals for this milestone

Do not implement:

```text
Lean integration
Mathlib integration
native Lean AST parsing
natural-deduction tactics
surface-level conjunction elimination as a primitive rule
hardcoded known proofs
proof-string replay as benchmark logic
large external proof database ingestion
one-off bad-shape penalties
axiom-family selection bonuses
target-specific axiom preferences
proof minimization
```

Lean integration should come after:

```text
1. small suite is stable,
2. expanded suite has been attempted,
3. solver provenance is reported,
4. reporting/profiling is usable.
```

---

## Summary

Current status:

```text
The tool passes the five-target P₂ + CD benchmark suite.
The current solver is hybrid and beam-driven on these examples.
```

Next milestone:

```text
expanded target-only benchmark suite
+ solver provenance
+ beam-only/no-beam diagnostics
+ continued concise reporting and full archived reports
```

Lean integration comes later, not yet.
