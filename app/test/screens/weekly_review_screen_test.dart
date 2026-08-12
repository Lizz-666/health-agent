// app/test/screens/weekly_review_screen_test.dart
//
// Phase 7 weekly review screen widget tests. The review endpoints are not
// implemented on the backend (Codex Task 3); these tests use the fake Dio
// adapter against the specified paths and assert the screen renders facts
// before proposals, never POSTs on load, treats real 404/network as
// unavailable, never counts missing data as zero, never labels active rest as
// failure, and keeps weight trend display-only. All data synthetic.
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:posture_app/core/api_client.dart';
import 'package:posture_app/providers/adaptive_review_provider.dart';
import 'package:posture_app/screens/plan/weekly_review_screen.dart';

import '../providers/_test_dio.dart';

ApiClient _apiWith(FakeDioAdapter adapter) {
  final api = ApiClient()..dio.interceptors.clear();
  api.dio.httpClientAdapter = adapter;
  return api;
}

Widget _wrap(ApiClient api) => ProviderScope(
  overrides: [
    apiClientProvider.overrideWithValue(api),
    adaptiveReviewProvider.overrideWith(
      (ref) =>
          AdaptiveReviewNotifier(api, onDraftCreated: (_, _, _) async => true),
    ),
  ],
  child: const MaterialApp(home: WeeklyReviewScreen()),
);

Map<String, dynamic> _snapshotJson({int week = 1}) => {
  'review_id': 'rv-$week',
  'plan_version_id': 'pv-1',
  'week_index': week,
  'review_version': 1,
  'input_fingerprint': 'a' * 64,
  'period_start': '2026-07-20',
  'period_end': '2026-07-26',
  'execution': {
    'scheduled': 3,
    'completed': 3,
    'partial': 0,
    'too_busy': 0,
    'intentional_rest': 0,
    'discomfort': 0,
    'active_rest': 1,
    'safety_adjustment': 0,
    'unavailable': 0,
    'effective': 3,
  },
  'execution_trend': {'available': true, 'direction': 'improving'},
  'adjustments': {
    'shortened': 0,
    'recovery': 0,
    'deferred': 0,
    'active_rest': 1,
    'unchanged': 0,
    'missing': 0,
    'unavailable': 0,
  },
  'weight_trend': {'available': true, 'direction': 'rising'},
  'nutrition': {
    'state': 'active',
    'age_days': 12,
    'refresh_available': false,
    'unavailable_reason': null,
    'recommendation_id': 'nr-1',
    'version': 3,
  },
  'posture': {
    'status': 'not_due',
    'baseline_sources': <String>[],
    'comparison_sources': <String>[],
  },
  'safety': {
    'gate': 'eligible',
    'blocked': false,
    'reason_codes': <String>[],
    'missing_fields': <String>[],
  },
  'proposals': [
    {'code': 'keep_current_plan', 'state': 'proposal'},
    {
      'code': 'offer_training_draft',
      'strategy': 'conservative_duration',
      'state': 'proposal',
    },
  ],
};

void main() {
  testWidgets(
    'on open auto-loads week 1 GET and renders facts before proposals',
    (tester) async {
      final adapter = FakeDioAdapter()
        ..registerJson(
          'GET',
          '/training/reviews/weeks/1',
          (_) => _snapshotJson(),
        );
      await tester.pumpWidget(_wrap(_apiWith(adapter)));
      await tester.pumpAndSettle();

      // No POST on load (generation is explicit only).
      expect(adapter.calls.every((c) => c.method != 'POST'), isTrue);
      expect(
        adapter.calls.any((c) => c.path == '/training/reviews/weeks/1'),
        isTrue,
      );

      // Facts section exists.
      expect(find.byKey(const Key('review-facts')), findsOneWidget);
      expect(find.textContaining('完成'), findsWidgets);
      // Active rest is a valid engagement state, not a failure.
      expect(find.textContaining('主动休息'), findsWidgets);
      // Proposals exist after facts.
      expect(find.byKey(const Key('review-proposals')), findsOneWidget);
      expect(find.textContaining('执行改善'), findsOneWidget);
      expect(find.textContaining('营养建议已生效'), findsOneWidget);
      expect(find.textContaining('保守缩短单次时长'), findsOneWidget);
      expect(find.textContaining('improving'), findsNothing);
      expect(find.textContaining('conservativeDuration'), findsNothing);
      // Facts appear above proposals in the tree.
      final factsBox = tester.getCenter(find.byKey(const Key('review-facts')));
      final proposalsBox = tester.getCenter(
        find.byKey(const Key('review-proposals')),
      );
      expect(factsBox.dy, lessThan(proposalsBox.dy));
    },
  );

  testWidgets('weight trend is display-only context', (tester) async {
    final adapter = FakeDioAdapter()
      ..registerJson(
        'GET',
        '/training/reviews/weeks/1',
        (_) => _snapshotJson(),
      );
    await tester.pumpWidget(_wrap(_apiWith(adapter)));
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('review-weight-trend')), findsOneWidget);
    expect(find.textContaining('仅供参考'), findsOneWidget);
  });

  testWidgets('safety block uses stable Chinese without raw reason codes', (
    tester,
  ) async {
    final adapter = FakeDioAdapter()
      ..registerJson('GET', '/training/reviews/weeks/1', (_) {
        final snapshot = _snapshotJson();
        snapshot['safety'] = {
          'gate': 'red_flag',
          'blocked': true,
          'reason_codes': ['review_red_flag', 'future_reason_code'],
          'missing_fields': ['checkin:2026-07-21'],
        };
        return snapshot;
      });
    await tester.pumpWidget(_wrap(_apiWith(adapter)));
    await tester.pumpAndSettle();

    expect(find.textContaining('需优先处理的安全信号'), findsOneWidget);
    expect(find.textContaining('review_red_flag'), findsNothing);
    expect(find.textContaining('future_reason_code'), findsNothing);
    expect(find.textContaining('checkin:2026-07-21'), findsNothing);
  });

  testWidgets(
    'proposal vs draft distinction; draft needs separate confirmation',
    (tester) async {
      final adapter = FakeDioAdapter()
        ..registerJson(
          'GET',
          '/training/reviews/weeks/1',
          (_) => _snapshotJson()
            ..['proposals'] = [
              {
                'code': 'offer_training_draft',
                'strategy': 'conservative_duration',
                'state': 'draft',
                'origin_weekly_review_id': 'rv-0',
              },
            ],
        );
      await tester.pumpWidget(_wrap(_apiWith(adapter)));
      await tester.pumpAndSettle();

      expect(
        find.byKey(const Key('review-proposal-offer_training_draft')),
        findsOneWidget,
      );
      // A draft must say it still requires the existing separate confirmation.
      expect(find.textContaining('单独确认'), findsOneWidget);
    },
  );

  testWidgets('proposal action creates a draft without activating it', (
    tester,
  ) async {
    var created = false;
    final adapter = FakeDioAdapter()
      ..registerJson('GET', '/training/reviews/weeks/1', (_) {
        final snapshot = _snapshotJson();
        snapshot['proposals'] = [
          {
            'code': 'offer_training_draft',
            'strategy': 'conservative_duration',
            'state': created ? 'draft' : 'proposal',
            if (created) 'origin_weekly_review_id': 'rv-1',
          },
        ];
        return snapshot;
      })
      ..registerJson('POST', '/training/reviews/weeks/1/training-drafts', (_) {
        created = true;
        return {
          'review_id': 'rv-1',
          'draft_id': 'draft-1',
          'status': 'created',
          'origin_weekly_review_id': 'rv-1',
        };
      });
    await tester.pumpWidget(_wrap(_apiWith(adapter)));
    await tester.pumpAndSettle();

    await tester.ensureVisible(
      find.byKey(const Key('review-create-training-draft')),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('review-create-training-draft')));
    await tester.pumpAndSettle();

    expect(find.textContaining('草案（尚未生效）'), findsOneWidget);
    expect(find.textContaining('单独确认'), findsOneWidget);
    expect(find.byKey(const Key('review-create-training-draft')), findsNothing);
  });

  testWidgets('generate button POSTs exactly once on explicit tap', (
    tester,
  ) async {
    final adapter = FakeDioAdapter()
      ..registerError('GET', '/training/reviews/weeks/1', 404, {
        'detail': 'x',
        'code': 'review_not_generated',
      })
      ..registerJson(
        'POST',
        '/training/reviews/weeks/1',
        (_) => _snapshotJson(),
      );
    await tester.pumpWidget(_wrap(_apiWith(adapter)));
    await tester.pumpAndSettle();

    // No POST yet.
    expect(adapter.calls.where((c) => c.method == 'POST'), isEmpty);

    await tester.tap(find.byKey(const Key('review-generate-button')));
    await tester.pumpAndSettle();

    expect(
      adapter.calls
          .where(
            (c) => c.method == 'POST' && c.path == '/training/reviews/weeks/1',
          )
          .length,
      1,
    );
    expect(find.byKey(const Key('review-facts')), findsOneWidget);
  });

  testWidgets('notGenerated renders explicit state with generate action', (
    tester,
  ) async {
    final adapter = FakeDioAdapter()
      ..registerError('GET', '/training/reviews/weeks/1', 404, {
        'detail': 'x',
        'code': 'review_not_generated',
      });
    await tester.pumpWidget(_wrap(_apiWith(adapter)));
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('review-not-generated')), findsOneWidget);
    expect(find.byKey(const Key('review-generate-button')), findsOneWidget);
  });

  testWidgets('stale state requires an explicit regenerate tap', (
    tester,
  ) async {
    final adapter = FakeDioAdapter()
      ..registerError('GET', '/training/reviews/weeks/1', 409, {
        'detail': 'x',
        'code': 'stale_context',
      })
      ..registerJson(
        'POST',
        '/training/reviews/weeks/1',
        (_) => _snapshotJson(),
      );
    await tester.pumpWidget(_wrap(_apiWith(adapter)));
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('review-stale')), findsOneWidget);
    expect(adapter.calls.where((c) => c.method == 'POST'), isEmpty);

    await tester.tap(find.byKey(const Key('review-regenerate-button')));
    await tester.pumpAndSettle();

    expect(adapter.calls.where((c) => c.method == 'POST').length, 1);
    expect(find.byKey(const Key('review-facts')), findsOneWidget);
  });

  testWidgets('real 404 without code -> unavailable', (tester) async {
    final adapter = FakeDioAdapter()
      ..registerError('GET', '/training/reviews/weeks/1', 404, {
        'detail': 'Not Found',
      });
    await tester.pumpWidget(_wrap(_apiWith(adapter)));
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('review-unavailable')), findsOneWidget);
  });

  testWidgets('unavailable shows retry', (tester) async {
    final adapter = FakeDioAdapter();
    await tester.pumpWidget(_wrap(_apiWith(adapter)));
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('review-unavailable')), findsOneWidget);
    expect(find.byKey(const Key('review-retry')), findsOneWidget);
  });

  testWidgets('parseError renders distinctly', (tester) async {
    final adapter = FakeDioAdapter()
      ..registerJson('GET', '/training/reviews/weeks/1', (_) => {'oops': true});
    await tester.pumpWidget(_wrap(_apiWith(adapter)));
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('review-parse-error')), findsOneWidget);
  });

  testWidgets('week selector bounded 1..4 loads chosen week (GET only)', (
    tester,
  ) async {
    final adapter = FakeDioAdapter()
      ..registerJson('GET', '/training/reviews/weeks/1', (_) => _snapshotJson())
      ..registerJson(
        'GET',
        '/training/reviews/weeks/3',
        (_) => _snapshotJson(week: 3),
      );
    await tester.pumpWidget(_wrap(_apiWith(adapter)));
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(const Key('review-week-3')));
    await tester.pumpAndSettle();

    expect(
      adapter.calls.any((c) => c.path == '/training/reviews/weeks/3'),
      isTrue,
    );
    expect(adapter.calls.where((c) => c.method == 'POST'), isEmpty);
  });

  testWidgets('narrow screen + large text does not overflow', (tester) async {
    tester.view.devicePixelRatio = 1;
    tester.view.physicalSize = const Size(320, 720);
    tester.platformDispatcher.textScaleFactorTestValue = 1.5;
    addTearDown(tester.view.resetDevicePixelRatio);
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.platformDispatcher.clearTextScaleFactorTestValue);

    final adapter = FakeDioAdapter()
      ..registerJson(
        'GET',
        '/training/reviews/weeks/1',
        (_) => _snapshotJson(),
      );
    await tester.pumpWidget(_wrap(_apiWith(adapter)));
    await tester.pumpAndSettle();

    expect(tester.takeException(), isNull);
  });

  testWidgets(
    '320x720 textScaler 2.0 no overflow on data state, week selector findable',
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
          '/training/reviews/weeks/1',
          (_) => _snapshotJson(),
        );
      await tester.pumpWidget(_wrap(_apiWith(adapter)));
      await tester.pumpAndSettle();

      expect(tester.takeException(), isNull);
      // Week selector must remain accessible
      expect(find.byKey(const Key('review-week-1')), findsOneWidget);
    },
  );

  testWidgets('320x720 textScaler 2.0 no overflow on unavailable state', (
    tester,
  ) async {
    tester.view.devicePixelRatio = 1;
    tester.view.physicalSize = const Size(320, 720);
    tester.platformDispatcher.textScaleFactorTestValue = 2.0;
    addTearDown(tester.view.resetDevicePixelRatio);
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.platformDispatcher.clearTextScaleFactorTestValue);

    final adapter = FakeDioAdapter();
    await tester.pumpWidget(_wrap(_apiWith(adapter)));
    await tester.pumpAndSettle();

    expect(tester.takeException(), isNull);
    expect(find.byKey(const Key('review-unavailable')), findsOneWidget);
    expect(find.byKey(const Key('review-retry')), findsOneWidget);
    expect(
      tester.getSemantics(find.byKey(const Key('review-unavailable'))),
      isSemantics(isLiveRegion: true),
    );
  });
}
