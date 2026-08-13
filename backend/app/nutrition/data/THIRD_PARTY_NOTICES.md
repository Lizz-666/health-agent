# Nutrition Data And Media Notices

## USDA FoodData Central

The food-composition subset is derived from USDA FoodData Central Foundation
Foods 04/2026 and the final SR Legacy 04/2018 release. USDA states that FoodData
Central data are in the public domain (CC0-equivalent) and asks products to cite
USDA Agricultural Research Service FoodData Central as the source.

Only the FDC IDs recorded in `fdc_foundation_subset.v1.json` and
`fdc_sr_legacy_subset.v1.json` are included. Chinese names, exchange groups,
household portions, allergen mappings, and preparation codes are separately
reviewed project-authored metadata and are not USDA claims.

Source and update/removal details are in `source_manifest.v1.json`.

## Wikimedia Commons

Nutrition photos are copied locally only when the individual Commons file page
declares CC0 or public-domain status. `media_manifest.v1.json` records each file
page, binary URL, author, transformation, dimensions, license, and final binary
SHA-256. Commons provides no warranty. Images are illustrative and do not prove
portion size, ingredients, allergen absence, or nutritional adequacy.

To remove a disputed file, delete the local asset and its manifest entry,
clear the matching catalog `image_key` (or replace it with a newly reviewed
asset), increment the media/catalog version, and run the release audit.

## Excluded Inputs

No Open Food Facts database/content/image data and no OpenNutriTracker code,
schema, UI, or import pipeline are included. No branded FDC records are used.
