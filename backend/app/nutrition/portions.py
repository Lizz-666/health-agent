"""Reviewed household-unit display projections."""
from app.nutrition.schemas import PortionProjection

_PORTIONS = {
    "small_bowl_cooked_staple": (150, 200, "g", "bowl_size_and_absorption_vary"),
    "fist_vegetable": (100, 150, "g", "fist_size_and_preparation_vary"),
    "fist_fruit": (150, 200, "g", "item_size_and_edible_fraction_vary"),
    "palm_protein_food": (80, 120, "g", "thickness_and_cooking_loss_vary"),
    "cup_dairy": (250, 300, "ml", "check_package_volume_and_allergens"),
    "thumb_nuts": (8, 12, "g", "not_available_when_nut_allergen_excluded"),
}


def project_portion(unit_code: str) -> PortionProjection:
    try:
        minimum, maximum, label, limitation = _PORTIONS[unit_code]
    except KeyError as exc:
        raise ValueError("unsupported household unit") from exc
    return PortionProjection(
        unit_code=unit_code,
        amount_min=minimum,
        amount_max=maximum,
        unit_label=label,
        limitation_code=limitation,
    )


def supported_portion_codes() -> tuple[str, ...]:
    return tuple(_PORTIONS)
