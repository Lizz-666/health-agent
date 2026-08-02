import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';
import 'package:posture_app/core/api_client.dart';
import 'package:posture_app/screens/nutrition/nutrition_screen.dart';

import '../test/nutrition_fixtures.dart';
import '../test/providers/_test_dio.dart';

ApiClient _apiWith(FakeDioAdapter adapter) {
  final api = ApiClient()..dio.interceptors.clear();
  api.dio.httpClientAdapter = adapter;
  return api;
}

Widget _app(FakeDioAdapter adapter) => ProviderScope(
  overrides: [apiClientProvider.overrideWithValue(_apiWith(adapter))],
  child: const MaterialApp(home: NutritionScreen()),
);

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('Android renders enabled active nutrition flow', (tester) async {
    final adapter = FakeDioAdapter()
      ..registerJson('GET', '/nutrition/eligibility', (_) => eligibilityJson())
      ..registerJson('GET', '/nutrition/foods', (_) => foodListJson())
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

    await tester.pumpWidget(_app(adapter));
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('nutrition-active-label')), findsOneWidget);
    expect(find.text('训练日模板'), findsOneWidget);
    expect(find.text('休息日模板'), findsOneWidget);
    expect(
      find.byKey(const Key('nutrition-source-uncertainty')),
      findsOneWidget,
    );
  });

  testWidgets('Android renders runtime-disabled fail-closed state', (
    tester,
  ) async {
    final adapter = FakeDioAdapter()
      ..registerError('GET', '/nutrition/eligibility', 503, {
        'detail': '饮食建议暂未开放',
        'code': 'nutrition_runtime_disabled',
      })
      ..registerJson('GET', '/nutrition/foods', (_) => foodListJson());

    await tester.pumpWidget(_app(adapter));
    await tester.pumpAndSettle();

    expect(find.text('饮食建议暂未开放'), findsWidgets);
    expect(find.byKey(const Key('nutrition-active-label')), findsNothing);
    expect(find.byKey(const Key('nutrition-generate-draft')), findsNothing);
  });
}
