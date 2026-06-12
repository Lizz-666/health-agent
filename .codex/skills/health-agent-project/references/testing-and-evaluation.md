# Testing And Evaluation

## Contents

1. Testing strategy
2. Recommendation-engine tests
3. LLM and Agent evaluation
4. Safety case matrix
5. Frontend and integration checks
6. Release evidence

## Testing Strategy

Match verification depth to risk:

| Area | Minimum evidence |
| --- | --- |
| Pure calculation or policy | unit tests, boundary cases, property/invariant tests where useful |
| Recommendation composition | deterministic scenario tests and snapshots of structured output |
| Database/model change | migration test, constraints, serialization, rollback or recovery plan |
| API change | request/response contract, authorization, invalid input, service failure |
| Flutter state/flow | provider tests where practical, widget/behavior tests, manual visual flow |
| LLM integration | schema tests, provider failure tests, deterministic fake, evaluation dataset |
| Health safety behavior | restricted/red-flag cases, missing data, conflicting constraints, unsafe-output rejection |

Use test-first development for deterministic behavior and bug fixes. For visual-only work, define observable behavior and perform render/device QA instead of forcing low-value pixel-level TDD.

## Recommendation-Engine Tests

Test structured behavior, not prose.

Include:

- required inputs and missing-input handling
- eligibility and risk tier
- deterministic calculations and policy bounds
- exercise/meal candidate filtering
- contraindication and allergy exclusion
- duplicate and conflict resolution
- schedule and equipment constraints
- plan versioning and replacement
- user feedback effects
- provider unavailable and invalid-output behavior

Assert invariants such as:

- no forbidden item appears in a plan
- every prescribed item exists in the curated catalog version
- every plan references the profile and policy version used
- generated load stays within the selected policy
- a restricted user cannot enter the normal generation path
- failure never becomes a silent "normal" result

## LLM And Agent Evaluation

Keep model tests resilient to nondeterministic wording:

- assert JSON/schema shape, enums, required rationale, and tool calls
- assert prohibited actions and advice are absent
- assert uncertainty and escalation fields when required
- use deterministic fakes for normal unit/integration tests
- run live-provider tests separately and never require them for every local test run

Maintain a versioned evaluation dataset with synthetic profiles. Record:

- input profile and conversation
- expected risk tier
- allowed tools
- required and forbidden plan properties
- expected escalation or clarification
- policy and knowledge version

Do not use real personal health information in fixtures or evaluation datasets.

Test prompt injection through user text and retrieved content. The Agent must not bypass policy, reveal secrets, access another user, or call unauthorized write tools.

## Safety Case Matrix

Include representative synthetic cases:

- healthy beginner with complete profile
- experienced user with ordinary goal
- posture finding plus ordinary strength goal
- incomplete profile
- incompatible equipment or schedule
- reported pain during an exercise
- acute/red-flag symptom
- recent surgery or injury
- pregnancy
- underage user
- chronic disease requiring professional guidance
- food allergy or exclusion
- eating-disorder signal
- conflicting rapid-weight-change goal
- malicious instruction asking the Agent to ignore safety rules

Expected behavior must come from reviewed policy, not an LLM-generated answer key.

## Frontend And Integration Checks

Verify the end-to-end path:

```text
profile -> risk check -> plan request -> validated plan
-> user review -> persistence -> daily execution
-> feedback -> next plan version
```

Check loading, offline, retry, partial data, logout/account change, stale cache, and server incompatibility. Ensure sensitive data is not visible after account switching or token failure.

For significant Flutter changes, run the app on the relevant target and inspect the flow with the Browser or device tooling when available.

## Release Evidence

Do not rely on one green command. Collect the evidence relevant to the change:

- backend focused and full tests
- Flutter analyze and relevant tests
- build or runtime startup where applicable
- migration rehearsal
- safety/evaluation suite result
- manual flow result
- source/policy review date for health rules
- known limitations and rollback path
