# Phase 2 Health Profile, Check-Ins, And Trends

## Outcome

Phase 2 establishes the structured health data needed by later training adjustments without relying on chat history, wearable data, or AI inference.

Users can maintain a lightweight health profile, complete a daily check-in in about 20 seconds, optionally record body weight, and review check-in and weight trends. The system records safety-relevant pain signals conservatively, keeps health data isolated per account, and gives users view, correction, and deletion paths for Phase 2 health data.

## Non-Goals

- No training-plan generation, exercise selection, substitutions, progression, or plan validation.
- No Agent chat, Tool orchestration, or long-term conversational memory.
- No nutrition targets, meal plans, calorie advice, diet tracking, or food database.
- No wearable-device import, automatic body measurement, or medical-device integration.
- No diagnosis, treatment guidance, rehabilitation protocol, or disease-specific coaching.
- No public-release compliance implementation beyond preserving the Phase 2 privacy and audit requirements.

## Users And Scenarios

- A generally healthy adult completes the health profile with a fitness goal, training experience, weekly frequency, available session time, equipment, restrictions, allergies, and exclusions.
- A user with missing required training inputs sees explicit gaps; the backend must not fill missing data through AI or defaults that look user-provided.
- A user completes today's check-in with sleep, energy, soreness, abnormal pain, and available time.
- A user reporting abnormal pain receives conditional follow-up questions before the check-in can be accepted as complete.
- A user records optional body weight and sees raw points plus a moving trend; the product does not recommend adjustments from a single measurement.
- A user logs out or switches account and no previous user's health data remains visible.
- A user reviews, corrects, or deletes Phase 2 health data.

## Assumptions And Open Decisions

- Phase 2 is implemented as a modular backend health/tracking domain, not by expanding posture-specific tables for non-posture data.
- Existing `/api/v1/user/profile` remains the basic account profile. Phase 2 health profile data uses new health endpoints so later training and nutrition rules can depend on versioned structured inputs.
- Existing Phase 1 posture safety signals remain valid for posture flows. Phase 2 creates health-profile and check-in safety records that later training safety policy can consume.
- Retention for personal development is user-controlled: active Phase 2 health data is retained until the user deletes it or the account deletion flow is implemented. Deletion must be verifiable by API tests and must not leave raw health values in ordinary logs.
- Phase 2 uses deterministic rules only. AI may explain UI copy in a future phase, but it cannot create, infer, or repair health profile fields in Phase 2.
- Open decision for implementation: whether backend package names use `health` only or split `health_profile` and `tracking`. The implementation plan assumes a single `backend/app/health/` package with submodules.

## Domain Model

### Health Profile

One current editable record per user.

Fields:

- `fitness_goal`: enum `posture_improvement`, `fat_loss`, `basic_strength`, `mobility`, `general_wellness`.
- `training_experience`: enum `beginner`, `some_experience`, `experienced`.
- `weekly_frequency`: integer 2 through 5, nullable until user supplies it.
- `session_duration_minutes`: enum 15, 30, 45, 60, nullable until user supplies it.
- `equipment`: object with `bodyweight`, `resistance_band`; at least one must be true before a later training request can be considered complete.
- `pain_injury_limitations`: structured list of user-stated limitations with body area, current status, optional note, and last updated date.
- `risk_screen`: structured yes/no/unknown fields for underage status derived from age, pregnancy or postpartum when applicable, recent surgery or major injury, major chronic condition affecting exercise, eating-disorder concern, and professional instruction limitations.
- `allergies`: structured list of user-stated allergy labels and optional note. Phase 2 stores these only; it does not generate nutrition advice.
- `diet_exclusions`: structured list of explicit food exclusions or preferences. Phase 2 stores these only; it does not generate nutrition advice.
- `version`: monotonically updated profile version or timestamp used by future recommendation requests.
- `updated_at`.

Missing fields are represented as missing. They are not inferred from posture results, chat text, defaults, or previous accounts.

### Daily Check-In

At most one current check-in per user per local calendar day.

Fields:

- `local_date`: user-local date.
- `sleep_quality`: enum `poor`, `ok`, `good`.
- `energy`: enum `low`, `normal`, `high`.
- `muscle_soreness`: enum `none`, `mild`, `significant`.
- `abnormal_pain`: boolean.
- `pain_followup`: required when `abnormal_pain` is true.
- `available_time`: enum `none`, `15_min`, `30_min`, `45_min_plus`.
- `daily_status`: enum `checked_in`, `active_rest`, `safety_adjustment`; later training phases may add execution-specific statuses.
- `risk_summary`: deterministic result for this check-in, including `normal`, `caution`, `restricted`, or `red_flag`.
- `created_at`, `updated_at`.

Conditional pain follow-up fields:

- `pain_area`: required when abnormal pain is true.
- `pain_started`: enum `today`, `recent_days`, `ongoing`, `after_acute_event`.
- `pain_intensity`: enum `mild`, `moderate`, `severe`.
- `has_neurological_symptom`: boolean for numbness, weakness, or loss of control.
- `has_dizziness_or_chest_symptom`: boolean.
- `has_acute_trauma`: boolean.
- `pain_note`: optional user text, stored as user-stated untrusted text and never used as the sole safety rule source.

Red-flag follow-up values block later ordinary recommendation paths and show escalation guidance. Phase 2 itself does not prescribe actions beyond recording the signal, marking the check-in safety state, and presenting a bounded safety message.

### Weight Record And Trend

Multiple records per user.

Fields:

- `id`.
- `recorded_at`.
- `weight_kg`: bounded positive decimal.
- `source`: enum `manual`.
- `note`: optional.
- `created_at`, `updated_at`.

Trend API returns:

- raw records in the selected date range.
- a moving trend series only when enough points exist for the selected window.
- `insufficient_data` metadata when a trend should not be interpreted.

Phase 2 does not output plan adjustments, warnings, calorie advice, or success/failure judgment from weight data.

### Activity Grid

The grid is a user-facing projection over daily check-ins and later execution events.

Phase 2 statuses:

- `none`
- `checked_in`
- `active_rest`
- `safety_adjustment`

`active_rest` and `safety_adjustment` are valid health-management states. They are explicitly not failures, gaps, or missed days, and they count as completed engagement for the day, consistent with the product vision section 8. Phase 2 must never label them red or penalizing.

Later training phases may add:

- `partial_execution`
- `main_plan_completed`

Phase 2 must not fake plan execution statuses before a plan exists.

### Deletion And Audit

Phase 2 provides deletion for:

- current health profile fields.
- daily check-ins.
- weight records.

Deletion must remove or tombstone user-linkable raw health values according to the implementation plan. Audit records can retain operation metadata without raw health payloads.

## User Flow

### My Page

The My page owns health profile, posture profile, body-weight trend, activity grid, preferences, and data-management entry points.

### Today Page

The Today page owns today's check-in and today's state. It may show whether the user has already checked in, whether abnormal pain requires follow-up, and whether today is marked as active rest or safety adjustment.

### Plan Page

The Plan page owns future training or nutrition arrangements in later phases. In Phase 2 it must not render check-in data as a plan, and it must not create a plan placeholder that looks active.

## API And State Contracts

All endpoints are JWT-only and use the authenticated user from the token. No endpoint accepts `user_id` as a request parameter.

Suggested endpoints:

- `GET /api/v1/health/profile`
- `PUT /api/v1/health/profile`
- `DELETE /api/v1/health/profile`
- `GET /api/v1/health/checkins/today`
- `PUT /api/v1/health/checkins/today`
- `GET /api/v1/health/checkins`
- `DELETE /api/v1/health/checkins/{checkin_id}`
- `POST /api/v1/health/weight-records`
- `GET /api/v1/health/weight-records`
- `PUT /api/v1/health/weight-records/{record_id}`
- `DELETE /api/v1/health/weight-records/{record_id}`
- `GET /api/v1/health/trends/weight`
- `GET /api/v1/health/activity-grid`

Validation:

- Required enum fields reject unknown strings.
- `weekly_frequency` accepts only 2 through 5.
- `session_duration_minutes` accepts only 15, 30, 45, or 60.
- `available_time` accepts only `none`, `15_min`, `30_min`, or `45_min_plus`.
- Abnormal pain requires the complete pain follow-up object.
- Weight accepts positive realistic kg values and rejects empty or nonnumeric strings.
- API responses include explicit missing fields rather than inferred values.

State and cache:

- Flutter providers for Phase 2 health data must clear state on logout and token loss.
- Failed parsing of a health response must not retain stale health data as if it were current.
- Account switching tests must cover profile, check-in, weight trend, and activity grid state.

## Recommendation And AI Behavior

Phase 2 has no recommendation generation and no AI-dependent behavior.

Rules:

- AI cannot infer missing profile fields.
- AI cannot classify pain or convert a red-flag signal into normal.
- AI cannot derive diet exclusions, allergies, training experience, frequency, or available time from free text.
- Any future Agent or plan-generation request must use the structured Phase 2 data and rerun deterministic risk classification at request time.

## Safety, Privacy, And Failure Handling

Safety rules:

- Missing safety-critical profile fields produce `missing_required_data` for later recommendation readiness.
- Abnormal pain without follow-up produces `pain_followup_required`.
- Neurological symptoms, dizziness or chest symptoms, severe pain after acute trauma, or configured red-flag fields produce `red_flag`.
- Recent surgery or major injury, underage status, pregnancy or postpartum, major chronic condition affecting exercise, and eating-disorder concern produce `restricted` for ordinary training or nutrition planning until a future limited-mode specification exists.
- Existing posture safety results continue to invalidate posture priority and future plan requests independently.

Privacy rules:

- Health, pain, body weight, allergy, diet exclusion, and restriction fields are sensitive data.
- Ordinary logs must not include raw values or free-text notes.
- API errors must be structured and must not expose DB values.
- Deletion endpoints must be covered by tests that confirm deleted user-linkable data is not returned.
- The implementation must preserve personal-data rights in the project boundary, referencing the official Personal Information Protection Law text for collection minimization, correction, and deletion rights.

Failure handling:

- Backend service failure returns a structured unavailable response.
- Invalid client payload returns deterministic validation errors.
- Partial Flutter loads must clearly show missing/unavailable states and not display stale data from a different account.
- Trend endpoints return `insufficient_data` instead of drawing unsupported conclusions.

## Observability And Audit

Record non-sensitive metadata for:

- health profile create/update/delete.
- daily check-in create/update/delete.
- weight record create/update/delete.
- safety classification result and policy version.

Audit metadata should include user id, operation, entity type, entity id when retained, policy version, created time, and request id/idempotency key when used. Do not store raw pain notes, allergy labels, body weight values, or full request bodies in audit logs.

## Acceptance Criteria

- Missing profile data remains explicit and cannot be filled by AI or silent defaults.
- A normal user can complete the check-in flow in about 20 seconds when no abnormal pain is reported.
- Reporting abnormal pain requires conditional follow-up before the check-in is accepted as complete.
- Red-flag follow-up answers produce a red-flag safety state and block ordinary future recommendation readiness.
- Active rest and safety adjustment are recorded and projected as valid, non-failure engagement states; they never reduce a day to `none`, missed, or failed on the activity grid.
- Weight trend shows raw points and a moving trend only when enough points exist; it does not recommend adjustments from one-day changes.
- Logout, token failure, and account switch clear Phase 2 health data from Flutter state.
- Users can view, correct, and delete health profile data, check-ins, and weight records.
- Phase 2 APIs are authenticated, never accept request-supplied `user_id`, and enforce cross-user isolation.
- No raw health data appears in ordinary backend logs or audit payloads.
- Phase 2 does not generate training plans, nutrition recommendations, or Agent responses.

## Test And Evaluation Strategy

Backend:

- migration upgrade and downgrade where supported by project migration policy.
- API contract tests for each endpoint, including auth, invalid input, cross-user isolation, and OpenAPI schemas.
- domain tests for profile completeness, risk readiness, abnormal-pain follow-up, red-flag and restricted cases, weight-trend insufficient data, and deletion.
- full backend test run before Phase 2 exit.

Flutter:

- model parsing tests for missing/null fields and unknown enums.
- provider tests for fetch/update/delete, parse failure, token failure, logout, and account switch.
- widget tests for health profile editing, today check-in, conditional pain follow-up, weight trend empty/insufficient states, and activity grid statuses.
- `flutter analyze` and relevant/full Flutter tests before Phase 2 exit.

Safety cases:

- complete normal profile.
- incomplete profile.
- beginner with pain history.
- abnormal pain without follow-up.
- severe pain after acute trauma.
- numbness or weakness.
- dizziness or chest symptom.
- underage user.
- recent surgery or major injury.
- pregnancy or postpartum where applicable.
- eating-disorder concern.
- allergy and explicit food exclusion storage.
- malicious free-text note asking the system to ignore safety rules.

## Rollout

Phase 2 is local personal-development functionality. Rollout is gated by:

- backend tests and migration rehearsal.
- Flutter analyze/tests.
- Android emulator smoke for login, My health profile, Today check-in, pain follow-up, weight entry, trend, grid, logout/account switch.
- documentation update in this spec, implementation plan, active task ledger, and roadmap completion status only after verification.

Rollback:

- migrations must allow a documented local rollback path or an explicit data-reset path for personal development.
- Flutter UI should degrade to hidden/unavailable Phase 2 routes if backend health endpoints are unavailable.

## References

- Project safety boundary: `docs/product/safety-boundaries.md`.
- Product vision: `docs/product/vision.md`.
- Roadmap Phase 2: `docs/product/roadmap.md` section 6.
- WHO physical activity and sedentary behaviour guidance, official publication page verified 2026-07-22: https://www.who.int/publications/i/item/9789240015128
- PRC Personal Information Protection Law, CAC repost of official text verified 2026-07-22: https://www.cac.gov.cn/2021-08/20/c_1631050028355286.htm
- NHC response referencing Chinese Dietary Guidelines 2022 core principles, verified 2026-07-22: https://www.nhc.gov.cn/wjw/jiany/202301/bd6c614391274ebd955fc9018f2032a2.shtml
