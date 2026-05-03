# AGENTS.md — birdrat-proplogic Identity / Quality-Diversity Update

## Project purpose

`birdrat-proplogic` is a prototype proof-search system for classical propositional logic.

The project searches for Hilbert-style proofs over the Łukasiewicz/Church `P₂` axiom schemata using condensed detachment (`CD`) as the internal inference rule. The long-term goal is to build a Lean-facing theorem generator whose proof search is restricted to an explicitly chosen set of valid logical moves.

This is not a general Lean tactic prover. Do not add general Lean automation. Do not use `simp`, `tauto`, `aesop`, `omega`, Mathlib automation, or native Lean proof search to bypass the restricted proof system.

The current priority is not Lean integration. The current priority is to make the internal proof-search substrate competent on small `P₂ + CD` benchmarks.

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
a ∧ b → a
```

is not a primitive projection rule.

It desugars to:

```text
¬(a → ¬b) → a
```

This is a nontrivial theorem in the `P₂ + CD` system. Do not treat surface conjunction elimination as a primitive proof rule.

---

## Immediate benchmark strategy

Do not use encoded conjunction examples as the first correctness tests.

Avoid using these as the first proof-search benchmarks:

```text
a ∧ b → a
a ∧ b → b
a ∧ b → b ∧ a
```

They look simple in surface syntax, but under the encoding of conjunction they become nontrivial classical theorems.

Start with smaller Hilbert/CD benchmarks:

```text
p → q → p
p → p
(p → q) → p → q
```

The first non-axiom benchmark should be identity:

```text
p → p
```

A known condensed-detachment proof of identity from `Ax1` and `Ax2` is:

```text
DD211
```

where:

```text
1 = Ax1
2 = Ax2
3 = Ax3
D = condensed detachment
```

`DD211` parses as:

```text
D(D(2, 1), 1)
```

An expanded proof shape is:

```text
1. ψ → (φ → ψ)                                      Ax1
2. ψ → ((φ → ψ) → ψ)                               Ax1
3. (ψ → ((φ → ψ) → ψ)) → ((ψ → (φ → ψ)) → (ψ → ψ)) Ax2
4. (ψ → (φ → ψ)) → (ψ → ψ)                         CD
5. ψ → ψ                                           CD
```

The system should be able to verify this proof before attempting encoded conjunction.

---

## Current diagnostic conclusion

The search can now produce valid Hilbert/CD proof artifacts, but it tends to plateau on compact schematic lemmas rather than closed proofs of the input theorem.

Examples of plateau families observed so far:

```text
(¬?p → ¬b) → b → ?p

((¬?r → ¬b) → b) → (¬?r → ¬b) → ?r

(b → ?p) → b → ?p
```

These are often legitimate schematic theorems. They are not necessarily bad. The issue is that they are not closed proofs of the user-provided target.

Do not keep adding one-off penalties for each new bad-looking proof shape. The repeated plateaus indicate an architectural issue: schematic theorem discovery and closed target proof search are currently competing in the same survival channel.

---

## Closed versus schematic candidates

The input theorem is closed. Therefore the final accepted proof must have a closed conclusion exactly equal to the core target.

Add or maintain:

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

closed candidate:
  valid proof whose conclusion is closed

schematic candidate:
  valid proof whose conclusion contains one or more Meta variables
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

The search frequently discovers useful open schemata. These should be treated as reusable lemma schemas, not as direct target candidates.

Add a schema-instantiation operation.

Suggested operation:

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

Example:

```text
schema candidate:
  (b → ?p) → b → ?p

try:
  ?p := a
  ?p := b
  ?p := ¬(a → ¬b)
  ?p := ¬(b → ¬a)
  ?p := a → ¬b
```

Also add direct schema-target matching:

```text
if unify(schema_conclusion, target_or_region) succeeds:
    instantiate the proof using the unifier
    evaluate the instantiated proof
```

If unification fails, keep the candidate in the schema archive rather than allowing it to dominate closed-target search.

---

## Quality-diversity selection

The search should not rely on one scalar fitness score as the only survival mechanism.

A scalar score is useful for reporting and local ranking, but population survival should preserve multiple roles.

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

The exact allocation can be configurable. The important rule is:

```text
Do not let a single scalar score define the whole next generation.
```

---

## Behavior descriptors and novelty

Add a behavior descriptor for each valid candidate.

Suggested fields:

```python
BehaviorDescriptor(
    closed: bool,
    root_symbol: str,
    implication_spine_length: int,
    final_head_shape: str,
    atom_set: frozenset[str],
    meta_count: int,
    cd_steps: int,
    substantive_cd_steps: int,
    proof_depth: int,
    axiom_counts: tuple[int, int, int],
    normalized_skeleton: str,
)
```

Use descriptors to compute novelty.

Simple novelty score:

```python
novelty(candidate) =
    average distance to k nearest behavior descriptors in the behavior archive
```

Distance can be approximate and feature-based:

```text
+ closed/schematic mismatch
+ difference in implication spine length
+ difference in meta count
+ difference in CD depth
+ difference in substantive CD steps
+ difference in axiom-count vector
+ final-head-shape mismatch
+ Jaccard distance between atom sets
+ skeleton mismatch penalty
```

This does not need to be perfect. The goal is to prevent one compact proof family from occupying the population for hundreds of generations.

---

## Deterministic or semi-deterministic CD beam search

Pure genetic programming is too stochastic for Hilbert/CD proof search.

Add a deterministic or semi-deterministic CD closure/beam mode.

Basic idea:

```text
1. seed with target-derived axiom instances
2. for depth d:
     try CD on promising ordered proof pairs
     keep top K closed candidates
     keep top K schematic candidates
3. use the resulting proof pool to seed or mix the GP population
```

Pseudo-code:

```python
known_closed = {}
known_schematic = {}

frontier = seeded_axiom_instances(target, regions)

for depth in range(max_depth):
    new = []

    for major in promising_majors(frontier, known_closed, known_schematic):
        for minor in promising_minors(frontier, known_closed, known_schematic):
            candidate = try_make_cd(major, minor)
            if candidate is valid:
                new.append(candidate)

    closed_new = [
        p for p in new
        if is_closed_formula(conclusion(p))
    ]

    schematic_new = [
        p for p in new
        if not is_closed_formula(conclusion(p))
    ]

    keep top K closed_new by target/region score
    keep top K schematic_new by schema score + novelty

    update frontier
```

The CD beam should be able to reproduce tiny known proofs such as `DD211` for `p → p`.

The GP layer can then mutate, crossover, and instantiate around the beam-generated pool.

---

## D-proof verification/import

Add a parser/verifier for condensed-detachment proof strings.

Notation:

```text
1 = Ax1
2 = Ax2
3 = Ax3
D = condensed detachment
```

Example:

```text
DD211
```

means:

```text
D(D(2, 1), 1)
```

Add a command such as:

```bash
python -m birdrat_proplogic.verify_d "DD211"
```

Expected behavior:

```text
- parse the D-expression
- expand leaves as Ax1/Ax2/Ax3 schemas
- compute the conclusion using CD
- print the derived formula
- confirm that DD211 derives p → p, up to variable renaming
```

This gives the project concrete known proof examples independent of the GP loop.

Once this works, add support for importing small proof databases such as Metamath-style `pmproofs.txt` condensed-detachment examples.

---

## Fitness function guidance

The current scalar fitness function includes many useful components:

```text
exact target match
exact generated-region match
directed implication-spine similarity
old symbolic/tree similarity
assumption debt
projection detection
vacuous weakening detection
substantive CD scoring
proof-size penalty
formula-size penalty
depth penalty
```

Keep these as target-directed scoring features.

But do not expect the scalar fitness function to solve population management by itself.

Use it mainly for:

```text
ranking closed target candidates
ranking closed region candidates
ranking candidate quality within an elite bucket
```

Do not use the same target-directed scalar as the only survival criterion for schematic lemmas, novelty elites, and random exploratory candidates.

---

## Schematic lemma scoring

Schematic candidates should be scored separately from closed target candidates.

Useful schematic candidates are:

```text
valid
compact
not pure vacuous weakening
not already common in the schema archive
instantiable against target/region subformulas
built using substantive CD steps
```

A schematic theorem is especially useful if it can be instantiated into a closed formula close to the target or a generated region.

Schematic scoring should prefer reusable lemmas, but schematic candidates should not be allowed to masquerade as proofs of the target.

---

## Mutation priorities

Useful mutation operators now include:

```text
subtree replacement
axiom replacement
formula argument mutation
CD child replacement
major/minor swap
random target-seeded subtree insertion
instantiate_meta_from_pool
close_schema_candidate
```

The most important new operators are:

```text
instantiate_meta_from_pool:
  replace a Meta variable with a target/region formula

close_schema_candidate:
  repeatedly instantiate metas from the formula pool until the conclusion is closed or closer to closed
```

This helps convert discovered schemata into closed theorem candidates.

---

## Archive design

Maintain separate archives:

```text
target_archive:
  best closed proofs near the full target

region_archive:
  best closed proofs for generated regions

schema_archive:
  compact valid schematic lemmas

behavior_archive:
  behavior descriptors for novelty computation

dproof_archive:
  imported known condensed-detachment proofs
```

Do not let the schema archive replace closed target search. It is supporting material.

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
mean_cd_steps
mean_substantive_cd_steps
mean_cd_depth
mean_proof_size
mean_formula_size
```

A healthy run should not report the same schematic conclusion as the only best candidate for hundreds of generations unless the run is intentionally doing lemma-schema discovery.

---

## Recommended implementation order

Implement the next changes in this order:

```text
1. Add/finish metas(formula) and is_closed_formula(formula).
2. Add schema instantiation from substitutions and formula-pool replacements.
3. Add D-proof parser/verifier for strings like DD211.
4. Add identity benchmark p → p and verify DD211.
5. Add deterministic/semi-deterministic CD beam search.
6. Add quality-diversity selection buckets.
7. Add behavior descriptors and novelty archive.
8. Add close-schema mutation operators.
9. Return to encoded conjunction benchmarks only after p → p is reliable.
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
more one-off bad-shape penalties
large external proof database ingestion before DD211 works
```

The next milestone is small and concrete:

```text
Verify and reproduce p → p from DD211.
Then use that proof as a known benchmark for search.
```

---

## Summary

Current issue:

```text
The system discovers valid schematic Hilbert facts but fails to instantiate them into closed target proofs.
```

Near-term fix:

```text
closed/schematic separation
+ schema instantiation
+ D-proof verification
+ CD beam search
+ quality-diversity selection
```

First benchmark:

```text
p → p
```

Known CD proof:

```text
DD211
```
