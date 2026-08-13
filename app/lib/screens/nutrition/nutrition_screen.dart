import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/constants.dart';
import '../../models/nutrition.dart';
import '../../providers/assessment_provider.dart' show LoadStatus;
import '../../providers/nutrition_provider.dart';
import 'nutrition_media.dart';

class NutritionScreen extends ConsumerStatefulWidget {
  const NutritionScreen({super.key});

  @override
  ConsumerState<NutritionScreen> createState() => _NutritionScreenState();
}

class _NutritionScreenState extends ConsumerState<NutritionScreen> {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      ref.read(nutritionProvider.notifier).load();
    });
  }

  @override
  Widget build(BuildContext context) {
    final state = ref.watch(nutritionProvider);
    return Scaffold(
      appBar: AppBar(
        title: const Text('饮食建议'),
        actions: [
          IconButton(
            key: const Key('nutrition-delete-button'),
            tooltip: '删除饮食建议数据',
            onPressed: () => _confirmDelete(context),
            icon: const Icon(Icons.delete_outline),
          ),
        ],
      ),
      body: SafeArea(child: _body(state)),
    );
  }

  Widget _body(NutritionState state) {
    if (state.status == LoadStatus.loading && state.eligibility == null) {
      return const Center(child: CircularProgressIndicator());
    }
    if (state.status == LoadStatus.parseError) {
      return _StatusView(
        icon: Icons.error_outline,
        title: '数据异常',
        detail: '服务返回内容无法安全解析，未生成或更新饮食建议。',
        onRetry: () => ref.read(nutritionProvider.notifier).load(),
      );
    }
    if (state.status == LoadStatus.networkError) {
      final disabled = state.errorCode == 'nutrition_runtime_disabled';
      return _StatusView(
        icon: disabled ? Icons.pause_circle_outline : Icons.cloud_off,
        title: disabled ? '饮食建议暂未开放' : '网络连接失败',
        detail: disabled ? '当前构建未启用饮食建议服务。' : '饮食建议加载失败，请检查网络后重试。',
        onRetry: disabled
            ? null
            : () => ref.read(nutritionProvider.notifier).load(),
      );
    }
    final eligibility = state.eligibility;
    if (eligibility == null) {
      return _StatusView(
        icon: Icons.restaurant_menu,
        title: '尚未加载饮食建议',
        detail: '饮食建议需要当前健康档案、风险筛查、今日状态和训练计划。',
        onRetry: () => ref.read(nutritionProvider.notifier).load(),
      );
    }
    if (!eligibility.gate.allowsRecommendation) {
      return _EligibilityView(eligibility: eligibility);
    }
    if (state.active != null && state.draft != null) {
      return _ActiveAndDraftNutritionView(
        targets: state.targets,
        active: _RecommendationView(
          recommendation: state.active!,
          foods: state.foods,
          active: true,
          onAlternative: _previewAlternative,
        ),
        draft: _DraftReview(
          recommendation: state.draft!,
          foods: state.foods,
          onConfirm: () => ref.read(nutritionProvider.notifier).confirmDraft(),
        ),
        onRefresh: () => ref.read(nutritionProvider.notifier).load(),
      );
    }
    return RefreshIndicator(
      onRefresh: () => ref.read(nutritionProvider.notifier).load(),
      child: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          if (state.targets != null) _TargetsCard(response: state.targets!),
          const SizedBox(height: 12),
          if (state.active != null)
            _RecommendationView(
              recommendation: state.active!,
              foods: state.foods,
              active: true,
              onAlternative: _previewAlternative,
            )
          else if (state.draft != null)
            _DraftReview(
              recommendation: state.draft!,
              foods: state.foods,
              onConfirm: () =>
                  ref.read(nutritionProvider.notifier).confirmDraft(),
            )
          else
            _GenerateCard(
              onGenerate: () =>
                  ref.read(nutritionProvider.notifier).createDraft(),
            ),
          if (state.replacementPreview != null) ...[
            const SizedBox(height: 12),
            _ReplacementPreview(
              recommendation: state.replacementPreview!,
              foods: state.foods,
              onConfirm: () =>
                  ref.read(nutritionProvider.notifier).confirmReplacement(),
            ),
          ],
          if (state.error != null) ...[
            const SizedBox(height: 12),
            Semantics(
              key: const Key('nutrition-error-live'),
              liveRegion: true,
              label: '饮食建议操作未完成，请重试。',
              excludeSemantics: true,
              child: const Text(
                '饮食建议操作未完成，请重试。',
                style: TextStyle(color: Color(AppConstants.severeColor)),
              ),
            ),
          ],
          const SizedBox(height: 20),
          const Text(
            '本功能提供一般健康饮食教育，不用于疾病治疗或特殊饮食处方，也不记录实际饮食。食物图片仅作识别参考。',
            key: Key('nutrition-scope-notice'),
            style: TextStyle(fontSize: 12),
          ),
        ],
      ),
    );
  }

  Future<void> _previewAlternative(
    NutritionDayKind dayKind,
    NutritionMeal meal,
    int itemIndex,
    MealFoodItem item,
    FoodAlternative alternative,
  ) async {
    await ref
        .read(nutritionProvider.notifier)
        .previewReplacement(
          ReplacementSelection(
            dayKind: dayKind,
            meal: meal,
            itemIndex: itemIndex,
            fromFoodId: item.foodId,
            toFoodId: alternative.foodId,
          ),
        );
  }

  Future<void> _confirmDelete(BuildContext context) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('删除饮食建议数据？'),
        content: const Text('这会删除饮食建议草案、激活版本和相关健康助手记录，不会删除训练计划。'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('取消'),
          ),
          FilledButton(
            key: const Key('nutrition-delete-confirm'),
            onPressed: () => Navigator.pop(context, true),
            child: const Text('确认删除'),
          ),
        ],
      ),
    );
    if (confirmed == true) {
      await ref.read(nutritionProvider.notifier).deleteNutritionData();
    }
  }
}

class _ActiveAndDraftNutritionView extends StatelessWidget {
  final NutritionTargetsResponse? targets;
  final Widget active;
  final Widget draft;
  final Future<void> Function() onRefresh;

  const _ActiveAndDraftNutritionView({
    required this.targets,
    required this.active,
    required this.draft,
    required this.onRefresh,
  });

  @override
  Widget build(BuildContext context) {
    return DefaultTabController(
      length: 2,
      child: Column(
        children: [
          const TabBar(
            tabs: [
              Tab(key: Key('nutrition-active-tab'), text: '当前生效'),
              Tab(key: Key('nutrition-draft-tab'), text: '待确认草案'),
            ],
          ),
          Expanded(child: TabBarView(children: [_tab(active), _tab(draft)])),
        ],
      ),
    );
  }

  Widget _tab(Widget content) => RefreshIndicator(
    onRefresh: onRefresh,
    child: ListView(
      physics: const AlwaysScrollableScrollPhysics(),
      padding: const EdgeInsets.all(16),
      children: [
        if (targets != null) _TargetsCard(response: targets!),
        if (targets != null) const SizedBox(height: 12),
        content,
        const SizedBox(height: 20),
        const Text(
          '本功能提供一般健康饮食教育，不用于疾病治疗或特殊饮食处方，也不记录实际饮食。食物图片仅作识别参考。',
          key: Key('nutrition-scope-notice'),
          style: TextStyle(fontSize: 12),
        ),
      ],
    ),
  );
}

class _TargetsCard extends StatelessWidget {
  final NutritionTargetsResponse response;
  const _TargetsCard({required this.response});

  @override
  Widget build(BuildContext context) {
    final t = response.targets;
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('每日参考范围', style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: 8),
            Text('能量 ${t.energyLowKcal}-${t.energyHighKcal} 千卡'),
            Text('蛋白质 ${t.proteinGMin}-${t.proteinGMax} 克'),
            Text('膳食纤维 ${t.fibreGMin}-${t.fibreGMax} 克'),
            Text('饮水 ${t.drinkingWaterMlMin}-${t.drinkingWaterMlMax} 毫升'),
            const SizedBox(height: 8),
            const Text(
              '范围来自版本化指南与审核食物数据，是产品估算区间，不是精确处方或置信区间。',
              key: Key('nutrition-source-uncertainty'),
              style: TextStyle(fontSize: 12),
            ),
            Text(
              '策略 ${response.versions.policyVersion} · 食物库 ${response.versions.catalogVersion}',
              style: const TextStyle(fontSize: 11),
            ),
          ],
        ),
      ),
    );
  }
}

class _GenerateCard extends StatelessWidget {
  final VoidCallback onGenerate;
  const _GenerateCard({required this.onGenerate});

  @override
  Widget build(BuildContext context) => Card(
    child: Padding(
      padding: const EdgeInsets.all(16),
      child: Column(
        children: [
          const Text('生成训练日和休息日饮食建议草案。生成不会自动激活。'),
          const SizedBox(height: 12),
          FilledButton(
            key: const Key('nutrition-generate-draft'),
            onPressed: onGenerate,
            child: const Text('生成草案'),
          ),
        ],
      ),
    ),
  );
}

class _DraftReview extends StatelessWidget {
  final NutritionRecommendation recommendation;
  final List<NutritionFood> foods;
  final VoidCallback onConfirm;
  const _DraftReview({
    required this.recommendation,
    required this.foods,
    required this.onConfirm,
  });

  @override
  Widget build(BuildContext context) => Column(
    crossAxisAlignment: CrossAxisAlignment.stretch,
    children: [
      const Text('草案尚未激活', key: Key('nutrition-draft-label')),
      _RecommendationView(
        recommendation: recommendation,
        foods: foods,
        active: false,
      ),
      FilledButton(
        key: const Key('nutrition-confirm-draft'),
        onPressed: onConfirm,
        child: const Text('确认并激活'),
      ),
    ],
  );
}

class _RecommendationView extends StatelessWidget {
  final NutritionRecommendation recommendation;
  final List<NutritionFood> foods;
  final bool active;
  final void Function(
    NutritionDayKind,
    NutritionMeal,
    int,
    MealFoodItem,
    FoodAlternative,
  )?
  onAlternative;

  const _RecommendationView({
    required this.recommendation,
    required this.foods,
    required this.active,
    this.onAlternative,
  });

  @override
  Widget build(BuildContext context) {
    final foodMap = {for (final food in foods) food.foodId: food};
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          active ? '当前激活建议 v${recommendation.version}' : '建议草案',
          key: Key(
            active ? 'nutrition-active-label' : 'nutrition-review-label',
          ),
          style: Theme.of(context).textTheme.titleMedium,
        ),
        const Text('如有食物过敏，请同时核对包装标签和交叉接触风险。'),
        for (final variant in recommendation.payload.variants)
          ExpansionTile(
            initiallyExpanded: variant.dayKind == NutritionDayKind.trainingDay,
            title: Text(
              variant.dayKind == NutritionDayKind.trainingDay
                  ? '训练日模板'
                  : '休息日模板',
            ),
            children: [
              for (final meal in variant.meals)
                _MealCard(
                  dayKind: variant.dayKind,
                  meal: meal,
                  foods: foodMap,
                  alternativesEnabled: active,
                  onAlternative: onAlternative,
                ),
            ],
          ),
      ],
    );
  }
}

class _MealCard extends StatelessWidget {
  final NutritionDayKind dayKind;
  final MealTemplate meal;
  final Map<String, NutritionFood> foods;
  final bool alternativesEnabled;
  final void Function(
    NutritionDayKind,
    NutritionMeal,
    int,
    MealFoodItem,
    FoodAlternative,
  )?
  onAlternative;

  const _MealCard({
    required this.dayKind,
    required this.meal,
    required this.foods,
    required this.alternativesEnabled,
    required this.onAlternative,
  });

  @override
  Widget build(BuildContext context) => Card(
    margin: const EdgeInsets.fromLTRB(12, 4, 12, 8),
    child: Column(
      children: [
        ListTile(title: Text(_mealLabel(meal.meal))),
        for (var index = 0; index < meal.items.length; index++)
          _FoodRow(
            dayKind: dayKind,
            meal: meal.meal,
            index: index,
            item: meal.items[index],
            food: foods[meal.items[index].foodId],
            foods: foods,
            alternativesEnabled: alternativesEnabled,
            onAlternative: onAlternative,
          ),
      ],
    ),
  );
}

class _FoodRow extends StatelessWidget {
  final NutritionDayKind dayKind;
  final NutritionMeal meal;
  final int index;
  final MealFoodItem item;
  final NutritionFood? food;
  final Map<String, NutritionFood> foods;
  final bool alternativesEnabled;
  final void Function(
    NutritionDayKind,
    NutritionMeal,
    int,
    MealFoodItem,
    FoodAlternative,
  )?
  onAlternative;

  const _FoodRow({
    required this.dayKind,
    required this.meal,
    required this.index,
    required this.item,
    required this.food,
    required this.foods,
    required this.alternativesEnabled,
    required this.onAlternative,
  });

  @override
  Widget build(BuildContext context) {
    final foodName = food?.nameZh ?? '食物信息暂不可用';
    return ListTile(
      leading: NutritionFoodImage(
        imageKey: item.imageKey ?? food?.imageKey,
        semanticLabel: foodName,
      ),
      title: Text(foodName),
      subtitle: Text(
        '${item.gramMin}-${item.gramMax} 克，约 ${item.householdPortion.amountMin}-${item.householdPortion.amountMax}${item.householdPortion.unitLabel}',
      ),
      trailing: alternativesEnabled && item.alternatives.isNotEmpty
          ? PopupMenuButton<FoodAlternative>(
              key: Key('nutrition-replace-${dayKind.wire}-${meal.wire}-$index'),
              tooltip: '预览替换',
              onSelected: (alternative) =>
                  onAlternative?.call(dayKind, meal, index, item, alternative),
              itemBuilder: (_) => item.alternatives
                  .map(
                    (alternative) => PopupMenuItem(
                      value: alternative,
                      child: Text(
                        '替换为 ${foods[alternative.foodId]?.nameZh ?? '食物信息暂不可用'}',
                      ),
                    ),
                  )
                  .toList(),
            )
          : null,
    );
  }
}

class NutritionFoodImage extends StatelessWidget {
  final String? imageKey;
  final String semanticLabel;
  final double size;
  const NutritionFoodImage({
    super.key,
    required this.imageKey,
    required this.semanticLabel,
    this.size = 56,
  });

  @override
  Widget build(BuildContext context) {
    final attribution = imageKey == null
        ? null
        : nutritionMediaAttributions[imageKey];
    final image = imageKey == null || attribution == null
        ? _fallback()
        : Image.asset(
            imageKey!,
            width: size,
            height: size,
            fit: BoxFit.cover,
            errorBuilder: (_, _, _) => _fallback(),
          );
    return Semantics(
      image: true,
      label: '$semanticLabel 食物参考图片',
      child: Stack(
        children: [
          ClipRRect(borderRadius: BorderRadius.circular(8), child: image),
          if (attribution != null)
            Positioned(
              right: 0,
              bottom: 0,
              child: InkWell(
                key: Key('nutrition-attribution-$imageKey'),
                onTap: () => showDialog<void>(
                  context: context,
                  builder: (_) => AlertDialog(
                    title: const Text('图片来源'),
                    content: SelectableText(
                      '作者：${attribution.author}\n许可：${attribution.license}\n来源：${attribution.sourceUrl}',
                    ),
                    actions: [
                      TextButton(
                        onPressed: () => Navigator.pop(context),
                        child: const Text('关闭'),
                      ),
                    ],
                  ),
                ),
                child: const DecoratedBox(
                  decoration: BoxDecoration(color: Colors.black54),
                  child: Padding(
                    padding: EdgeInsets.all(2),
                    child: Icon(Icons.info_outline, size: 16),
                  ),
                ),
              ),
            ),
        ],
      ),
    );
  }

  Widget _fallback() => SizedBox(
    key: const Key('nutrition-image-fallback'),
    width: size,
    height: size,
    child: const DecoratedBox(
      decoration: BoxDecoration(color: Color(0x22111111)),
      child: Icon(Icons.image_not_supported_outlined),
    ),
  );
}

class _ReplacementPreview extends StatelessWidget {
  final NutritionRecommendation recommendation;
  final List<NutritionFood> foods;
  final VoidCallback onConfirm;
  const _ReplacementPreview({
    required this.recommendation,
    required this.foods,
    required this.onConfirm,
  });

  @override
  Widget build(BuildContext context) {
    final diff = recommendation.payload.replacementDiff!;
    final names = {for (final food in foods) food.foodId: food.nameZh};
    return Card(
      key: const Key('nutrition-replacement-preview'),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text('替换预览', style: Theme.of(context).textTheme.titleMedium),
            Text(
              '${names[diff.fromFoodId] ?? '食物信息暂不可用'} ${diff.fromGramMin}-${diff.fromGramMax} 克',
            ),
            const Icon(Icons.arrow_downward),
            Text(
              '${names[diff.toFoodId] ?? '食物信息暂不可用'} ${diff.toGramMin}-${diff.toGramMax} 克',
            ),
            const Text('预览不会修改当前建议。确认后才会创建新的激活版本。'),
            FilledButton(
              key: const Key('nutrition-confirm-replacement'),
              onPressed: onConfirm,
              child: const Text('确认替换'),
            ),
          ],
        ),
      ),
    );
  }
}

class _EligibilityView extends StatelessWidget {
  final NutritionEligibility eligibility;
  const _EligibilityView({required this.eligibility});

  @override
  Widget build(BuildContext context) {
    final (title, detail) = switch (eligibility.gate) {
      NutritionGate.redFlag => ('今日状态需要优先处理', '当前存在安全警示，不生成饮食建议。请按页面提示寻求适当帮助。'),
      NutritionGate.restricted => ('当前不适用', '此功能仅面向一般健康成年人，不提供治疗性或特殊人群饮食方案。'),
      NutritionGate.limitedEducation => (
        '仅提供一般科普',
        '当前只能显示一般健康饮食说明，不能生成个性化建议。',
      ),
      NutritionGate.clarificationRequired => (
        '需要补充资料',
        '请先在健康档案中完成结构化风险、过敏原和排除项。',
      ),
      _ => ('暂不可用', '当前无法生成饮食建议。'),
    };
    final missingHint = eligibility.missingFieldCodes.isNotEmpty
        ? '\n请补全健康档案中缺失的项目后重试。'
        : '';
    return KeyedSubtree(
      key: Key('nutrition-status-${eligibility.gate.wire}'),
      child: _StatusView(
        icon: Icons.health_and_safety_outlined,
        title: title,
        detail: '$detail$missingHint',
      ),
    );
  }
}

class _StatusView extends StatelessWidget {
  final IconData icon;
  final String title;
  final String detail;
  final VoidCallback? onRetry;
  const _StatusView({
    required this.icon,
    required this.title,
    required this.detail,
    this.onRetry,
  });

  @override
  Widget build(BuildContext context) => Semantics(
    key: const Key('nutrition-status-live'),
    liveRegion: true,
    child: Center(
      child: SingleChildScrollView(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(icon, size: 48),
            const SizedBox(height: 12),
            Text(title, style: Theme.of(context).textTheme.titleLarge),
            const SizedBox(height: 8),
            Text(detail, textAlign: TextAlign.center),
            if (onRetry != null) ...[
              const SizedBox(height: 16),
              FilledButton(onPressed: onRetry, child: const Text('重试')),
            ],
          ],
        ),
      ),
    ),
  );
}

String _mealLabel(NutritionMeal meal) => switch (meal) {
  NutritionMeal.breakfast => '早餐',
  NutritionMeal.lunch => '午餐',
  NutritionMeal.dinner => '晚餐',
};
