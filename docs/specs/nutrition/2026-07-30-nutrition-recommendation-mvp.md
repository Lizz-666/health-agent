# Phase 6 Nutrition Recommendation MVP

> Status: proposed for Gate 0 review, 2026-07-30. This specification defines a
> personal-development wellness feature for synthetic-data validation. It does
> not authorize disease treatment diets, public deployment, or use of real
> health data in development tools.

## Outcome

A signed-in, supported adult can use current owned profile, check-in, weight,
goal, and active training-plan state to obtain a deterministic nutrition
estimate and two three-meal templates: one for a training day and one for a rest
day. The user can review and confirm a recommendation, inspect approximate
household portions, and replace a food with a validated equivalent.

The feature is recommendation-only. It does not record meals, infer intake,
score adherence, recognize food photos, scan barcodes, or operate as a nutrition
tracker. All targets, exclusions, candidate selection, replacement, and
validation work without a model. Agent integration calls the same services and
never becomes the safety or calculation source.

## Non-Goals

- No diagnosis, treatment, medical nutrition therapy, disease-specific diet,
  pregnancy/postpartum diet, child/adolescent diet, eating-disorder support, or
  professional dietitian replacement.
- No vegetarian, vegan, halal, kosher, ketogenic, fasting, bodybuilding-cut,
  supplement, sports-nutrition, or other special-diet claim in this MVP.
- No meal diary, calorie logging, photo recognition, actual-intake statistics,
  nutrition check-in, barcode scan, pantry, shopping list, wearable import, or
  adherence score.
- No exact calorie prescription, promised weight-change rate, automatic calorie
  deficit/surplus, supplement dose, or model-invented nutrient value.
- No use of account `gender` as an unstated physiological-sex input. The energy
  estimate spans both published Mifflin-St Jeor equation branches.
- No runtime dependency on USDA or Wikimedia availability. Reviewed snapshots
  and media are local, versioned build inputs.
- No Open Food Facts database or product image import in Phase 6. Its ODbL,
  Database Contents License, share-alike image terms, and packaging/trademark
  rights require a separate distribution decision.
- No OpenNutriTracker code, UI, import pipeline, schema, or tracking behavior.
  Its GPL-3.0 implementation is not copied or linked.
- No live AI in tests, CI, fixtures, screenshots, or acceptance. No real health
  data, photos, credentials, or provider payloads.

## Approved Gate 0 Decisions

1. **Formula is an estimate range, not a prescription.** Calculate both sex-
   specific branches from Mifflin et al. (1990), apply the Chinese DRIs 2023
   low-intensity PAL of `1.40`, add an explicit product uncertainty allowance,
   and round outward. The response names the formula and limitations. It never
   reports a single exact daily-calorie target.
2. **`gender` is not equation sex.** The existing account field is not used to
   choose one branch. The lower and upper published branches define a wider,
   inclusive estimate. A future narrower estimate needs a separately defined,
   consented input and a new review.
3. **Goals do not create an invented deficit or surplus.** `fat_loss` changes
   food density and selection rationale; `basic_strength` changes distribution
   and training-adjacent choices. Neither subtracts nor adds a fixed calorie
   amount in Phase 6.
4. **Chinese references govern meal structure.** Chinese DRIs 2023 provides
   adult protein, macro distribution, fibre, water, and PAL references. Chinese
   Dietary Guidelines 2022 provides food-group ranges and balanced-plate
   structure. Mifflin supplies only estimated resting energy expenditure.
5. **USDA FDC is a bounded composition source.** Use a manually reviewed local
   subset of Foundation Foods and, only where necessary, SR Legacy. Pin every
   FDC ID, data type, publication date, source release, field mapping, and
   transformation. Chinese names and food-group mappings are project-authored.
6. **Open Food Facts is excluded.** Do not combine an ODbL database or CC BY-SA
   product imagery with this private catalog by default. The source remains a
   documented rejected candidate, not a fallback.
7. **Media is per-file licensed.** Use only real food photos whose individual
   Wikimedia Commons pages show CC0 or public-domain status. Store the original
   page, author, license, retrieval date, checksum, transformation, and removal
   path. Do not reuse Chinese Dietary Guidelines graphics; their site limits
   those graphics to attributed non-commercial public-interest use.
8. **Allergy handling is ingredient-level and fail-closed.** The structured
   vocabulary is the eight categories named by GB 7718-2025. Unknown free-text
   allergies or exclusions block automatic generation until resolved. The UI
   states that generic recommendations cannot guarantee restaurant, factory, or
   cross-contact safety and tells users to check labels.
9. **Recommendation versions are immutable.** Draft generation and confirmed
   replacements create new rows. Confirmation atomically makes one version
   active and supersedes the prior active version. No in-place mutation of an
   active recommendation.
10. **No intake state exists.** Database schemas and APIs store recommendation
    drafts/versions only. They contain no eaten/completed quantity, meal event,
    intake total, or compliance field.

## Authoritative Source And License Ledger

Access date for all web sources below: 2026-07-30.

| Source | Version / URL | Permitted use in Phase 6 | Limitations / decision |
| --- | --- | --- | --- |
| Mifflin et al., *A new predictive equation for resting energy expenditure in healthy individuals* | 1990, DOI `10.1093/ajcn/51.2.241`, PMID `2305711`, `https://ajcn.nutrition.org/article/S0002-9165(23)16698-6/abstract` | Implement the two published REE equations and record the 498-person, age 19-78 derivation scope | REE estimate only; not a measured expenditure, treatment target, or proof for one individual |
| Chinese DRIs | 2023 edition, Chinese Nutrition Society, `https://www.cnsoc.org/drpostand/` and official adult table images | Low-intensity PAL `1.40`; adult RNI/AMDR/fibre/water reference ranges | Tables are sex-stratified; Phase 6 spans male/female values instead of inferring equation sex; no copyrighted table image is redistributed |
| Chinese Dietary Guidelines | 2022 edition, `https://www.cnsoc.org/bookpublica/0522202019.html`, `https://dg.cnsoc.org/article/04/J4-AsD_DR3OLQMnHG0-jZA.html`, `https://dg.cnsoc.org/article/04/RMAbPdrjQ6CGWTwmo62hQg.html` | Food groups, adult 1600-2400 kcal envelope, balanced plate, three regular meals, water and food variety | Guidance text/facts are referenced and paraphrased; official graphics are not copied into the product |
| Adult weight classification | WS/T 428-2013, `https://www.nhc.gov.cn/wjw/yingyang/201308/a233d450fdbc47c5ad4f08b7e394d1e8.shtml` | Scope gate: BMI `<18.5`, `24-<28`, and `>=28` categories; BMI is screening context only | Not applicable to pregnancy or some special populations; those are already restricted. The product does not present a diagnosis |
| Food allergen vocabulary | GB 7718-2025 official Q&A, published 2025-03-16 and effective 2027-03-16, `https://www.nhc.gov.cn/sps/c100087/202509/bc824a504ec34c27883da73f14c20d44.shtml` | Eight structured categories: gluten cereals, crustaceans, fish, eggs, peanuts, soy, milk, tree nuts | The standard is published but not yet effective on the Gate 0 review date. Phase 6 uses only its vocabulary, not a claim that a generic meal is cross-contact safe or a legal labeling conclusion |
| USDA FoodData Central | API v1.0.1 and 04/2026 downloads, `https://fdc.nal.usda.gov/api-guide/`, `https://fdc.nal.usda.gov/download-datasets/`, `https://fdc.nal.usda.gov/data-documentation/` | CC0/public-domain composition fields for a pinned curated local subset; cite USDA ARS FoodData Central | US food supply and analytical variability limit China representativeness; no branded-food import; no runtime API key |
| Open Food Facts | current official license page, `https://openfoodfacts.github.io/documentation/docs/Product-Opener/api/tutorials/license-be-on-the-legal-side/` | Candidate assessment only | Database ODbL, contents DbCL, images CC BY-SA, and possible packaging rights: excluded from MVP |
| Wikimedia Commons | reuse policy, `https://commons.wikimedia.org/wiki/Commons:Reusing_content_outside_Wikimedia/en` | Individually verified CC0/public-domain food photos downloaded and attributed in a local manifest | Commons gives no warranty; every file must be independently checked and removable; no hotlinking |
| OpenNutriTracker | repository license and design review only | Inspiration limited to local-first/source-combination questions | GPL-3.0 code, UI, schema, import pipeline, and tracking features are excluded |

The committed source manifest must include source URL, exact data release or
file revision, retrieved timestamp, license, raw checksum, selected fields,
normalization script version, manual reviewer state, and deletion/update steps.
Generated catalog files fail validation if any record lacks lineage.

The DRI values above were checked against official Tables 9-14 for men and
women aged 18-29, 30-49, and 50-64. Tables 9-12 are published from
`https://www.cnsoc.org/drpostand/`; Tables 13-14 are on
`https://www.cnsoc.org/drpostand/page2.html`. The reviewed image URLs are:

- Table 9: `https://www.cnsoc.org/www/@6f91a3f6-ece6-4777-865d-5cb3ff30095a.jpg`
- Table 10: `https://www.cnsoc.org/www/@0dde980a-f7cb-4407-b784-e1fb17d757ab.jpg`
- Table 11: `https://www.cnsoc.org/www/@d82d5763-e449-4419-9ba7-29d47684485a.jpg`
- Table 12: `https://www.cnsoc.org/www/@d8670add-1ae0-4f81-9de4-43ad7ec07d8b.jpg`
- Table 13: `https://www.cnsoc.org/www/@e59cdffa-a0e4-4c31-9fec-ffed593d19e9.jpg`
- Table 14: `https://www.cnsoc.org/www/@5174270c-8a5d-4894-b8c6-8391b8676c1f.jpg`

The implementation source ledger must retain these exact URLs rather than a
screenshot or copied table. Across the six tables, low-intensity PAL is `1.40`,
protein RNI is `65 g/day` for men and `55 g/day` for women, and the macro,
fibre, and water ranges used below are unchanged across supported age bands.

## Supported Population And Safety Decision

Every target calculation, draft generation, confirmation, preview, and
replacement rebuilds current owned context. A stored prior decision is never an
authorization.

Decision precedence:

```text
red_flag
  > restricted
  > limited_education
  > clarification_required
  > eligible_conservative
  > eligible
```

### Required current inputs

- authenticated owner and server-derived current local date from a validated
  IANA timezone
- account age, height, and `updated_at`
- authoritative current weight: the newest owned manual weight record whose
  `recorded_at` is not later than the server evaluation instant; if none exists,
  the explicit account weight is used. If neither exists, clarification is
  required. The selected source kind, row ID when present, and timestamp are
  pinned; no trend average or client-selected record is substituted
- current health-profile version
- all six structured risk-screen answers
- explicit structured allergy state: `food_allergen_codes` is present, where an
  empty list means “answered none”
- explicit structured exclusion state: `excluded_food_codes` is present, where
  an empty list means “answered none”
- no unresolved non-empty legacy free-text allergy or diet-exclusion entry
- current-day structured check-in and recomputed risk
- current active training plan and today's effective `session` or `rest_day`
  state; `no_active_plan`, `plan_complete`, or a safety-blocked plan cannot
  authorize personalized nutrition
- the active plan's confirmed fitness goal; clients cannot override it for
  nutrition. A missing or unsupported active-plan goal requires clarification
- current policy, catalog, source-manifest, and media-manifest versions

### Deterministic outcomes

| Condition | Outcome | Product behavior |
| --- | --- | --- |
| Current check-in or posture/training global state is `red_flag` | `red_flag` | no target, draft, confirmation, or replacement; route to the existing safety flow |
| Account age is `<18`, or any risk-screen qualifier is `yes` | `restricted` | no ordinary automatic recommendation; fixed boundary education only. Age and a contradictory `underage=no` answer cannot downgrade this result |
| Age is exactly `18` or above `64`, BMI `<18.5` or `>=28`, or estimated reference center outside the guidelines' 1600-2400 kcal envelope | `limited_education` | show scope limit and general guideline education; no personalized meal plan |
| Required value absent, risk answer `unknown`/missing, no current check-in/effective active plan, unknown allergy/exclusion code, or unresolved free text | `clarification_required` | name only missing/unsupported field codes; no target/draft/replacement |
| BMI `24-<28` or current check-in is `caution` | `eligible_conservative` | balanced lower-energy-density template; no promised loss rate or numeric deficit |
| BMI `18.5-<24`, all gates complete, no higher condition | `eligible` | ordinary deterministic recommendation |

`professional_instruction_limitations=yes` remains restricted. A statement that
a professional approved a diet does not lower the tier. Recovery requires the
underlying structured source to be corrected or deleted and a new decision;
elapsed time or acknowledgement never clears it.

The API may return BMI category and scope codes but must not label the result as
a medical diagnosis. Raw allergy labels, body values, or notes never enter
ordinary logs or Agent audit metadata.

## Deterministic Target Contract

For weight `w` kg, height `h` cm, and age `a` years:

```text
REE lower branch = 10*w + 6.25*h - 5*a - 161
REE upper branch = 10*w + 6.25*h - 5*a + 5
PAL              = 1.40
lower reference  = REE lower branch * PAL
upper reference  = REE upper branch * PAL
reference center = mean(REE branches) * PAL
display low      = floor(lower reference * 0.90) to the next lower 100 kcal
display high     = ceil(upper reference * 1.10) to the next higher 100 kcal
```

The `10%` allowance is a versioned product uncertainty band, not a confidence
interval. Tests must name that distinction. No result is described as measured
energy expenditure. Missing/out-of-scope inputs never receive defaults, clamps,
or an average-person fallback.

The response also contains these Chinese DRIs 2023 reference ranges:

- protein RNI span: `55-65 g/day`
- protein AMDR: `10-20%` of energy
- carbohydrate AMDR: `50-65%`
- fat AMDR: `20-30%`
- dietary fibre AI: `25-30 g/day`
- drinking water: `1500-1700 mL/day` in temperate, low-activity conditions
- total water: `2700-3000 mL/day`, including food and beverages

They are displayed as adult reference ranges, not calculated intake or proof of
adequacy. Heat, exercise, illness, medication, and clinician instructions are
explicit limitations. The product does not calculate micronutrient sufficiency.

The independent daily food-group validator uses these Chinese Dietary
Guidelines 2022 ranges for the supported `1600-2400 kcal` envelope:

| Food group | Daily reference | Validation treatment |
| --- | --- | --- |
| grains | `200-300 g` | required; dry/raw guideline equivalent, not cooked bowl weight |
| whole grains and mixed beans | `50-150 g` within the grain pattern | required across the day |
| tubers | `50-100 g` | required across the day |
| vegetables | at least `300 g` | required; dark vegetables are at least half of the vegetable guideline equivalent |
| fresh fruit | `200-350 g` | required; juice is not a substitute |
| fish, poultry, eggs, and lean meat combined | `120-200 g` | required as a combined range; processed meat is not a candidate |
| dairy equivalents | at least `300 mL` liquid-milk equivalent | required unless `milk` is excluded; an excluded required group yields `no_safe_candidate`, not an invented substitute |
| soy and nuts combined | `25-35 g` | required as guideline equivalents; allergen exclusions apply before validation |
| cooking oil | `25-30 g` maximum-guidance range | education only unless every recipe oil input is represented; never claim a computed total otherwise |
| salt | at most `5 g` | education only unless every sodium-bearing ingredient is represented; never claim a computed total otherwise |

These are recommendation-template constraints, not observations of what the
user ate. If exclusions make a required group impossible, the system returns a
bounded failure state instead of weakening the exclusion or claiming complete
guideline coverage.

Goal adaptations are categorical:

- `fat_loss`: lower-energy-density choices, vegetables first, whole grains, lean
  protein foods, and limits on fried/sugary options; no fixed deficit.
- `basic_strength`: distribute protein-containing foods across meals and place a
  grain/fruit option near the training session when practical; no supplement or
  surplus claim.
- `posture_improvement`: balanced-maintenance template. The Phase 4 active-plan
  contract supports only `posture_improvement`, `fat_loss`, and
  `basic_strength`; any other value fails closed as an unsupported plan goal.

Training and rest templates keep the same daily reference envelope. Training
days alter food selection/distribution and show a bounded
`choose_meal_nearest_training` guidance code; they do not select a specific meal
because the current training plan has no time-of-day field, and they do not
silently add calories. Rest days emphasize whole grains, legumes, and the
ordinary balanced-plate distribution.

## Portion Contract

Internal grams and food-group equivalents are authoritative. Household units
are bounded display aids, never inferred from a photo:

| Display unit | Version-1 estimate | Required label |
| --- | --- | --- |
| `small_bowl_cooked_staple` | `150-200 g` cooked staple; catalog stores dry/raw guideline equivalent separately | bowl size and water absorption vary |
| `fist_vegetable` | `100-150 g` edible vegetables | fist size and preparation vary |
| `fist_fruit` | `150-200 g` edible fruit | item size and edible fraction vary |
| `palm_protein_food` | `80-120 g` cooked edible protein food | thickness and cooking loss vary |
| `cup_dairy` | `250-300 mL` | check package volume and allergens |
| `thumb_nuts` | about `10 g` | not available when peanut/tree-nut excluded |

Every UI amount shows a range and `approximate` marker. It must not render
`173 g`, `1842 kcal`, or similarly unsupported precision. API schemas use
integer bounds and reviewed display codes rather than prose generated from raw
floating-point calculations.

## Food Catalog, Exclusions, And Media

The versioned catalog is a reviewed static dataset, not a user-editable table.
Version 1 must include at least 24 China-common generic foods across grains,
tubers, vegetables, fruit, animal protein, eggs, dairy, soy, and nuts. Each
replacement-capable exchange group has at least three candidates before user
exclusions.

Every food record includes:

- stable project `food_id`, Chinese display name, source English description,
  category, preparation state, and exchange group
- FDC ID/data type/publication date or explicit project-authored-only lineage
- per-100-g energy, protein, carbohydrate, fat, fibre where the source provides
  them; missing remains null and never becomes zero
- edible portion range, guideline-equivalent amount, household unit, and
  preparation note code
- allergen codes, ingredient/category tags, supported exclusion codes, and
  replacement constraints
- optional image key, source record version, manual-review state, and
  quality-limit codes. An absent image uses an accessible text fallback; an
  unrelated image is never reused to make the catalog look complete

A record with missing/non-finite energy, protein, carbohydrate, or fat remains
traceable catalog information but is not `generation_eligible`. Fibre may remain
null and is never imputed; the product therefore reports the adult fibre
reference but does not claim that a generated template proves fibre adequacy.

Only the eight structured allergen categories drive automatic exclusion:
`gluten_cereal`, `crustacean`, `fish`, `egg`, `peanut`, `soy`, `milk`, and
`tree_nut`. A matching food is removed before generation. Every supported
exclusion code is an allowlisted catalog-policy key that expands to a reviewed,
explicit set of food IDs; arbitrary client tags and substring matching are
forbidden. Unknown codes, non-empty unresolved legacy text, or too few safe
candidates yield `clarification_required`/`no_safe_candidate`; the engine never
reintroduces a blocked food to complete a template.

Replacement requires the same exchange group and an overlapping portion range.
It must preserve all daily validators, remain disjoint from allergy/exclusion
sets, and expose at least two alternatives when available. “Equivalent” means a
versioned food-group/portion exchange, not nutritionally identical.

Version 1 media includes at least 12 real ingredient photos and three real
prepared-meal examples; at least 12 distinct food records therefore have a
reviewed ingredient image. Only CC0/public-domain files pass import. Images are
locally resized/cropped without health claims; originals are not required in the
build. The app has an attribution/source screen even where attribution is not a
license condition. A manifest validator verifies file checksum, dimensions,
license allowlist, source URL, and orphan references.

## Meal Draft And Validation

A recommendation payload contains:

- immutable recommendation/version IDs and status
- eligibility/gate codes and all source/policy/catalog version pins
- rounded nutrition reference ranges and rationale codes
- `training_day` and `rest_day`, each with exactly breakfast/lunch/dinner
- meal items with food ID, gram range, household-unit range, preparation code,
  allergen codes, optional image key, and at least two validated alternatives
  where the safe catalog permits
- daily food-group summaries, guideline-source codes, uncertainty notices, and
  cross-contact warning
- confirmation/replacement diff metadata, never meal-completion state

Each variant contains exactly three meals and no snack/intake event. Internally,
the validator checks the catalog-energy midpoint against the broad guideline
meal shares: breakfast `25-30%`, lunch `30-40%`, and dinner `30-35%` of the
variant total. It also checks daily food-group equivalents. These internal
checks do not turn the output into measured intake, and the UI does not expose
exact meal calories or a claim of nutrient adequacy.

The deterministic generator selects only from the filtered catalog. Identical
canonical input yields identical output. It may rotate templates using a stable
hash of non-secret version/context codes, but it cannot use randomness, model
output, or user ID as displayed content.

The validator independently checks:

- current safety decision is still eligible/conservative
- all version/freshness pins match
- three-meal structure and training/rest variants are complete
- every food exists in the pinned catalog and media references resolve
- no allergy/exclusion intersection
- portion and guideline-equivalent bounds
- required food-group coverage and Chinese Dietary Guidelines ranges
- replacement equivalence and alternative uniqueness
- no unsupported exact value, disease/supplement claim, or tracking field

Generator success is not validator success. Drafts that fail validation are not
persisted or returned as usable.

## Persistence And State

`nutrition_recommendations` stores immutable owned versions with statuses
`draft`, `active`, and `superseded`. It stores only recommendation payloads,
version/freshness metadata, validation codes, and timestamps. It does not store
user prose, model output, allergy notes, meal intake, completion, or adherence.
Payloads and version pins are immutable after insertion; only the reviewed
status transition and bounded supersession metadata may change.

Invariants:

- unique `(user_id, version)`
- at most one current draft per user; regeneration atomically supersedes the
  prior draft and inserts a new version
- at most one active recommendation per user, enforced by PostgreSQL partial
  unique indexes for `draft` and `active` plus the same transaction/lock
  invariants on SQLite
- draft confirmation uses owner lock, expected version/fingerprint, latest
  context rebuild, deterministic revalidation, and idempotency
- activating a draft atomically supersedes the prior active version
- replacement creates a new immutable active version only after a previewed
  diff and explicit user confirmation
- stale, foreign, failed, or invalid drafts never change active state
- payload schema and policy/catalog/source/media versions are pinned

Reuse the existing reviewed idempotency table and lock helpers with nutrition-
specific operation namespaces. A partial idempotency hit or mismatched result
reference fails closed. Migration `0009` adds the nullable structured nutrition
profile fields; migration `0010` adds recommendation persistence. Both must
upgrade/downgrade on SQLite and PostgreSQL and leave no orphan column, index, or
constraint.

Nutrition-data deletion removes all owned recommendation rows and nutrition
idempotency entries, clears `food_allergen_codes` and `excluded_food_codes` to
`null` with a new health-profile version, and removes pending proposals/audit
rows that explicitly reference a nutrition Tool, entry, or recommendation. It
preserves independent account, legacy health-profile, posture, training, and
general Agent conversation data. The UI states that general Agent history has
its own `/agent/data` deletion control. Project-wide account deletion remains a
Phase 8 integration gate and must explicitly include every nutrition row and
reference.

## API Contract

All endpoints are JWT-authenticated except the public static catalog list only
if implementation proves it contains no user state. The conservative default is
JWT for every endpoint.

```text
GET    /api/v1/nutrition/eligibility
GET    /api/v1/nutrition/targets
GET    /api/v1/nutrition/foods
GET    /api/v1/nutrition/foods/{food_id}
POST   /api/v1/nutrition/recommendations/drafts
GET    /api/v1/nutrition/recommendations/draft
GET    /api/v1/nutrition/recommendations/active
POST   /api/v1/nutrition/recommendations/{draft_id}:confirm
POST   /api/v1/nutrition/recommendations/{active_id}/replacements:preview
POST   /api/v1/nutrition/recommendations/{active_id}/replacements:confirm
DELETE /api/v1/nutrition/data
```

Every context-sensitive request requires a valid IANA timezone. The server
derives current local date; clients cannot provide risk tier, user ID, profile
version, check-in result, plan state, food nutrient value, candidate set, or
validation result. State-changing POST endpoints require a strict request-body
`idempotency_key`, matching the existing training and Agent application-service
contract; preview reads do not. `DELETE /nutrition/data` is idempotent by its
post-delete state and accepts no request body. Identity and safety state remain
server-derived.

Stable error/result codes distinguish missing data, restricted/limited scope,
red flag, unresolved exclusion, no safe candidate, stale context, invalid
replacement, idempotency conflict, and service failure. Cross-user/missing IDs
are non-enumerating. OpenAPI tests cover auth, strict unknown-field rejection,
serialization, ownership, replay/conflict, and failure envelopes.

## Agent Tool Contract

Extend the static registry only after the nutrition domain API is accepted:

| Tool | Class | Behavior |
| --- | --- | --- |
| `calculate_nutrition_targets` | read | current owned deterministic target/gate codes; no model arithmetic |
| `convert_targets_to_portions` | read | current target-to-household range projection |
| `generate_meal_plan_draft` | proposal/write | explicit confirmation creates a validated draft only; it does not activate it |
| `replace_food` | proposal/write | explicit typed diff + confirmation creates a validated active version |
| `validate_nutrition_plan` | read | validate an owned current draft/active version; generation/replacement also invoke validation unconditionally |

Add `nutrition_plan` as an owned entry type. Provider context contains only
gate/result codes, version pins, recommendation presence/status, food IDs needed
for the selected entry, and bounded rationale codes. It excludes body values,
allergy text, exact exclusions, notes, complete catalog, complete meal payload,
and other accounts.

The provider cannot supply nutrient values, bypass exclusions, choose safety
outcomes, register tools, or execute confirmation. Unknown nutrition intents and
special/disease diets receive fixed unsupported messages. Button and Agent paths
call the same service/validator and produce the same domain result.

## Flutter Contract

- Add a nutrition recommendation surface under `计划`; do not add a diary tab.
- Show eligibility/missing/limited states before any generation action.
- Let the user review target ranges, source/uncertainty notices, training/rest
  three-meal templates, images, portions, allergens, and alternatives.
- Confirmation shows an explicit diff and never labels a draft as active.
- Replacement preview shows from/to food, portion-range comparison, allergen
  status, and resulting version before confirmation.
- Health profile provides structured selection for the eight allergens and
  catalog-backed exclusions. `null` means unanswered; `[]` means answered none.
- Every media surface links to source/attribution details and has an accessible
  text fallback.
- Logout, account switch, auth failure, profile change, safety change, or
  deletion invalidates in-memory nutrition state and late responses.
- No screen contains “已吃”, calories consumed/remaining, meal completion,
  streak, photo-food input, barcode, or intake chart.

## Verification And Exit Criteria

Phase 6 is complete only when all are true on an exact SHA:

1. Source/license manifests validate, every food/media item is traceable, and no
   Open Food Facts or GPL-derived artifact is present.
2. Formula golden tests, boundary tests, missing/NaN/infinity tests, age/BMI/
   energy-envelope scope tests, and no-default tests pass.
3. Every calculate/generate/confirm/preview/replace path rebuilds latest safety
   context; restricted/red-flag/unknown cases have zero recommendation writes.
4. Allergy/exclusion property tests prove blocked foods never appear in meals or
   alternatives; unknown text/codes fail closed.
5. Deterministic generation, independent validation, training/rest differences,
   goal rationale, portion ranges, and at least two equivalent replacements are
   covered without AI.
6. Migration upgrade/downgrade, one-active invariant, immutable versions,
   ownership, idempotency, stale context, rollback, deletion, SQLite parity, and
   PostgreSQL constraints pass.
7. Agent registry/context/proposal/confirmation tests prove no direct write,
   invented nutrient value, hidden Tool, or safety bypass.
8. Flutter analyze/full tests pass; Android synthetic smoke covers profile,
   check-in, active training plan, draft, confirm, images, replacement, offline/
   failure state, and data deletion.
9. Schema/code/UI audit finds no intake-log, photo recognition, barcode,
   tracking, special-diet claim, exact deficit/surplus, or live-AI dependency.
10. Local Fast/Full with PostgreSQL and GitHub Fast/Flutter/Full CI pass on the
    final SHA. No real health data, credentials, or external paid calls are used.

## Rollback

- Disable nutrition routes/navigation with a dedicated default-off feature flag
  if a post-acceptance safety or data issue appears; existing posture/training/
  Agent core remains usable.
- Revert the Phase 6 implementation commits and downgrade migrations `0010`
  then `0009` only on a disposable/local database or with an explicit data-loss
  decision.
- Catalog/media releases are independently versioned and removable; a withdrawn
  item is removed from future generation and old active versions become
  unavailable/stale rather than silently substituting an unreviewed food.
- Never “roll back” a blocked safety decision by using an older profile,
  check-in, catalog, or policy snapshot.
