// app/test/providers/_test_dio.dart
//
// Test-only Dio adapter: routes (method, pathPrefix) -> handler. Kept private
// to the providers test directory; no production file imports this.
import 'dart:async';
import 'dart:convert';

import 'package:dio/dio.dart';

typedef RequestHandler = FutureOr<Response> Function(RequestOptions options);

class _RouteKey {
  final String method;
  final String pathPrefix;
  _RouteKey(this.method, this.pathPrefix);

  @override
  bool operator ==(Object other) =>
      other is _RouteKey &&
      other.method == method &&
      other.pathPrefix == pathPrefix;

  @override
  int get hashCode => Object.hash(method, pathPrefix);
}

/// Minimal in-memory Dio adapter for provider tests.
///
/// Routes are matched by HTTP method + path prefix (so `/posture/profile`
/// matches `/posture/profile/HN-01` only if you register both). If no route
/// matches, the adapter throws a [DioException] with type connectionError.
///
/// Each registered route records the most recent request body / headers so
/// tests can assert on the outgoing payload (e.g. idempotency_key presence).
class FakeDioAdapter implements HttpClientAdapter {
  final Map<_RouteKey, RequestHandler> _routes = {};
  final List<RequestOptions> calls = [];

  void register(String method, String pathPrefix, RequestHandler handler) {
    _routes[_RouteKey(method.toUpperCase(), pathPrefix)] = handler;
  }

  /// Register a JSON-200 shortcut.
  void registerJson(
    String method,
    String pathPrefix,
    Map<String, dynamic> Function(RequestOptions options) body,
  ) {
    register(method, pathPrefix, (options) {
      return Response(
        requestOptions: options,
        statusCode: 200,
        data: body(options),
      );
    });
  }

  /// Register an error shortcut. [body] becomes response.data (typically
  /// {"detail": "...", "code": "..."}); [statusCode] becomes the HTTP status.
  void registerError(
    String method,
    String pathPrefix,
    int statusCode,
    Map<String, dynamic> body,
  ) {
    register(method, pathPrefix, (options) {
      throw DioException(
        requestOptions: options,
        response: Response(
          requestOptions: options,
          statusCode: statusCode,
          data: body,
        ),
        type: DioExceptionType.badResponse,
      );
    });
  }

  @override
  void close({bool force = false}) {}

  @override
  Future<ResponseBody> fetch(
    RequestOptions options,
    Stream<List<int>>? requestStream,
    Future<void>? cancelFuture,
  ) async {
    calls.add(options);
    // Find the most specific matching route: longest matching prefix.
    RequestHandler? handler;
    var bestLen = -1;
    for (final entry in _routes.entries) {
      if (entry.key.method == options.method.toUpperCase() &&
          options.path.startsWith(entry.key.pathPrefix) &&
          entry.key.pathPrefix.length > bestLen) {
        handler = entry.value;
        bestLen = entry.key.pathPrefix.length;
      }
    }
    if (handler == null) {
      throw DioException(
        requestOptions: options,
        type: DioExceptionType.connectionError,
        error: 'no fake route registered for ${options.method} ${options.path}',
      );
    }
    final response = await handler(options);
    final data = response.data;
    final bodyBytes = data is String
        ? utf8.encode(data)
        : utf8.encode(jsonEncode(data));
    return ResponseBody.fromBytes(
      bodyBytes,
      response.statusCode ?? 200,
      headers: {
        Headers.contentTypeHeader: ['application/json'],
      },
    );
  }
}

/// Build a Dio wired to a [FakeDioAdapter]. Interceptors and baseUrl mirror
/// the production ApiClient shape so request paths line up with the routes.
Dio buildFakeDio(FakeDioAdapter adapter) {
  final dio = Dio(
    BaseOptions(
      baseUrl: 'http://test.local/api/v1',
      headers: {'Content-Type': 'application/json'},
    ),
  );
  dio.httpClientAdapter = adapter;
  return dio;
}
