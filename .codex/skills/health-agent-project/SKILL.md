---
name: health-agent-project
description: Plan, architect, implement, review, and evolve this repository from a posture-analysis MVP into a personal health coaching Agent. Use for product roadmaps, architecture decisions, feature specifications, data models, training and nutrition recommendation systems, Agent orchestration, health-safety and privacy controls, implementation plans, feature delivery, debugging, code review, and release verification in this project.
---

# Health Agent Project

Build this project as a trustworthy personal health coach for generally healthy users, not as an autonomous medical diagnosis or treatment system.

Borrow the useful discipline from Superpowers: inspect first, design before expensive changes, split work into testable increments, investigate root causes, review against the specification, and verify before claiming completion. Adapt the process to the task's risk instead of applying ceremony uniformly.

## Load Context Selectively

Read only the references needed for the current task:

- Read [project-context.md](references/project-context.md) before roadmap, architecture, module-boundary, or cross-stack work.
- Read [health-ai-safety.md](references/health-ai-safety.md) before changing profile collection, posture analysis, training recommendations, nutrition recommendations, prompts, Agent tools, health records, consent, or privacy behavior.
- Read [delivery-workflow.md](references/delivery-workflow.md) before writing a specification, ADR, implementation plan, milestone, or roadmap.
- Read [testing-and-evaluation.md](references/testing-and-evaluation.md) before implementing recommendation logic, safety rules, LLM behavior, migrations, or release-critical flows.

## Start With Repository Truth

Before making decisions:

1. Inspect `git status`, relevant diffs, recent commits, source files, tests, and current documentation.
2. Treat running code, schemas, tests, and migrations as stronger evidence than status documents.
3. Treat old plans as historical intent, not proof of current behavior.
4. Preserve unrelated user changes in a dirty worktree.
5. Follow existing Flutter, Riverpod, FastAPI, SQLAlchemy, and testing patterns unless a documented architectural reason requires a change.
6. Verify unstable technical, medical, nutrition, legal, privacy, or platform facts against current primary sources.

Do not repeat broad repository discovery once enough current context is available.

## Classify The Work

Choose the smallest workflow that fits:

| Work type | Required flow |
| --- | --- |
| Roadmap or product direction | Context -> options -> recommendation -> roadmap artifact |
| Cross-domain architecture | Context -> constraints -> 2-3 approaches -> ADR/spec -> phased plan |
| Safety-sensitive recommendation behavior | Sources -> safety model -> structured contract -> tests/evals -> implementation |
| Normal feature | Inspect -> concise design -> implementation plan if multi-step -> implement -> verify |
| Small local change | Inspect -> edit -> focused verification |
| Bug or failing test | Reproduce -> trace root cause -> regression test -> minimal fix -> full relevant verification |
| Review | Findings first -> severity -> file/line evidence -> test gaps -> brief summary |

Ask the user only when a missing decision materially changes product scope, health risk, data ownership, irreversible migration behavior, or external cost. Otherwise state reasonable assumptions and continue.

## Apply The Health Product Boundary

Enforce these rules:

1. Position the product as wellness education, planning, habit support, and progress tracking.
2. Do not claim diagnosis, treatment, guaranteed outcomes, or professional equivalence.
3. Route red flags, restricted populations, and disease-specific needs out of automated planning or into an explicitly limited mode.
4. Never let an LLM be the sole authority for contraindications, eligibility, training load limits, nutrition limits, or emergency guidance.
5. Use deterministic, versioned policy rules for safety-critical decisions.
6. Require structured, schema-validated outputs before storing or presenting AI-generated plans.
7. Record the inputs, policy version, knowledge/source version, model version, and validation outcome needed to explain a recommendation.
8. Minimize collection and exposure of health data. Separate consent, retention, deletion, and audit concerns from ordinary profile UX.

Use AI for interpretation, personalization, explanation, substitution, and conversational support. Use code and curated data for calculations, constraints, eligibility, validation, and persistence.

## Preserve Architectural Boundaries

Prefer a modular monolith until scale proves otherwise. Keep these concerns independently understandable and testable:

- identity, consent, and health profile
- posture assessment and posture knowledge
- exercise catalog and contraindications
- training-plan generation and progression
- workout execution, adherence, and feedback
- nutrition targets, food/meal knowledge, and meal planning
- Agent orchestration and tool contracts
- safety policy and recommendation validation
- audit, provenance, and observability

Do not put core recommendation logic directly in API routers, Flutter widgets, or prompt text. Keep domain logic callable without an LLM and without HTTP.

Do not let the Agent write arbitrary database state. Expose narrow application tools with validated inputs, authorization checks, idempotency where needed, and explicit side effects.

## Design Before Expensive Changes

For cross-module, data-model, recommendation, privacy, or Agent changes:

1. Define the user outcome and non-goals.
2. Identify required profile data and what happens when it is missing.
3. Describe the deterministic baseline behavior without AI.
4. Describe where AI adds value and how its output is constrained.
5. Define data ownership, API contracts, state transitions, and failure behavior.
6. Define safety gates and escalation behavior.
7. Propose 2-3 viable approaches when trade-offs are meaningful.
8. Record the chosen decision in a spec or ADR.
9. Split large initiatives into independently releasable vertical slices.

Avoid one giant plan for training, nutrition, chat, wearables, and analytics. Each slice must create a usable, testable capability.

When the user explicitly requests implementation, proceed with the smallest reversible slice after documenting essential decisions. Pause for approval only when alternatives materially affect safety, product scope, external spend, or irreversible data changes.

## Write Executable Plans

Create implementation plans that are detailed enough to execute but short enough to stay current.

Include:

- goal, non-goals, assumptions, and acceptance criteria
- exact files or modules likely to change
- domain model and API/event contracts
- migration and backward-compatibility strategy
- safety rules and AI boundaries
- tasks ordered as vertical slices
- tests, evaluations, and manual verification
- rollout, observability, and rollback for risky changes

Do not paste entire future implementations into plans. Include schemas, pseudocode, or examples only where they remove ambiguity. Keep each task independently verifiable and update its status while executing.

## Implement In Safe Increments

1. Protect the current branch and dirty worktree. Recommend a `codex/` branch for risky multi-day work, but do not move existing changes without consent.
2. Add or change one coherent behavior at a time.
3. Use test-first development for recommendation rules, safety policy, calculations, parsers, state transitions, bug fixes, and migrations.
4. Use focused behavior tests plus visual/manual QA for UI styling and exploratory interaction work.
5. Keep AI providers behind interfaces. Make deterministic fakes available for tests.
6. Validate model output with typed schemas and reject unsafe or incomplete results; do not silently convert failures into healthy outcomes.
7. Keep prompts versioned and reviewable. Keep medical or nutrition facts in curated sources or policy data rather than hidden prompt prose.
8. Add observability without logging raw sensitive health data.
9. Avoid unrelated refactors and speculative abstractions.

## Review In Two Passes

After a substantial task:

1. Review specification compliance: missing requirements, extra behavior, unsafe fallback, contract mismatch, migration gaps.
2. Review engineering quality: correctness, security, privacy, maintainability, performance, tests, and operational behavior.

Fix critical and important findings before continuing. For delegated work, independently inspect the diff and rerun verification rather than trusting a completion report.

## Verify Before Completion

Identify the evidence needed for each claim, run it fresh, and report the actual result.

Depending on the change, verify:

- focused and full backend tests
- Flutter analyze and relevant Flutter tests
- API schema and serialization contracts
- database upgrade/downgrade or migration rehearsal
- recommendation safety and adversarial evaluation cases
- LLM schema-validation and failure paths
- local end-to-end user flow
- privacy-sensitive logging and authorization behavior
- documentation links and plan/spec consistency

Never infer that a build passes because linting passes. Never claim a health recommendation path is safe solely because unit tests pass.

## Keep Documentation Current

Use the artifact locations in [delivery-workflow.md](references/delivery-workflow.md). Prefer small current documents over monolithic historical plans.

Update documentation after behavior is implemented and verified. Mark assumptions, unresolved decisions, and deferred scope explicitly. Do not mark roadmap items complete based only on code presence; verify the acceptance criteria.
