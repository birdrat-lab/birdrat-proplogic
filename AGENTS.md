# AGENTS.md — birdrat-proplogic: Search Benchmark Suite and Target-Directed Beam Search

## Project purpose

`birdrat-proplogic` is a prototype proof-search system for classical propositional logic.

The project searches for Hilbert-style proofs over the Łukasiewicz/Church `P₂` axiom schemata using condensed detachment (`CD`) as the internal inference rule. The long-term goal is to build a Lean-facing theorem generator whose proof search is restricted to an explicitly chosen set of valid logical moves.

This is not a general Lean tactic prover. Do not add general Lean automation. Do not use `simp`, `tauto`, `aesop`, `omega`, Mathlib automation, or native Lean proof search to bypass the restricted proof system.

The current priority is not Lean integration. The current priority is to make the internal `P₂ + CD` proof-search substrate competent on small search benchmarks.

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

## Current diagnostic conclusion

The system can now find a proof of the identity theorem:

```text
p → p
```

using the evolutionary loop when seeded with a CD beam.

This is a real milestone.

However, attempting encoded conjunction projection:

```text
p ∧ q → p
```

is still premature. Under the project’s encoding, this is:

```text
¬(p → ¬q) → p
```

and the current search still tends to plateau on compact schematic lemmas instead of closed target proofs.

Observed schematic plateau examples include:

```text
(¬?p → ¬b) → b → ?p

((¬?r → ¬b) → b) → (¬?r → ¬b) → ?r

(b → ?p) → b → ?p

(¬?p3 → ¬(q → p → q)) → ?p3
```

These are often legitimate Hilbert-style theorem schemata. They are not necessarily bad. The issue is that they are not closed proofs of the user-provided target.

Do not keep adding one-off penalties for each new bad-looking proof shape. The repeated plateaus indicate an architectural issue: schematic theorem discovery and closed target proof search are still competing in the same survival channel.

---

## Important benchmark policy

Do **not** hardcode known proofs.

Do **not** build the demo around verifying known proof strings.

Do **not** seed the search with external proof strings.

The benchmark suite should consist of theorem targets only. The search system must attempt to find proofs of those targets using the internal proof search machinery.

It is acceptable that these targets were selected because they are known externally to have short `P₂ + CD` proofs. But the implementation should not use the known proofs during search, scoring, initialization, benchmarking, or verification.

The purpose of the benchmark suite is:

```text
Given only the theorem target, can the tool find a proof?
```

not:

```text
Can the tool replay a known proof?
```

---

## Immediate benchmark strategy

Do not use encoded conjunction examples as the first proof-search benchmark suite.

Avoid using these as the first targets for search validation:

```text
p ∧ q → p
p ∧ q → q
p ∧ q → q ∧ p
```

They look simple in surface syntax, but under the encoded conjunction definition they are nontrivial classical theorems.

The next milestone is to build a small benchmark suite of target formulas that are expected to have short `P₂ + CD` proofs.

The system should search for these proofs itself.

---

## Five-target search benchmark suite

Add a small benchmark suite of theorem targets. These are deliberately small and are intended to become regression tests and search calibration targets.

Do not include proof strings in the benchmark definitions.

Each benchmark should include:

```text
name
surface/core target formula
optional notes
search configuration
expected status under current search
```

It should not include a hardcoded proof.

---

### Benchmark 1: Identity

Target:

```text
p → p
```

Why it matters:

```text
First non-axiom theorem. Confirms that the CD beam and evolutionary loop can construct a basic Hilbert proof rather than only axiom instances.
```

Expected near-term status:

```text
Should be found by the current beam/evolution pipeline.
```

---

### Benchmark 2: Syllogism / functoriality

Target:

```text
(p → q) → ((r → p) → (r → q))
```

Equivalent right-associated form:

```text
(p → q) → (r → p) → r → q
```

Why it matters:

```text
Tests composition through Ax2. This theorem says implication can be transported through a context.
```

Expected near-term status:

```text
Should be a plausible next target after identity.
```

---

### Benchmark 3: Classical negation / explosion-like theorem

Target:

```text
¬p → p → q
```

Why it matters:

```text
Uses Ax3. Tests whether the system handles classical negation/contraposition-style reasoning rather than only Ax1/Ax2 implicational reasoning.
```

Expected near-term status:

```text
May require better target-directed CD pair selection.
```

---

### Benchmark 4: Contraction

Target:

```text
(p → p → q) → p → q
```

Why it matters:

```text
Tests duplicate antecedent handling. This is a useful benchmark for Hilbert-style proof search because contraction is not a primitive rule.
```

Expected near-term status:

```text
May require more than the shallow identity configuration.
```

---

### Benchmark 5: Distribution/application

Target:

```text
(p → q) → (p → q → r) → p → r
```

Why it matters:

```text
Tests a slightly deeper Ax2 pattern. This is a more demanding benchmark than identity and should expose whether the beam can construct useful multi-step implications.
```

Expected near-term status:

```text
Likely requires beam preselection before large beam widths become practical.
```

---

## Benchmark command

Add a benchmark command such as:

```bash
PYTHONPATH=src python -m birdrat_proplogic.run_benchmarks --small-targets
```

For each benchmark theorem, report:

```text
name
target formula
whether search found an exact proof
best closed candidate
best schematic candidate
best novelty candidate
best score
target similarity
proof CD steps
proof CD depth
proof size
formula size
runtime
beam width
beam max depth
beam pair attempts
beam valid products
population size
generations
```

The benchmark command should run the actual search. It should not replay or verify hardcoded proof strings.

The immediate goal is:

```text
Can the system independently find proofs for a small set of known-small target formulas?
```

not:

```text
Can it solve encoded conjunction?
```

---

## Target-directed CD pair preselection

The current beam search is too expensive when `beam-width` grows because it tries too many ordered CD pairs.

Avoid the naive pattern:

```python
for major in pair_pool:
    for minor in pair_pool:
        try_make_cd(major, minor)
```

This becomes effectively quadratic in the pair-pool size.

Increasing beam width from 80 to 500 can cause roughly:

```text
(500 / 80)^2 ≈ 39×
```

more pair attempts per beam layer, and the actual pair pool may be larger than the nominal width because it includes seeds, known proofs, and frontier proofs.

Before increasing beam widths substantially, add preselection.

---

## CD pair-selection heuristic

A CD step proves `B` when:

```text
major proves A → B
minor proves A
```

Therefore, for a target `T`, good major candidates are not merely formulas globally similar to `T`.

A good major is an implication whose consequent is close to the target or to a generated region.

### Major candidate priority

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

Sketch:

```python
def major_priority(major, target, regions):
    parts = implication_major_parts(major)
    if parts is None:
        return float("-inf")

    antecedent, consequent = parts

    return (
        1000.0 * best_consequent_similarity(consequent, target, regions)
        + 500.0 * int(unifies_with_any(consequent, [target, *regions]))
        - 2.0 * formula_size(antecedent)
        - 1.0 * proof_size(major)
        - 5.0 * cd_steps(major)
    )
```

Weights can be configuration values.

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
        - 1.0 * proof_size(minor)
        - 0.5 * substitution_size(sigma)
    )
```

---

## Beam pair budget

Add a configuration option such as:

```text
beam_pair_budget
```

The beam should try only the top-ranked candidate pairs per layer.

Example:

```text
beam_pair_budget = 5000
```

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

The beam should become:

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

Preserve the existing closed/schematic ranking after candidates are generated. The new heuristic is for reducing pair attempts before CD, not for replacing candidate ranking after CD.

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

Keep schema instantiation as a priority, but after the benchmark targets and pair preselection.

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

Beam-specific diagnostics are important now. Report:

```text
how many major candidates were considered
how many compatible minor candidates were found
how many CD pairs were attempted
how many valid CD products were produced
how many closed products survived
how many schematic products survived
```

---

## Recommended implementation order

Implement the next changes in this order:

```text
1. Add the 5 target-only search benchmarks.
2. Add a benchmark command that runs search on those 5 targets.
3. Confirm p → p remains solvable through search.
4. Add target-directed CD pair preselection.
5. Add beam_pair_budget and beam diagnostics.
6. Try to solve the 5 targets through search.
7. Add schema instantiation from substitutions and formula-pool replacements.
8. Strengthen quality-diversity selection only after the benchmark suite is stable.
9. Return to encoded conjunction benchmarks only after the small target suite is reliable.
```

Encoded conjunction projection:

```text
p ∧ q → p
```

should wait until the tool handles the small target-only benchmark suite.

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
```

The next milestone is small and concrete:

```text
Use search to solve a small suite of known-small theorem targets.
Do not provide the search with the known proofs.
```

---

## Summary

Current issue:

```text
The beam can prove p → p, but larger widths are too slow because CD pair generation is too close to O(n²).
```

Near-term fix:

```text
small target-only benchmark suite
+ benchmark command
+ target-directed CD pair preselection
+ beam pair budget
```

Do not return to encoded conjunction until the beam can reliably search for several small known theorem targets.
