// app/lib/providers/auth_provider.dart
import 'dart:async';
import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../core/api_client.dart';
import '../core/storage.dart';
import '../models/token.dart';

class AuthState {
  final bool isLoggedIn;
  final bool isLoading;
  final String? error;
  final bool isNewUser;
  final int countdown;

  const AuthState({
    this.isLoggedIn = false,
    this.isLoading = false,
    this.error,
    this.isNewUser = false,
    this.countdown = 0,
  });

  AuthState copyWith({
    bool? isLoggedIn,
    bool? isLoading,
    String? error,
    bool? isNewUser,
    int? countdown,
    bool clearError = false,
  }) =>
      AuthState(
        isLoggedIn: isLoggedIn ?? this.isLoggedIn,
        isLoading: isLoading ?? this.isLoading,
        error: clearError ? null : (error ?? this.error),
        isNewUser: isNewUser ?? this.isNewUser,
        countdown: countdown ?? this.countdown,
      );
}

class AuthNotifier extends StateNotifier<AuthState> {
  final ApiClient _api;
  Timer? _timer;

  AuthNotifier(this._api) : super(const AuthState());

  Future<void> checkAuth() async {
    final hasToken = await AppStorage.hasToken();
    state = state.copyWith(isLoggedIn: hasToken);
  }

  Future<bool> sendCode(String phone) async {
    try {
      state = state.copyWith(isLoading: true, clearError: true);
      await _api.dio.post('/auth/send-code', data: {'phone': phone});
      _startCountdown();
      state = state.copyWith(isLoading: false);
      return true;
    } on DioException catch (e) {
      final msg = e.response?.data?['detail'] ?? '发送验证码失败';
      state = state.copyWith(isLoading: false, error: msg);
      return false;
    }
  }

  Future<bool> login(String phone, String code) async {
    try {
      state = state.copyWith(isLoading: true, clearError: true);
      final resp = await _api.dio.post('/auth/verify-login', data: {
        'phone': phone,
        'code': code,
      });
      final token = TokenResponse.fromJson(resp.data as Map<String, dynamic>);
      await AppStorage.saveTokens(token.accessToken, token.refreshToken);
      state = state.copyWith(
        isLoading: false,
        isLoggedIn: true,
        isNewUser: token.isNewUser,
      );
      return true;
    } on DioException catch (e) {
      final msg = e.response?.data?['detail'] ?? '登录失败';
      state = state.copyWith(isLoading: false, error: msg);
      return false;
    }
  }

  Future<void> logout() async {
    await AppStorage.clearTokens();
    state = const AuthState();
  }

  void _startCountdown() {
    state = state.copyWith(countdown: 60);
    _timer?.cancel();
    _timer = Timer.periodic(const Duration(seconds: 1), (_) {
      if (state.countdown <= 1) {
        _timer?.cancel();
        state = state.copyWith(countdown: 0);
      } else {
        state = state.copyWith(countdown: state.countdown - 1);
      }
    });
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }
}

final authProvider = StateNotifierProvider<AuthNotifier, AuthState>((ref) {
  final api = ref.read(apiClientProvider);
  return AuthNotifier(api);
});
