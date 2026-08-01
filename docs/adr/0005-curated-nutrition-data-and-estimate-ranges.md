# ADR-0005: Curated Nutrition Data And Estimate Ranges

## Status

Accepted at Phase 6 Gate 0 (2026-08-01). Contract candidate `0109f96` passed
exact-SHA GitHub Fast/Flutter/Full CI run `30696443907`.

## Context

Phase 6 needs deterministic nutrition estimates, common-food composition,
household portions, substitutions, and real food images. The product is for
ordinary adult wellness and explicitly rejects false precision, model-invented
nutrients, disease diets, and nutrition tracking.

The current account has age, height, weight, and a field named `gender`. The
Mifflin-St Jeor paper publishes separate male/female equations, while the field's
semantics are not a reviewed physiological-sex contract. China-specific food
composition data is not available under a clearly redistributable repository
license in the current evidence. Open Food Facts is reusable only under database
and image obligations that are undesirable for this small private catalog.

## Decision

Calculate both published Mifflin-St Jeor branches and report one outward-rounded
range after the Chinese DRIs 2023 low-intensity PAL `1.40` and a versioned
uncertainty allowance. Do not use `gender`
to select a branch. Treat the result as estimated reference energy, not a calorie
prescription or measured expenditure. Chinese DRIs 2023 and Chinese Dietary
Guidelines 2022 supply the adult reference ranges and food-group structure.
The lower display bound is the lower branch times PAL and `0.90`, rounded down;
the upper display bound is the upper branch times PAL and `1.10`, rounded up.
The mean of the two PAL-adjusted branches is used only for the supported-scope
envelope check.

Self-host a small reviewed USDA FoodData Central subset. Only pinned Foundation
Foods and necessary SR Legacy records are accepted. Every normalized record has
an FDC ID, source data type/date/release, raw checksum, field map, transformation
version, and manual review state. Missing values remain missing. The application
has no runtime FDC API dependency or API key.

Exclude Open Food Facts from Phase 6 because ODbL/DbCL database obligations,
CC BY-SA product images, and independent packaging/trademark rights would add
distribution and attribution complexity disproportionate to the MVP. Do not
copy OpenNutriTracker GPL-3.0 code, UI, schema, or import/tracking logic.

Use locally stored real ingredient/meal images only when each Wikimedia Commons
file page shows CC0 or public-domain status. Record page URL, author, license,
retrieval date, checksum, transformation, attribution, and removal path. Do not
copy official Chinese guideline graphics because their stated reuse terms limit
commercial use.

## Alternatives Considered

1. **Choose one equation branch from `gender`.** Rejected because it silently
   changes an identity-style account field into an unreviewed physiological
   input and creates false precision.
2. **Use a single average-person Chinese energy table.** Rejected as the only
   estimate because it ignores available body measurements. It remains a scope
   and sanity envelope.
3. **Use Open Food Facts live or merge its export.** Rejected for Phase 6 due to
   database share-alike/attribution and product-image rights complexity.
4. **Call FDC at runtime.** Rejected because outages, API-key handling, source
   drift, and unreviewed records would change health output without a release.
5. **Generate food images with AI.** Rejected because the roadmap requires real
   standard ingredient and meal examples and generated imagery could misstate
   portions.
6. **Use guideline graphics in-app.** Rejected because the official page limits
   them to attributed public-interest, non-commercial use.

## Consequences

- Energy ranges are wider and less personalized than a single-branch calculator;
  that is an intentional honesty/safety trade-off.
- Applying both Mifflin branches, PAL `1.40`, and a product uncertainty allowance
  is an explicit product estimate policy, not a validated confidence interval
  or a replacement for measured energy expenditure.
- China-common labels and substitutions need manual mapping and review, and USDA
  nutrient values retain a documented geographic limitation.
- Data/media updates happen through explicit reviewed releases, not silent API
  refreshes.
- A future China-specific database or narrower equation needs a new source,
  license, field-semantics, migration, and validation decision.
- Binary assets increase repository size but make offline behavior and exact
  license/version acceptance reproducible.

## Follow-Up

- Add strict source/catalog/media manifest validators before domain generation.
- Record rejected candidates and per-file removal procedures in third-party
  notices.
- Re-audit current source versions and image pages at every catalog release and
  before any public distribution.
