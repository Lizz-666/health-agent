# Project Context

## Contents

1. Product direction
2. Current system
3. Target bounded contexts
4. Architectural defaults
5. Repository orientation
6. Suggested delivery sequence

## Product Direction

Evolve the existing posture-analysis MVP into a personal health coaching Agent that:

- builds a user-controlled health and fitness profile
- uses posture findings as one input, not the whole product
- creates explainable training plans
- creates nutrition guidance aligned with the profile and training plan
- tracks adherence, symptoms, recovery, and progress
- adjusts plans conservatively from longitudinal feedback
- escalates situations outside a wellness product's scope

The product is not an autonomous clinician, dietitian, or rehabilitation provider.

## Current System

Verify these details against the repository before relying on them:

- `app/`: Flutter client using Riverpod, GoRouter, Dio, secure storage, and Hive.
- `backend/`: FastAPI service using async SQLAlchemy, PostgreSQL in production intent, and SQLite in tests.
- Backend code has historically targeted Python 3.9 compatibility. Verify the actual runtime before introducing newer syntax or dependency requirements.
- `backend/app/posture/data/`: version-controlled posture knowledge stored as JSON.
- `backend/app/posture/`: posture issue lookup, self-assessment, photo analysis, and history.
- `backend/app/posture/ai_service.py`: current direct multimodal-provider integration for posture photos; treat it as an existing adapter to isolate, not the final Agent architecture.
- `backend/app/auth/`, `backend/app/user/`, `backend/app/upload/`: authentication, profile, and upload foundations.
- `issue.md`: broad posture-domain research and relationship notes. Treat it as input requiring source review, not as executable medical truth.
- `docs/plans/`: historical implementation plans that may no longer match current code.
- `docs/specs/`: design and status documents that must be checked against source and tests.

The worktree may contain substantial user changes. Inspect and preserve them.

## Target Bounded Contexts

Keep domain ownership explicit:

| Context | Owns |
| --- | --- |
| Identity and consent | authentication, authorization, consent records, account lifecycle |
| Health profile | demographics, goals, experience, equipment, schedule, preferences, restrictions |
| Posture | assessments, posture state, knowledge, related issues |
| Exercise knowledge | exercises, regressions/progressions, equipment, muscles, contraindications |
| Training planning | cycles, sessions, prescriptions, progression, substitutions |
| Execution and recovery | completion, RPE, pain, fatigue, sleep, readiness, notes |
| Nutrition knowledge | nutrient targets, foods, meal templates, substitutions, exclusions |
| Nutrition planning | energy/macro targets, meal structure, training-day adjustments |
| Agent orchestration | conversation state, tool selection, explanation, clarification |
| Safety policy | eligibility, red flags, contraindications, output validation, escalation |
| Audit and provenance | versions, recommendation rationale, source lineage, model/tool traces |

Keep posture assessment independent from training-plan state. A posture result is evidence consumed by planning, not a mutable field embedded in a generated plan.

## Architectural Defaults

Prefer:

- a modular FastAPI monolith with clear domain packages
- PostgreSQL for user-generated and transactional state
- versioned curated content in JSON only while editing frequency and relational needs remain low
- typed Pydantic contracts at every AI and API boundary
- deterministic domain services that work without HTTP or an LLM
- an application service layer that coordinates persistence, policies, and AI
- Flutter feature modules with providers acting as state/application adapters, not domain engines
- asynchronous jobs only when latency or reliability justifies them

Avoid:

- microservices before operational scale requires them
- a free-form chatbot that directly reads and writes tables
- prompts containing the only copy of business or safety rules
- storing only final AI prose without structured recommendation data
- merging user facts, inferred facts, and AI suggestions into one untraceable profile

## Repository Orientation

For architecture work, inspect:

1. `backend/app/main.py`
2. `backend/app/core/`, `backend/app/db/`
3. each affected backend domain package
4. `app/lib/app.dart`, `app/lib/core/`, affected providers and screens
5. backend and Flutter tests
6. relevant current specs and `git diff`

For recommendation work, also inspect the posture JSON schema, user profile schema, assessment history, and any existing sync/cache behavior.

## Suggested Delivery Sequence

Keep each phase usable:

1. **Foundation:** product boundary, consent/privacy model, expanded profile, policy framework, audit fields.
2. **Exercise catalog:** structured exercise data, contraindications, substitutions, media references.
3. **Training MVP:** deterministic plan generator, posture-aware constraints, plan display, execution and feedback.
4. **Adaptive training:** weekly review, progression/regression, pain/fatigue handling, plan versioning.
5. **Nutrition foundation:** nutrition profile, exclusions, deterministic target calculator, food/meal knowledge.
6. **Nutrition MVP:** meal templates and substitutions aligned with training and goals.
7. **Agent layer:** conversational orchestration over validated domain tools.
8. **Production hardening:** observability, content operations, model evaluation, security/privacy review, deployment.

Do not start with a general chat UI. Build trustworthy domain tools first so the Agent has safe capabilities to call.
