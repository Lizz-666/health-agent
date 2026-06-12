// app/lib/core/api_client.dart
import 'dart:async';
import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'constants.dart';
import 'storage.dart';

typedef AuthLogoutCallback = void Function();

class ApiClient {
  late final Dio dio;
  AuthLogoutCallback? onAuthFailed;
  Completer<String?>? _refreshCompleter;

  ApiClient() {
    dio = Dio(BaseOptions(
      baseUrl: AppConstants.apiBaseUrl,
      connectTimeout: AppConstants.httpTimeout,
      receiveTimeout: AppConstants.httpTimeout,
      headers: {'Content-Type': 'application/json'},
    ));

    dio.interceptors.add(InterceptorsWrapper(
      onRequest: (options, handler) async {
        final token = await AppStorage.getAccessToken();
        if (token != null) {
          options.headers['Authorization'] = 'Bearer $token';
        }
        handler.next(options);
      },
      onError: (error, handler) async {
        if (error.response?.statusCode == 401) {
          final newToken = await _doRefresh();
          if (newToken != null) {
            error.requestOptions.headers['Authorization'] =
                'Bearer $newToken';
            final retryResp = await dio.fetch(error.requestOptions);
            return handler.resolve(retryResp);
          } else {
            onAuthFailed?.call();
          }
        }
        handler.next(error);
      },
    ));
  }

  Future<String?> _doRefresh() async {
    if (_refreshCompleter != null) {
      return _refreshCompleter!.future;
    }
    _refreshCompleter = Completer<String?>();
    try {
      final refreshToken = await AppStorage.getRefreshToken();
      if (refreshToken == null) {
        await AppStorage.clearTokens();
        _refreshCompleter!.complete(null);
        return null;
      }
      final resp = await Dio(BaseOptions(
        baseUrl: AppConstants.apiBaseUrl,
        connectTimeout: AppConstants.httpTimeout,
        receiveTimeout: AppConstants.httpTimeout,
      )).post('/auth/refresh', data: {'refresh_token': refreshToken});
      final data = resp.data as Map<String, dynamic>?;
      if (data == null ||
          data['access_token'] == null ||
          data['refresh_token'] == null) {
        await AppStorage.clearTokens();
        _refreshCompleter!.complete(null);
        return null;
      }
      await AppStorage.saveTokens(
          data['access_token'] as String, data['refresh_token'] as String);
      final token = data['access_token'] as String;
      _refreshCompleter!.complete(token);
      return token;
    } catch (_) {
      await AppStorage.clearTokens();
      _refreshCompleter!.complete(null);
      return null;
    } finally {
      _refreshCompleter = null;
    }
  }
}

final apiClientProvider = Provider<ApiClient>((ref) => ApiClient());
