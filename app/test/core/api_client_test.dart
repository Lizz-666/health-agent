import 'dart:async';

import 'package:dio/dio.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:posture_app/core/api_client.dart';
import 'package:posture_app/core/constants.dart';
import 'package:posture_app/core/storage.dart';

import '../providers/_test_dio.dart';

ApiClient _client(FakeDioAdapter adapter) => ApiClient(
  client: buildFakeDio(adapter),
  refreshClient: buildFakeDio(adapter),
);

DioException _httpError(RequestOptions options, int status, String code) =>
    DioException(
      requestOptions: options,
      response: Response(
        requestOptions: options,
        statusCode: status,
        data: {'detail': 'synthetic', 'code': code},
      ),
      type: DioExceptionType.badResponse,
    );

void main() {
  setUp(() {
    FlutterSecureStorage.setMockInitialValues({});
  });

  test(
    'every app and refresh request carries the pinned Android version',
    () async {
      final adapter = FakeDioAdapter()
        ..registerJson('GET', '/probe', (_) => {'ok': true});
      final api = _client(adapter);

      await api.dio.get('/probe');

      final request = adapter.calls.single;
      expect(request.headers['X-Client-Platform'], AppConstants.clientPlatform);
      expect(
        request.headers['X-Client-Version-Code'],
        AppConstants.clientVersionCode.toString(),
      );
    },
  );

  test('concurrent 401 responses rotate refresh once and retry once', () async {
    await AppStorage.saveTokens('expired-access', 'valid-refresh');
    var refreshCalls = 0;
    final adapter = FakeDioAdapter();
    for (final path in ['/one', '/two']) {
      adapter.register('GET', path, (options) {
        if (options.headers['Authorization'] != 'Bearer fresh-access') {
          throw _httpError(options, 401, 'unauthorized');
        }
        return Response(
          requestOptions: options,
          statusCode: 200,
          data: {'ok': true},
        );
      });
    }
    final refreshGate = Completer<void>();
    adapter.register('POST', '/auth/refresh', (options) async {
      refreshCalls += 1;
      await refreshGate.future;
      return Response(
        requestOptions: options,
        statusCode: 200,
        data: {
          'access_token': 'fresh-access',
          'refresh_token': 'fresh-refresh',
        },
      );
    });
    final api = _client(adapter);

    final requests = Future.wait([api.dio.get('/one'), api.dio.get('/two')]);
    await Future<void>.delayed(Duration.zero);
    refreshGate.complete();
    final responses = await requests;

    expect(responses.every((response) => response.statusCode == 200), isTrue);
    expect(refreshCalls, 1);
    final refreshRequest = adapter.calls.singleWhere(
      (call) => call.path.endsWith('/auth/refresh'),
    );
    expect(
      refreshRequest.headers['X-Client-Platform'],
      AppConstants.clientPlatform,
    );
    expect(
      refreshRequest.headers['X-Client-Version-Code'],
      AppConstants.clientVersionCode.toString(),
    );
    expect(await AppStorage.getAccessToken(), 'fresh-access');
    expect(await AppStorage.getRefreshToken(), 'fresh-refresh');
  });

  test(
    'late stale 401 reuses the rotated access token without refreshing again',
    () async {
      await AppStorage.saveTokens('expired-access', 'valid-refresh');
      final lateResponse = Completer<void>();
      var refreshCalls = 0;
      final adapter = FakeDioAdapter()
        ..register('GET', '/first', (options) {
          if (options.headers['Authorization'] != 'Bearer fresh-access') {
            throw _httpError(options, 401, 'unauthorized');
          }
          return Response(requestOptions: options, statusCode: 200);
        })
        ..register('GET', '/late', (options) async {
          if (options.headers['Authorization'] == 'Bearer expired-access') {
            await lateResponse.future;
            throw _httpError(options, 401, 'unauthorized');
          }
          return Response(requestOptions: options, statusCode: 200);
        })
        ..register('POST', '/auth/refresh', (options) {
          refreshCalls += 1;
          return Response(
            requestOptions: options,
            statusCode: 200,
            data: {
              'access_token': 'fresh-access',
              'refresh_token': 'fresh-refresh',
            },
          );
        });
      final api = _client(adapter);

      final late = api.dio.get('/late');
      await Future<void>.delayed(Duration.zero);
      expect((await api.dio.get('/first')).statusCode, 200);
      lateResponse.complete();

      expect((await late).statusCode, 200);
      expect(refreshCalls, 1);
      expect(
        adapter.calls.where((call) => call.path.endsWith('/late')),
        hasLength(2),
      );
    },
  );

  test('failed refresh clears tokens and signals auth failure once', () async {
    await AppStorage.saveTokens('expired-access', 'replayed-refresh');
    final adapter = FakeDioAdapter()
      ..register('GET', '/protected', (options) {
        throw _httpError(options, 401, 'unauthorized');
      })
      ..register('POST', '/auth/refresh', (options) {
        throw _httpError(options, 401, 'auth_failed');
      });
    final api = _client(adapter);
    var failures = 0;
    api.onAuthFailed = () => failures += 1;

    await expectLater(api.dio.get('/protected'), throwsA(isA<DioException>()));

    expect(failures, 1);
    expect(await AppStorage.getAccessToken(), isNull);
    expect(await AppStorage.getRefreshToken(), isNull);
  });

  test(
    '426 clears tokens and signals incompatibility without refresh',
    () async {
      await AppStorage.saveTokens('access', 'refresh');
      final adapter = FakeDioAdapter()
        ..register('GET', '/protected', (options) {
          throw _httpError(options, 426, 'client_version_incompatible');
        });
      final api = _client(adapter);
      var incompatibilities = 0;
      api.onClientIncompatible = () => incompatibilities += 1;

      await expectLater(
        api.dio.get('/protected'),
        throwsA(isA<DioException>()),
      );

      expect(incompatibilities, 1);
      expect(
        adapter.calls.where((call) => call.path.endsWith('/auth/refresh')),
        isEmpty,
      );
      expect(await AppStorage.getAccessToken(), isNull);
      expect(await AppStorage.getRefreshToken(), isNull);
    },
  );

  test(
    '426 during refresh signals incompatibility and does not retry',
    () async {
      await AppStorage.saveTokens('expired-access', 'refresh');
      final adapter = FakeDioAdapter()
        ..register('GET', '/protected', (options) {
          throw _httpError(options, 401, 'unauthorized');
        })
        ..register('POST', '/auth/refresh', (options) {
          throw _httpError(options, 426, 'client_version_incompatible');
        });
      final api = _client(adapter);
      var failures = 0;
      var incompatibilities = 0;
      api.onAuthFailed = () => failures += 1;
      api.onClientIncompatible = () => incompatibilities += 1;

      await expectLater(
        api.dio.get('/protected'),
        throwsA(isA<DioException>()),
      );

      expect(incompatibilities, 1);
      expect(failures, 0);
      expect(
        adapter.calls.where((call) => call.path.endsWith('/protected')),
        hasLength(1),
      );
      expect(await AppStorage.getAccessToken(), isNull);
      expect(await AppStorage.getRefreshToken(), isNull);
    },
  );
}
