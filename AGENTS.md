# AGENTS.md — birdrat-proplogic: Reporting, Runtime Analysis, and Next Benchmark Stage

## Project purpose

`birdrat-proplogic` is a prototype proof-search system for classical propositional logic.

The project searches for Hilbert-style proofs over the Łukasiewicz/Church `P₂` axiom schemata using condensed detachment (`CD`) as the internal inference rule. The long-term goal is to build a Lean-facing theorem generator whose proof search is restricted to an explicitly chosen set of valid logical moves.

Lean integration is a future milestone, but **not the next milestone**.

Do not add Lean integration yet. Do not add Mathlib integration yet. Do not use Lean automation to solve the current proof-search problem. The current priority is:

```text
1. stabilize the current P₂ + CD proof-search core,
2. improve user-facing reporting,
3. archive full diagnostic reports,
4. add runtime/profiling instrumentation,
5. freeze the current benchmark suite as regression coverage,
6. then add a slightly expanded benchmark suite.
```

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

# Current milestone

## Current success state

The current small target-only benchmark suite is passing.

Baseline targets:

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

These should now be treated as regression benchmarks.

Expected behavior:

```text
identity:
  must pass

syllogism:
  must pass

classical-negation:
  must pass

contraction:
  must pass

distribution/application:
  must pass
```

The tests should require exact proof discovery, not merely high target similarity.

Use loose upper bounds for proof metrics to avoid failing on harmless proof variation. For example:

```text
exact proof found: required
CD steps: bounded but generous
CD depth: bounded but generous
proof size: bounded but generous
runtime: reported, not initially enforced
```

---

# Immediate next goal: reporting and runtime analysis

The next implementation priority is not a new proof-search heuristic. The next implementation priority is to make the tool easier to read and easier to analyze.

The user-facing output should say **less and more**:

```text
less:
  less raw diagnostic noise printed to the terminal

more:
  clearer progress updates while running
  clearer final summary
  full detailed reports archived to files
  runtime/profiling information preserved for analysis
```

Both the regular `run` command and the benchmark command should follow this policy.

---

# User-facing reporting design

## Terminal output should be concise

The terminal should not dump full beam-layer diagnostics by default.

During a run, print compact progress updates at a configurable interval, defaulting to every 10 generations.

Suggested default:

```text
--progress-interval 10
```

For very short benchmark runs with fewer than 10 generations, print at least generation 0 and the final generation.

## Regular run progress output

For:

```bash
PYTHONPATH=src python -m birdrat_proplogic.run 'target'
```

print something like:

```text
target: (p → q) → (p → q → r) → p → r
phase: strict-preselected
gen 0:  best=742.1  sim=0.61  exact=0  valid=0.97  closed=0.62  beam=4930  time=4.2s
gen 10: best=901.4  sim=0.72  exact=0  valid=1.00  closed=0.70  beam=4930  time=12.9s
gen 20: FOUND exact proof  cd=6  depth=4  size=13  time=18.4s
```

Keep each progress line short.

Suggested fields:

```text
generation
phase name
best score
best target similarity
exact target count
valid fraction
closed fraction
beam valid products or beam pool size
elapsed time
```

Do not include by default:

```text
full proof tree
full best schematic candidate
full novelty candidate
full beam layer counts
full suffix diagnostics
full schema-instantiation diagnostics
axiom-family telemetry
```

Those belong in the archived full report.

## Benchmark progress output

For:

```bash
PYTHONPATH=src python -m birdrat_proplogic.run_benchmarks --small-targets
```

print a compact per-target status.

Example:

```text
[1/5] identity
  strict-preselected: FOUND cd=2 depth=2 size=5 time=0.7s

[2/5] syllogism
  strict-preselected: FOUND cd=3 depth=3 size=7 time=20.1s

[3/5] classical-negation
  strict-preselected: FOUND cd=3 depth=3 size=7 time=15.4s

[4/5] contraction
  strict-preselected: FOUND cd=3 depth=2 size=7 time=34.0s

[5/5] distribution/application
  strict-preselected: FOUND cd=6 depth=4 size=13 time=79.5s
```

At the end, print a compact table:

```text
summary
name                      found  phase               cd  depth  size  runtime
identity                  yes    strict-preselected  2   2      5     0.7s
syllogism                 yes    strict-preselected  3   3      7     20.1s
classical-negation         yes    strict-preselected  3   3      7     15.4s
contraction               yes    strict-preselected  3   2      7     34.0s
distribution/application   yes    strict-preselected  6   4      13    79.5s

full report: reports/benchmarks/small-targets-YYYYMMDD-HHMMSS.json
```

If a benchmark fails:

```text
distribution/application   no     none                -   -      -     120.0s
  best closed: ...
  best similarity: 0.74
  full report: ...
```

Keep the terminal failure detail short.

---

# Full report archival

## Full reports should be archived automatically

By default, both `run` and `run_benchmarks` should save a full report to disk.

Suggested default output directories:

```text
reports/runs/
reports/benchmarks/
```

Suggested filenames:

```text
reports/runs/run-YYYYMMDD-HHMMSS.json
reports/benchmarks/small-targets-YYYYMMDD-HHMMSS.json
```

Optionally also support Markdown reports:

```text
reports/runs/run-YYYYMMDD-HHMMSS.md
reports/benchmarks/small-targets-YYYYMMDD-HHMMSS.md
```

Add CLI options:

```text
--report-dir PATH
--no-report
--report-format json
--report-format md
--report-format both
```

Default:

```text
--report-format json
```

or, if easy:

```text
--report-format both
```

## Full report contents

The archived full report should include everything needed to analyze the run.

For a regular run:

```text
target surface formula
core target formula
generated regions
configuration
random seed
phases attempted
phase reports
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

For benchmarks:

```text
benchmark suite name
per-target configurations
per-target result summaries
per-target phase reports
per-target proof metrics
per-target runtime profile
overall summary table
```

## Store found proofs

When an exact proof is found, the report should store:

```text
surface target
core target
conclusion
proof tree
expanded numbered proof
CD steps
CD depth
proof size
formula size
phase found
seed/config
```

Do not feed archived proofs back into future searches unless explicitly requested. Reports are for inspection and regression analysis, not proof seeding.

---

# Runtime analysis

## Motivation

The benchmark suite now passes, but runtime varies substantially between targets. Before expanding the benchmark suite, add runtime analysis and profiling instrumentation.

The goal is to understand where time is going:

```text
unification
conclusion recomputation
formula similarity
schema instantiation
proof substitution
candidate deduplication
beam pair generation
beam candidate ranking
fitness scoring
quality-diverse selection
```

## Add a runtime profiler

Implement a lightweight internal profiler.

Suggested API:

```python
class RuntimeProfiler:
    def start(section: str) -> None: ...
    def stop(section: str) -> None: ...
    def time_block(section: str): ...
    def increment(counter: str, amount: int = 1) -> None: ...
    def snapshot() -> RuntimeProfile: ...
```

or use a simple context manager:

```python
with profiler.section("beam.pair_generation"):
    ...
```

Do not over-engineer.

## Sections to time

At minimum, time:

```text
total
parse_surface
generate_regions
formula_pool_construction
beam.total
beam.seed_generation
beam.pair_generation
beam.try_cd
beam.retention
beam.suffix_retention
beam.schema_instantiation
evolution.total
evolution.scoring
evolution.selection
evolution.mutation
quality.novelty
fitness.total
unify.total
conclusion.total
formula_similarity.total
report_writing
```

## Counters to track

At minimum, count:

```text
unify.calls
unify.successes
unify.failures

conclusion.calls

formula_similarity.calls

try_cd.calls
try_cd.valid
try_cd.invalid

beam.pairs_considered
beam.pairs_attempted
beam.valid_products
beam.closed_products
beam.schematic_products

schema_instantiation.attempts
schema_instantiation.valid
schema_instantiation.closed
schema_instantiation.exact_target
schema_instantiation.exact_region
schema_instantiation.exact_suffix

dedup.input_count
dedup.output_count

fitness.calls
```

## Runtime report output

Terminal output should include only a compact runtime summary, for example:

```text
runtime summary:
  total: 79.5s
  beam: 72.1s
  schema instantiation: 18.4s
  unification: 25.7s
  fitness: 8.3s
  report: 0.2s
```

The archived full report should include the complete profile.

## Optional detailed profile command

Add:

```text
--profile
```

Behavior:

```text
- include compact runtime summary in terminal
- save full runtime profile in report
```

If profiling overhead is small, it may be enabled by default for benchmarks.

---

# Caching and performance follow-up

After runtime instrumentation is in place, use the profile to decide what to cache or optimize.

Likely candidates:

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

Do not blindly cache everything before profiling. Add instrumentation first, inspect the data, then optimize.

Possible cache implementation:

```python
functools.lru_cache
```

works best when formulas/proofs are immutable and hashable.

If proof objects are large, consider caching by object identity or canonical structural key.

---

# Proof minimization: next after profiling, not now

Proof minimization is desirable but should wait until reporting and runtime analysis are stable.

Future proof-minimization ideas:

```text
given exact proof P:
  verify P
  canonicalize metavariable names
  deduplicate identical subproofs/conclusions
  try greedy subtree replacement from archive
  rerun bounded search for the same conclusion with smaller size
  reverify minimized proof
```

Do not implement proof minimization in this reporting/profiling milestone unless explicitly requested.

---

# Slightly expanded benchmark suite: next after runtime analysis

After reporting and runtime profiling are in place, add a slightly expanded benchmark suite.

Do not jump directly to encoded conjunction as the only next target.

Suggested next tier:

```text
double-negation introduction:
  p → ¬¬p

contraposition-like:
  (p → q) → ¬q → ¬p

permutation:
  (p → q → r) → q → p → r

composition:
  (q → r) → (p → q) → p → r
```

Then return to encoded connective targets:

```text
encoded left projection:
  p ∧ q → p
  core: ¬(p → ¬q) → p

encoded right projection:
  p ∧ q → q
  core: ¬(p → ¬q) → q

encoded conjunction commutativity:
  p ∧ q → q ∧ p
  core: ¬(p → ¬q) → ¬(q → ¬p)
```

Add these as target-only benchmarks. Do not hardcode proofs.

---

# Regular run and benchmark run should share reporting infrastructure

Avoid duplicating reporting logic.

Implement shared data structures where possible:

```python
RunSummary
BenchmarkSummary
PhaseReport
ProgressSnapshot
RuntimeProfile
ProofReport
```

Both commands should use the same report writer.

Suggested modules:

```text
reporting.py
profiling.py
```

or similar.

---

# CLI changes

Suggested additions:

```text
--progress-interval N
--report-dir PATH
--report-format json|md|both
--no-report
--profile
--quiet
--verbose
```

Default behavior:

```text
progress interval: 10 generations
report: enabled
report format: json
profile: enabled for benchmarks, optional for single runs
quiet: false
verbose: false
```

`--verbose` may print more diagnostic detail to terminal, but the default should remain concise.

`--quiet` should print only final summary and report path.

---

# Regression expectations

After this milestone:

```text
run_benchmarks --small-targets
```

should:

```text
- solve all five current targets,
- print compact per-target progress,
- print a compact final summary table,
- write a full report to disk,
- include runtime profile data in the report.
```

The current passing suite should not regress.

Expected baseline:

```text
identity: found
syllogism: found
classical-negation: found
contraction: found
distribution/application: found
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
more one-off bad-shape penalties
axiom-family selection bonuses
target-specific axiom preferences
proof minimization
expanded benchmark suite before reporting/profiling is stable
```

Lean integration is an upcoming milestone after:

```text
1. current benchmark suite is stable,
2. reporting is usable,
3. runtime analysis is available,
4. a slightly expanded suite has been attempted.
```

---

## Summary

Current status:

```text
The tool now passes the five-target P₂ + CD benchmark suite.
```

Immediate next milestone:

```text
concise progress output
+ compact final summaries
+ archived full reports
+ runtime profiling
```

Then:

```text
slightly expanded benchmark suite
```

Then later:

```text
Lean integration
```
