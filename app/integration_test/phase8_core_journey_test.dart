// app/integration_test/phase8_core_journey_test.dart
//
// Phase 8 Task 3 hard-gate driver: replays the supported-adult core journey
// through the REAL Flutter application over REAL HTTP against the deterministic
// Phase 8 test-only FastAPI backend on an Android emulator.
//
// This driver deliberately does NOT use FakeDioAdapter, does NOT override
// apiClientProvider, does NOT call domain services, and does NOT seed
// application tables. The app talks to the backend through the normal
// ApiClient, AppConstants.apiBaseUrl, and real flutter_secure_storage token
// handling. The only backend calls this test issues directly are the Phase 8
// control-plane routes (reset / faults) from test setup, per the frozen
// Gate 2 contract.
//
// Requirements to run (executed by Codex on an Android emulator):
//   flutter test integration_test/phase8_core_journey_test.dart -d emulator-5554 \
//     --dart-define=API_BASE_URL=http://10.0.2.2:8000/api/v1 \
//     --dart-define=DEV_ADMIN_PHONE=13900000008 \
//     --dart-define=DEV_ADMIN_PASSWORD=synthetic-phase8-only
// with `python scripts/phase8.py serve --host 127.0.0.1 --port 8000` running.
//
// It is NOT run by `flutter test` (which only scans test/) and cannot pass
// headless: it requires the live synthetic backend. Never logs tokens,
// credentials, request/response bodies, or health values.
import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';
import 'package:posture_app/app.dart';
import 'package:posture_app/core/constants.dart';
import 'package:posture_app/core/storage.dart';
import 'package:posture_app/models/adaptive_review.dart';
import 'package:posture_app/models/nutrition.dart';
import 'package:posture_app/models/plan.dart';
import 'package:posture_app/providers/adaptive_review_provider.dart';
import 'package:posture_app/providers/assessment_provider.dart' show LoadStatus;
import 'package:posture_app/providers/nutrition_provider.dart';
import 'package:posture_app/providers/plan_provider.dart';

// --- Frozen Gate 2 control-plane contract -----------------------------------
const String _kControlHeaderName = 'X-Phase8-Control-Token';
const String _kControlHeaderValue = 'phase8-local-control-only';
const String _kCheckpointBlank = 'blank_supported';
const String _kCheckpointCycleDue = 'cycle_due';
const String _kCheckpointSafetyBlocked = 'safety_blocked';

/// Derives the backend origin strictly from the app's configured API base URL.
/// The base MUST end with `/api/v1`; the control plane lives at the origin,
/// outside `/api/v1`.
String _controlBaseUrl() {
  const base = AppConstants.apiBaseUrl;
  const suffix = '/api/v1';
  if (!base.endsWith(suffix)) {
    throw StateError(
      'API_BASE_URL must end with "$suffix" so the Phase 8 control origin can '
      'be derived; refusing to guess the control endpoint.',
    );
  }
  final origin = base.substring(0, base.length - suffix.length);
  return '$origin/__phase8';
}

/// Thin control-plane client. Uses an independent Dio (NOT the app ApiClient)
/// so that resets/faults are pure test setup and never travel through the app
/// under test. Only reset/checkpoint/fault operations are permitted here.
class _ControlPlane {
  _ControlPlane()
    : _dio = Dio(
        BaseOptions(
          baseUrl: _controlBaseUrl(),
          connectTimeout: const Duration(seconds: 20),
          receiveTimeout: const Duration(seconds: 20),
          headers: {_kControlHeaderName: _kControlHeaderValue},
          contentType: Headers.jsonContentType,
        ),
      );

  final Dio _dio;
  int _lastResetGeneration = 0;

  /// Drops + reseeds the disposable synthetic database at the named checkpoint.
  /// Throws (failing the test) on any non-2xx result.
  Future<_ResetEvidence> reset(String checkpoint) async {
    assert(
      checkpoint == _kCheckpointBlank ||
          checkpoint == _kCheckpointCycleDue ||
          checkpoint == _kCheckpointSafetyBlocked,
      'Only the three frozen checkpoints are permitted.',
    );
    final resp = await _dio.post<dynamic>(
      '/reset',
      data: {'checkpoint': checkpoint},
    );
    if (resp.statusCode != 200) {
      throw StateError('reset($checkpoint) failed: HTTP ${resp.statusCode}');
    }
    final evidence = _ResetEvidence.fromJson(resp.data, checkpoint);
    if (evidence.resetGeneration <= _lastResetGeneration) {
      throw StateError('reset generation did not increase');
    }
    _lastResetGeneration = evidence.resetGeneration;
    return evidence;
  }

  /// Installs a one-shot allowlisted fault for an allowlisted route/kind.
  ///
  /// NOTE (assumption for Codex): the exact allowlisted route/kind enum values
  /// and body field names are owned by the Task 2 test app. This helper posts
  /// `{route, kind}`; if the frozen schema differs, adjust this single method.
  Future<void> installFault({
    required String route,
    required String kind,
  }) async {
    final resp = await _dio.post<dynamic>(
      '/faults',
      data: {'route': route, 'kind': kind},
    );
    if (resp.statusCode != 200) {
      throw StateError(
        'installFault($route,$kind) failed: HTTP ${resp.statusCode}',
      );
    }
  }

  Future<_ResetEvidence> evidence(String checkpoint) async {
    final resp = await _dio.get<dynamic>('/evidence');
    if (resp.statusCode != 200) {
      throw StateError('evidence failed: HTTP ${resp.statusCode}');
    }
    return _ResetEvidence.fromJson(resp.data, checkpoint);
  }
}

class _ResetEvidence {
  final String checkpoint;
  final int resetGeneration;
  final Map<String, int> tableCounts;

  const _ResetEvidence({
    required this.checkpoint,
    required this.resetGeneration,
    required this.tableCounts,
  });

  factory _ResetEvidence.fromJson(Object? raw, String expectedCheckpoint) {
    if (raw is! Map<String, dynamic> ||
        raw.length != 6 ||
        raw['synthetic_only'] != true ||
        raw['checkpoint'] != expectedCheckpoint ||
        raw['reset_generation'] is! int ||
        raw['provider_calls'] != 0 ||
        raw['object_count'] != 0 ||
        raw['table_counts'] is! Map<String, dynamic>) {
      throw const FormatException('invalid synthetic reset evidence');
    }
    final counts = <String, int>{};
    for (final entry in (raw['table_counts'] as Map<String, dynamic>).entries) {
      if (entry.value is! int || (entry.value as int) < 0) {
        throw const FormatException('invalid synthetic table count');
      }
      counts[entry.key] = entry.value as int;
    }
    return _ResetEvidence(
      checkpoint: expectedCheckpoint,
      resetGeneration: raw['reset_generation'] as int,
      tableCounts: counts,
    );
  }

  void expectBlankBaseline() {
    if (tableCounts['users'] != 1 || tableCounts['health_profiles'] != 1) {
      throw TestFailure('blank reset baseline identity/profile counts differ');
    }
    final residual = tableCounts.entries.where(
      (entry) =>
          entry.key != 'users' &&
          entry.key != 'health_profiles' &&
          entry.value != 0,
    );
    if (residual.isNotEmpty) {
      throw TestFailure('blank reset left residual domain rows');
    }
  }
}

// --- Test harness helpers ----------------------------------------------------

/// Boots the real PostureApp under a fresh ProviderContainer with NO overrides.
/// Returns the container so the driver can perform real GoRouter navigation for
/// destinations that have no on-screen entry point (e.g. `/posture`).
Future<ProviderContainer> _bootApp(WidgetTester tester) async {
  final container = ProviderContainer();
  addTearDown(container.dispose);
  await tester.pumpWidget(
    UncontrolledProviderScope(container: container, child: const PostureApp()),
  );
  await tester.pump();
  return container;
}

Future<void> _pumpUntilNutritionGate(
  WidgetTester tester,
  ProviderContainer container,
  NutritionGate expected,
) async {
  final deadline = DateTime.now().add(const Duration(seconds: 30));
  while (DateTime.now().isBefore(deadline)) {
    await tester.pump(const Duration(milliseconds: 200));
    final state = container.read(nutritionProvider);
    if (state.status == LoadStatus.loading || state.status == LoadStatus.idle) {
      continue;
    }
    if (state.status == LoadStatus.data &&
        state.eligibility?.gate == expected) {
      return;
    }
    throw TestFailure(
      'Nutrition gate failed closed: status=${state.status.name}, '
      'gate=${state.eligibility?.gate.wire ?? 'none'}',
    );
  }
  throw TestFailure('Timed out waiting for nutrition gate ${expected.wire}');
}

Future<void> _pumpUntilTodayRecovered(
  WidgetTester tester,
  ProviderContainer container,
) async {
  final deadline = DateTime.now().add(const Duration(seconds: 30));
  while (DateTime.now().isBefore(deadline)) {
    await tester.pump(const Duration(milliseconds: 200));
    final state = container.read(planProvider);
    if (state.todayStatus == LoadStatus.loading) continue;
    if (state.todayStatus == LoadStatus.data && state.today != null) return;
    throw TestFailure(
      'Today retry failed closed: status=${state.todayStatus.name}',
    );
  }
  throw TestFailure('Timed out waiting for Today retry recovery');
}

void _navigate(ProviderContainer container, String location) {
  container.read(routerProvider).go(location);
}

/// Pumps in fixed steps until [finder] resolves or [timeout] elapses. Avoids
/// `pumpAndSettle` hangs caused by persistent progress indicators during real
/// network round-trips.
Future<void> _pumpUntil(
  WidgetTester tester,
  Finder finder, {
  Duration timeout = const Duration(seconds: 30),
}) async {
  final deadline = DateTime.now().add(timeout);
  while (DateTime.now().isBefore(deadline)) {
    await tester.pump(const Duration(milliseconds: 200));
    if (finder.evaluate().isNotEmpty) return;
  }
  throw TestFailure('Timed out waiting for $finder');
}

Future<Finder> _pumpUntilAny(
  WidgetTester tester,
  List<Finder> finders, {
  Duration timeout = const Duration(seconds: 30),
}) async {
  final deadline = DateTime.now().add(timeout);
  while (DateTime.now().isBefore(deadline)) {
    await tester.pump(const Duration(milliseconds: 200));
    for (final finder in finders) {
      if (finder.evaluate().isNotEmpty) return finder;
    }
  }
  throw TestFailure('Timed out waiting for any of $finders');
}

Finder _keyStartsWith(String prefix) => find.byWidgetPredicate((widget) {
  final key = widget.key;
  return key is ValueKey<String> && key.value.startsWith(prefix);
});

Future<void> _tap(WidgetTester tester, Finder finder) async {
  await _pumpUntil(tester, finder);
  await tester.ensureVisible(finder.first);
  await tester.pumpAndSettle();
  final hitTestable = finder.hitTestable();
  await _pumpUntil(tester, hitTestable);
  await tester.tap(hitTestable.first);
  await tester.pump();
}

Future<void> _scrollUntilVisible(WidgetTester tester, Finder finder) async {
  await tester.scrollUntilVisible(
    finder,
    500,
    scrollable: find.byType(Scrollable).hitTestable().last,
    maxScrolls: 50,
  );
  await tester.pumpAndSettle();
}

Future<void> _advanceSelfTestToAnswer(WidgetTester tester) async {
  final pages = find.byKey(const Key('self-test-pages'));
  final answer = find
      .byKey(const Key('self-test-answer-positive'))
      .hitTestable();
  for (var page = 0; page < 8; page++) {
    if (answer.evaluate().isNotEmpty) return;
    await tester.drag(pages, const Offset(-320, 0));
    await tester.pumpAndSettle();
  }
  throw TestFailure('Self-test answer page was not reachable');
}

Future<void> _pumpUntilFeedbackRecorded(WidgetTester tester) async {
  final finder = find.byKey(const Key('feedback-completed'));
  final deadline = DateTime.now().add(const Duration(seconds: 30));
  while (DateTime.now().isBefore(deadline)) {
    await tester.pump(const Duration(milliseconds: 200));
    final widgets = finder.evaluate();
    if (widgets.isNotEmpty &&
        tester.widget<ActionChip>(finder).onPressed == null) {
      return;
    }
  }
  throw TestFailure('Completed session feedback was not recorded');
}

Future<void> _pumpUntilDraftSettled(
  WidgetTester tester,
  ProviderContainer container,
) async {
  final deadline = DateTime.now().add(const Duration(seconds: 30));
  while (DateTime.now().isBefore(deadline)) {
    await tester.pump(const Duration(milliseconds: 200));
    final state = container.read(planProvider);
    if (state.draftStatus == LoadStatus.loading) continue;
    if (state.draftStatus == LoadStatus.data && state.draft != null) return;
    throw TestFailure(
      'Plan draft failed closed: status=${state.draftStatus.name}, '
      'failure=${state.draftFailure.name}',
    );
  }
  throw TestFailure('Timed out waiting for plan draft request to settle');
}

Future<void> _pumpUntilNutritionDraftSettled(
  WidgetTester tester,
  ProviderContainer container,
) async {
  final deadline = DateTime.now().add(const Duration(seconds: 30));
  while (DateTime.now().isBefore(deadline)) {
    await tester.pump(const Duration(milliseconds: 200));
    final state = container.read(nutritionProvider);
    if (state.status == LoadStatus.loading) continue;
    if (state.status == LoadStatus.data && state.draft != null) return;
    throw TestFailure(
      'Nutrition draft failed closed: status=${state.status.name}, '
      'code=${state.errorCode ?? 'none'}',
    );
  }
  throw TestFailure('Timed out waiting for nutrition draft request to settle');
}

Future<void> _pumpUntilPlanPairLoaded(
  WidgetTester tester,
  ProviderContainer container,
) async {
  final deadline = DateTime.now().add(const Duration(seconds: 30));
  while (DateTime.now().isBefore(deadline)) {
    await tester.pump(const Duration(milliseconds: 200));
    final state = container.read(planProvider);
    if (state.draftStatus == LoadStatus.loading ||
        state.activeStatus == LoadStatus.loading ||
        state.draftStatus == LoadStatus.idle ||
        state.activeStatus == LoadStatus.idle) {
      continue;
    }
    if (state.draft != null && state.activePlan != null) return;
    throw TestFailure(
      'Plan pair failed closed: draftStatus=${state.draftStatus.name}, '
      'hasDraft=${state.draft != null}, '
      'activeStatus=${state.activeStatus.name}, '
      'hasActive=${state.activePlan != null}',
    );
  }
  throw TestFailure('Timed out waiting for active plan and pending draft');
}

Future<void> _pumpUntilTrainingReviewDraftSettled(
  WidgetTester tester,
  ProviderContainer container,
) async {
  final deadline = DateTime.now().add(const Duration(seconds: 30));
  while (DateTime.now().isBefore(deadline)) {
    await tester.pump(const Duration(milliseconds: 200));
    final state = container.read(adaptiveReviewProvider);
    if (state.mutating || state.phase == ReviewPhase.loading) continue;
    final proposal = state.snapshot?.proposals.where(
      (item) => item.code == ReviewProposalCode.offerTrainingDraft,
    );
    if (state.phase == ReviewPhase.data &&
        proposal != null &&
        proposal.length == 1 &&
        proposal.single.state == ReviewProposalState.draft) {
      return;
    }
    throw TestFailure(
      'Weekly-review training draft failed closed: phase=${state.phase.name}',
    );
  }
  throw TestFailure('Timed out waiting for weekly-review training draft');
}

/// Dev-login through the real `/auth/dev-login` endpoint using the build-time
/// synthetic credentials, then wait for the authenticated Today surface.
Future<void> _devLogin(WidgetTester tester) async {
  await _tap(tester, find.byKey(const Key('login-dev-submit')));
  // After a successful real login the router redirects to /today.
  await _pumpUntil(tester, find.byKey(const Key('today-training-card')));
}

// --- Journey ----------------------------------------------------------------

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  final control = _ControlPlane();

  setUp(() async {
    // Real secure storage may still hold a token from a previous run whose
    // backend rows were just dropped. Clear it so the app authenticates fresh.
    await AppStorage.clearTokens();
  });

  testWidgets('blank_supported: full supported-adult UI journey', (
    tester,
  ) async {
    await control.reset(_kCheckpointBlank);
    final container = await _bootApp(tester);

    // 1. Real dev-login.
    await _devLogin(tester);

    // 2. Posture home -> category -> issue -> illustrated self-test -> result.
    _navigate(container, '/posture');
    await _tap(
      tester,
      find.byKey(const Key('home-posture-category-lower_limb')),
    );
    await _tap(tester, find.byKey(const Key('issue-list-item-LL-18')));
    await _tap(tester, find.byKey(const Key('issue-detail-start-self-test')));
    await _pumpUntil(tester, find.byKey(const Key('self-test-pages')));
    // Traverse every illustrated instruction page before answering.
    await _advanceSelfTestToAnswer(tester);
    await _tap(tester, find.byKey(const Key('self-test-answer-positive')));
    // Result + server posture-profile entry must render.
    await _pumpUntil(tester, find.byKey(const Key('result-screen')));

    // 3. Confirm an allowed posture goal.
    _navigate(container, '/profile/posture');
    await _tap(tester, _keyStartsWith('candidate-'));
    await _tap(tester, find.byKey(const Key('confirm-goals-button')));
    await _pumpUntil(tester, find.text('已确认目标'));

    // 4. The deterministic training gate requires today's current safety input
    //    before generation. Save the normal synthetic check-in first.
    _navigate(container, '/today');
    await _tap(tester, find.byKey(const Key('today-checkin-submit')));
    await _pumpUntil(tester, find.text('今日已签到'));

    // 5. Generate a four-week plan, verify no draft is shown as active, then
    //    explicitly confirm.
    _navigate(container, '/plan');
    await _tap(tester, find.byKey(const Key('plan-generate-button')));
    await _pumpUntilDraftSettled(tester, container);
    await tester.pumpAndSettle();
    await _scrollUntilVisible(
      tester,
      find.byKey(const Key('plan-confirm-button')),
    );
    await _pumpUntil(tester, find.byKey(const Key('plan-confirm-button')));
    // A draft must not be presented as an active plan before confirmation:
    // the confirm control is present and the active-view Agent entry is not.
    expect(find.byKey(const Key('agent-plan-entry')), findsNothing);
    await _tap(tester, find.byKey(const Key('plan-confirm-button')));
    await _pumpUntil(tester, find.byKey(const Key('agent-plan-entry')));

    // 6. Return to Today and prove the saved check-in plus training projection
    //    are both visible. Merely revisiting must not issue another save.
    _navigate(container, '/today');
    await _pumpUntil(tester, find.text('今日已签到'));
    await _pumpUntil(tester, find.byKey(const Key('today-training-card')));

    // 7. Inspect effective Today and request a legal same-day adjustment.
    _navigate(container, '/plan');
    await _pumpUntilTodayRecovered(tester, container);
    final effectiveToday = container.read(planProvider).today!;
    if (effectiveToday.state == TodayState.session) {
      await _tap(tester, find.byKey(const Key('today-adjust-button')));
      await _pumpUntilAny(tester, [
        find.byKey(const Key('adjust-status-applied')),
        find.byKey(const Key('adjust-status-replayed')),
      ]);
      await _pumpUntil(
        tester,
        find.byKey(const Key('today-effective-summary')),
      );
      await _tap(tester, find.byKey(const Key('feedback-completed')));
      await _pumpUntilFeedbackRecorded(tester);
    } else {
      expect(effectiveToday.localDate?.weekday, DateTime.saturday);
      expect(effectiveToday.state, TodayState.restDay);
      expect(find.byKey(const Key('today-adjust-button')), findsNothing);
    }

    // 8. Add a synthetic manual weight through the UI.
    _navigate(container, '/profile/weight');
    await _tap(tester, find.byKey(const Key('weight-add-fab')));
    await _pumpUntil(tester, find.byKey(const Key('weight-input')));
    await tester.enterText(find.byKey(const Key('weight-input')), '70.5');
    await tester.pump();
    await _tap(tester, find.byKey(const Key('weight-save-button')));
    await _pumpUntil(tester, _keyStartsWith('weight-delete-'));

    // Activity grid + weight trend render (presence/state only).
    _navigate(container, '/profile/grid');
    await _pumpUntil(tester, _keyStartsWith('grid-cell-'));

    // 9. Agent bounded explanation. Grant consent if required, then send.
    _navigate(container, '/agent');
    await _pumpUntil(tester, find.byKey(const Key('agent-consent-view')));
    await _tap(tester, find.byKey(const Key('agent-consent-checkbox')));
    await _tap(tester, find.byKey(const Key('agent-consent-grant')));
    await _pumpUntil(tester, find.byKey(const Key('agent-message-input')));
    await tester.enterText(
      find.byKey(const Key('agent-message-input')),
      'Summarize the synthetic health profile without changing records.',
    );
    await tester.pump();
    await _tap(tester, find.byKey(const Key('agent-send')));
    final conversationCards = find.descendant(
      of: find.byKey(const Key('agent-conversation')),
      matching: find.byType(Card),
    );
    final messageDeadline = DateTime.now().add(const Duration(seconds: 30));
    while (DateTime.now().isBefore(messageDeadline) &&
        conversationCards.evaluate().length < 2) {
      await tester.pump(const Duration(milliseconds: 200));
    }
    expect(conversationCards, findsAtLeastNWidgets(2));
    expect(find.byKey(const Key('agent-proposal-card')), findsNothing);

    // 10. Nutrition draft -> explicit confirm; source/uncertainty rendered.
    _navigate(container, '/plan/nutrition');
    await _pumpUntil(
      tester,
      find.byKey(const Key('nutrition-source-uncertainty')),
    );
    await _tap(tester, find.byKey(const Key('nutrition-generate-draft')));
    await _pumpUntilNutritionDraftSettled(tester, container);
    await _pumpUntil(tester, find.byKey(const Key('nutrition-draft-label')));
    // A draft must not be active before its own confirmation.
    expect(find.byKey(const Key('nutrition-active-label')), findsNothing);
    await _tap(tester, find.byKey(const Key('nutrition-confirm-draft')));
    await _pumpUntil(tester, find.byKey(const Key('nutrition-active-label')));
  });

  testWidgets(
    'cycle_due: week-4 review facts precede proposals, no auto-activation',
    (tester) async {
      await control.reset(_kCheckpointCycleDue);
      final container = await _bootApp(tester);
      await _devLogin(tester);

      // Generate + inspect the week-four review.
      _navigate(container, '/plan/weekly-review');
      await _tap(tester, find.byKey(const Key('review-week-4')));
      await _pumpUntil(tester, find.byKey(const Key('review-not-generated')));
      await _tap(tester, find.byKey(const Key('review-generate-button')));
      await _pumpUntil(tester, find.byKey(const Key('review-facts')));
      expect(find.byKey(const Key('review-proposals')), findsOneWidget);

      // Facts must render before proposals.
      final factsY = tester.getCenter(find.byKey(const Key('review-facts'))).dy;
      final proposalsY = tester
          .getCenter(find.byKey(const Key('review-proposals')))
          .dy;
      expect(factsY, lessThan(proposalsY));

      // The posture-recheck state is visible in the review.
      expect(
        find.byKey(const Key('review-proposal-posture_recheck_due')),
        findsOneWidget,
      );

      // Materialize exactly one offered domain draft. Review generation alone
      // did not create it, and this action still must not activate it.
      final createDraft = find.byKey(const Key('review-create-training-draft'));
      await _scrollUntilVisible(tester, createDraft);
      await _tap(tester, createDraft);
      await _pumpUntilTrainingReviewDraftSettled(tester, container);

      // The pre-existing active plan is still present and is NOT hidden by any
      // review-offered draft; activation remains a separate, explicit action.
      _navigate(container, '/plan');
      await _pumpUntilPlanPairLoaded(tester, container);
      await _pumpUntil(tester, find.byKey(const Key('plan-active-tab')));
      await _pumpUntil(tester, find.byKey(const Key('agent-plan-entry')));
      expect(find.byKey(const Key('plan-confirm-button')), findsNothing);
      await _tap(tester, find.byKey(const Key('plan-draft-tab')));
      await tester.pumpAndSettle();
      await _scrollUntilVisible(
        tester,
        find.byKey(const Key('plan-confirm-button')),
      );
      await _pumpUntil(tester, find.byKey(const Key('plan-confirm-button')));
    },
  );

  testWidgets('safety_blocked: safety state visible, no ordinary activation', (
    tester,
  ) async {
    await control.reset(_kCheckpointSafetyBlocked);
    final container = await _bootApp(tester);
    await _devLogin(tester);

    // This checkpoint has no active plan. An explicit generation attempt must
    // preserve the backend's restricted_no_plan code as a visible safety block.
    _navigate(container, '/plan');
    await _pumpUntil(tester, find.byKey(const Key('plan-generate-button')));
    await _tap(tester, find.byKey(const Key('plan-generate-button')));
    await _pumpUntil(tester, find.byKey(const Key('plan-status-safety')));
    expect(find.byKey(const Key('plan-confirm-button')), findsNothing);
    expect(find.byKey(const Key('adjust-status-applied')), findsNothing);

    // Nutrition must not offer an activate-able draft under a safety block.
    _navigate(container, '/plan/nutrition');
    await _pumpUntilNutritionGate(tester, container, NutritionGate.restricted);
    await _pumpUntil(
      tester,
      find.byKey(const Key('nutrition-status-restricted')),
    );
    expect(find.byKey(const Key('nutrition-confirm-draft')), findsNothing);
    expect(find.byKey(const Key('nutrition-active-label')), findsNothing);
  });

  testWidgets(
    'missing input: real plan mutation fails closed without a draft write',
    (tester) async {
      final baseline = await control.reset(_kCheckpointBlank);
      final container = await _bootApp(tester);
      await _devLogin(tester);

      // The blank checkpoint deliberately has no current-day check-in. The
      // production training gate, not the control plane, must reject this POST.
      _navigate(container, '/plan');
      await _pumpUntil(tester, find.byKey(const Key('plan-generate-button')));
      await _tap(tester, find.byKey(const Key('plan-generate-button')));
      await _pumpUntil(tester, find.byKey(const Key('plan-status-missing')));
      expect(find.byKey(const Key('plan-confirm-button')), findsNothing);

      final evidence = await control.evidence(_kCheckpointBlank);
      expect(evidence.tableCounts['training_plan_versions'], 0);
      expect(evidence.tableCounts, baseline.tableCounts);
    },
  );

  testWidgets(
    'stale context: one-shot real plan mutation fails closed without a draft',
    (tester) async {
      final baseline = await control.reset(_kCheckpointBlank);
      final container = await _bootApp(tester);
      await _devLogin(tester);
      await control.installFault(
        route: '/api/v1/training/plans:draft',
        kind: 'stale_context',
      );

      _navigate(container, '/plan');
      await _pumpUntil(tester, find.byKey(const Key('plan-generate-button')));
      await _tap(tester, find.byKey(const Key('plan-generate-button')));
      await _pumpUntil(tester, find.byKey(const Key('plan-status-stale')));
      expect(find.byKey(const Key('plan-confirm-button')), findsNothing);

      final evidence = await control.evidence(_kCheckpointBlank);
      expect(evidence.tableCounts['training_plan_versions'], 0);
      expect(evidence.tableCounts, baseline.tableCounts);
    },
  );

  testWidgets(
    'one-shot fault: unavailable state then fresh-HTTP retry recovers',
    (tester) async {
      await control.reset(_kCheckpointCycleDue);
      final container = await _bootApp(tester);
      await _devLogin(tester);

      // Install only after Today finishes booting, so PlanScreen's next fresh
      // request is the deterministic one-shot consumer.
      await control.installFault(
        route: '/api/v1/training/today',
        kind: 'service_unavailable',
      );

      _navigate(container, '/plan');
      await _pumpUntil(
        tester,
        find.byKey(const Key('today-status-unavailable')),
      );
      expect(find.byKey(const Key('today-adjust-button')), findsNothing);

      // Explicit retry performs a fresh request; the one-shot fault is spent and
      // the effective Today projection recovers.
      await _tap(
        tester,
        find.descendant(
          of: find.byKey(const Key('today-status-unavailable')),
          matching: find.byType(OutlinedButton),
        ),
      );
      await _pumpUntilTodayRecovered(tester, container);
      expect(find.byKey(const Key('today-status-unavailable')), findsNothing);
    },
  );

  testWidgets(
    'malformed Today: parse-error or unavailable then retry recovers',
    (tester) async {
      await control.reset(_kCheckpointCycleDue);
      final container = await _bootApp(tester);
      await _devLogin(tester);
      await control.installFault(
        route: '/api/v1/training/today',
        kind: 'malformed_json',
      );

      _navigate(container, '/plan');
      final failed = await _pumpUntilAny(tester, [
        find.byKey(const Key('today-status-parse-error')),
        find.byKey(const Key('today-status-unavailable')),
      ]);
      expect(find.byKey(const Key('today-adjust-button')), findsNothing);
      await _tap(
        tester,
        find.descendant(of: failed, matching: find.byType(OutlinedButton)),
      );
      await _pumpUntilTodayRecovered(tester, container);
      expect(find.byKey(const Key('today-status-parse-error')), findsNothing);
      expect(find.byKey(const Key('today-status-unavailable')), findsNothing);
    },
  );

  testWidgets('final reset clears prior active/draft state from the UI', (
    tester,
  ) async {
    final evidence = await control.reset(_kCheckpointBlank);
    evidence.expectBlankBaseline();
    final container = await _bootApp(tester);
    await _devLogin(tester);

    // No active plan / draft: the generation form is shown, not an active view.
    _navigate(container, '/plan');
    await _pumpUntil(tester, find.byKey(const Key('plan-generate-button')));
    expect(find.byKey(const Key('plan-confirm-button')), findsNothing);
    expect(find.byKey(const Key('agent-plan-entry')), findsNothing);

    // No active nutrition recommendation from a previous run.
    _navigate(container, '/plan/nutrition');
    await _pumpUntilNutritionGate(
      tester,
      container,
      NutritionGate.clarificationRequired,
    );
    await _pumpUntil(
      tester,
      find.byKey(const Key('nutrition-status-clarification_required')),
    );
    expect(find.byKey(const Key('nutrition-active-label')), findsNothing);
  });
}
