// app/lib/core/api_client.dart
import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'constants.dart';
import 'storage.dart';

class ApiClient {
  late final Dio dio;

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
          final refreshToken = await AppStorage.getRefreshToken();
          if (refreshToken != null) {
            try {
              final resp = await Dio(BaseOptions(
                baseUrl: AppConstants.apiBaseUrl,
              )).post('/auth/refresh', data: {'refresh_token': refreshToken});
              final data = resp.data;
              await AppStorage.saveTokens(
                data['access_token'], data['refresh_token']);
              error.requestOptions.headers['Authorization'] =
                  'Bearer ${data['access_token']}';
              final retryResp = await Dio().fetch(error.requestOptions);
              return handler.resolve(retryResp);
            } catch (_) {
              await AppStorage.clearTokens();
            }
          }
        }
        handler.next(error);
      },
    ));
  }
}

final apiClientProvider = Provider<ApiClient>((ref) => ApiClient());
