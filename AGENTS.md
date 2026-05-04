# AGENTS.md — birdrat-proplogic: Suffix Retention, Antecedent Coverage, and Beam-Local Schema Instantiation

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

Current expected behavior:

```text
identity:
  should pass, typically in strict-preselected

contraction:
  should pass, typically in strict-preselected

syllogism:
  should pass by some phase; currently recovered in expanded-hybrid

classical-negation:
  may still fail, but should produce useful diagnostics

distribution/application:
  may still fail, but should produce useful diagnostics
```

Do not return to encoded conjunction benchmarks such as:

```text
p ∧ q → p
p ∧ q → q
p ∧ q → q ∧ p
```

until the small target suite is reliable.

---

## Current search architecture

The search uses a default cascading policy:

```text
Phase 1: strict-preselected
Phase 2: hybrid
Phase 3: expanded-hybrid
Failure: report not found
```

The user should not have to choose beam modes manually. The tool should run the cascade automatically.

Current interpretation:

```text
strict-preselected:
  fast path using target-directed CD-pair preselection

hybrid:
  fallback with suffix/subgoal and exploratory pair channels

expanded-hybrid:
  larger bounded fallback with more budget and possibly +1 beam depth
```

This cascade is useful and should remain.

The next issue is that the fallback phases can recover some regressions, but suffix/subgoal tracking and schema instantiation are not yet operational enough. The next milestone is to make the beam preserve suffix-progress candidates and turn schematic lemmas into closed candidates more effectively.

---

## Do not add proof-shape hacks

Do not add one-off penalties for specific bad-looking formulas.

Do not add rules such as:

```text
penalize this exact projection form
penalize this exact Ax1 wrapper
penalize this exact Ax2/Ax3 pattern
```

The benchmark failures should be addressed structurally through:

```text
suffix retention
antecedent coverage
schema instantiation
quality-diverse retention
better diagnostics
```

not by patching against individual plateaus.

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

# Next milestone

## Main goal

Make suffix retention and schema instantiation operational.

The current benchmark results show:

```text
identity passes
contraction passes
syllogism is recovered by expanded-hybrid
classical-negation still fails
distribution/application still fails
```

The next goal is not to solve the remaining two targets by hardcoding proof ideas.

The next goal is to improve the search substrate so that it:

```text
1. preserves useful target-suffix candidates,
2. notices whether a candidate covers the target antecedents,
3. turns schematic lemmas into closed candidates using target-derived substitutions,
4. reports enough diagnostics to see where the proof search is failing.
```

---

# 1. Real suffix retention buckets

## Motivation

For a target with implication spine:

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

These suffixes are target-derived subgoals. Preserving candidates near these suffixes is a neutral formula-driven heuristic, not a proof-specific trick.

Example: syllogism

```text
target:
  (p → q) → (r → p) → r → q

suffixes:
  q
  r → q
  (r → p) → r → q
  (p → q) → (r → p) → r → q
```

Example: distribution/application

```text
target:
  (p → q) → (p → q → r) → p → r

suffixes:
  r
  p → r
  (p → q → r) → p → r
  (p → q) → (p → q → r) → p → r
```

The distribution/application failure often produces candidates close to:

```text
((p → q → r) → p → r) → (p → q → r) → p → r
```

This suggests the search sees a useful suffix-like object but does not assemble the missing antecedent `(p → q)`. Real suffix retention should preserve candidates near the intermediate suffixes while antecedent coverage scoring distinguishes complete from incomplete candidates.

## Required functions

Add or maintain:

```python
implication_spine(formula: Formula) -> tuple[tuple[Formula, ...], Formula]
```

For:

```text
A1 → A2 → ... → An → H
```

return:

```text
((A1, A2, ..., An), H)
```

Add or maintain:

```python
implication_spine_suffixes(formula: Formula) -> tuple[Formula, ...]
```

For:

```text
A1 → A2 → ... → An → H
```

return:

```text
(
    H,
    An → H,
    A(n-1) → An → H,
    ...
    A1 → A2 → ... → An → H,
)
```

Use right-associated implication throughout.

## Suffix bucket retention

During beam retention, reserve slots for each suffix.

Suggested configuration fields:

```python
suffix_closed_keep_per_suffix: int = 3
suffix_schematic_keep_per_suffix: int = 3
```

or comparable names.

For each suffix `S`, keep:

```text
top suffix_closed_keep_per_suffix closed candidates by similarity to S
top suffix_schematic_keep_per_suffix schematic candidates by similarity/usefulness to S
```

These suffix survivors should be added to the next frontier alongside globally best closed/schematic candidates.

Do not let one suffix consume all suffix slots. Allocate per suffix.

## Ranking inside suffix buckets

For a candidate conclusion `C` and suffix `S`, rank by:

```text
directed similarity to S
antecedent coverage relative to S
low assumption debt relative to S
closedness when the suffix is closed
smaller proof size
smaller formula size
fewer CD steps
```

A schematic candidate can survive a suffix bucket if it is close to the suffix and plausibly instantiable, but closed candidates should be preferred when available.

## Deduplication

Deduplicate proof candidates after combining:

```text
global closed keep
global schematic keep
suffix closed keep
suffix schematic keep
novelty keep, if applicable
instantiated schema products
```

Deduplication can be by conclusion first, keeping the best/smallest proof for that conclusion.

If proof identity is easier to track than conclusion identity, use proof identity for initial implementation but prefer conclusion-based deduplication eventually.

## Suffix diagnostics

Report suffix retention after retention, not before.

Add diagnostics such as:

```text
suffix_survivors_by_suffix:
  q: 2 closed, 3 schematic
  r → q: 1 closed, 3 schematic
  (r → p) → r → q: 3 closed, 2 schematic
  full target: 0 closed, 1 schematic
```

The existing `suffix_survivors=[...:0]` diagnostic suggests suffix tracking is not yet operational enough. The diagnostic should show candidates actually retained in suffix buckets.

Also report:

```text
suffix_candidates_seen_by_suffix
suffix_closed_candidates_seen_by_suffix
suffix_schematic_candidates_seen_by_suffix
suffix_survivors_by_suffix
```

---

# 2. Antecedent coverage scoring

## Motivation

A candidate may have the correct final head but fail to use all target assumptions.

For distribution/application:

```text
target:
  (p → q) → (p → q → r) → p → r
```

the target antecedents are:

```text
p → q
p → q → r
p
```

and the final head is:

```text
r
```

A common attractor is:

```text
((p → q → r) → p → r) → (p → q → r) → p → r
```

This is close to a useful suffix but does not cover the antecedent:

```text
p → q
```

So ranking by consequent/head similarity alone is insufficient. The search needs a secondary score for how well candidate antecedents cover target antecedents.

## Required function

Add:

```python
antecedent_coverage_score(candidate: Formula, target: Formula) -> float
```

Suggested behavior:

```text
1. Flatten both formulas into implication spines.
2. Let target antecedents be T_ants.
3. Let candidate antecedents be C_ants.
4. For each target antecedent t in T_ants, find the best unmatched candidate antecedent c in C_ants.
5. Use formula similarity or unification success to score the match.
6. Return normalized score in [0, 1].
```

A simple first implementation:

```text
coverage = matched_target_antecedents / total_target_antecedents
```

where a target antecedent is matched if:

```text
candidate antecedent exactly equals it
or candidate antecedent unifies with it
or directed formula similarity exceeds a threshold
```

A more graded implementation may use maximum bipartite matching with formula similarities, but that is optional.

## Important asymmetry

Coverage is asymmetric.

A candidate should get credit for covering target assumptions. It should not get equal credit just because the target covers candidate assumptions.

For target:

```text
A → B → H
```

candidate:

```text
A → H
```

covers only `A`, not `B`.

candidate:

```text
A → B → C → H
```

covers `A` and `B` but has extra assumption debt `C`.

Use antecedent coverage together with assumption debt.

## Use sites

Use antecedent coverage as a secondary term in:

```text
closed candidate ranking
major_priority
suffix bucket ranking
quality-diverse closed-target scoring
benchmark diagnostics
```

Do not let antecedent coverage dominate exact target matching. Exact target remains decisive.

Do not use antecedent coverage to reward arbitrary extra assumptions. Pair it with existing assumption-debt penalties.

## Example expectations

For:

```text
target:
  (p → q) → (p → q → r) → p → r
```

candidate:

```text
((p → q → r) → p → r) → (p → q → r) → p → r
```

should receive:

```text
head/suffix similarity: moderately high
antecedent coverage: incomplete
assumption debt / missing assumption issue: significant
```

candidate:

```text
(p → q) → (p → q → r) → p → r
```

should receive:

```text
antecedent coverage: 1.0
exact target: true
```

For syllogism:

```text
target:
  (p → q) → (r → p) → r → q
```

candidate:

```text
(p → q) → p → q
```

should receive:

```text
final head match: yes
coverage: incomplete
missing contextual assumptions: r → p and r
```

---

# 3. Beam-local schema instantiation

## Motivation

The search often discovers useful schematic lemmas. Examples include:

```text
(p → ?x) → p → ?x

(?p → ?p → ?r) → ?p → ?r

(¬?p → ¬?q) → ?q → ?p
```

These are legitimate schematic theorem candidates. But a schematic formula is not a closed proof of the user target.

The search needs to instantiate schematic candidates using target-derived formulas and feed the instantiated results back into the beam.

This should happen inside the beam, not only after final selection.

## Closed versus schematic invariant

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

## Target formula pool for instantiation

Build a small formula pool for schema instantiation.

Include:

```text
atoms from target and regions
target antecedents
target head
target implication suffixes
target formula itself
generated region formulas
subformulas of target
subformulas of generated regions
selected negations
selected small implications
```

Keep this pool small and deterministic.

Suggested caps:

```python
schema_instantiation_pool_size: int = 50
schema_instantiation_max_metas: int = 2
schema_instantiation_max_attempts_per_proof: int = 100
```

Start conservative. Increase only after diagnostics show the need.

## Required proof substitution

Add or maintain:

```python
apply_substitution_to_proof(proof: Proof, subst: Mapping[Meta, Formula]) -> Proof
```

This should replace metas consistently throughout the proof tree.

After substitution:

```text
1. recompute conclusion
2. verify the proof remains valid under the internal checker
3. discard invalid instantiated proofs
```

If the proof dataclasses use `Meta(name)` objects rather than string keys, be consistent in substitution representation.

## Beam-local instantiation procedure

During each beam layer, after candidate generation and before final retention:

```text
1. collect top schematic candidates
2. for each schematic candidate:
     a. inspect metas in its conclusion
     b. generate a bounded set of substitutions from the target formula pool
     c. instantiate the proof
     d. verify instantiated proof
     e. add valid instantiated candidates to the candidate pool
3. allow instantiated candidates to compete in closed/schematic/suffix retention
```

This is important: instantiated products should feed the next frontier if retained.

## Direct schema-target unification

Also support direct unification against target, regions, and suffixes:

```text
if unify(schema_conclusion, target_or_region_or_suffix) succeeds:
    instantiate proof using that unifier
    verify instantiated proof
    add valid instantiated proof to candidates
```

This can catch exact promotions cheaply.

## Instantiation diagnostics

Report:

```text
schema_instantiation_attempts
schema_instantiation_valid
schema_instantiation_closed
schema_instantiation_schematic
schema_instantiation_exact_target
schema_instantiation_exact_region
schema_instantiation_exact_suffix
best_instantiated_candidate
```

Also report per phase and per beam layer if possible.

The current benchmark logs report only `schema instantiation products`. That is too coarse. Add enough detail to determine whether instantiation is not being attempted, invalidating, staying schematic, or simply not useful.

---

# 4. Target-directed pair generation remains necessary

The beam should avoid trying all ordered CD pairs.

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

## Pair channels

The cascade should preserve multiple pair channels:

```text
strict target-prioritized pairs
suffix/subgoal-diverse pairs
exploratory compatible pairs
```

Later phases should be monotone: they should include the earlier strict channel and add additional channels, not replace strict search with a different search.

## Prioritized pairs

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

## Suffix pairs

Suffix pairs should target major consequents near implication suffixes.

For each suffix:

```text
collect candidate pairs whose major consequent is close to that suffix
rank by suffix similarity, antecedent coverage, proof size, formula size
keep a bounded number per suffix
```

Do not let all suffix-channel budget go to the final head. Distribute across suffixes.

## Exploratory pairs

The exploratory channel prevents catastrophic pruning.

It should remain compatible-pair based, not arbitrary invalid-pair search.

Acceptable exploratory sources:

```text
random compatible pairs from the current pair pool
novelty-ranked compatible pairs
pairs involving underrepresented behavior descriptors
pairs involving closed candidates not selected by target-prioritized channel
pairs involving schematic candidates not selected by target-prioritized channel
```

Keep the exploratory budget small.

---

# 5. Quality-diversity selection

The search should not rely on one scalar fitness score as the only survival mechanism.

Use separate elite buckets:

```text
closed target elites:
  closed candidates closest to the full target

closed region elites:
  closed candidates closest to generated regions

suffix elites:
  candidates close to target implication suffixes

schematic lemma elites:
  valid schematic candidates that are compact and potentially reusable

novelty elites:
  candidates whose behavior descriptors are far from known candidates

random immigrants:
  fresh target-seeded candidates injected each generation
```

The exact allocation can be configurable.

The important rule is:

```text
Do not let a single scalar score define the whole next generation.
```

---

# 6. Diagnostics

Add or preserve broad diagnostics:

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

Suffix diagnostics:

```text
suffixes
suffix_candidates_seen_by_suffix
suffix_closed_candidates_seen_by_suffix
suffix_schematic_candidates_seen_by_suffix
suffix_survivors_by_suffix
best_candidate_by_suffix
```

Schema-instantiation diagnostics:

```text
schema_instantiation_attempts
schema_instantiation_valid
schema_instantiation_closed
schema_instantiation_schematic
schema_instantiation_exact_target
schema_instantiation_exact_region
schema_instantiation_exact_suffix
best_instantiated_candidate
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

# 7. Regression expectations

The benchmark suite should guard against regressions.

Expected near-term results:

```text
identity:
  must be found

contraction:
  must be found

syllogism:
  must be found by some cascade phase

classical-negation:
  may still fail
  should show useful schema-instantiation and suffix diagnostics

distribution/application:
  may still fail
  should show useful antecedent-coverage, suffix-retention, and schema-instantiation diagnostics
```

Do not treat classical-negation and distribution/application as hard failures yet. They are active search targets.

---

# 8. Recommended implementation order

Implement the next changes in this order:

```text
1. Add real suffix retention buckets in the beam.
2. Add suffix retention diagnostics after retention.
3. Add antecedent_coverage_score.
4. Use antecedent coverage in closed ranking, major priority, and suffix bucket ranking.
5. Add beam-local schema instantiation.
6. Add detailed schema-instantiation diagnostics.
7. Re-run the five target-only benchmarks.
8. Confirm identity, contraction, and syllogism still pass.
9. Examine classical-negation and distribution/application diagnostics.
10. Only then decide whether further structural changes are needed.
```

---

# 9. Non-goals for the next milestone

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
The system solves identity, contraction, and recovered syllogism.
The remaining failures are classical-negation and distribution/application.
```

Near-term fix:

```text
real suffix retention buckets
+ antecedent coverage scoring
+ beam-local schema instantiation
+ detailed diagnostics
```

This should improve the search substrate without hardcoding proofs or inserting axiom-specific proof strategy.
