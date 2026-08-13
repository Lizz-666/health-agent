// app/lib/core/api_client.dart
import 'dart:async';
import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'constants.dart';
import 'storage.dart';

typedef AuthLogoutCallback = void Function();
typedef ClientIncompatibleCallback = void Function();

class _RefreshResult {
  const _RefreshResult({this.token, this.clientIncompatible = false});

  final String? token;
  final bool clientIncompatible;
}

class ApiClient {
  late final Dio dio;
  late final Dio _refreshDio;
  AuthLogoutCallback? onAuthFailed;
  ClientIncompatibleCallback? onClientIncompatible;
  Completer<_RefreshResult>? _refreshCompleter;
  bool _authFailureNotified = false;
  bool _incompatibilityNotified = false;
  static const String _retriedAfterRefresh = 'retried_after_refresh';

  ApiClient({Dio? client, Dio? refreshClient}) {
    dio = client ?? _buildDio();
    _refreshDio = refreshClient ?? _buildDio();
    _applyClientHeaders(dio);
    _applyClientHeaders(_refreshDio);

    dio.interceptors.add(
      InterceptorsWrapper(
        onRequest: (options, handler) async {
          final token = await AppStorage.getAccessToken();
          if (token != null) {
            options.headers['Authorization'] = 'Bearer $token';
          }
          handler.next(options);
        },
        onResponse: (response, handler) {
          _authFailureNotified = false;
          handler.next(response);
        },
        onError: (error, handler) async {
          if (error.response?.statusCode == 426) {
            await _failIncompatible();
            return handler.next(error);
          }
          if (error.response?.statusCode == 401 &&
              error.requestOptions.extra[_retriedAfterRefresh] != true) {
            final currentToken = await AppStorage.getAccessToken();
            final failedAuthorization =
                error.requestOptions.headers['Authorization'];
            if (currentToken != null &&
                failedAuthorization != null &&
                failedAuthorization != 'Bearer $currentToken') {
              error.requestOptions.headers['Authorization'] =
                  'Bearer $currentToken';
              error.requestOptions.extra[_retriedAfterRefresh] = true;
              try {
                final retryResp = await dio.fetch(error.requestOptions);
                return handler.resolve(retryResp);
              } on DioException catch (retryError) {
                if (retryError.response?.statusCode == 401) {
                  await _failAuth();
                }
                return handler.next(retryError);
              }
            }
            final refresh = await _doRefresh();
            if (refresh.token != null) {
              error.requestOptions.headers['Authorization'] =
                  'Bearer ${refresh.token}';
              error.requestOptions.extra[_retriedAfterRefresh] = true;
              try {
                final retryResp = await dio.fetch(error.requestOptions);
                return handler.resolve(retryResp);
              } on DioException catch (retryError) {
                if (retryError.response?.statusCode == 401) {
                  await _failAuth();
                }
                return handler.next(retryError);
              }
            }
            if (!refresh.clientIncompatible) {
              await _failAuth();
            }
          } else if (error.response?.statusCode == 401) {
            await _failAuth();
          }
          handler.next(error);
        },
      ),
    );
  }

  Future<_RefreshResult> _doRefresh() async {
    if (_refreshCompleter != null) {
      return _refreshCompleter!.future;
    }
    _refreshCompleter = Completer<_RefreshResult>();
    try {
      final refreshToken = await AppStorage.getRefreshToken();
      if (refreshToken == null) {
        await AppStorage.clearTokens();
        const result = _RefreshResult();
        _refreshCompleter!.complete(result);
        return result;
      }
      final resp = await _refreshDio.post(
        '/auth/refresh',
        data: {'refresh_token': refreshToken},
      );
      final data = resp.data as Map<String, dynamic>?;
      if (data == null ||
          data['access_token'] == null ||
          data['refresh_token'] == null) {
        await AppStorage.clearTokens();
        const result = _RefreshResult();
        _refreshCompleter!.complete(result);
        return result;
      }
      await AppStorage.saveTokens(
        data['access_token'] as String,
        data['refresh_token'] as String,
      );
      final result = _RefreshResult(token: data['access_token'] as String);
      _refreshCompleter!.complete(result);
      return result;
    } on DioException catch (error) {
      if (error.response?.statusCode == 426) {
        await _failIncompatible();
        const result = _RefreshResult(clientIncompatible: true);
        _refreshCompleter!.complete(result);
        return result;
      } else {
        await AppStorage.clearTokens();
      }
      const result = _RefreshResult();
      _refreshCompleter!.complete(result);
      return result;
    } catch (_) {
      await AppStorage.clearTokens();
      const result = _RefreshResult();
      _refreshCompleter!.complete(result);
      return result;
    } finally {
      _refreshCompleter = null;
    }
  }

  static Dio _buildDio() => Dio(
    BaseOptions(
      baseUrl: AppConstants.apiBaseUrl,
      connectTimeout: AppConstants.httpTimeout,
      receiveTimeout: AppConstants.httpTimeout,
      headers: {'Content-Type': 'application/json'},
    ),
  );

  static void _applyClientHeaders(Dio target) {
    target.options.headers.addAll({
      'X-Client-Platform': AppConstants.clientPlatform,
      'X-Client-Version-Code': AppConstants.clientVersionCode.toString(),
    });
  }

  Future<void> _failAuth() async {
    await AppStorage.clearTokens();
    if (_authFailureNotified) return;
    _authFailureNotified = true;
    onAuthFailed?.call();
  }

  Future<void> _failIncompatible() async {
    await AppStorage.clearTokens();
    if (_incompatibilityNotified) return;
    _incompatibilityNotified = true;
    onClientIncompatible?.call();
  }
}

final apiClientProvider = Provider<ApiClient>((ref) => ApiClient());
