# Delivery Workflow

## Contents

1. Artifact structure
2. Roadmap workflow
3. Specification workflow
4. ADR workflow
5. Implementation-plan workflow
6. Execution workflow
7. Completion checklist

## Artifact Structure

Use this structure for new work without moving historical files unless requested:

```text
docs/
  product/
    vision.md
    safety-boundaries.md
    roadmap.md
  architecture/
    system-overview.md
    data-model.md
    agent-design.md
  decisions/
    ADR-NNN-short-title.md
  specs/
    posture/
    training/
    nutrition/
    agent/
    platform/
  plans/
    posture/
    training/
    nutrition/
    agent/
    platform/
```

Name specs and plans `YYYY-MM-DD-short-topic.md`. Keep one initiative per document.

## Roadmap Workflow

Create a roadmap around user outcomes and dependencies, not a flat feature list.

For each phase include:

- outcome and target users
- capabilities delivered
- prerequisites
- safety/privacy work
- exit criteria
- explicit exclusions

Prefer a small number of milestones. Link each milestone to its specs instead of embedding implementation details in the roadmap.

## Specification Workflow

Use this compact structure:

```markdown
# Feature Name

## Outcome
## Non-Goals
## Users And Scenarios
## Assumptions And Open Decisions
## Domain Model
## User Flow
## API And State Contracts
## Recommendation And AI Behavior
## Safety, Privacy, And Failure Handling
## Observability And Audit
## Acceptance Criteria
## Test And Evaluation Strategy
## Rollout
```

For recommendation features, explicitly answer:

- What deterministic baseline works without AI?
- Which inputs are required, optional, user-stated, measured, or inferred?
- What blocks generation?
- What can AI modify?
- What validation runs after AI?
- How is the recommendation versioned and explained?
- How does user feedback change future versions?

Self-review for placeholders, contradictions, ambiguous ownership, missing failure states, and scope too broad for one plan.

## ADR Workflow

Write an ADR when a decision:

- affects multiple modules
- changes persistence or API ownership
- introduces a provider or infrastructure dependency
- determines AI orchestration or safety behavior
- is costly to reverse

Use:

```markdown
# ADR-NNN: Decision

## Status
## Context
## Decision
## Alternatives Considered
## Consequences
## Follow-Up
```

Record decisions, not meeting transcripts.

## Implementation-Plan Workflow

Start with:

```markdown
# Feature Implementation Plan

**Goal:** One measurable outcome.
**Spec:** Link to the approved/current spec.
**Architecture:** Short summary.
**Safety:** Key gates and restricted behavior.
**Verification:** Commands and evaluation suites.
```

Then provide:

1. a file/module map
2. ordered vertical-slice tasks
3. exact acceptance checks per task
4. migrations and compatibility notes
5. rollout/rollback for risky changes

Task shape:

```markdown
### Task N: User-visible or domain capability

**Files:** exact paths or packages
**Behavior:** concrete change
**Tests/Evals:** exact cases and commands
**Done when:** observable acceptance criteria
```

Use checkboxes when the plan will be executed over multiple turns. Avoid full source listings, vague "add validation" steps, and giant tasks spanning unrelated domains.

## Execution Workflow

For each task:

1. Re-read the task and affected contracts.
2. Inspect current files and user changes.
3. Add the failing behavior test when appropriate.
4. Implement the smallest coherent slice.
5. Run focused verification.
6. Review specification compliance.
7. Review quality, safety, and privacy.
8. Update task status and current documentation.
9. Continue unless genuinely blocked.

Use subagents when available for independent, well-bounded tasks or review. Do not dispatch parallel implementers against overlapping files. Give subagents task-local context and verify their output independently.

## Completion Checklist

Before declaring an initiative complete:

- verify every acceptance criterion
- run fresh test/analyze/build/evaluation commands
- inspect migration and rollback behavior
- confirm unsafe and missing-data paths
- confirm authorization and sensitive logging behavior
- confirm AI output schema and deterministic validation
- update docs to actual behavior
- report residual risks and work not performed
