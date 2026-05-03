# AGENTS.md Update — Search Diagnostics and Next Design Direction

## Current diagnostic conclusion

Stop adding one-off fitness penalties for each newly discovered bad proof shape.

The repeated plateaus are diagnostic evidence that the current scalar fitness function is too brittle. The search keeps discovering compact, valid, but target-irrelevant proof artifacts. Each new patch suppresses one artifact, but another artifact appears because the underlying selection architecture still lets a single scalar score dominate population survival.

Recent plateau examples include:

- trivial or projection-like `Ax1` applications,
- vacuous weakening wrappers of the form `H → R`,
- candidates that prove the desired consequent only after adding extra assumptions,
- compact schematic theorems with unresolved metavariables,
- valid but target-irrelevant `Ax2`/`Ax3` schemas.

These are not necessarily bad lemmas. They are often legitimate Hilbert-system facts. The issue is that they are competing in the same elite channel as closed target-proof candidates.

## Key principle

Separate proof-search roles instead of forcing everything through one scalar score.

The search should distinguish:

```text
closed target attempts
closed region attempts
schematic lemma candidates
novel proof/formula behaviors
random exploratory candidates
```

A candidate with unresolved metavariables is not a closed proof of the input theorem. It may be useful as a lemma schema, but it should not compete directly with closed candidates for target or region elite status unless it can be instantiated to the target or a generated region.

## Closed versus schematic candidates

Add:

```python
is_closed_formula(formula) -> bool
metas(formula) -> set[Meta]
```

Definitions:

```text
closed candidate:
  conclusion contains no Meta variables

schematic candidate:
  conclusion contains one or more Meta variables
```

Rules:

```text
- Only closed candidates should receive target-proof elite status.
- Only closed candidates should receive generated-region elite status.
- Schematic candidates should be stored/ranked separately as lemma schemas.
- A schematic candidate may be promoted only if it can be instantiated to a closed target or region.
```

Useful optional promotion rule:

```text
If unify(schematic_conclusion, target_or_region) succeeds,
instantiate the proof by that substitution,
then evaluate the instantiated closed proof.
```

## Avoid further ad hoc penalties

Do not keep adding narrowly tailored penalties such as:

```text
penalize this exact Ax1 wrapper
penalize this exact projection form
penalize this exact Ax2/Ax3 pattern
```

Some structural diagnostics remain useful, but they should serve a more general selection framework. Existing detectors such as weakening detection, assumption-debt scoring, projection detection, and implication-spine scoring can remain as features, but they should not be the only mechanism preventing collapse.

The higher-level fix is quality-diversity selection.

## Quality-diversity selection

Replace or supplement single-score elitism with separate elite buckets.

Suggested population partition:

```text
target elites:
  closed candidates closest to the full target

region elites:
  closed candidates closest to generated regions

novelty elites:
  candidates with behavior descriptors far from previously seen candidates

lemma-schema elites:
  schematic candidates that are compact, valid, and potentially reusable

random immigrants:
  fresh target-seeded candidates injected every generation
```

Example allocation for population size 100:

```text
20 target elites
20 region elites
20 novelty elites
20 lemma-schema elites
20 random immigrants / high-mutation candidates
```

For smaller populations, preserve the same structure proportionally.

## Behavior descriptors for novelty

Add a behavior descriptor for each candidate.

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

Use descriptors to compute novelty distance. Candidates with common descriptors should become less novel over time, even if they retain decent symbolic similarity.

This prevents one proof family from occupying the whole population for hundreds of generations.

## Novelty score

Implement a simple first version:

```python
novelty(candidate) =
    average distance to k nearest archived behavior descriptors
```

Use a small archive of behavior descriptors from prior elites and sampled population members.

Distance can be approximate and feature-based:

```text
+ difference in closed/schematic status
+ difference in implication spine length
+ difference in meta count
+ difference in CD depth
+ difference in axiom count vector
+ difference in final-head shape
+ Jaccard distance between atom sets
+ skeleton mismatch penalty
```

This does not need to be perfect. It just needs to prevent total collapse into one family.

## Selection algorithm sketch

Instead of selecting only by `total_fitness`, build the next population from multiple channels.

Pseudo-code:

```python
closed = [p for p in population if is_closed_formula(conclusion(p))]
schematic = [p for p in population if not is_closed_formula(conclusion(p))]

next_population = []

next_population += top_k(
    closed,
    key=target_directed_score,
    k=target_elite_count,
)

next_population += top_k(
    closed,
    key=region_directed_score,
    k=region_elite_count,
)

next_population += top_k(
    population,
    key=novelty_score,
    k=novelty_elite_count,
)

next_population += top_k(
    schematic,
    key=lemma_schema_score,
    k=schema_elite_count,
)

next_population += random_immigrants(
    k=random_immigrant_count,
    target=target,
    regions=regions,
)
```

Then fill any remaining slots by tournament selection over a mixed objective.

## Target and region scoring

Closed candidates should still be scored against the target and generated regions.

Target/region score should prioritize:

```text
exact target match
exact generated-region match
directed implication-spine similarity
low assumption debt
low vacuous weakening
low projection-like behavior
proof compactness
```

However, these features should no longer be expected to solve all selection pressure alone. They are target-directed features, not global population-management features.

## Schematic lemma scoring

Schematic candidates should be scored separately.

Useful schematic candidates are:

```text
valid
compact
not pure vacuous weakening
not already common in the schema archive
instantiable against target/region subformulas
built using substantive CD steps
```

A schematic theorem is especially useful if it can be instantiated to produce a closed candidate closer to the target or a region.

## Random immigrants and mutation

Increasing mutation alone is not enough. The logs show that the system already explores, but then collapses into compact attractors.

Still, add explicit diversity pressure:

```text
- random immigrants every generation
- occasional high-mutation children
- subtree replacement using target-seeded formulas
- mutation that instantiates metas with target/region subformulas
- mutation that closes schematic formulas by replacing metas with atoms/subformulas
```

A useful mutation operator:

```text
instantiate_meta_from_pool:
  choose a Meta variable in a proof/formula
  replace it with a formula from the target/region formula pool
```

This helps turn schematic candidates into closed target attempts.

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
```

Do not let the schema archive replace closed target search. It is supporting material.

## Important invariant for final theorem search

The input theorem is closed. Therefore the final accepted proof must have a closed conclusion exactly equal to the core target.

A candidate with metas in the conclusion is not a final proof.

```text
valid schematic theorem ≠ valid closed proof of the input theorem
```

## Recommended next implementation task

Implement quality-diversity selection and closed/schematic separation.

Suggested Codex task:

```text
Read AGENTS.md and docs/SPEC.md.

The current search repeatedly plateaus on compact valid proof artifacts. Stop adding one-off formula-shape penalties. Implement a quality-diversity selection layer.

Add:
- metas(formula)
- is_closed_formula(formula)
- behavior_descriptor(proof, conclusion)
- novelty_score based on behavior descriptors
- separate ranking for closed target elites, closed region elites, novelty elites, schematic lemma elites, and random immigrants
- schema archive for valid schematic candidates
- optional instantiation of schematic conclusions against target/region formulas

Only closed candidates may receive target or region elite status unless a schematic candidate can be instantiated into a closed target/region candidate.

Do not remove Ax1, Ax2, Ax3, or CD.
Do not add natural-deduction rules.
Do not add Lean integration.
Do not add more one-off bad-shape penalties.

The goal is to prevent population collapse and preserve diverse proof-search behavior.
```

## Expected diagnostic improvement

After this update, diagnostics should report more than one elite family.

Add diagnostic fields:

```text
closed_fraction
schematic_fraction
target_elite_best
region_elite_best
novelty_elite_best
schema_elite_best
unique_behavior_count
behavior_archive_size
random_immigrant_count
```

A healthy run should not show the same best conclusion occupying the entire search for hundreds of generations unless it is an exact target or region proof.

## Summary

The current issue is not just insufficient mutation. It is selection collapse.

The fix is to move from:

```text
one scalar fitness score for everything
```

to:

```text
quality-diversity selection with closed/schematic separation
```

This should reduce the need for repeated ad hoc fitness patches while preserving legitimate Hilbert-system lemmas discovered by the search.
