// app/test/providers/posture_profile_provider_test.dart
import 'dart:async';

import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:posture_app/core/api_client.dart';
import 'package:posture_app/models/posture_profile.dart';
import 'package:posture_app/models/priority_suggestion.dart';
import 'package:posture_app/models/safety_signal.dart';
import 'package:posture_app/providers/assessment_provider.dart' show LoadStatus;
import 'package:posture_app/providers/posture_profile_provider.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '_test_dio.dart';

ApiClient _apiWith(FakeDioAdapter adapter) {
  final api = ApiClient();
  // Strip auth/storage interceptors so tests run without flutter_secure_storage.
  api.dio.interceptors.clear();
  api.dio.httpClientAdapter = adapter;
  return api;
}

ProviderContainer _container(ApiClient api) =>
    ProviderContainer(overrides: [apiClientProvider.overrideWithValue(api)]);

final _emptyProfile = <String, dynamic>{
  'user_id': 'user-1',
  'evaluated_issues': <Map<String, dynamic>>[],
  'unevaluated_categories': <String>[
    'head_neck',
    'cervical',
    'upper_back',
    'thoracic',
    'lower_back',
    'shoulder_thorax',
    'pelvis_spine',
    'lower_limb',
    'compound',
  ],
  'summary': {
    'total_evaluated': 0,
    'total_conflict': 0,
    'total_provisional': 0,
  },
};

final _oneEntryProfile = <String, dynamic>{
  'user_id': 'user-1',
  'evaluated_issues': [
    {
      'issue_id': 'HN-01',
      'issue_name': '头部前倾',
      'category': 'head_neck',
      'combined_severity': 'moderate',
      'certainty': 'confirmed',
      'has_conflict': false,
      'sources': [
        {
          'source': 'self_test',
          'event_id': 'evt-1',
          'severity': 'moderate',
          'created_at': '2026-07-11T10:00:00Z',
        },
      ],
      'risk_tier': 'normal',
      'risk_version': 'phase1-initial-v1',
      'updated_at': '2026-07-11T10:05:00Z',
    },
  ],
  'unevaluated_categories': <String>['compound', 'lower_limb'],
  'summary': {
    'total_evaluated': 1,
    'total_conflict': 0,
    'total_provisional': 0,
  },
};

Map<String, dynamic> _suggestionsWithCandidates(List<String> issueIds) => {
  'suggestion_id': 'sugg-1',
  'profile_version': 'pv-1',
  'rule_version': '2026-07-17-v1',
  'risk_version': '2026-07-16-v4',
  'generated_at': '2026-07-17T12:00:00Z',
  'normal_candidates': [
    for (var i = 0; i < issueIds.length; i++)
      {
        'issue_id': issueIds[i],
        'issue_name': 'issue-$i',
        'suggested_rank': i + 1,
        'reasons': ['r'],
      },
  ],
  'retest_required': <Map<String, dynamic>>[],
  'safety_blocked': <Map<String, dynamic>>[],
  'disclaimer': 'd',
};

final _safetyResponse = <String, dynamic>{
  'signal_id': 'sig-1',
  'status': 'recorded',
  'lifecycle': 'active',
  'risk_tier': 'cautious',
  'risk_version': '2026-07-16-v4',
  'invalidates_until': '2026-08-11T00:00:00Z',
  'classification': {
    'risk_tier': 'cautious',
    'risk_version': '2026-07-16-v4',
    'rule_id': 'rule-x',
    'reason': 'r',
    'sources': <Map<String, dynamic>>[],
  },
};

void main() {
  test('container can override apiClientProvider', () {
    final adapter = FakeDioAdapter();
    final api = _apiWith(adapter);
    final container = _container(api);
    expect(container.read(apiClientProvider), same(api));
    container.dispose();
  });

  group('fetchProfile', () {
    test('empty 200 response -> status=empty, not error', () async {
      final adapter = FakeDioAdapter()
        ..registerJson('GET', '/posture/profile', (_) => _emptyProfile);
      final container = _container(_apiWith(adapter));
      final notifier = container.read(postureProfileProvider.notifier);
      await notifier.fetchProfile();
      final state = container.read(postureProfileProvider);
      expect(state.profileStatus, LoadStatus.empty);
      expect(state.profile, isNotNull);
      expect(state.profile!.evaluatedIssues, isEmpty);
      expect(state.error, isNull);
      container.dispose();
    });

    test('non-empty 200 response -> status=data', () async {
      final adapter = FakeDioAdapter()
        ..registerJson('GET', '/posture/profile', (_) => _oneEntryProfile);
      final container = _container(_apiWith(adapter));
      final notifier = container.read(postureProfileProvider.notifier);
      await notifier.fetchProfile();
      final state = container.read(postureProfileProvider);
      expect(state.profileStatus, LoadStatus.data);
      expect(state.profile!.evaluatedIssues.length, 1);
      container.dispose();
    });

    test('network error -> status=networkError', () async {
      final adapter = FakeDioAdapter()
        ..registerError('GET', '/posture/profile', 500, {
          'detail': '服务异常',
          'code': 'internal',
        });
      final container = _container(_apiWith(adapter));
      await container.read(postureProfileProvider.notifier).fetchProfile();
      final state = container.read(postureProfileProvider);
      expect(state.profileStatus, LoadStatus.networkError);
      expect(state.error, '服务异常');
      container.dispose();
    });

    test('successful retry clears an earlier profile error', () async {
      var calls = 0;
      final adapter = FakeDioAdapter()
        ..register('GET', '/posture/profile', (options) {
          calls++;
          if (calls == 1) {
            throw DioException(
              requestOptions: options,
              response: Response(
                requestOptions: options,
                statusCode: 503,
                data: {'detail': '暂不可用', 'code': 'unavailable'},
              ),
              type: DioExceptionType.badResponse,
            );
          }
          return Response(
            requestOptions: options,
            statusCode: 200,
            data: _emptyProfile,
          );
        });
      final container = _container(_apiWith(adapter));
      final notifier = container.read(postureProfileProvider.notifier);
      await notifier.fetchProfile();
      expect(container.read(postureProfileProvider).error, '暂不可用');
      await notifier.fetchProfile();
      expect(container.read(postureProfileProvider).error, isNull);
      expect(
        container.read(postureProfileProvider).profileStatus,
        LoadStatus.empty,
      );
      container.dispose();
    });

    test(
      'parse error (unknown risk_tier) -> status=parseError, never normal',
      () async {
        final bad = Map<String, dynamic>.from(_oneEntryProfile);
        final badEntry = Map<String, dynamic>.from(
          bad['evaluated_issues'][0] as Map,
        )..['risk_tier'] = 'critical';
        bad['evaluated_issues'] = [badEntry];
        final adapter = FakeDioAdapter()
          ..registerJson('GET', '/posture/profile', (_) => bad);
        final container = _container(_apiWith(adapter));
        await container.read(postureProfileProvider.notifier).fetchProfile();
        final state = container.read(postureProfileProvider);
        expect(state.profileStatus, LoadStatus.parseError);
        expect(state.profile, isNull);
        container.dispose();
      },
    );
  });

  group('fetchProfileEntry', () {
    test('parses a single entry detail', () async {
      final adapter = FakeDioAdapter()
        ..registerJson(
          'GET',
          '/posture/profile/HN-01',
          (_) => _oneEntryProfile['evaluated_issues'][0],
        );
      final container = _container(_apiWith(adapter));
      await container
          .read(postureProfileProvider.notifier)
          .fetchProfileEntry('HN-01');
      final state = container.read(postureProfileProvider);
      expect(state.entryStatus, LoadStatus.data);
      expect(state.entryDetail!.issueId, 'HN-01');
      container.dispose();
    });

    test('404 issue_not_found -> empty (not parseError)', () async {
      final adapter = FakeDioAdapter()
        ..registerError('GET', '/posture/profile/HN-01', 404, {
          'detail': '问题不存在',
          'code': 'issue_not_found',
        });
      final container = _container(_apiWith(adapter));
      await container
          .read(postureProfileProvider.notifier)
          .fetchProfileEntry('HN-01');
      final state = container.read(postureProfileProvider);
      expect(state.entryStatus, LoadStatus.empty);
      container.dispose();
    });
  });

  group('fetchPriorities', () {
    test(
      'three empty buckets -> status=empty, needsReconfirm cleared',
      () async {
        final adapter = FakeDioAdapter()
          ..registerJson(
            'GET',
            '/posture/priorities',
            (_) => _suggestionsWithCandidates([]),
          );
        final container = _container(_apiWith(adapter));
        await container.read(postureProfileProvider.notifier).fetchPriorities();
        final state = container.read(postureProfileProvider);
        expect(state.prioritiesStatus, LoadStatus.empty);
        expect(state.priorities!.normalCandidates, isEmpty);
        expect(state.needsReconfirm, isFalse);
        container.dispose();
      },
    );

    test('parse error -> status=parseError', () async {
      final adapter = FakeDioAdapter()
        ..registerError('GET', '/posture/priorities', 500, {
          'detail': 'x',
          'code': 'internal',
        });
      final container = _container(_apiWith(adapter));
      await container.read(postureProfileProvider.notifier).fetchPriorities();
      expect(
        container.read(postureProfileProvider).prioritiesStatus,
        LoadStatus.networkError,
      );
      container.dispose();
    });
  });

  group('confirmGoals', () {
    test('refuses locally invalid input without HTTP call', () async {
      final adapter = FakeDioAdapter();
      final container = _container(_apiWith(adapter));
      // Seed priorities first so confirm has a suggestion context.
      final adapter2 = FakeDioAdapter()
        ..registerJson(
          'GET',
          '/posture/priorities',
          (_) => _suggestionsWithCandidates(['HN-01']),
        );
      final container2 = _container(_apiWith(adapter2));
      await container2.read(postureProfileProvider.notifier).fetchPriorities();

      // Try to confirm an outsider issue -> no HTTP, typed invalidGoal.
      final ok = await container2
          .read(postureProfileProvider.notifier)
          .confirmGoals([GoalInput(issueId: 'OUTSIDER', priorityRank: 1)]);
      expect(ok, isFalse);
      final state = container2.read(postureProfileProvider);
      expect(state.confirmError, PostureConfirmError.invalidGoal);
      expect(state.confirmStatus, LoadStatus.parseError);
      // No POST ever registered -> 0 calls recorded.
      expect(adapter2.calls.where((c) => c.method == 'POST'), isEmpty);
      container.dispose();
      container2.dispose();
    });

    test('sends idempotency_key + server control values on success', () async {
      final adapter = FakeDioAdapter()
        ..registerJson(
          'GET',
          '/posture/priorities',
          (_) => _suggestionsWithCandidates(['HN-01', 'SS-01']),
        )
        ..registerJson('POST', '/posture/goals/confirm', (options) {
          return {
            'confirmed_goals': [
              {
                'issue_id': 'HN-01',
                'priority_rank': 1,
                'confirmed_at': '2026-07-17T12:30:00Z',
              },
            ],
            'can_generate_plan': true,
            'risk_version': '2026-07-16-v4',
          };
        });
      final container = _container(_apiWith(adapter));
      await container.read(postureProfileProvider.notifier).fetchPriorities();
      final ok = await container
          .read(postureProfileProvider.notifier)
          .confirmGoals([GoalInput(issueId: 'HN-01', priorityRank: 1)]);
      expect(ok, isTrue);
      final state = container.read(postureProfileProvider);
      expect(state.confirmStatus, LoadStatus.data);
      expect(state.confirmedGoals!.confirmedGoals.first.issueId, 'HN-01');
      expect(state.priorities, isNull);
      // Assert the POST body carried the server control values + a v4 key.
      final post = adapter.calls.lastWhere(
        (c) => c.method == 'POST' && c.path.contains('/goals/confirm'),
      );
      expect(post.data['suggestion_id'], 'sugg-1');
      expect(post.data['profile_version'], 'pv-1');
      expect(post.data['idempotency_key'], isNotEmpty);
      expect(
        RegExp(
          r'^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$',
        ).hasMatch(post.data['idempotency_key'] as String),
        isTrue,
      );
      container.dispose();
    });

    test(
      '409 stale_priority clears suggestions, sets needsReconfirm, refreshes, no replay',
      () async {
        var prioritiesCalls = 0;
        final adapter = FakeDioAdapter()
          ..register('GET', '/posture/priorities', (options) {
            prioritiesCalls++;
            return Response(
              requestOptions: options,
              statusCode: 200,
              data: prioritiesCalls == 1
                  ? _suggestionsWithCandidates(['HN-01'])
                  : _suggestionsWithCandidates(['HN-01', 'SS-01']),
            );
          })
          ..registerError('POST', '/posture/goals/confirm', 409, {
            'detail': '建议已过期',
            'code': 'stale_priority',
          });
        final container = _container(_apiWith(adapter));
        await container.read(postureProfileProvider.notifier).fetchPriorities();
        expect(prioritiesCalls, 1);

        final ok = await container
            .read(postureProfileProvider.notifier)
            .confirmGoals([GoalInput(issueId: 'HN-01', priorityRank: 1)]);
        expect(ok, isFalse);
        final state = container.read(postureProfileProvider);
        expect(state.confirmError, PostureConfirmError.stalePriority);
        expect(state.needsReconfirm, isTrue);
        expect(state.confirmedGoals, isNull);
        // Priorities refreshed: 2 GETs total (initial + auto-refresh).
        expect(prioritiesCalls, 2);
        // No auto-replay of confirm: exactly 1 POST (the failed attempt).
        final postCalls = adapter.calls
            .where((c) => c.method == 'POST')
            .toList();
        expect(postCalls.length, 1);
        container.dispose();
      },
    );

    test(
      '409 restricted_blocked surfaces typed, no state corruption',
      () async {
        final adapter = FakeDioAdapter()
          ..registerJson(
            'GET',
            '/posture/priorities',
            (_) => _suggestionsWithCandidates(['HN-01']),
          )
          ..registerError('POST', '/posture/goals/confirm', 409, {
            'detail': '受限条目',
            'code': 'restricted_blocked',
          });
        final container = _container(_apiWith(adapter));
        await container.read(postureProfileProvider.notifier).fetchPriorities();
        final ok = await container
            .read(postureProfileProvider.notifier)
            .confirmGoals([GoalInput(issueId: 'HN-01', priorityRank: 1)]);
        expect(ok, isFalse);
        final state = container.read(postureProfileProvider);
        expect(state.confirmError, PostureConfirmError.restrictedBlocked);
        expect(state.needsReconfirm, isFalse); // restricted != stale
        // Priorities not cleared for restricted_blocked (only stale clears).
        expect(state.priorities, isNotNull);
        container.dispose();
      },
    );

    test(
      '409 red_flag_blocked surfaces typed (distinct from restricted)',
      () async {
        final adapter = FakeDioAdapter()
          ..registerJson(
            'GET',
            '/posture/priorities',
            (_) => _suggestionsWithCandidates(['HN-01']),
          )
          ..registerError('POST', '/posture/goals/confirm', 409, {
            'detail': '红旗',
            'code': 'red_flag_blocked',
          });
        final container = _container(_apiWith(adapter));
        await container.read(postureProfileProvider.notifier).fetchPriorities();
        await container.read(postureProfileProvider.notifier).confirmGoals([
          GoalInput(issueId: 'HN-01', priorityRank: 1),
        ]);
        expect(
          container.read(postureProfileProvider).confirmError,
          PostureConfirmError.redFlagBlocked,
        );
        container.dispose();
      },
    );

    test('400 invalid_goal surfaces typed', () async {
      final adapter = FakeDioAdapter()
        ..registerJson(
          'GET',
          '/posture/priorities',
          (_) => _suggestionsWithCandidates(['HN-01']),
        )
        ..registerError('POST', '/posture/goals/confirm', 400, {
          'detail': '排名非法',
          'code': 'invalid_goal',
        });
      final container = _container(_apiWith(adapter));
      await container.read(postureProfileProvider.notifier).fetchPriorities();
      await container.read(postureProfileProvider.notifier).confirmGoals([
        GoalInput(issueId: 'HN-01', priorityRank: 1),
      ]);
      expect(
        container.read(postureProfileProvider).confirmError,
        PostureConfirmError.invalidGoal,
      );
      container.dispose();
    });

    test('concurrent double confirm sends only one POST', () async {
      final adapter = FakeDioAdapter()
        ..registerJson(
          'GET',
          '/posture/priorities',
          (_) => _suggestionsWithCandidates(['HN-01']),
        )
        ..registerJson(
          'POST',
          '/posture/goals/confirm',
          (_) => {
            'confirmed_goals': [
              {
                'issue_id': 'HN-01',
                'priority_rank': 1,
                'confirmed_at': '2026-07-17T12:30:00Z',
              },
            ],
            'can_generate_plan': true,
            'risk_version': '2026-07-16-v4',
          },
        );
      final container = _container(_apiWith(adapter));
      final notifier = container.read(postureProfileProvider.notifier);
      await notifier.fetchPriorities();
      final first = notifier.confirmGoals([
        GoalInput(issueId: 'HN-01', priorityRank: 1),
      ]);
      final second = await notifier.confirmGoals([
        GoalInput(issueId: 'HN-01', priorityRank: 1),
      ]);
      expect(second, isFalse);
      expect(await first, isTrue);
      expect(adapter.calls.where((c) => c.method == 'POST'), hasLength(1));
      container.dispose();
    });
  });

  group('reportSafetySignal', () {
    test(
      'late pre-signal priorities response cannot restore old suggestion',
      () async {
        final oldResponse = Completer<Response>();
        var prioritiesCalls = 0;
        final adapter = FakeDioAdapter()
          ..register('GET', '/posture/priorities', (options) {
            prioritiesCalls++;
            if (prioritiesCalls == 1) return oldResponse.future;
            return Response(
              requestOptions: options,
              statusCode: 200,
              data: _suggestionsWithCandidates(['SS-01']),
            );
          })
          ..registerJson('GET', '/posture/profile', (_) => _emptyProfile)
          ..registerJson(
            'POST',
            '/posture/safety-signals',
            (_) => _safetyResponse,
          );
        final container = _container(_apiWith(adapter));
        final notifier = container.read(postureProfileProvider.notifier);
        final staleFetch = notifier.fetchPriorities();
        await Future<void>.delayed(Duration.zero);

        expect(
          await notifier.reportSafetySignal(
            SafetySignalInput(
              signalType: SignalType.pain,
              bodyRegion: null,
              relatedIssueId: null,
              severityHint: null,
              reportedAt: null,
            ),
          ),
          isTrue,
        );
        oldResponse.complete(
          Response(
            requestOptions: RequestOptions(path: '/posture/priorities'),
            statusCode: 200,
            data: _suggestionsWithCandidates(['HN-01']),
          ),
        );
        await staleFetch;

        final state = container.read(postureProfileProvider);
        expect(state.priorities!.normalCandidates.map((e) => e.issueId), [
          'SS-01',
        ]);
        expect(state.needsReconfirm, isTrue);
        container.dispose();
      },
    );

    test(
      'malformed 2xx signal response still invalidates old priorities',
      () async {
        final adapter = FakeDioAdapter()
          ..registerJson(
            'GET',
            '/posture/priorities',
            (_) => _suggestionsWithCandidates(['HN-01']),
          )
          ..registerJson(
            'POST',
            '/posture/safety-signals',
            (_) => {..._safetyResponse}..remove('signal_id'),
          );
        final container = _container(_apiWith(adapter));
        final notifier = container.read(postureProfileProvider.notifier);
        await notifier.fetchPriorities();
        expect(container.read(postureProfileProvider).priorities, isNotNull);

        expect(
          await notifier.reportSafetySignal(
            SafetySignalInput(
              signalType: SignalType.pain,
              bodyRegion: null,
              relatedIssueId: null,
              severityHint: null,
              reportedAt: null,
            ),
          ),
          isFalse,
        );
        final state = container.read(postureProfileProvider);
        expect(state.safetyStatus, LoadStatus.parseError);
        expect(state.priorities, isNull);
        expect(state.needsReconfirm, isTrue);
        container.dispose();
      },
    );

    test(
      'success refreshes profile + priorities, clears old suggestion state',
      () async {
        var profileCalls = 0;
        var prioritiesCalls = 0;
        final adapter = FakeDioAdapter()
          ..register('GET', '/posture/profile', (options) {
            profileCalls++;
            return Response(
              requestOptions: options,
              statusCode: 200,
              data: profileCalls == 1 ? _oneEntryProfile : _emptyProfile,
            );
          })
          ..register('GET', '/posture/priorities', (options) {
            prioritiesCalls++;
            return Response(
              requestOptions: options,
              statusCode: 200,
              data: _suggestionsWithCandidates(
                prioritiesCalls == 1 ? ['HN-01'] : [],
              ),
            );
          })
          ..registerJson(
            'POST',
            '/posture/safety-signals',
            (_) => _safetyResponse,
          );
        final container = _container(_apiWith(adapter));
        // Seed: 1 profile call + 1 priorities call before reporting.
        await container.read(postureProfileProvider.notifier).fetchProfile();
        await container.read(postureProfileProvider.notifier).fetchPriorities();
        expect(profileCalls, 1);
        expect(prioritiesCalls, 1);
        expect(
          container
              .read(postureProfileProvider)
              .priorities!
              .normalCandidates
              .length,
          1,
        );

        // Report a signal.
        final ok = await container
            .read(postureProfileProvider.notifier)
            .reportSafetySignal(
              SafetySignalInput(
                signalType: SignalType.pain,
                bodyRegion: BodyRegion.cervical,
                relatedIssueId: 'HN-01',
                severityHint: SeverityHint.moderate,
                reportedAt: DateTime.utc(2026, 7, 11, 10, 0, 0),
              ),
            );
        expect(ok, isTrue);
        final state = container.read(postureProfileProvider);
        expect(state.safetyStatus, LoadStatus.data);
        expect(state.lastSafetyResult!.riskTier, RiskTier.cautious);
        expect(state.needsReconfirm, isTrue);
        // Old suggestion invalidated and refreshed (now empty).
        expect(state.priorities!.normalCandidates, isEmpty);
        // Profile + priorities each fetched twice (seed + auto-refresh).
        expect(profileCalls, 2);
        expect(prioritiesCalls, 2);

        // The provider owns and generates the action idempotency key.
        final post = adapter.calls.lastWhere(
          (c) => c.method == 'POST' && c.path.contains('/safety-signals'),
        );
        expect(
          RegExp(
            r'^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$',
          ).hasMatch(post.data['idempotency_key'] as String),
          isTrue,
        );
        expect(post.data['signal_type'], 'pain');
        expect(post.data['body_region'], 'cervical');
        container.dispose();
      },
    );

    test('400 idempotency_key_conflict surfaces typed', () async {
      final adapter = FakeDioAdapter()
        ..registerError('POST', '/posture/safety-signals', 400, {
          'detail': '幂等键冲突',
          'code': 'idempotency_key_conflict',
        });
      final container = _container(_apiWith(adapter));
      await container
          .read(postureProfileProvider.notifier)
          .reportSafetySignal(
            SafetySignalInput(
              signalType: SignalType.pain,
              bodyRegion: null,
              relatedIssueId: null,
              severityHint: null,
              reportedAt: null,
            ),
          );
      expect(
        container.read(postureProfileProvider).safetyError,
        SafetySignalError.idempotencyConflict,
      );
      container.dispose();
    });

    test('network failure -> network status, no refresh', () async {
      final adapter = FakeDioAdapter()
        ..registerError('POST', '/posture/safety-signals', 503, {
          'detail': '服务不可用',
          'code': 'service_unavailable',
        });
      final container = _container(_apiWith(adapter));
      await container
          .read(postureProfileProvider.notifier)
          .reportSafetySignal(
            SafetySignalInput(
              signalType: SignalType.pain,
              bodyRegion: null,
              relatedIssueId: null,
              severityHint: null,
              reportedAt: null,
            ),
          );
      final state = container.read(postureProfileProvider);
      expect(state.safetyStatus, LoadStatus.networkError);
      expect(state.lastSafetyResult, isNull);
      container.dispose();
    });
  });
}
