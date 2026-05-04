# AGENTS.md — birdrat-proplogic: Neutral Beam Heuristics, Benchmark Search, and Diagnostics

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

## Important benchmark policy

Do **not** hardcode known proofs.

Do **not** build benchmarks around replaying known proof strings.

Do **not** seed the search with external proof strings.

The benchmark suite should consist of theorem targets only. The search system must attempt to find proofs of those targets using the internal proof-search machinery.

It is acceptable that benchmark targets were selected because they are externally known to have short `P₂ + CD` proofs. But the implementation should not use the known proofs during search, scoring, initialization, benchmarking, or verification.

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

The small target benchmark suite has become useful.

Current target suite:

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
- syllogism is solvable
- contraction is solvable
- classical-negation remains unsolved
- distribution/application remains unsolved
```

This is good progress. The failures are informative and should be treated as search diagnostics, not as reasons to add proof-specific hacks.

Do not return to encoded conjunction benchmarks such as:

```text
p ∧ q → p
p ∧ q → q
p ∧ q → q ∧ p
```

until the small target suite is reliable.

---

## Neutrality requirement for heuristics

Do not seed the beam heuristic with proof ideas tied to a specific axiom.

In particular, do **not** implement rules such as:

```text
if the target contains negation, boost Ax3
if the target looks classical, prefer Ax3-containing candidates
if the target is implicational, prefer Ax1/Ax2
```

This would encode proof strategy knowledge into the heuristic and would weaken the experiment.

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

---

## Axiom-family diagnostics are allowed

Although axiom identity should not drive selection, axiom usage should be reported as telemetry.

The purpose of axiom-family diagnostics is to answer questions such as:

```text
Is the search generating candidates using all three axioms?
Is selection accidentally deleting all candidates from one axiom family?
Are candidates using a particular axiom present but consistently low-ranked?
Is the beam dominated by one proof family?
```

Add or maintain functions such as:

```python
axiom_counts(proof) -> tuple[int, int, int]
uses_ax1(proof) -> bool
uses_ax2(proof) -> bool
uses_ax3(proof) -> bool
```

Suggested diagnostics:

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

best_closed_candidate_using_ax1
best_closed_candidate_using_ax2
best_closed_candidate_using_ax3

best_schematic_candidate_using_ax1
best_schematic_candidate_using_ax2
best_schematic_candidate_using_ax3
```

These are diagnostics only. Do not feed them directly into the scoring function as axiom-family bonuses.

If a benchmark involving negation fails and diagnostics show:

```text
many Ax3 candidates generated
almost no Ax3 candidates kept
```

then the fix should still be structural, for example:

```text
improve consequent-suffix scoring
improve closed/schematic separation
improve schema instantiation
improve assumption-debt handling
```

not:

```text
add Ax3 bonus
```

---

## Target-directed CD pair preselection

The beam search should avoid trying all ordered CD pairs.

Avoid the naive pattern:

```python
for major in pair_pool:
    for minor in pair_pool:
        try_make_cd(major, minor)
```

This becomes effectively quadratic in the pair-pool size.

A CD step proves `B` when:

```text
major proves A → B
minor proves A
```

Therefore, for a target `T`, good major candidates are implications whose consequents are useful relative to `T`.

This is a formula-driven criterion and is acceptable.

---

## Implication suffixes

For a target formula with right-associated implication spine:

```text
A1 → A2 → ... → An → H
```

the useful target suffixes are:

```text
H
An → H
A(n-1) → An → H
...
A1 → A2 → ... → An → H
```

Example:

```text
target:
  (p → q) → (p → q → r) → p → r

suffixes:
  r
  p → r
  (p → q → r) → p → r
  (p → q) → (p → q → r) → p → r
```

A CD major whose consequent matches or unifies with one of these suffixes is promising.

Add:

```python
implication_spine(formula) -> tuple[tuple[Formula, ...], Formula]
implication_spine_suffixes(formula) -> tuple[Formula, ...]
```

---

## Major candidate priority

Add:

```python
implication_major_parts(proof) -> tuple[Formula, Formula] | None
```

If:

```text
conclusion(proof) = A → B
```

then return:

```text
(A, B)
```

Otherwise return `None`.

Add:

```python
major_priority(major, target, regions) -> float
```

Major priority should reward:

```text
- consequent exactly equals target
- consequent unifies with target
- consequent exactly equals a generated region
- consequent unifies with a generated region
- consequent equals a target implication suffix
- consequent unifies with a target implication suffix
- consequent has high directed similarity to target/regions
- consequent has the same final implication-spine head as target/regions
```

Major priority should penalize:

```text
- large antecedent A
- large proof size
- many CD steps
- large formula size
- purely vacuous weakening patterns
```

Do not include axiom-family bonuses in `major_priority`.

Sketch:

```python
def major_priority(major, target, regions):
    parts = implication_major_parts(major)
    if parts is None:
        return float("-inf")

    antecedent, consequent = parts

    return (
        suffix_match_weight * suffix_priority(consequent, target, regions)
        + consequent_similarity_weight * best_consequent_similarity(consequent, target, regions)
        + unification_weight * int(unifies_with_target_or_suffix(consequent, target, regions))
        - antecedent_size_penalty * formula_size(antecedent)
        - proof_size_penalty * proof_size(major)
        - cd_step_penalty * cd_steps(major)
    )
```

Weights should be configurable.

---

## Minor candidate compatibility

Given a major antecedent `A`, do not try every possible minor.

A minor candidate is useful only if its conclusion can unify with `A`.

Add a coarse shape index for minor conclusions.

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

This index does not need to be complete. It is a preselection heuristic. The actual `unify` call remains the final authority.

Add:

```python
compatible_minor_candidates(antecedent, proof_pool, index) -> Iterable[Proof]
```

Then filter/rank by actual unification.

---

## Pair priority

Add:

```python
pair_priority(major, minor, target, regions) -> float
```

It should:

```text
1. require major conclusion to be implication-shaped
2. require major antecedent to unify with minor conclusion
3. reward high major_priority
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

## Beam pair budget

Add or preserve a configuration option:

```text
beam_pair_budget
```

The beam should try only the top-ranked candidate pairs per layer.

Instead of:

```text
try all O(n²) ordered pairs
```

do:

```text
rank plausible pairs
try top beam_pair_budget pairs
```

This is the most important performance change before increasing `beam-width`.

---

## Revised beam algorithm

The beam should use preselected CD pairs.

Sketch:

```python
for depth in range(max_depth):
    pair_pool = build_pair_pool(seeds, known, frontier)

    index = build_minor_shape_index(pair_pool)

    candidate_pairs = []

    majors = top_k(
        [p for p in pair_pool if implication_major_parts(p) is not None],
        key=lambda p: major_priority(p, target, regions),
        k=major_budget,
    )

    for major in majors:
        antecedent, _ = implication_major_parts(major)
        minors = compatible_minor_candidates(antecedent, pair_pool, index)

        for minor in minors:
            priority = pair_priority(major, minor, target, regions)
            if priority is finite:
                candidate_pairs.append((priority, major, minor))

    for _, major, minor in top_k(candidate_pairs, k=beam_pair_budget):
        candidate = try_make_cd(major, minor)
        if candidate is valid:
            collect candidate

    split candidates into:
        closed candidates
        schematic candidates

    keep top closed candidates by target/region score
    keep top schematic candidates by schema score + novelty

    update frontier
```

Preserve existing closed/schematic ranking after candidates are generated. The new heuristic reduces pair attempts before CD; it does not replace candidate ranking after CD.

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

Axiom-family diagnostics:

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

best_closed_candidate_using_ax1
best_closed_candidate_using_ax2
best_closed_candidate_using_ax3

best_schematic_candidate_using_ax1
best_schematic_candidate_using_ax2
best_schematic_candidate_using_ax3
```

Again: axiom-family diagnostics are telemetry only. They should not be converted into axiom-family bonuses.

---

## Recommended implementation order

Implement the next changes in this order:

```text
1. Preserve the target-only benchmark suite.
2. Confirm identity, syllogism, and contraction remain solvable.
3. Add or strengthen target implication suffix logic.
4. Add stronger target-directed CD pair preselection.
5. Add or improve beam_pair_budget and beam diagnostics.
6. Add axiom-family survival diagnostics as telemetry only.
7. Add schema instantiation from substitutions and formula-pool replacements.
8. Re-run the five benchmark targets.
9. Do not return to encoded conjunction benchmarks until the five-target suite is reliable.
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
```

---

## Summary

Current status:

```text
The system can solve some small target-only P₂ + CD benchmarks.
The remaining failures reveal issues in target-directed beam generation, schema instantiation, and search diversity.
```

Near-term fix:

```text
neutral target-formula-driven beam heuristics
+ implication suffix priority
+ CD pair preselection
+ schema instantiation
+ axiom-family diagnostics as telemetry only
```

Do not return to encoded conjunction until the small target-only benchmark suite is reliable.
