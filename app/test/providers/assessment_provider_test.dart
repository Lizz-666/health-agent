// app/test/providers/assessment_provider_test.dart
import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:posture_app/core/api_client.dart';
import 'package:posture_app/providers/assessment_provider.dart';

import '_test_dio.dart';

ApiClient _apiWith(FakeDioAdapter adapter) {
  final api = ApiClient();
  api.dio.interceptors.clear();
  api.dio.httpClientAdapter = adapter;
  return api;
}

ProviderContainer _container(ApiClient api) =>
    ProviderContainer(overrides: [apiClientProvider.overrideWithValue(api)]);

Map<String, dynamic> _record({
  String id = 'rec-1',
  String issueId = 'HN-01',
  String issueName = '头部前倾',
  String source = 'self_test',
  String method = 'self_test',
  String result = 'moderate',
  String createdAt = '2026-07-11T10:00:00Z',
}) => {
  'id': id,
  'issue_id': issueId,
  'issue_name': issueName,
  'source': source,
  'method': method,
  'result': result,
  'created_at': createdAt,
};

void main() {
  group('submitPhotoAssess idempotency', () {
    test(
      'auto-generates and sends a UUID v4 idempotency_key when omitted',
      () async {
        final adapter = FakeDioAdapter()
          ..registerJson(
            'POST',
            '/posture/assess/photo',
            (options) => {
              'id': 'ph-1',
              'issue_id': 'HN-01',
              'result': 'mild',
              'suggestion': 's',
            },
          );
        final container = _container(_apiWith(adapter));
        final result = await container
            .read(assessmentProvider.notifier)
            .submitPhotoAssess('HN-01', ['k.jpg']);
        expect(result, isNotNull);
        final post = adapter.calls.lastWhere((c) => c.method == 'POST');
        expect(post.data['issue_id'], 'HN-01');
        expect(post.data['photo_keys'], ['k.jpg']);
        final key = post.data['idempotency_key'] as String;
        expect(key, isNotEmpty);
        expect(
          RegExp(
            r'^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$',
          ).hasMatch(key),
          isTrue,
          reason: 'expected v4 UUID, got: $key',
        );
        container.dispose();
      },
    );

    test('separate photo actions generate different keys', () async {
      final adapter = FakeDioAdapter()
        ..registerJson(
          'POST',
          '/posture/assess/photo',
          (options) => {
            'id': 'ph-1',
            'issue_id': 'HN-01',
            'result': 'mild',
            'suggestion': 's',
          },
        );
      final container = _container(_apiWith(adapter));
      final notifier = container.read(assessmentProvider.notifier);
      await notifier.submitPhotoAssess('HN-01', ['k.jpg']);
      await notifier.submitPhotoAssess('HN-01', ['k.jpg']);
      final posts = adapter.calls.where((c) => c.method == 'POST').toList();
      expect(posts, hasLength(2));
      expect(
        posts[0].data['idempotency_key'],
        isNot(posts[1].data['idempotency_key']),
      );
      container.dispose();
    });

    test('missing photo result is a parse error, never normal', () async {
      final adapter = FakeDioAdapter()
        ..registerJson(
          'POST',
          '/posture/assess/photo',
          (_) => {'id': 'ph-1', 'issue_id': 'HN-01', 'suggestion': 's'},
        );
      final container = _container(_apiWith(adapter));
      final result = await container
          .read(assessmentProvider.notifier)
          .submitPhotoAssess('HN-01', ['k.jpg']);
      expect(result, isNull);
      expect(container.read(assessmentProvider).status, LoadStatus.parseError);
      container.dispose();
    });

    test('401 retry reuses the original photo idempotency key', () async {
      var attempts = 0;
      final adapter = FakeDioAdapter()
        ..register('POST', '/posture/assess/photo', (options) {
          attempts++;
          if (attempts == 1) {
            throw DioException(
              requestOptions: options,
              response: Response(requestOptions: options, statusCode: 401),
              type: DioExceptionType.badResponse,
            );
          }
          return Response(
            requestOptions: options,
            statusCode: 200,
            data: {
              'id': 'ph-1',
              'issue_id': 'HN-01',
              'result': 'mild',
              'suggestion': 's',
            },
          );
        });
      final api = _apiWith(adapter);
      api.dio.interceptors.add(
        InterceptorsWrapper(
          onError: (error, handler) async {
            if (error.response?.statusCode == 401) {
              handler.resolve(await api.dio.fetch(error.requestOptions));
              return;
            }
            handler.next(error);
          },
        ),
      );
      final container = _container(api);
      final result = await container
          .read(assessmentProvider.notifier)
          .submitPhotoAssess('HN-01', ['k.jpg']);
      expect(result, isNotNull);
      final posts = adapter.calls.where((c) => c.method == 'POST').toList();
      expect(posts, hasLength(2));
      expect(
        posts[0].data['idempotency_key'],
        posts[1].data['idempotency_key'],
      );
      container.dispose();
    });

    test('network error -> networkError status + message', () async {
      final adapter = FakeDioAdapter()
        ..registerError('POST', '/posture/assess/photo', 503, {
          'detail': '照片分析未启用',
          'code': 'photo_analysis_disabled',
        });
      final container = _container(_apiWith(adapter));
      final result = await container
          .read(assessmentProvider.notifier)
          .submitPhotoAssess('HN-01', ['k.jpg']);
      expect(result, isNull);
      final state = container.read(assessmentProvider);
      expect(state.status, LoadStatus.networkError);
      expect(state.error, '照片分析未启用');
      container.dispose();
    });
  });

  group('fetchHistory status semantics', () {
    test('200 + empty list -> status=empty (not error)', () async {
      final adapter = FakeDioAdapter()
        ..register('GET', '/posture/history', (options) {
          return Response(
            requestOptions: options,
            statusCode: 200,
            data: <Map<String, dynamic>>[],
          );
        });
      final container = _container(_apiWith(adapter));
      await container.read(assessmentProvider.notifier).fetchHistory();
      final state = container.read(assessmentProvider);
      expect(state.status, LoadStatus.empty);
      expect(state.history, isEmpty);
      expect(state.error, isNull);
      container.dispose();
    });

    test('200 + valid records -> status=data, history populated', () async {
      final adapter = FakeDioAdapter()
        ..register('GET', '/posture/history', (options) {
          return Response(
            requestOptions: options,
            statusCode: 200,
            data: [
              _record(id: 'r1'),
              _record(
                id: 'r2',
                issueId: 'SS-01',
                source: 'ai_photo',
                method: 'ai_photo',
                result: 'severe',
              ),
            ],
          );
        });
      final container = _container(_apiWith(adapter));
      await container.read(assessmentProvider.notifier).fetchHistory();
      final state = container.read(assessmentProvider);
      expect(state.status, LoadStatus.data);
      expect(state.history.length, 2);
      expect(state.history.first.source, 'self_test');
      expect(state.history.last.method, 'ai_photo');
      container.dispose();
    });

    test(
      '200 + one malformed record -> status=parseError, history not partial',
      () async {
        final adapter = FakeDioAdapter()
          ..register('GET', '/posture/history', (options) {
            return Response(
              requestOptions: options,
              statusCode: 200,
              data: [
                _record(id: 'good'),
                // missing created_at entirely
                {
                  'id': 'bad',
                  'issue_id': 'X',
                  'issue_name': 'x',
                  'method': 'self_test',
                  'result': 'moderate',
                },
              ],
            );
          });
        final container = _container(_apiWith(adapter));
        await container.read(assessmentProvider.notifier).fetchHistory();
        final state = container.read(assessmentProvider);
        expect(state.status, LoadStatus.parseError);
        // Critically: no partial history leaked (no fabricated timestamps).
        expect(state.history, isEmpty);
        expect(state.error, '数据解析异常');
        container.dispose();
      },
    );

    test(
      'DioException -> status=networkError (distinct from parseError)',
      () async {
        final adapter = FakeDioAdapter()
          ..registerError('GET', '/posture/history', 500, {
            'detail': '服务异常',
            'code': 'internal',
          });
        final container = _container(_apiWith(adapter));
        await container.read(assessmentProvider.notifier).fetchHistory();
        final state = container.read(assessmentProvider);
        expect(state.status, LoadStatus.networkError);
        expect(state.error, '服务异常');
        container.dispose();
      },
    );

    test('200 + non-list body -> status=parseError', () async {
      final adapter = FakeDioAdapter()
        ..register('GET', '/posture/history', (options) {
          return Response(
            requestOptions: options,
            statusCode: 200,
            data: <String, dynamic>{'unexpected': 'shape'},
          );
        });
      final container = _container(_apiWith(adapter));
      await container.read(assessmentProvider.notifier).fetchHistory();
      final state = container.read(assessmentProvider);
      expect(state.status, LoadStatus.parseError);
      container.dispose();
    });
  });

  group('submitSelfAssess', () {
    test('parses a valid response -> status=data', () async {
      final adapter = FakeDioAdapter()
        ..registerJson(
          'POST',
          '/posture/assess',
          (_) => {
            'id': 'a-1',
            'issue_id': 'HN-01',
            'result': 'moderate',
            'suggestion': 's',
          },
        );
      final container = _container(_apiWith(adapter));
      final result = await container
          .read(assessmentProvider.notifier)
          .submitSelfAssess('HN-01', 0, 'positive');
      expect(result, isNotNull);
      expect(result!.result, 'moderate');
      expect(container.read(assessmentProvider).status, LoadStatus.data);
      container.dispose();
    });

    test('malformed response (missing id) -> status=parseError', () async {
      final adapter = FakeDioAdapter()
        ..registerJson(
          'POST',
          '/posture/assess',
          (_) => {'issue_id': 'HN-01', 'result': 'moderate'},
        );
      final container = _container(_apiWith(adapter));
      final result = await container
          .read(assessmentProvider.notifier)
          .submitSelfAssess('HN-01', 0, 'positive');
      expect(result, isNull);
      expect(container.read(assessmentProvider).status, LoadStatus.parseError);
      container.dispose();
    });
  });
}
