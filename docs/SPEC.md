# birdrat-proplogic v0.1 Specification

## 1. Project purpose

`birdrat-proplogic` is a prototype genetic-programming theorem prover for classical propositional logic.

The initial domain is Łukasiewicz-style propositional logic using the three `P₂` axiom schemata and condensed detachment as the internal inference representation. The long-term goal is to prototype a general Lean-facing theorem generator whose search space is restricted to an explicitly chosen subset of valid Lean moves.

The prototype should evolve symbolic proof candidates, evaluate them internally, and eventually render successful candidates into Lean terms that Lean can verify.

The project should **not** begin as a general Lean tactic prover. It should not use automation such as `simp`, `tauto`, `aesop`, `omega`, or any Lean tactic that bypasses the explicitly restricted proof system.

---

## 2. Logical system

The initial proof system is based on the following Hilbert-style axiom schemata:

```text
P2_1: p → (q → p)

P2_2: (p → (q → r)) → ((p → q) → (p → r))

P2_3: (¬p → ¬q) → (q → p)
```

The intended primitive proof moves are:

```text
1. instantiate P2_1, P2_2, or P2_3
2. apply condensed detachment
3. eventually render condensed detachment as substitution + modus ponens in Lean
```

Internally, condensed detachment should be the primary inference node. This keeps the proof search closer to the automated-reasoning literature on Hilbert systems while still allowing later Lean verification.

---

## 3. Formula languages

The system should distinguish between a user-facing surface language and a proof-search core language.

### 3.1 Surface formula language

Surface formulas are what users write and what reports should display.

```python
SurfaceFormula =
    SAtom(name)
  | SNot(A)
  | SImp(A, B)
  | SAnd(A, B)
  | SOr(A, B)
  | SIff(A, B)
```

Example user-facing formula:

```text
a ∧ b → b ∧ a
```

This should parse as something equivalent to:

```python
SImp(
    SAnd(SAtom("a"), SAtom("b")),
    SAnd(SAtom("b"), SAtom("a")),
)
```

### 3.2 Core formula language

The proof engine should initially use only implication and negation.

```python
Formula =
    Atom(name)
  | Meta(name)
  | Not(A)
  | Imp(A, B)
```

`Atom(name)` represents a fixed propositional variable from the user-facing theorem, such as `a`, `b`, or `c`.

`Meta(name)` represents a schematic variable used in axiom instances and unification. No `Meta` variable should remain in a final closed theorem presented as a successful proof.

### 3.3 Desugaring

Surface connectives should be desugared into the core language before proof search.

Use these classical translations:

```text
A ∨ B    := ¬A → B

A ∧ B    := ¬(A → ¬B)

A ↔ B    := (A → B) ∧ (B → A)
```

Since conjunction is itself desugared:

```text
A ↔ B := ¬((A → B) → ¬(B → A))
```

if fully expanded into only `→` and `¬`.

Example:

```text
a ∧ b → b ∧ a
```

desugars to:

```text
¬(a → ¬b) → ¬(b → ¬a)
```

The system should retain the original surface formula for reporting, goal decomposition, and user-facing output.

---

## 4. Proof genome

The genome is a symbolic Hilbert derivation tree.

It is not:

```text
- Lean's internal AST
- a Lean tactic script
- a natural-deduction proof
```

It is a restricted proof tree built from P₂ axiom instances and condensed detachment.

```python
Proof =
    Ax1(p, q)
  | Ax2(p, q, r)
  | Ax3(p, q)
  | CD(major, minor)
```

where `p`, `q`, and `r` are core formulas.

### 4.1 Axiom nodes

The axiom nodes represent instantiated axiom schemata.

```python
Ax1(p, q)
```

has conclusion:

```text
p → (q → p)
```

```python
Ax2(p, q, r)
```

has conclusion:

```text
(p → (q → r)) → ((p → q) → (p → r))
```

```python
Ax3(p, q)
```

has conclusion:

```text
(¬p → ¬q) → (q → p)
```

### 4.2 Condensed detachment node

A condensed detachment node contains proof subtrees, not merely formulas.

```python
CD(major, minor)
```

Let:

```python
major_conclusion = conclusion(major)
minor_conclusion = conclusion(minor)
```

If:

```text
major_conclusion = A → B
```

and `A` unifies with `minor_conclusion` under most-general unifier `σ`, then:

```text
conclusion(CD(major, minor)) = σ(B)
```

Otherwise the CD node is invalid.

The distinction between `major` and `minor` matters:

```text
major: proof of something implication-shaped
minor: proof of something that unifies with the antecedent
```

Example:

```text
major conclusion: p → (q → p)
minor conclusion: a
```

The antecedent `p` unifies with `a`, so the CD conclusion is:

```text
q → a
```

after applying the substitution `p ↦ a`.

### 4.3 Nested proof trees

Proofs achieve arbitrary depth by nesting CD applications.

Example shape:

```text
CD
├── major: CD
│   ├── major: Ax2(...)
│   └── minor: Ax1(...)
└── minor: CD
    ├── major: Ax3(...)
    └── minor: Ax1(...)
```

Each node has a derived conclusion. The root conclusion is the theorem proved by the candidate.

Start with proof trees because they are easy to mutate and crossover. Later, add DAG compression to share repeated subproofs.

---

## 5. Validity and conclusion checking

The internal checker should compute:

```python
conclusion(proof) -> Formula | Invalid
```

A proof is internally valid if:

```text
- every axiom node has a well-formed instantiated conclusion
- every CD node has a major proof whose conclusion is implication-shaped
- every CD node's antecedent unifies with the minor proof's conclusion
```

Invalid candidates should not crash the system. They should return a structured invalid result and receive a fitness penalty.

Lean should eventually be used as the final verifier, but the internal checker should be the cheap first-pass evaluator.

---

## 6. Unification

Implement first-order-style unification over core formula trees.

Unification must support:

```text
Atom(name)
Meta(name)
Not(A)
Imp(A, B)
```

Requirements:

```text
- compute a most-general unifier where possible
- include an occurs check
- distinguish fixed atoms from schematic metavariables
- fail cleanly on incompatible structures
```

Examples:

```text
unify(Meta("?p"), Atom("a")) succeeds with {?p ↦ a}

unify(Imp(Meta("?p"), Meta("?q")), Imp(Atom("a"), Not(Atom("b"))))
succeeds with {?p ↦ a, ?q ↦ ¬b}

unify(Atom("a"), Atom("b")) fails if a ≠ b

unify(Meta("?p"), Imp(Atom("a"), Meta("?p"))) fails by occurs check
```

---

## 7. Metrics

Track proof and formula metrics separately.

### 7.1 CD step count

```python
cd_steps(proof)
```

The total number of `CD` nodes in the proof tree.

### 7.2 CD depth

```python
cd_depth(proof)
```

The maximum nested CD depth.

Definitions:

```text
cd_depth(Ax1(...)) = 0
cd_depth(Ax2(...)) = 0
cd_depth(Ax3(...)) = 0

cd_depth(CD(major, minor)) =
    1 + max(cd_depth(major), cd_depth(minor))
```

### 7.3 Proof size

```python
proof_size(proof)
```

The total number of proof nodes.

### 7.4 Formula size

```python
formula_size(formula)
```

The total number of nodes in a formula tree.

Example:

```text
formula_size(a) = 1
formula_size(¬a) = 2
formula_size(a → b) = 3
```

Track formula sizes in axiom instantiations and conclusions to discourage explosive formula growth.

---

## 8. Goal and region extraction

The system should not hardcode theorem-specific subgoals.

Instead, it should derive structurally meaningful goals from the surface formula using generic logical decomposition rules.

A good module name is either:

```text
goals.py
```

or:

```text
regions.py
```

The central datatype should be a sequent-like goal:

```python
@dataclass(frozen=True)
class Goal:
    context: tuple[SurfaceFormula, ...]
    target: SurfaceFormula
    name: str
    weight: float
```

A goal:

```text
Γ ⊢ T
```

corresponds to the theorem:

```text
H₁ → H₂ → ... → T
```

where `Γ = [H₁, H₂, ...]`.

### 8.1 Implication decomposition

For:

```text
Γ ⊢ A → B
```

generate at least:

```text
Γ, A ⊢ B
Γ ⊢ A → B
```

### 8.2 Conjunction target decomposition

For:

```text
Γ ⊢ A ∧ B
```

generate:

```text
Γ ⊢ A
Γ ⊢ B
Γ ⊢ A ∧ B
```

### 8.3 Biconditional target decomposition

For:

```text
Γ ⊢ A ↔ B
```

generate:

```text
Γ ⊢ A → B
Γ ⊢ B → A
Γ ⊢ A ↔ B
```

This lets a candidate proving one direction of an iff receive meaningful fitness.

### 8.4 Conjunction in context

For:

```text
Γ, A ∧ B ⊢ C
```

generate useful regions such as:

```text
Γ, A ∧ B ⊢ A
Γ, A ∧ B ⊢ B
Γ, A, B ⊢ C
Γ, A ∧ B ⊢ C
```

### 8.5 Disjunction in context

For:

```text
Γ, A ∨ B ⊢ C
```

generate case-analysis style regions such as:

```text
Γ, A ⊢ C
Γ, B ⊢ C
Γ, A ∨ B ⊢ C
```

This is a structural guide for fitness. It does not mean the proof engine has primitive natural-deduction rules.

### 8.6 Example: conjunction commutativity

Input:

```text
a ∧ b → b ∧ a
```

The system should extract regions including:

```text
whole:       a ∧ b → b ∧ a
projection: a ∧ b → b
projection: a ∧ b → a
```

Each region should be independently desugared into a core target formula.

### 8.7 Example: biconditional

Input:

```text
A ↔ B
```

The system should extract regions including:

```text
whole:     A ↔ B
forward:   A → B
backward:  B → A
```

Again, these are generated from connective structure, not hardcoded for a particular theorem.

---

## 9. Proof archive

Maintain a passive proof archive:

```python
archive: dict[Formula, list[Proof]]
```

Whenever a candidate exactly proves a generated region, store it.

For example, if the target is:

```text
A ↔ B
```

and a candidate proves:

```text
A → B
```

then store that proof under the core formula for `A → B`.

In v0.1, the archive should be passive:

```text
- it records useful partial proofs
- it does not generate new targets
- it does not attempt automatic lemma synthesis
```

Later versions may use the archive actively to combine region proofs.

---

## 10. Fitness function

Fitness should reward:

```text
1. exact proof of the full target
2. exact proof of a structurally generated region
3. symbolic similarity to the target or a region
4. shorter proofs
5. shallower proofs, subject to adaptive thresholding
6. smaller formulas
7. internal validity
```

A first scalar fitness function:

```text
F(P)
=
TARGET_MATCH * 1[conclusion(P) = target]
+
REGION_MATCH * max_i 1[conclusion(P) = region_i]
+
SIMILARITY_SCALE * max_i similarity(conclusion(P), region_i)
-
CD_STEP_PENALTY * cd_steps(P)
-
PROOF_NODE_PENALTY * proof_size(P)
-
FORMULA_SIZE_PENALTY * total_formula_size(P)
-
DEPTH_PENALTY(P)
-
INVALID_PENALTY(P)
```

Suggested initial constants:

```python
TARGET_MATCH = 1_000_000
REGION_MATCH = 50_000
SIMILARITY_SCALE = 1_000

CD_STEP_PENALTY = 5
PROOF_NODE_PENALTY = 1
FORMULA_SIZE_PENALTY = 0.1
INVALID_PENALTY = 100_000
```

The exact constants are not mathematically important. They should be configurable.

### 10.1 Fitness after exact success

Once a candidate exactly proves the full target, switch the objective toward minimization:

```text
fitness =
    HUGE_CONSTANT
  - α * cd_steps
  - β * proof_size
  - γ * lean_term_size
  - δ * total_formula_size
```

This implements the intended pressure:

```text
shorter correct proof > longer correct proof
```

Correctness should dominate length. Length matters most once correctness has been achieved.

---

## 11. Symbolic similarity

The similarity function should compare a candidate conclusion against the full target and all generated regions.

Start simple. A formula similarity score should reward:

```text
- exact equality
- same root connective
- same implication skeleton
- same negation skeleton
- shared atoms
- subformula overlap
- successful unification
```

Example:

```text
A → B
```

should be closer to:

```text
A → C
```

than to:

```text
¬(A → C)
```

The region score should use:

```python
best_region_similarity = max(
    similarity(candidate_conclusion, region.core_formula)
    for region in regions
)
```

This allows useful partial proofs to survive selection.

Examples of useful partial proofs:

```text
- one direction of an iff
- one projection needed for a conjunction target
- an implication with the correct antecedent but incomplete consequent
- a formula whose structure unifies with a generated region
```

---

## 12. Adaptive CD-depth control

Proofs should be allowed arbitrary depth in principle, but the search should be controlled.

Maintain a soft active CD-depth threshold:

```python
D = current_active_cd_depth
```

Candidates with:

```python
cd_depth(proof) <= D
```

receive no depth penalty.

Candidates above `D` are legal but penalized.

Use a sigmoid-like penalty:

```python
def depth_penalty(depth: int, threshold: int, lam: float = 100.0, k: float = 1.5) -> float:
    excess = max(0, depth - threshold)
    if excess == 0:
        return 0.0
    return lam * (2.0 / (1.0 + exp(-k * excess)) - 1.0)
```

Behavior:

```text
depth ≤ D       no penalty
depth D+1       mild penalty
depth D+3       strong penalty
far above D     penalty approaches λ
```

Threshold update rule:

```text
After N trials, increase D by 1.

If a valid useful proof is found above D, raise D slightly.
```

Use a jump cap:

```python
D = max(D, min(found_depth, D + 2))
```

This avoids letting one bloated valid proof immediately move the entire population into a much larger search regime.

---

## 13. Mutation operators

Initial proof mutations:

```text
- replace an axiom node with Ax1/Ax2/Ax3
- mutate a formula argument inside an axiom node
- replace a subtree with a random shallow proof tree
- wrap an existing proof in a new CD node
- replace one child of a CD node
- swap major/minor children of CD
```

Swapping major and minor will often produce invalid candidates, but invalid candidates may still be useful for exploration if the penalty is not absolute.

Initial formula mutations:

```text
Atom(a) → Atom(b)
A → B  → A' → B
A → B  → A → B'
¬A     → ¬A'
A      → ¬A
A      → A → B
A      → B → A
```

Generation should limit formula size to avoid immediate explosion, but the system should not impose a permanent maximum proof depth.

---

## 14. Crossover operators

Use subtree crossover.

```text
proof1 subtree ↔ proof2 subtree
```

Prefer crossover between nodes of the same broad kind:

```text
- axiom node with axiom node
- CD node with CD node
- formula subtree with formula subtree
```

This improves the chance that offspring remain meaningful.

---

## 15. Selection

Use tournament selection with elitism.

Preserve:

```text
- best exact target proof
- best proof for each generated region
- best high-similarity candidates
- some structurally diverse candidates
```

Basic evolutionary loop:

```python
population = initialize()

for generation in range(max_generations):
    scored = [(fitness(p), p) for p in population]

    update_archive(scored)
    update_depth_threshold(scored)

    elites = keep_top(scored, k=elite_count)
    children = []

    while len(children) < population_size - elite_count:
        parent1 = tournament(scored)
        parent2 = tournament(scored)

        child = crossover(parent1, parent2)
        child = mutate(child)

        children.append(child)

    population = elites + children
```

The first implementation should not try to optimize this loop. It should favor clarity, inspectability, and testability.

---

## 16. Lean rendering

Lean integration is not required for the first internal-checker milestone.

Eventually, Lean should be used as a final verifier.

The Lean environment should expose only the allowed P₂ axioms:

```lean
axiom P2_1 : ∀ p q : Prop, p → q → p

axiom P2_2 :
  ∀ p q r : Prop,
    (p → q → r) → (p → q) → p → r

axiom P2_3 :
  ∀ p q : Prop,
    (¬p → ¬q) → q → p
```

Each axiom node renders as an instantiation:

```lean
P2_1 A B
P2_2 A B C
P2_3 A B
```

Each CD node should render as function application after the necessary instantiations have been computed.

Internally:

```text
CD(major, minor)
```

externally becomes something like:

```lean
(major_term) (minor_term)
```

provided the major term has the appropriate implication type.

The rendered theorem for surface input:

```text
a ∧ b → b ∧ a
```

may initially use the core-desugared formula:

```lean
theorem generated (a b : Prop) :
    ¬ (a → ¬ b) → ¬ (b → ¬ a) :=
  <generated proof term>
```

A later version may provide custom surface connectives or Lean-level definitions for `myAnd`, `myOr`, and `myIff`.

---

## 17. Suggested module layout

```text
src/birdrat_proplogic/
├── formula.py
├── surface.py
├── proof.py
├── unify.py
├── goals.py
├── fitness.py
├── mutate.py
├── crossover.py
├── archive.py
├── render_lean.py
├── lean_eval.py
└── run.py
```

### 17.1 `formula.py`

Core formula dataclasses:

```text
Atom
Meta
Not
Imp
```

Utilities:

```text
formula_size
pretty-printing
normalization
atoms
metas
subformulas
```

### 17.2 `surface.py`

Surface formula dataclasses:

```text
SAtom
SNot
SImp
SAnd
SOr
SIff
```

Utilities:

```text
desugar_to_core
surface pretty-printing
optional parser
```

### 17.3 `unify.py`

Unification functions:

```text
mgu
occurs_check
apply_subst
compose_subst
```

### 17.4 `proof.py`

Proof dataclasses:

```text
Ax1
Ax2
Ax3
CD
```

Utilities:

```text
conclusion
is_valid
cd_steps
cd_depth
proof_size
```

### 17.5 `goals.py`

Goal extraction:

```text
Goal
extract_regions
goal_to_surface_theorem
goal_to_core_theorem
```

### 17.6 `fitness.py`

Fitness and similarity:

```text
formula_similarity
depth_penalty
region_score
total_fitness
```

### 17.7 `mutate.py`

Proof and formula mutation.

### 17.8 `crossover.py`

Subtree crossover.

### 17.9 `archive.py`

Region proof archive.

### 17.10 `render_lean.py`

Restricted Lean proof rendering.

### 17.11 `lean_eval.py`

Lean subprocess integration.

### 17.12 `run.py`

Evolutionary loop and CLI entry point.

---

## 18. Testing expectations

Use `pytest`.

At minimum, tests should cover:

```text
- formula equality
- formula pretty-printing
- formula_size
- desugaring of And
- desugaring of Or
- desugaring of Iff
- successful unification
- failed unification
- occurs-check failure
- P2 axiom conclusions
- valid CD
- invalid CD where major is not implication-shaped
- invalid CD where antecedent does not unify with minor
- cd_steps
- cd_depth
- proof_size
- region extraction for a ∧ b → b ∧ a
- region extraction for A ↔ B
- conversion of Goal(context, target) back into theorem form
```

The first implementation milestone should not require Lean to be installed.

---

## 19. MVP demonstration

The first meaningful demo target is:

```text
a ∧ b → b ∧ a
```

The system should report:

```text
surface target:
  a ∧ b → b ∧ a

core target:
  ¬(a → ¬b) → ¬(b → ¬a)

generated regions:
  a ∧ b → b ∧ a
  a ∧ b → b
  a ∧ b → a

best exact proof:
  found / not found

best region proofs:
  a ∧ b → a : found / not found
  a ∧ b → b : found / not found

best candidate:
  conclusion
  fitness
  cd_steps
  cd_depth
  proof_size
```

For v0.1, a successful internal checker plus region extraction is enough. Genetic search and Lean rendering should be added only after the internal checker is stable.

---

## 20. First implementation milestone

The first Codex task should be narrow:

```text
Implement the internal checker.
Do not implement GP.
Do not implement Lean integration.
```

Specifically, implement:

```text
formula.py
surface.py
unify.py
proof.py
goals.py
```

with tests for all core functionality.

The goal is to obtain a clean, typed, testable base on which mutation, fitness, archive behavior, and Lean rendering can later be built.

---

## 21. Non-goals for v0.1

Do not implement:

```text
- full Lean integration
- Mathlib integration
- native Lean AST parsing
- natural-deduction tactics
- proof-minimization databases
- active lemma synthesis from the archive
- general theorem discovery outside propositional logic
- automated Lean tactics
```

The point of v0.1 is to build a simple, inspectable restricted proof-search substrate.
