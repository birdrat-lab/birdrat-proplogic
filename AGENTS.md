# AGENTS.md — birdrat-proplogic: Default Cascading Beam Search

## Project purpose

`birdrat-proplogic` is a prototype proof-search system for classical propositional logic.

The project searches for Hilbert-style proofs over the Łukasiewicz/Church `P₂` axiom schemata using condensed detachment (`CD`) as the internal inference rule. The long-term goal is to build a Lean-facing theorem generator whose proof search is restricted to an explicitly chosen set of valid logical moves.

This is not a general Lean tactic prover. Do not add general Lean automation. Do not use `simp`, `tauto`, `aesop`, `omega`, Mathlib automation, or native Lean proof search to bypass the restricted proof system.

The current priority is not Lean integration. The current priority is to make the internal `P₂ + CD` proof-search substrate competent on small target-only benchmarks.

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

It is acceptable that benchmark targets were selected because they are externally known to have short `P₂ + CD` proofs. But the implementation should not use known proofs during search, scoring, initialization, benchmarking, or verification.

The benchmark question is:

```text
Given only the theorem target, can the tool find a proof?
```

not:

```text
Can the tool replay a known proof?
```

---

## Current benchmark status

The small target benchmark suite is the current calibration set.

Targets:

```text
1. identity:
   p → p

2. syllogism / functoriality:
   (p → q) → (r → p) → r → q

3. classical-negation:
   ¬p → p → q

4. contraction:
   (p → p → q) → p → q

5. distribution/application:
   (p → q) → (p → q → r) → p → r
```

Current interpretation:

```text
- identity is solvable
- contraction is solvable
- syllogism was previously solvable but regressed after strict pair preselection
- classical-negation remains unsolved
- distribution/application remains unsolved
```

The regression on syllogism is the immediate motivation for the cascading search policy.

Do not return to encoded conjunction benchmarks such as:

```text
p ∧ q → p
p ∧ q → q
p ∧ q → q ∧ p
```

until the small target suite is reliable.

---

## Problem: strict preselected beam is brittle

The beam now uses target-directed pair preselection. This is necessary because trying all ordered CD pairs is too slow.

The naive pattern:

```python
for major in pair_pool:
    for minor in pair_pool:
        try_make_cd(major, minor)
```

is effectively quadratic in the size of the pair pool.

However, a purely strict preselected-pair beam can over-prune useful intermediate proofs. This caused a regression on the syllogism benchmark. The tool found the weaker theorem:

```text
(p → q) → p → q
```

instead of the target:

```text
(p → q) → (r → p) → r → q
```

This suggests that strict target-directed preselection is too exploitative. It preserves target-shaped candidates but may discard intermediate formulas needed to build contextualized implications.

The fix should not be to expose user-facing beam modes. Instead, implement one default cascading search policy.

---

## Design decision: default cascading beam search

Do not expose beam modes as a main user interface.

The tool should run a single default search procedure that automatically escalates:

```text
Phase 1: strict-preselected beam
Phase 2: hybrid beam
Phase 3: expanded-budget hybrid beam
Failure: report not found
```

The user should still call the tool simply:

```bash
PYTHONPATH=src python -m birdrat_proplogic.run 'target'
```

or:

```bash
PYTHONPATH=src python -m birdrat_proplogic.run_benchmarks --small-targets
```

They should not need to choose between `strict`, `hybrid`, or `expanded` modes.

The benchmark output may report which phase solved the theorem, but the phases should be implementation details of the default search policy.

---

## SearchPhase dataclass

Add a dataclass representing one search attempt in the cascade.

Suggested type:

```python
@dataclass(frozen=True)
class SearchPhase:
    name: str
    beam_width: int
    beam_max_depth: int
    beam_pair_budget: int
    prioritized_fraction: float
    suffix_fraction: float
    exploratory_fraction: float
    population_size: int
    generations: int
```

Field meanings:

```text
name:
  human-readable phase name used in reports
  examples: strict-preselected, hybrid, expanded-hybrid

beam_width:
  number of beam candidates retained per layer/category

beam_max_depth:
  number of deterministic CD expansion layers

beam_pair_budget:
  maximum number of CD pairs attempted per beam layer

prioritized_fraction:
  fraction of pair budget allocated to target-directed prioritized pairs

suffix_fraction:
  fraction of pair budget allocated to implication-suffix/subgoal-diverse pairs

exploratory_fraction:
  fraction of pair budget allocated to exploratory compatible pairs

population_size:
  evolutionary population size for this phase

generations:
  number of evolutionary generations for this phase
```

Fractions should be validated:

```text
prioritized_fraction >= 0
suffix_fraction >= 0
exploratory_fraction >= 0
sum is approximately 1.0
```

If the sum differs slightly due to floating point rounding, normalize or assign the remainder to the prioritized bucket.

---

## Default phase schedule

Add:

```python
make_default_search_phases(base_config) -> tuple[SearchPhase, ...]
```

This should produce three phases.

### Phase 1: strict-preselected

Purpose:

```text
Fast path. Try the current strict target-directed pair search first.
```

Suggested values:

```text
name = "strict-preselected"

beam_width = base_config.beam_width
beam_max_depth = base_config.beam_max_depth
beam_pair_budget = base_config.beam_pair_budget

prioritized_fraction = 1.00
suffix_fraction = 0.00
exploratory_fraction = 0.00

population_size = base_config.population_size
generations = base_config.max_generations
```

This keeps easy successes fast. Identity and contraction should often be solved here.

### Phase 2: hybrid

Purpose:

```text
Recover from over-pruning by reserving some budget for suffix/subgoal-diverse and exploratory pairs.
```

Suggested values:

```text
name = "hybrid"

beam_width = base_config.beam_width
beam_max_depth = base_config.beam_max_depth
beam_pair_budget = base_config.beam_pair_budget

prioritized_fraction = 0.70
suffix_fraction = 0.20
exploratory_fraction = 0.10

population_size = base_config.population_size
generations = base_config.max_generations
```

This phase should help targets like syllogism, where strict preselection may discard contextual intermediate formulas.

### Phase 3: expanded-hybrid

Purpose:

```text
Last bounded attempt before reporting failure.
```

Suggested values:

```text
name = "expanded-hybrid"

beam_width = ceil(1.5 * base_config.beam_width)
beam_max_depth = base_config.beam_max_depth + 1
beam_pair_budget = 2 * base_config.beam_pair_budget

prioritized_fraction = 0.60
suffix_fraction = 0.25
exploratory_fraction = 0.15

population_size = base_config.population_size
generations = base_config.max_generations
```

Avoid unbounded escalation. If this phase fails, report failure cleanly.

Do not aggressively increase every parameter. Prefer this order:

```text
increase beam_pair_budget first
increase beam_width moderately
increase beam_max_depth by at most 1
```

---

## Beam pair budget allocation

Modify beam pair generation so it accepts the three phase fractions:

```text
prioritized_fraction
suffix_fraction
exploratory_fraction
```

For each beam layer:

```python
prioritized_budget = floor(beam_pair_budget * prioritized_fraction)
suffix_budget = floor(beam_pair_budget * suffix_fraction)
exploratory_budget = beam_pair_budget - prioritized_budget - suffix_budget
```

Then generate pair candidates from three channels:

```text
1. prioritized target-directed pairs
2. suffix/subgoal-diverse pairs
3. exploratory compatible pairs
```

Deduplicate pairs before attempting CD.

A pair can be identified by object identity or stable proof IDs, depending on the current architecture. Avoid trying the same ordered pair twice in the same layer.

---

## Pair channel 1: prioritized target-directed pairs

This is the current strict strategy.

A CD step proves `B` when:

```text
major proves A → B
minor proves A
```

Good major candidates are implications whose consequents are useful relative to the target or generated regions.

Prioritized-pair ranking should use:

```text
- major consequent equals target
- major consequent unifies with target
- major consequent equals a generated region
- major consequent unifies with a generated region
- major consequent has high directed similarity to target/regions
- candidate has low assumption debt
- candidate is not pure vacuous weakening
- proof and formula sizes are controlled
```

Do not use axiom-family bonuses.

No rule should say:

```text
prefer Ax1
prefer Ax2
prefer Ax3
if target contains negation, boost Ax3
```

Axiom identity can be logged, but not used as a selection bonus.

---

## Pair channel 2: suffix/subgoal-diverse pairs

Strict target matching can miss useful intermediate formulas. Add a channel that explicitly preserves implication-suffix progress.

For a target formula with right-associated implication spine:

```text
A1 → A2 → ... → An → H
```

the useful suffixes are:

```text
H
An → H
A(n-1) → An → H
...
A1 → A2 → ... → An → H
```

Example target:

```text
(p → q) → (r → p) → r → q
```

Suffixes:

```text
q
r → q
(r → p) → r → q
(p → q) → (r → p) → r → q
```

Example target:

```text
(p → q) → (p → q → r) → p → r
```

Suffixes:

```text
r
p → r
(p → q → r) → p → r
(p → q) → (p → q → r) → p → r
```

Add or maintain:

```python
implication_spine(formula) -> tuple[tuple[Formula, ...], Formula]
implication_spine_suffixes(formula) -> tuple[Formula, ...]
```

Suffix/subgoal-diverse pairs should include majors whose consequent matches, unifies with, or is close to one of these suffixes.

This is still a neutral formula-driven heuristic. It does not encode specific proof ideas.

The suffix channel should prefer diversity across suffixes. Do not allow all suffix-budget pairs to target only the final head `H`.

Suggested allocation inside the suffix channel:

```text
for each suffix:
    collect/rank candidate pairs whose major consequent is close to that suffix
    keep roughly suffix_budget / number_of_suffixes pairs
```

---

## Pair channel 3: exploratory compatible pairs

The exploratory channel exists to prevent catastrophic pruning.

It should not try arbitrary invalid pairs. It should still require basic compatibility:

```text
major conclusion is implication-shaped
major antecedent is shape-compatible with minor conclusion
actual unification succeeds before the pair is accepted
```

But it should be less target-directed.

Acceptable exploratory sources:

```text
- random compatible pairs from the current pair pool
- novelty-ranked compatible pairs
- pairs involving candidates from underrepresented behavior descriptors
- pairs involving closed candidates not selected by the target-directed channel
- pairs involving schematic candidates not selected by the target-directed channel
```

The exploratory channel should be small, for example 10–15% of the budget. Its purpose is insurance against over-pruning, not random search dominance.

---

## Minor candidate compatibility

Given a major antecedent `A`, do not try every possible minor.

A minor candidate is useful only if its conclusion can unify with `A`.

Use a coarse shape index for minor conclusions.

Suggested shape categories:

```text
Meta
Atom(name)
Not
Imp
Other/Invalid
```

Compatibility heuristic:

```text
A is Meta:
  can try many minor shapes

A is Atom(name):
  try Atom(name) and schematic/meta-compatible candidates

A is Not(...):
  try Not(...) and schematic/meta-compatible candidates

A is Imp(...):
  try Imp(...) and schematic/meta-compatible candidates
```

This index is only a preselection heuristic. The actual `unify` call remains the final authority.

Add or maintain:

```python
compatible_minor_candidates(antecedent, proof_pool, index) -> Iterable[Proof]
```

Then filter/rank by actual unification.

---

## Pair priority

Maintain a pair-priority function.

Suggested type:

```python
pair_priority(major, minor, target, regions) -> float
```

It should:

```text
1. require major conclusion to be implication-shaped
2. require major antecedent to unify with minor conclusion
3. reward high major priority
4. penalize large minor proof
5. penalize large substitution terms
6. optionally reward closed minors when target search is closed
```

Sketch:

```python
def pair_priority(major, minor, target, regions):
    parts = implication_major_parts(major)
    if parts is None:
        return float("-inf")

    antecedent, consequent = parts
    minor_conclusion = conclusion(minor)

    sigma = unify(antecedent, minor_conclusion)
    if sigma fails:
        return float("-inf")

    return (
        major_priority(major, target, regions)
        - minor_size_penalty * proof_size(minor)
        - substitution_size_penalty * substitution_size(sigma)
    )
```

Do not include axiom-family bonuses in `pair_priority`.

---

## Search with fallback

Add:

```python
search_with_fallback(target, config, rng) -> SearchResult
```

or equivalent.

Behavior:

```text
1. Build default phases from base config.
2. Run strict-preselected phase.
3. If an exact target proof is found, stop and return success.
4. Otherwise run hybrid phase.
5. If an exact target proof is found, stop and return success.
6. Otherwise run expanded-hybrid phase.
7. If an exact target proof is found, stop and return success.
8. Otherwise report failure with best candidates and diagnostics from all phases.
```

Do not merge populations across phases initially. Each phase can run from scratch using the same target and a deterministic phase-specific RNG seed.

Reason:

```text
Running from scratch avoids carrying a collapsed population from a failed strict phase into the fallback phase.
```

Use deterministic phase seeds so runs are reproducible:

```python
phase_rng = random.Random(base_seed + phase_index * LARGE_CONSTANT)
```

or another stable derivation.

---

## SearchResult / PhaseReport

Add or maintain structured result objects.

Suggested:

```python
@dataclass
class PhaseReport:
    phase_name: str
    found_exact: bool
    best_exact_proof: Proof | None
    best_closed_candidate: Proof | None
    best_schematic_candidate: Proof | None
    best_novelty_candidate: Proof | None
    best_score: float
    target_similarity: float
    runtime_seconds: float
    beam_pair_attempts: int
    beam_valid_products: int
    beam_layer_counts: tuple[BeamLayerStats, ...]
    population_size: int
    generations: int
```

Suggested:

```python
@dataclass
class SearchResult:
    found: bool
    proof: Proof | None
    solved_in_phase: str | None
    phase_reports: tuple[PhaseReport, ...]
    best_closed_candidate: Proof | None
    best_schematic_candidate: Proof | None
    best_novelty_candidate: Proof | None
    total_runtime_seconds: float
```

When success occurs in an early phase, later phases should not run.

---

## Benchmark reporting

Update:

```bash
PYTHONPATH=src python -m birdrat_proplogic.run_benchmarks --small-targets
```

to report phase information.

For each benchmark:

```text
name
target
core target
found exact proof
solved in phase
total runtime
best final proof stats
phase reports:
  phase name
  found exact proof
  best closed candidate
  best schematic candidate
  best novelty candidate
  runtime
  beam pair attempts
  beam valid products
  beam layer counts
```

Example success output:

```text
name: syllogism
target: (p → q) → (r → p) → r → q
found exact proof: True
solved in phase: hybrid

phase results:
  strict-preselected:
    found: False
    best closed: (p → q) → p → q
    runtime: 36.8s

  hybrid:
    found: True
    best closed: (p → q) → (r → p) → r → q
    runtime: 12.4s
```

Example failure output:

```text
name: distribution-application
found exact proof: False
solved in phase: none

phase results:
  strict-preselected: not found
  hybrid: not found
  expanded-hybrid: not found

best closed candidate across phases: ...
best schematic candidate across phases: ...
```

---

## Regression expectations

The benchmark suite should guard against regressions.

Expected near-term results:

```text
identity:
  should be found by some phase, preferably strict-preselected

syllogism:
  should be found by some phase
  this is the immediate regression target

contraction:
  should be found by some phase

classical-negation:
  may still fail
  failure should be cleanly reported

distribution/application:
  may still fail
  failure should be cleanly reported
```

Do not mark classical-negation and distribution/application as hard failures yet. They are active search targets, not baseline requirements.

---

## Closed versus schematic candidates

The input theorem is closed. Therefore the final accepted proof must have a closed conclusion exactly equal to the core target.

Maintain:

```python
metas(formula) -> set[Meta]
is_closed_formula(formula) -> bool
```

Definitions:

```text
closed formula:
  contains no Meta variables

schematic formula:
  contains one or more Meta variables
```

Rules:

```text
- Only closed candidates may compete as target-proof elites.
- Only closed candidates may compete as generated-region elites.
- Schematic candidates should be stored and ranked separately as lemma schemas.
- A schematic candidate may be promoted only if it can be instantiated into a closed target or closed generated-region candidate.
```

A valid schematic theorem is not a valid proof of the input theorem.

---

## Schema instantiation

Keep schema instantiation as a priority.

Useful operation:

```text
instantiate_meta_from_pool
```

Behavior:

```text
1. choose a Meta variable in a proof or formula
2. choose a replacement formula from the target/region formula pool
3. replace that Meta consistently throughout the proof
4. recompute/check the conclusion
5. if the result is closed or closer to closed, evaluate it as a closed/partially closed candidate
```

Also support direct schema-target matching:

```text
if unify(schema_conclusion, target_or_region) succeeds:
    instantiate the proof using the unifier
    evaluate the instantiated proof
```

If unification fails, keep the candidate in the schema archive rather than allowing it to dominate closed-target search.

Schema instantiation should not use known proofs. It may use formulas from:

```text
target
generated regions
target subformulas
region subformulas
simple formula-pool expansions
```

---

## Quality-diversity selection

The search should not rely on one scalar fitness score as the only survival mechanism.

Use separate elite buckets:

```text
closed target elites:
  closed candidates closest to the full target

closed region elites:
  closed candidates closest to generated regions

schematic lemma elites:
  valid schematic candidates that are compact and potentially reusable

novelty elites:
  candidates whose behavior descriptors are far from known candidates

random immigrants:
  fresh target-seeded candidates injected each generation
```

For population size 100, a reasonable first allocation is:

```text
20 closed target elites
20 closed region elites
20 schematic lemma elites
20 novelty elites
20 random immigrants / high-mutation candidates
```

The exact allocation can be configurable.

The important rule is:

```text
Do not let a single scalar score define the whole next generation.
```

---

## Neutrality requirement for heuristics

Do not seed the beam heuristic with proof ideas tied to a specific axiom.

Do not implement rules such as:

```text
if the target contains negation, boost Ax3
if the target looks classical, prefer Ax3-containing candidates
if the target is implicational, prefer Ax1/Ax2
```

The beam heuristic should be target-formula driven, not axiom-family driven.

Acceptable heuristic signals:

```text
- consequent of a CD major matches or unifies with the target
- consequent of a CD major matches or unifies with a target implication suffix
- candidate conclusion has a useful implication spine
- candidate covers target antecedents
- candidate has low assumption debt
- candidate is closed when the target is closed
- schematic candidate can be instantiated toward the target
- proof is smaller or has fewer CD steps
- formula size is controlled
```

Unacceptable heuristic signals:

```text
- explicit bonus for using Ax1
- explicit bonus for using Ax2
- explicit bonus for using Ax3
- target-specific axiom preferences
- benchmark-specific proof strategy rules
```

Axiom usage may be logged as diagnostics only.

---

## Diagnostics to report

Add or preserve diagnostics such as:

```text
generation
active depth
valid_fraction
closed_fraction
schematic_fraction
exact_target_count
exact_region_count
best_closed_target_candidate
best_closed_region_candidate
best_schema_candidate
best_novelty_candidate
unique_behavior_count
behavior_archive_size
schema_archive_size
random_immigrant_count
beam_pool_size
beam_pair_attempts
beam_pair_budget
beam_layer_counts
mean_cd_steps
mean_substantive_cd_steps
mean_cd_depth
mean_proof_size
mean_formula_size
```

Beam-specific diagnostics:

```text
major candidates considered
compatible minor candidates found
CD pairs attempted
valid CD products
closed products generated
schematic products generated
closed products kept
schematic products kept
instantiated schema products
```

Axiom-family diagnostics are allowed as telemetry only:

```text
generated_ax1_fraction
generated_ax2_fraction
generated_ax3_fraction

kept_ax1_fraction
kept_ax2_fraction
kept_ax3_fraction

best_candidate_using_ax1
best_candidate_using_ax2
best_candidate_using_ax3
```

Do not feed axiom-family diagnostics back into scoring as bonuses.

---

## Recommended implementation order

Implement the cascading search changes in this order:

```text
1. Add SearchPhase dataclass.
2. Add make_default_search_phases(base_config).
3. Modify beam pair generation to accept prioritized/suffix/exploratory budget fractions.
4. Implement strict-preselected phase using current behavior.
5. Implement hybrid pair generation.
6. Implement expanded-hybrid phase.
7. Implement search_with_fallback.
8. Update run_benchmarks to report solved_in_phase and phase reports.
9. Add regression expectations:
   - identity should be found
   - syllogism should be found by some phase
   - contraction should be found
10. Re-run the five target-only benchmarks.
```

---

## Non-goals for the next milestone

Do not implement:

```text
Lean integration
Mathlib integration
native Lean AST parsing
natural-deduction tactics
surface-level conjunction elimination as a primitive rule
hardcoded known proofs
proof-string replay as a benchmark
large external proof database ingestion
more one-off bad-shape penalties
axiom-family selection bonuses
target-specific axiom preferences
user-facing beam mode selection
```

---

## Summary

Current issue:

```text
Strict preselected-pair beam search is fast and structured, but it can over-prune useful intermediate proofs and caused a regression on syllogism.
```

Near-term fix:

```text
one default cascading search policy:
  strict-preselected
  then hybrid
  then expanded-hybrid
  then report failure
```

This avoids exposing user-facing modes while making the tool more robust against heuristic over-pruning.
