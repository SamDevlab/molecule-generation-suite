# Biolab — Autonomous Scientific Discovery Roadmap

Mission:

> Build a scientific system capable of turning human objectives into bounded hypotheses, executing scalable computational investigation, recognizing when computation has reached its evidence ceiling, obtaining real physical measurements, incorporating those measurements as auditable scientific evidence, and using them to decide what hypothesis should be tested next.

## Phase destination

Research OS is the evidence, provenance, gate, lineage, reproducibility, stop
condition, and scientific-state layer. Biolab turns a scientific objective
into bounded questions and proposes the next action. OmniHub is a future
operational control plane. Sam / Central retains human objective, budget,
constraints, and approval authority. Workers execute registered work; they do
not become evidence or claim authorities.

The active transition is:

```text
MOLDISC-018 / E2 computational state
        ↓
Biolab next-action assessment
        ↓
BIOEXP-001 physical solubility package
        ↓
external measurement
        ↓
E4 ingestion and state reassessment
```

The anti-loop rule is `DO_NOT_SCALE_AN_OPEN_LOOP`: when the next decision
requires a higher evidence class, the default is to stop and obtain that
class, not to run an infinite sequence of same-level explanations.

## Formal project phases

| Phase | Name | Status |
|---|---|---|
| PHASE_0 | Research OS foundation | STABLE |
| PHASE_1 | Computational Molecular Discovery / MOLDISC-001–018 | CLOSED_ENOUGH_TO_TRANSITION |
| PHASE_2 | Biolab Experimental Bridge | ACTIVE |
| PHASE_3 | Experiment-Informed Molecular Discovery | BLOCKED_ON_FIRST_NEW_E4 |
| PHASE_4 | Autonomous Scientific Iteration | FUTURE |
| PHASE_5 | S3-Accelerated High-Throughput Discovery | FUTURE_AFTER_CLOSED_LOOP_WORKS |

## Stages

1. Research OS foundation.
2. Computational discovery.
3. First physical feedback.
4. Experiment-informed generation.
5. Repeated closed-loop discovery.
6. Worker orchestration.
7. S3 high-throughput kernels.
8. Large-scale autonomous hypothesis search.

MOLDISC-019 implements only the first bounded transition into Stage 3.
MOLDISC-020, if opened after real physical feedback, must be
`FIRST_EXPERIMENT_INFORMED_DISCOVERY`, not another default docking iteration.

## Future operating model

Future workers may include planner, source, compute, software/Codex,
experimental-coordination, and evidence-ingestion workers. They are
documented as roles, not implemented as a universal autonomous scientist.
The project should prove one closed physical loop before parallelizing worker
orchestration or scaling to millions of hypotheses.

## Strategic metric

The important optimization target is not maximum compute throughput. It is
increasing useful scientific information obtained per unit of human time,
money, compute, and experimental budget.

> The goal of Biolab is not to produce the largest number of computational outputs. Its purpose is to increase the amount of reliable scientific knowledge one person can create with finite time, money and compute. Computation is valuable while it changes a decision. When the next decision requires reality, the system must know how to stop computing, ask reality, learn from the result and continue.
