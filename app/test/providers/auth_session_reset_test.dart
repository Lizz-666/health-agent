import 'dart:async';

import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:posture_app/core/api_client.dart';
import 'package:posture_app/providers/activity_grid_provider.dart';
import 'package:posture_app/providers/agent_provider.dart';
import 'package:posture_app/providers/assessment_provider.dart';
import 'package:posture_app/providers/auth_provider.dart';
import 'package:posture_app/providers/daily_checkin_provider.dart';
import 'package:posture_app/providers/health_profile_provider.dart';
import 'package:posture_app/providers/plan_provider.dart';
import 'package:posture_app/providers/posture_profile_provider.dart';
import 'package:posture_app/providers/posture_state_provider.dart';
import 'package:posture_app/providers/user_provider.dart';
import 'package:posture_app/providers/weight_trend_provider.dart';

import '_test_dio.dart';

ApiClient _apiWith(FakeDioAdapter adapter) {
  final api = ApiClient()..dio.interceptors.clear();
  api.dio.httpClientAdapter = adapter;
  return api;
}

void main() {
  test('auth failure synchronously invalidates cached health state', () async {
    final adapter = FakeDioAdapter();
    adapter.register(
      'GET',
      '/posture/history',
      (options) => Response(
        requestOptions: options,
        statusCode: 200,
        data: [
          {
            'id': 'record-user-a',
            'issue_id': 'HN-01',
            'issue_name': '用户 A 的记录',
            'source': 'self_test',
            'method': 'self_test',
            'result': 'moderate',
            'created_at': '2026-07-18T10:00:00Z',
          },
        ],
      ),
    );
    adapter.registerJson(
      'GET',
      '/posture/profile',
      (_) => {
        'user_id': 'user-a',
        'evaluated_issues': <Map<String, dynamic>>[],
        'unevaluated_categories': <String>['head_neck'],
        'summary': {
          'total_evaluated': 0,
          'total_conflict': 0,
          'total_provisional': 0,
        },
      },
    );
    adapter.registerJson(
      'GET',
      '/user/profile',
      (_) => {
        'id': 'user-a',
        'phone': 'synthetic-user-a',
        'membership_level': 'free',
      },
    );
    final api = _apiWith(adapter);
    final container = ProviderContainer(
      overrides: [apiClientProvider.overrideWithValue(api)],
    );
    addTearDown(container.dispose);

    // Register the authentication-failure callback, then seed synthetic
    // user-A data in each user-scoped health provider.
    container.read(authProvider);
    await container.read(assessmentProvider.notifier).fetchHistory();
    await container.read(postureProfileProvider.notifier).fetchProfile();
    await container.read(userProvider.notifier).fetchProfile();
    container
        .read(postureStateProvider.notifier)
        .updateState(issueId: 'HN-01', result: 'moderate', method: 'self_test');

    expect(container.read(assessmentProvider).history, isNotEmpty);
    expect(container.read(postureProfileProvider).profile?.userId, 'user-a');
    expect(container.read(postureStateProvider), isNotEmpty);
    expect(container.read(userProvider).profile?.id, 'user-a');

    final pendingResponse = Completer<Response>();
    adapter.register('GET', '/posture/history', (_) => pendingResponse.future);
    final oldSessionRefresh = container
        .read(assessmentProvider.notifier)
        .fetchHistory();
    await Future<void>.delayed(Duration.zero);

    api.onAuthFailed?.call();

    expect(container.read(assessmentProvider).history, isEmpty);
    expect(container.read(postureProfileProvider).profile, isNull);
    expect(container.read(postureStateProvider), isEmpty);
    expect(container.read(userProvider).profile, isNull);

    pendingResponse.complete(
      Response(
        requestOptions: RequestOptions(path: '/posture/history'),
        statusCode: 200,
        data: [
          {
            'id': 'late-record-user-a',
            'issue_id': 'HN-01',
            'issue_name': '用户 A 的延迟记录',
            'source': 'self_test',
            'method': 'self_test',
            'result': 'severe',
            'created_at': '2026-07-18T11:00:00Z',
          },
        ],
      ),
    );
    await oldSessionRefresh;
    expect(container.read(assessmentProvider).history, isEmpty);
  });

  test(
    'auth failure clears all Phase 2 health state and blocks stale repopulation',
    () async {
      final profile = <String, dynamic>{
        'configured': true,
        'profile': {
          'id': 'health-user-a',
          'fitness_goal': 'basic_strength',
          'training_experience': null,
          'weekly_frequency': null,
          'session_duration_minutes': null,
          'equipment': null,
          'pain_injury_limitations': null,
          'risk_screen': null,
          'allergies': null,
          'diet_exclusions': null,
          'version': 1,
          'updated_at': '2026-07-23T08:00:00Z',
          'created_at': '2026-07-23T08:00:00Z',
        },
        'readiness': {
          'readiness': 'ready',
          'risk_version': '2026-07-22-v1',
          'reason': 'synthetic',
          'missing_fields': <String>[],
          'restricted_reason': null,
        },
      };
      final checkin = <String, dynamic>{
        'checked_in': true,
        'checkin': {
          'id': 'checkin-user-a',
          'local_date': '2026-07-23',
          'sleep_quality': 'good',
          'energy': 'normal',
          'muscle_soreness': 'mild',
          'available_time': '30_min',
          'daily_status': 'checked_in',
          'abnormal_pain': false,
          'pain_followup': null,
          'risk_summary': 'normal',
          'risk_version': '2026-07-22-v1',
          'created_at': '2026-07-23T08:00:00Z',
          'updated_at': '2026-07-23T08:00:00Z',
        },
      };
      final trend = <String, dynamic>{
        'records': [
          {
            'id': 'weight-user-a',
            'recorded_at': '2026-07-23T08:00:00Z',
            'weight_kg': 70.0,
            'source': 'manual',
            'note': null,
            'created_at': '2026-07-23T08:00:00Z',
            'updated_at': '2026-07-23T08:00:00Z',
          },
        ],
        'trend': <Map<String, dynamic>>[],
        'window': 7,
        'sufficient': false,
      };
      final grid = <String, dynamic>{
        'start_date': '2026-07-20',
        'end_date': '2026-07-23',
        'cells': [
          {'date': '2026-07-21', 'status': 'checked_in'},
        ],
      };

      final adapter = FakeDioAdapter()
        ..registerJson('GET', '/health/profile', (_) => profile)
        ..registerJson('GET', '/health/checkins/today', (_) => checkin)
        ..registerJson('GET', '/health/trends/weight', (_) => trend)
        ..registerJson('GET', '/health/activity-grid', (_) => grid);
      final api = _apiWith(adapter);
      final container = ProviderContainer(
        overrides: [apiClientProvider.overrideWithValue(api)],
      );
      addTearDown(container.dispose);

      // Wire the auth-failure reset callback.
      container.read(authProvider);

      // Seed synthetic user-A Phase 2 state.
      await container.read(healthProfileProvider.notifier).fetchProfile();
      await container
          .read(dailyCheckinProvider.notifier)
          .fetchToday(localDate: DateTime(2026, 7, 23));
      await container.read(weightTrendProvider.notifier).fetchTrend();
      await container.read(activityGridProvider.notifier).fetchGrid();

      expect(
        container.read(healthProfileProvider).result?.profile?.id,
        'health-user-a',
      );
      expect(
        container.read(dailyCheckinProvider).checkin?.id,
        'checkin-user-a',
      );
      expect(container.read(weightTrendProvider).trend?.records.length, 1);
      expect(container.read(activityGridProvider).grid?.cells.length, 1);

      // Start a slow profile fetch (user A), then trigger the auth reset.
      final pending = Completer<Response>();
      adapter.register('GET', '/health/profile', (_) => pending.future);
      final staleFetch = container
          .read(healthProfileProvider.notifier)
          .fetchProfile();
      await Future<void>.delayed(Duration.zero);

      api.onAuthFailed?.call();

      // All Phase 2 state is cleared (fresh idle notifiers after invalidate).
      expect(container.read(healthProfileProvider).result, isNull);
      expect(container.read(dailyCheckinProvider).checkin, isNull);
      expect(container.read(weightTrendProvider).trend, isNull);
      expect(container.read(activityGridProvider).grid, isNull);

      // A late user-A response must not repopulate the cleared state.
      pending.complete(
        Response(
          requestOptions: RequestOptions(path: '/health/profile'),
          statusCode: 200,
          data: profile,
        ),
      );
      await staleFetch;
      expect(container.read(healthProfileProvider).result, isNull);
    },
  );

  test(
    'auth failure clears Phase 4 plan state (no cross-account leak)',
    () async {
      final plan = <String, dynamic>{
        'has_active': true,
        'plan': {
          'plan_version_id': 'plan-user-a',
          'requested_goal': 'basic_strength',
          'weekly_frequency': 3,
          'session_duration_minutes': 30,
          'status': 'active',
          'change_reason': 'initial_confirmation',
          'decision_gate': 'eligible',
          'generated_at': '2026-07-27T08:00:00Z',
          'confirmed_at': '2026-07-27T08:05:00Z',
          'catalog_version': 'v1',
          'policy_version': 'v1',
          'sessions': [
            {
              'session_id': 's-a',
              'week_index': 1,
              'day_of_week': 1,
              'session_order': 1,
              'target_minutes': null,
              'prescriptions': [
                {
                  'prescription_id': 'p-a',
                  'exercise_id': 'ex-1',
                  'sets': 3,
                  'reps': 10,
                  'duration_seconds': null,
                  'rest_seconds': 60,
                  'relation_reason': null,
                  'exercise': {
                    'exercise_id': 'ex-1',
                    'name_en': 'Squat',
                    'name_zh': '深蹲',
                    'training_roles': ['strength'],
                    'difficulty': 'beginner',
                    'illustration_asset_key':
                        'assets/training/illustrations/ex-1.svg',
                    'illustration_alt_zh': '深蹲',
                    'instruction_steps': ['stand'],
                    'form_cues': ['straight'],
                    'substitution_ids': [],
                  },
                },
              ],
            },
          ],
        },
      };
      final adapter = FakeDioAdapter()
        ..registerJson('GET', '/training/plans/active', (_) => plan);
      final api = _apiWith(adapter);
      final container = ProviderContainer(
        overrides: [apiClientProvider.overrideWithValue(api)],
      );
      addTearDown(container.dispose);

      container.read(authProvider);
      await container.read(planProvider.notifier).fetchActive();
      expect(
        container.read(planProvider).activePlan?.planVersionId,
        'plan-user-a',
      );

      // Trigger the auth-failure reset (logout / token failure / account switch).
      api.onAuthFailed?.call();

      // Plan state is cleared so the next user never sees user A's plan.
      expect(container.read(planProvider).activePlan, isNull);
    },
  );

  test('auth failure destroys ephemeral Phase 5 Agent conversation', () async {
    final disclosure = {
      'disclosure_version': 'agent-disclosure-v1',
      'provider_id': 'dashscope',
      'provider_name_zh': 'synthetic provider',
      'purpose_code': 'wellness_agent_assistance',
      'processing_boundary_code': 'cloud_model_processing',
      'data_scope_codes': ['structured_health_context'],
      'application_retention_code': 'no_chat_transcript_persistence',
      'withdrawal_available': true,
      'agent_data_deletion_available': true,
    };
    final adapter = FakeDioAdapter()
      ..registerJson(
        'GET',
        '/agent/capabilities',
        (_) => {
          'runtime_enabled': true,
          'provider_configured': true,
          'provider_id': 'dashscope',
          'model_id': 'qwen-plus',
          'disclosure_version': 'agent-disclosure-v1',
          'consent_active': true,
          'available': true,
          'result_code': 'agent_available',
          'message': 'Agent 已满足当前运行与隐私条件。',
          'disclosure': disclosure,
        },
      )
      ..registerJson(
        'POST',
        '/agent/turns',
        (_) => {
          'run_id': '20000000-0000-4000-8000-000000000001',
          'status': 'answer',
          'message': '已根据当前可访问的信息整理结果。',
          'result_code': 'agent_answer_ready',
          'display_data': <Map<String, dynamic>>[],
          'proposal': null,
          'replayed': false,
        },
      );
    final api = _apiWith(adapter);
    final container = ProviderContainer(
      overrides: [apiClientProvider.overrideWithValue(api)],
    );
    addTearDown(container.dispose);

    container.read(authProvider);
    await container.read(agentProvider.notifier).loadCapabilities();
    await container
        .read(agentProvider.notifier)
        .sendMessage('synthetic message');
    expect(container.read(agentProvider).messages, isNotEmpty);

    api.onAuthFailed?.call();

    expect(container.read(agentProvider).messages, isEmpty);
    expect(
      container.read(agentProvider).capabilitiesStatus,
      AgentLoadStatus.idle,
    );
  });
}
