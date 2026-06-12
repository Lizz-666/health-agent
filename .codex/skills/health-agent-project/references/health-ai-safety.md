# Health And AI Safety

## Contents

1. Product boundary
2. Risk classification
3. Recommendation pipeline
4. Training safeguards
5. Nutrition safeguards
6. AI constraints
7. Privacy and audit
8. Source policy

## Product Boundary

Design for wellness education, general fitness planning, nutrition support, adherence, and self-management. Do not represent outputs as diagnosis, treatment, rehabilitation, or a substitute for licensed care.

Use clear language:

- say "assessment signal", "screening result", or "reported symptom"
- avoid "confirmed condition" unless provided by a qualified external source and explicitly recorded as user-supplied
- explain uncertainty and missing information
- distinguish recommendation rationale from medical fact

## Risk Classification

Classify every recommendation request before plan generation:

| Tier | Example | Behavior |
| --- | --- | --- |
| Normal wellness | generally healthy adult, ordinary fitness goal | generate within validated policy |
| Caution | pain history, low experience, conflicting goals, incomplete profile | use conservative defaults, ask targeted questions, restrict progression |
| Restricted | pregnancy, underage user, eating-disorder signal, major chronic disease, recent surgery/injury, medication-sensitive nutrition | do not generate an ordinary plan; provide limited education and professional referral |
| Urgent/red flag | acute neurological, cardiovascular, severe pain, trauma, or other configured red flags | stop planning and present escalation guidance |

Store risk rules in versioned policy data or code. Do not bury them only in prompts.

Do not hard-code clinical thresholds from memory. Research current primary guidance, cite it in the design or policy source, and record the policy version.

## Recommendation Pipeline

Use this order:

```text
validated profile
  -> eligibility and risk classification
  -> deterministic calculations and constraints
  -> curated knowledge retrieval
  -> candidate plan generation
  -> optional LLM personalization/explanation
  -> schema validation
  -> deterministic safety validation
  -> user confirmation when required
  -> versioned persistence and audit
```

Reject or repair invalid output before presentation. Never treat AI failure as a healthy or normal result.

Keep generated plan data separate from explanatory prose. The application must be able to render and validate a plan without parsing natural language.

## Training Safeguards

Represent at least:

- user goal, experience, schedule, available equipment, and session duration
- posture findings and their confidence/source
- pain, injury, restrictions, and professional instructions
- exercise purpose, difficulty, movement pattern, muscles, equipment
- contraindications, regressions, progressions, and substitutions
- sets, reps or duration, intensity target, rest, frequency, and progression rule
- stop conditions and feedback prompts

Resolve conflicts deterministically. Examples include an exercise matching a goal but violating a restriction, duplicate corrective exercises across posture findings, and excessive combined volume.

Treat pain, neurological symptoms, dizziness, chest symptoms, and acute injury feedback as safety signals, not ordinary adherence data.

## Nutrition Safeguards

Do not infer a nutrition plan from posture alone. Require the relevant profile, goal, activity/training load, preferences, allergies/exclusions, and risk screening.

Separate:

- deterministic energy and nutrient target calculations
- policy-approved minimum/maximum bounds
- meal templates and food substitutions
- AI-written explanations and preference-aware presentation

Do not let the model invent nutrient values, allergies, disease-specific restrictions, or food-drug guidance. Use curated data and explicit policy.

Use a restricted path for disease-specific nutrition, pregnancy, underage users, eating-disorder risk, and other configured populations.

## AI Constraints

Require:

- typed input and output schemas
- bounded tool permissions
- allowlisted tools per Agent action
- timeouts, retry limits, and explicit unavailable states
- prompt and model version recording
- deterministic validation after model output
- adversarial tests for unsafe advice, missing data, and instruction injection
- provenance for retrieved health content

Treat user text, uploaded documents, retrieved content, and model output as untrusted. Do not allow retrieved text to override system safety policy or tool authorization.

Do not expose secrets, raw internal prompts, or other users' data to the model.

## Privacy And Audit

Treat health, body, photo, diet, and symptom data as sensitive.

Implement:

- purpose-specific and minimal collection
- explicit consent where required
- authorization at every read/write boundary
- retention and deletion behavior
- exportability where product requirements call for it
- encryption and secret management appropriate to the deployment
- redaction or omission of sensitive fields from logs and traces
- auditable recommendation versions without storing unnecessary raw conversation

Keep user-stated facts, measured data, imported clinical facts, algorithmic calculations, and AI inferences distinguishable.

## Source Policy

For health, exercise, nutrition, privacy, and legal rules:

1. Browse current primary sources by default.
2. Prefer government health authorities, WHO, recognized professional bodies, peer-reviewed guidelines, and official law/regulation text.
3. Record publication/version dates and applicability.
4. Separate strong guidance from expert consensus and product policy.
5. Do not copy claims from `issue.md` or old plans into safety policy without source verification.
6. Revisit policies when sources or regulations change.

Useful starting points include WHO physical-activity guidance, China's National Health Commission guidance, and official Chinese privacy and AI regulations. Verify the current documents and URLs at the time of use.
