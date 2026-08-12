import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:posture_app/core/api_client.dart';
import 'package:posture_app/screens/nutrition/nutrition_screen.dart';

import '../nutrition_fixtures.dart';
import '../providers/_test_dio.dart';

ApiClient _apiWith(FakeDioAdapter adapter) {
  final api = ApiClient()..dio.interceptors.clear();
  api.dio.httpClientAdapter = adapter;
  return api;
}

Widget _wrap(FakeDioAdapter adapter, Widget child) => ProviderScope(
  overrides: [apiClientProvider.overrideWithValue(_apiWith(adapter))],
  child: MaterialApp(home: child),
);

void _registerActive(FakeDioAdapter adapter, {bool withDraft = false}) {
  adapter
    ..registerJson('GET', '/nutrition/eligibility', (_) => eligibilityJson())
    ..registerJson('GET', '/nutrition/foods', (_) => foodListJson())
    ..registerJson('GET', '/nutrition/targets', (_) => targetsResponseJson())
    ..registerJson(
      'GET',
      '/nutrition/recommendations/draft',
      (_) => recommendationResultJson(status: withDraft ? 'draft' : null),
    )
    ..registerJson(
      'GET',
      '/nutrition/recommendations/active',
      (_) => recommendationResultJson(status: 'active'),
    );
}

void main() {
  testWidgets('pending draft remains separately confirmable beside active', (
    tester,
  ) async {
    final adapter = FakeDioAdapter();
    _registerActive(adapter, withDraft: true);
    await tester.pumpWidget(_wrap(adapter, const NutritionScreen()));
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('nutrition-active-tab')), findsOneWidget);
    expect(find.byKey(const Key('nutrition-active-label')), findsOneWidget);
    expect(find.byKey(const Key('nutrition-confirm-draft')), findsNothing);

    await tester.tap(find.byKey(const Key('nutrition-draft-tab')));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('nutrition-draft-label')), findsOneWidget);
    expect(find.byKey(const Key('nutrition-confirm-draft')), findsOneWidget);
  });

  testWidgets('renders source notice, day templates, images and attribution', (
    tester,
  ) async {
    final adapter = FakeDioAdapter();
    _registerActive(adapter);
    await tester.pumpWidget(_wrap(adapter, const NutritionScreen()));
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('nutrition-active-label')), findsOneWidget);
    expect(
      find.byKey(const Key('nutrition-source-uncertainty')),
      findsOneWidget,
    );
    expect(find.text('训练日模板'), findsOneWidget);
    expect(find.text('休息日模板'), findsOneWidget);
    expect(find.byType(NutritionFoodImage), findsWidgets);

    final attribution = find.byKey(
      const Key(
        'nutrition-attribution-assets/images/nutrition/ingredients/rice_white.jpg',
      ),
    );
    expect(attribution, findsWidgets);
    await tester.tap(attribution.first);
    await tester.pumpAndSettle();
    expect(find.text('图片来源'), findsOneWidget);
    expect(find.textContaining('CC0-1.0'), findsOneWidget);
  });

  testWidgets('missing or unapproved image key renders semantic fallback', (
    tester,
  ) async {
    await tester.pumpWidget(
      const MaterialApp(
        home: Scaffold(
          body: NutritionFoodImage(
            imageKey: 'assets/images/nutrition/ingredients/not-reviewed.jpg',
            semanticLabel: '合成食物',
          ),
        ),
      ),
    );
    expect(find.byKey(const Key('nutrition-image-fallback')), findsOneWidget);
    final semantics = tester.getSemantics(find.byType(NutritionFoodImage));
    expect(semantics.label, contains('合成食物'));
  });

  testWidgets('restricted state never renders generation or active controls', (
    tester,
  ) async {
    final adapter = FakeDioAdapter()
      ..registerJson(
        'GET',
        '/nutrition/eligibility',
        (_) => eligibilityJson(gate: 'restricted'),
      )
      ..registerJson('GET', '/nutrition/foods', (_) => foodListJson());
    await tester.pumpWidget(_wrap(adapter, const NutritionScreen()));
    await tester.pumpAndSettle();

    expect(find.text('当前不适用'), findsOneWidget);
    expect(find.byKey(const Key('nutrition-generate-draft')), findsNothing);
    expect(find.byKey(const Key('nutrition-active-label')), findsNothing);
  });

  testWidgets('red flag state fails closed without recommendation controls', (
    tester,
  ) async {
    final adapter = FakeDioAdapter()
      ..registerJson(
        'GET',
        '/nutrition/eligibility',
        (_) => eligibilityJson(gate: 'red_flag'),
      )
      ..registerJson('GET', '/nutrition/foods', (_) => foodListJson());
    await tester.pumpWidget(_wrap(adapter, const NutritionScreen()));
    await tester.pumpAndSettle();

    expect(find.text('今日状态需要优先处理'), findsOneWidget);
    expect(find.byKey(const Key('nutrition-generate-draft')), findsNothing);
    expect(find.byKey(const Key('nutrition-active-label')), findsNothing);
  });

  testWidgets(
    '320x720 textScaler 2.0 keeps red-flag guidance visible without overflow',
    (tester) async {
      tester.view.devicePixelRatio = 1;
      tester.view.physicalSize = const Size(320, 720);
      tester.platformDispatcher.textScaleFactorTestValue = 2.0;
      addTearDown(tester.view.resetDevicePixelRatio);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.platformDispatcher.clearTextScaleFactorTestValue);

      final adapter = FakeDioAdapter()
        ..registerJson(
          'GET',
          '/nutrition/eligibility',
          (_) => eligibilityJson(gate: 'red_flag'),
        )
        ..registerJson('GET', '/nutrition/foods', (_) => foodListJson());
      await tester.pumpWidget(_wrap(adapter, const NutritionScreen()));
      await tester.pumpAndSettle();

      expect(tester.takeException(), isNull);
      expect(find.text('今日状态需要优先处理'), findsOneWidget);
      expect(find.byIcon(Icons.health_and_safety_outlined), findsOneWidget);
      expect(
        tester.getSemantics(find.byKey(const Key('nutrition-status-live'))),
        isSemantics(isLiveRegion: true),
      );
    },
  );

  testWidgets('nutrition surface contains no meal tracking controls', (
    tester,
  ) async {
    final adapter = FakeDioAdapter();
    _registerActive(adapter);
    await tester.pumpWidget(_wrap(adapter, const NutritionScreen()));
    await tester.pumpAndSettle();
    final allText = tester
        .widgetList<Text>(find.byType(Text))
        .map((widget) => widget.data ?? '')
        .join('\n');
    for (final forbidden in ['饮食打卡', '餐食完成', '记录摄入', '已吃']) {
      expect(allText, isNot(contains(forbidden)));
    }
  });

  testWidgets('missing catalog entries never expose internal food ids', (
    tester,
  ) async {
    final adapter = FakeDioAdapter();
    final foods = foodListJson();
    (foods['foods'] as List).clear();
    adapter
      ..registerJson('GET', '/nutrition/eligibility', (_) => eligibilityJson())
      ..registerJson('GET', '/nutrition/foods', (_) => foods)
      ..registerJson('GET', '/nutrition/targets', (_) => targetsResponseJson())
      ..registerJson(
        'GET',
        '/nutrition/recommendations/draft',
        (_) => recommendationResultJson(),
      )
      ..registerJson(
        'GET',
        '/nutrition/recommendations/active',
        (_) => recommendationResultJson(status: 'active'),
      );

    await tester.pumpWidget(_wrap(adapter, const NutritionScreen()));
    await tester.pumpAndSettle();

    expect(find.textContaining('食物信息暂不可用'), findsWidgets);
    expect(find.textContaining('rice_white'), findsNothing);
    expect(find.textContaining('oats_cooked'), findsNothing);
  });
}
