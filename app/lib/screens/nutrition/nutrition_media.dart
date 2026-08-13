class NutritionMediaAttribution {
  final String author;
  final String license;
  final String sourceUrl;

  const NutritionMediaAttribution({
    required this.author,
    required this.license,
    required this.sourceUrl,
  });
}

const nutritionMediaAttributions = <String, NutritionMediaAttribution>{
  'assets/images/nutrition/ingredients/rice_white.jpg': NutritionMediaAttribution(
    author: 'Andy Li',
    license: 'CC0-1.0',
    sourceUrl:
        'https://commons.wikimedia.org/wiki/File:Package-free_rices_in_HISBE,_Brighton.jpg',
  ),
  'assets/images/nutrition/ingredients/oats_cooked.jpg':
      NutritionMediaAttribution(
        author: 'en:user:Hankwang',
        license: 'Public Domain',
        sourceUrl: 'https://commons.wikimedia.org/wiki/File:Rolled_oats.jpg',
      ),
  'assets/images/nutrition/ingredients/sweet_potato_boiled.jpg':
      NutritionMediaAttribution(
        author: 'JacquesDemien',
        license: 'CC0-1.0',
        sourceUrl: 'https://commons.wikimedia.org/wiki/File:A_sweet_potato.jpg',
      ),
  'assets/images/nutrition/ingredients/broccoli.jpg': NutritionMediaAttribution(
    author: 'Alabama Extension',
    license: 'CC0-1.0',
    sourceUrl: 'https://commons.wikimedia.org/wiki/File:Cutting_Broccoli.jpg',
  ),
  'assets/images/nutrition/ingredients/apple_raw.jpg': NutritionMediaAttribution(
    author: 'Eunice Ameh',
    license: 'CC0-1.0',
    sourceUrl:
        'https://commons.wikimedia.org/wiki/File:Apple_fruit_in_illorin.jpg',
  ),
  'assets/images/nutrition/ingredients/banana_raw.jpg':
      NutritionMediaAttribution(
        author: 'Shewagramji',
        license: 'CC0-1.0',
        sourceUrl: 'https://commons.wikimedia.org/wiki/File:Banana*.jpg',
      ),
  'assets/images/nutrition/ingredients/orange_raw.jpg':
      NutritionMediaAttribution(
        author: 'Raizkgh',
        license: 'CC0-1.0',
        sourceUrl: 'https://commons.wikimedia.org/wiki/File:Citrus_Orange.jpg',
      ),
  'assets/images/nutrition/ingredients/chicken_breast.jpg':
      NutritionMediaAttribution(
        author: 'ReshmaNazeerhussain',
        license: 'CC0-1.0',
        sourceUrl: 'https://commons.wikimedia.org/wiki/File:Breast_chicken.jpg',
      ),
  'assets/images/nutrition/ingredients/egg_chicken.jpg':
      NutritionMediaAttribution(
        author: 'Achim',
        license: 'CC0-1.0',
        sourceUrl:
            'https://commons.wikimedia.org/wiki/File:Ten_chicken_eggs.jpg',
      ),
  'assets/images/nutrition/ingredients/milk_whole.jpg':
      NutritionMediaAttribution(
        author: 'Couleur',
        license: 'CC0-1.0',
        sourceUrl:
            'https://commons.wikimedia.org/wiki/File:Milk-2474993_1920.jpg',
      ),
  'assets/images/nutrition/ingredients/tofu_firm.jpg':
      NutritionMediaAttribution(
        author: 'Fumikas Sagisavas',
        license: 'CC0-1.0',
        sourceUrl: 'https://commons.wikimedia.org/wiki/File:Soft_tofu_(1).jpg',
      ),
  'assets/images/nutrition/ingredients/almonds_raw.jpg':
      NutritionMediaAttribution(
        author: 'Ranjithkumar Murugesan',
        license: 'CC0-1.0',
        sourceUrl:
            'https://commons.wikimedia.org/wiki/File:KASHMIRI_MAMRA_ALMONDS.jpg',
      ),
  'assets/images/nutrition/meals/meal_chicken_salad.jpg': NutritionMediaAttribution(
    author: 'Daderot',
    license: 'CC0-1.0',
    sourceUrl:
        'https://commons.wikimedia.org/wiki/File:Chicken_breast_and_salad_-_Massachusetts.jpg',
  ),
  'assets/images/nutrition/meals/meal_rice_vegetables.jpg':
      NutritionMediaAttribution(
        author: 'Adesolive',
        license: 'CC0-1.0',
        sourceUrl:
            'https://commons.wikimedia.org/wiki/File:Rice_and_mixed_vegetables.jpg',
      ),
  'assets/images/nutrition/meals/meal_vegetable_rice.jpg':
      NutritionMediaAttribution(
        author: 'safaritravelplus',
        license: 'CC0-1.0',
        sourceUrl:
            'https://commons.wikimedia.org/wiki/File:Vegetable_rice_image.jpg',
      ),
};
