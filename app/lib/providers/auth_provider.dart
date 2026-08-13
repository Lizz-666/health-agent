// app/lib/providers/auth_provider.dart
import 'dart:async';
import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../core/api_client.dart';
import '../core/storage.dart';
import '../core/constants.dart';
import '../models/token.dart';
import 'activity_grid_provider.dart';
import 'agent_provider.dart';
import 'assessment_provider.dart';
import 'daily_checkin_provider.dart';
import 'health_profile_provider.dart';
import 'nutrition_provider.dart';
import 'plan_provider.dart';
import 'posture_profile_provider.dart';
import 'posture_state_provider.dart';
import 'user_provider.dart';
import 'weight_trend_provider.dart';

class AuthState {
  final bool isLoggedIn;
  final bool isLoading;
  final String? error;
  final bool isNewUser;
  final int countdown;
  final bool clientIncompatible;

  const AuthState({
    this.isLoggedIn = false,
    this.isLoading = false,
    this.error,
    this.isNewUser = false,
    this.countdown = 0,
    this.clientIncompatible = false,
  });

  AuthState copyWith({
    bool? isLoggedIn,
    bool? isLoading,
    String? error,
    bool? isNewUser,
    int? countdown,
    bool clearError = false,
    bool clearisNewUser = false,
    bool? clientIncompatible,
  }) => AuthState(
    isLoggedIn: isLoggedIn ?? this.isLoggedIn,
    isLoading: isLoading ?? this.isLoading,
    error: clearError ? null : (error ?? this.error),
    isNewUser: clearisNewUser ? false : (isNewUser ?? this.isNewUser),
    countdown: countdown ?? this.countdown,
    clientIncompatible: clientIncompatible ?? this.clientIncompatible,
  );
}

class AuthNotifier extends StateNotifier<AuthState> {
  final ApiClient _api;
  final void Function() _resetSessionState;
  final bool _controlledTrialAuth;
  Timer? _timer;
  bool _trialAuthenticationInFlight = false;

  AuthNotifier(
    this._api, {
    void Function()? resetSessionState,
    bool? controlledTrialAuth,
  }) : _resetSessionState = resetSessionState ?? _noop,
       _controlledTrialAuth =
           controlledTrialAuth ?? AppConstants.controlledTrialAuth,
       super(const AuthState()) {
    _api.onAuthFailed = _onAuthFailed;
    _api.onClientIncompatible = _onClientIncompatible;
  }

  void _onClientIncompatible() {
    _resetSessionState();
    state = const AuthState(clientIncompatible: true);
  }

  void _onAuthFailed() {
    _resetSessionState();
    if (state.isLoggedIn) {
      state = const AuthState();
    }
  }

  Future<void> checkAuth() async {
    final hasToken = await AppStorage.hasToken();
    if (!hasToken) {
      _resetSessionState();
      state = state.copyWith(isLoggedIn: false);
      return;
    }
    try {
      await _api.dio.get('/user/profile');
      state = state.copyWith(isLoggedIn: true);
    } catch (_) {
      await AppStorage.clearTokens();
      _resetSessionState();
      state = state.copyWith(isLoggedIn: false);
    }
  }

  Future<bool> sendCode(String phone) async {
    try {
      state = state.copyWith(isLoading: true, clearError: true);
      await _api.dio.post('/auth/send-code', data: {'phone': phone});
      _startCountdown();
      state = state.copyWith(isLoading: false);
      return true;
    } on DioException catch (e) {
      final msg = _extractError(e);
      state = state.copyWith(isLoading: false, error: msg);
      return false;
    } catch (e) {
      state = state.copyWith(isLoading: false, error: '发送验证码失败');
      return false;
    }
  }

  Future<bool> login(String phone, String code) async {
    try {
      state = state.copyWith(isLoading: true, clearError: true);
      final resp = await _api.dio.post(
        '/auth/verify-login',
        data: {'phone': phone, 'code': code},
      );
      final token = TokenResponse.fromJson(resp.data as Map<String, dynamic>);
      await AppStorage.saveTokens(token.accessToken, token.refreshToken);
      _resetSessionState();
      state = state.copyWith(
        isLoading: false,
        isLoggedIn: true,
        isNewUser: token.isNewUser,
      );
      return true;
    } on DioException catch (e) {
      final msg = _extractError(e);
      state = state.copyWith(isLoading: false, error: msg);
      return false;
    } catch (e) {
      state = state.copyWith(isLoading: false, error: '登录失败，请重试');
      return false;
    }
  }

  Future<void> logout() async {
    if (_controlledTrialAuth) {
      final refreshToken = await AppStorage.getRefreshToken();
      if (refreshToken != null) {
        try {
          await _api.dio.post(
            '/auth/trial/logout',
            data: {'refresh_token': refreshToken},
          );
        } catch (_) {
          // Local logout still clears credentials when the service is offline.
        }
      }
    }
    await AppStorage.clearTokens();
    _resetSessionState();
    state = AuthState(clientIncompatible: state.clientIncompatible);
  }

  Future<bool> trialAuthenticate({
    required bool activate,
    required String accountName,
    required String credential,
    String? invitationCode,
  }) async {
    if (_trialAuthenticationInFlight) return false;
    _trialAuthenticationInFlight = true;
    try {
      state = state.copyWith(isLoading: true, clearError: true);
      final deviceKey = await AppStorage.getOrCreateTrialDeviceKey();
      final data = <String, dynamic>{
        'account_name': accountName,
        'provider_id': AppConstants.authCredentialProvider,
        'credential': credential,
        'device_key': deviceKey,
      };
      if (activate) data['invitation_code'] = invitationCode;
      final response = await _api.dio.post(
        activate ? '/auth/trial/activate' : '/auth/trial/login',
        data: data,
      );
      final token = TokenResponse.fromJson(
        response.data as Map<String, dynamic>,
      );
      await AppStorage.saveTokens(token.accessToken, token.refreshToken);
      _resetSessionState();
      state = state.copyWith(
        isLoading: false,
        isLoggedIn: true,
        isNewUser: token.isNewUser,
      );
      return true;
    } on DioException catch (error) {
      state = state.copyWith(isLoading: false, error: _extractError(error));
      return false;
    } catch (_) {
      state = state.copyWith(isLoading: false, error: '认证失败，请重试');
      return false;
    } finally {
      _trialAuthenticationInFlight = false;
    }
  }

  /// 开发环境密码快速登录
  Future<bool> devLogin(String phone, String password) async {
    try {
      state = state.copyWith(isLoading: true, clearError: true);
      final resp = await _api.dio.post(
        '/auth/dev-login',
        data: {'phone': phone, 'password': password},
      );
      final token = TokenResponse.fromJson(resp.data as Map<String, dynamic>);
      await AppStorage.saveTokens(token.accessToken, token.refreshToken);
      _resetSessionState();
      state = state.copyWith(
        isLoading: false,
        isLoggedIn: true,
        isNewUser: token.isNewUser,
      );
      return true;
    } on DioException catch (e) {
      final msg = _extractError(e);
      state = state.copyWith(isLoading: false, error: msg);
      return false;
    } catch (e) {
      state = state.copyWith(isLoading: false, error: '登录失败');
      return false;
    }
  }

  void clearisNewUser() {
    state = state.copyWith(clearisNewUser: true);
  }

  String _extractError(DioException e) {
    final data = e.response?.data;
    if (data is Map<String, dynamic>) {
      return (data['detail'] as String?) ?? '请求失败';
    }
    return '请求失败';
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
  return AuthNotifier(
    api,
    resetSessionState: () {
      ref.invalidate(userProvider);
      ref.invalidate(assessmentProvider);
      ref.invalidate(postureProfileProvider);
      ref.invalidate(postureStateProvider);
      // Phase 2 health state: clear on logout / token failure / account switch
      // so no previous user's health data is ever retained as current.
      ref.invalidate(healthProfileProvider);
      ref.invalidate(dailyCheckinProvider);
      ref.invalidate(weightTrendProvider);
      ref.invalidate(activityGridProvider);
      // Phase 4 plan state: clear so no previous user's plan/today data leaks
      // across accounts.
      ref.invalidate(planProvider);
      ref.invalidate(nutritionProvider);
      // Phase 5 chat is memory-only and must never cross an auth, token, or
      // account boundary.
      ref.invalidate(agentProvider);
    },
  );
});

void _noop() {}
