import 'dart:async';

import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:posture_app/core/api_client.dart';
import 'package:posture_app/models/nutrition.dart';
import 'package:posture_app/providers/assessment_provider.dart' show LoadStatus;
import 'package:posture_app/providers/nutrition_provider.dart';

import '../nutrition_fixtures.dart';
import '_test_dio.dart';

ApiClient _apiWith(FakeDioAdapter adapter) {
  final api = ApiClient()..dio.interceptors.clear();
  api.dio.httpClientAdapter = adapter;
  return api;
}

ProviderContainer _container(FakeDioAdapter adapter) => ProviderContainer(
  overrides: [apiClientProvider.overrideWithValue(_apiWith(adapter))],
);

void _registerReads(
  FakeDioAdapter adapter, {
  String? draftStatus,
  String? activeStatus,
}) {
  adapter
    ..registerJson('GET', '/nutrition/eligibility', (_) => eligibilityJson())
    ..registerJson('GET', '/nutrition/foods', (_) => foodListJson())
    ..registerJson('GET', '/nutrition/targets', (_) => targetsResponseJson())
    ..registerJson(
      'GET',
      '/nutrition/recommendations/draft',
      (_) => recommendationResultJson(status: draftStatus),
    )
    ..registerJson(
      'GET',
      '/nutrition/recommendations/active',
      (_) => recommendationResultJson(status: activeStatus),
    );
}

void main() {
  test('load keeps draft separate and never reports false active', () async {
    final adapter = FakeDioAdapter();
    _registerReads(adapter, draftStatus: 'draft');
    final container = _container(adapter);
    addTearDown(container.dispose);

    await container.read(nutritionProvider.notifier).load();
    final state = container.read(nutritionProvider);
    expect(state.status, LoadStatus.data);
    expect(state.draft?.status, RecommendationStatus.draft);
    expect(state.active, isNull);
    expect(state.targets, isNotNull);
  });

  test('draft requires a separate confirmation before active state', () async {
    final adapter = FakeDioAdapter();
    _registerReads(adapter);
    adapter
      ..registerJson(
        'POST',
        '/nutrition/recommendations/drafts',
        (_) => recommendationResultJson(status: 'draft'),
      )
      ..registerJson(
        'POST',
        '/nutrition/recommendations/00000000-0000-0000-0000-000000000001:confirm',
        (_) => recommendationResultJson(status: 'active'),
      );
    final container = _container(adapter);
    addTearDown(container.dispose);
    await container.read(nutritionProvider.notifier).load();

    expect(
      await container.read(nutritionProvider.notifier).createDraft(),
      isTrue,
    );
    expect(container.read(nutritionProvider).active, isNull);
    expect(
      await container.read(nutritionProvider.notifier).confirmDraft(),
      isTrue,
    );
    expect(container.read(nutritionProvider).draft, isNull);
    expect(
      container.read(nutritionProvider).active?.status,
      RecommendationStatus.active,
    );
  });

  test('replacement preview performs no confirm until explicit action', () async {
    final adapter = FakeDioAdapter();
    _registerReads(adapter, activeStatus: 'active');
    adapter
      ..registerJson(
        'POST',
        '/nutrition/recommendations/00000000-0000-0000-0000-000000000001/replacements:preview',
        (_) => recommendationResultJson(status: 'draft', withDiff: true),
      )
      ..registerJson(
        'POST',
        '/nutrition/recommendations/00000000-0000-0000-0000-000000000001/replacements:confirm',
        (_) => recommendationResultJson(status: 'active', withDiff: true),
      );
    final container = _container(adapter);
    addTearDown(container.dispose);
    await container.read(nutritionProvider.notifier).load();
    const selection = ReplacementSelection(
      dayKind: NutritionDayKind.trainingDay,
      meal: NutritionMeal.breakfast,
      itemIndex: 0,
      fromFoodId: 'rice_white',
      toFoodId: 'oats_cooked',
    );

    expect(
      await container
          .read(nutritionProvider.notifier)
          .previewReplacement(selection),
      isTrue,
    );
    expect(
      adapter.calls.where((call) => call.path.endsWith('replacements:confirm')),
      isEmpty,
    );
    expect(container.read(nutritionProvider).replacementPreview, isNotNull);

    expect(
      await container.read(nutritionProvider.notifier).confirmReplacement(),
      isTrue,
    );
    expect(container.read(nutritionProvider).replacementPreview, isNull);
  });

  test('disabled and offline errors are explicit and retryable', () async {
    final adapter = FakeDioAdapter()
      ..registerError('GET', '/nutrition/eligibility', 503, {
        'detail': 'disabled',
        'code': 'nutrition_runtime_disabled',
      })
      ..registerJson('GET', '/nutrition/foods', (_) => foodListJson());
    final container = _container(adapter);
    addTearDown(container.dispose);
    await container.read(nutritionProvider.notifier).load();
    expect(container.read(nutritionProvider).status, LoadStatus.networkError);
    expect(
      container.read(nutritionProvider).errorCode,
      'nutrition_runtime_disabled',
    );

    _registerReads(adapter);
    await container.read(nutritionProvider.notifier).load();
    expect(container.read(nutritionProvider).status, LoadStatus.data);
  });

  test('stale confirmation clears draft and active recommendation state',
      () async {
    final adapter = FakeDioAdapter();
    _registerReads(adapter, draftStatus: 'draft');
    adapter.registerError(
      'POST',
      '/nutrition/recommendations/00000000-0000-0000-0000-000000000001:confirm',
      409,
      {'detail': 'context changed', 'code': 'stale_context'},
    );
    final container = _container(adapter);
    addTearDown(container.dispose);
    await container.read(nutritionProvider.notifier).load();

    expect(
      await container.read(nutritionProvider.notifier).confirmDraft(),
      isFalse,
    );
    final state = container.read(nutritionProvider);
    expect(state.errorCode, 'stale_context');
    expect(state.draft, isNull);
    expect(state.active, isNull);
  });

  test('late response after profile invalidation is discarded', () async {
    final pending = Completer<Response>();
    final adapter = FakeDioAdapter()
      ..register('GET', '/nutrition/eligibility', (_) => pending.future)
      ..registerJson('GET', '/nutrition/foods', (_) => foodListJson());
    final container = _container(adapter);
    addTearDown(container.dispose);
    final load = container.read(nutritionProvider.notifier).load();
    await Future<void>.delayed(Duration.zero);
    container.read(nutritionProvider.notifier).invalidateForProfileChange();
    pending.complete(
      Response(
        requestOptions: RequestOptions(path: '/nutrition/eligibility'),
        statusCode: 200,
        data: eligibilityJson(gate: 'eligible'),
      ),
    );
    await load;
    expect(container.read(nutritionProvider).status, LoadStatus.idle);
    expect(container.read(nutritionProvider).eligibility, isNull);
  });

  test('delete clears all local nutrition state', () async {
    final adapter = FakeDioAdapter();
    _registerReads(adapter, activeStatus: 'active');
    adapter.registerJson(
      'DELETE',
      '/nutrition/data',
      (_) => {
        'status': 'deleted',
        'recommendations_deleted': 1,
        'idempotency_deleted': 1,
        'proposals_deleted': 0,
        'tool_events_deleted': 0,
        'runs_deleted': 0,
        'profile_updated': false,
      },
    );
    final container = _container(adapter);
    addTearDown(container.dispose);
    await container.read(nutritionProvider.notifier).load();
    expect(container.read(nutritionProvider).active, isNotNull);
    expect(
      await container.read(nutritionProvider.notifier).deleteNutritionData(),
      isTrue,
    );
    expect(container.read(nutritionProvider).status, LoadStatus.idle);
    expect(container.read(nutritionProvider).active, isNull);
    expect(container.read(nutritionProvider).foods, isEmpty);
  });
}
