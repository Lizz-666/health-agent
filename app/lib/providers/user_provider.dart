// app/lib/providers/user_provider.dart
import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../core/api_client.dart';
import '../core/constants.dart';
import '../models/user.dart';

class UserState {
  final UserProfile? profile;
  final bool isLoading;
  final String? error;

  const UserState({this.profile, this.isLoading = false, this.error});

  UserState copyWith({
    UserProfile? profile,
    bool clearProfile = false,
    bool? isLoading,
    String? error,
    bool clearError = false,
  }) => UserState(
    profile: clearProfile ? null : (profile ?? this.profile),
    isLoading: isLoading ?? this.isLoading,
    error: clearError ? null : (error ?? this.error),
  );
}

class UserNotifier extends StateNotifier<UserState> {
  final ApiClient _api;

  UserNotifier(this._api) : super(const UserState());

  Future<void> fetchProfile() async {
    try {
      state = state.copyWith(isLoading: true, clearError: true);
      final resp = await _api.dio.get('/user/profile');
      if (!mounted) return;
      final profile = UserProfile.fromJson(resp.data as Map<String, dynamic>);
      state = state.copyWith(profile: profile, isLoading: false);
    } on DioException catch (e) {
      if (!mounted) return;
      final data = e.response?.data;
      final msg = (data is Map<String, dynamic>)
          ? (data['detail'] as String?) ?? '获取用户信息失败'
          : '获取用户信息失败';
      state = state.copyWith(isLoading: false, error: msg);
    } catch (e) {
      if (!mounted) return;
      state = state.copyWith(isLoading: false, error: '获取用户信息失败');
    }
  }

  Future<bool> updateProfile({
    String? nickname,
    double? height,
    double? weight,
    int? age,
    String? gender,
  }) async {
    try {
      state = state.copyWith(isLoading: true, clearError: true);
      final data = <String, dynamic>{};
      if (nickname != null) data['nickname'] = nickname;
      if (height != null) data['height'] = height;
      if (weight != null) data['weight'] = weight;
      if (age != null) data['age'] = age;
      if (gender != null) data['gender'] = gender;
      final resp = await _api.dio.put('/user/profile', data: data);
      if (!mounted) return false;
      final profile = UserProfile.fromJson(resp.data as Map<String, dynamic>);
      state = state.copyWith(profile: profile, isLoading: false);
      return true;
    } on DioException catch (e) {
      if (!mounted) return false;
      final data = e.response?.data;
      final msg = (data is Map<String, dynamic>)
          ? (data['detail'] as String?) ?? '更新失败'
          : '更新失败';
      state = state.copyWith(isLoading: false, error: msg);
      return false;
    } catch (e) {
      if (!mounted) return false;
      state = state.copyWith(isLoading: false, error: '更新失败');
      return false;
    }
  }

  Future<bool> completeOnboarding({
    required double height,
    required double weight,
    required int age,
    required String gender,
  }) async {
    try {
      state = state.copyWith(isLoading: true, clearError: true);
      final consent = await _api.dio.get('/privacy/consent');
      final consentData = consent.data;
      final hasCurrentConsent =
          consentData is Map<String, dynamic> &&
          consentData['active'] == true &&
          consentData['notice_version'] == AppConstants.privacyNoticeVersion;
      if (!hasCurrentConsent) {
        final granted = await _api.dio.post(
          '/privacy/consent',
          data: {
            'action': 'grant',
            'notice_version': AppConstants.privacyNoticeVersion,
          },
        );
        final grantedData = granted.data;
        if (grantedData is! Map<String, dynamic> ||
            grantedData['active'] != true ||
            grantedData['notice_version'] !=
                AppConstants.privacyNoticeVersion) {
          throw const FormatException('invalid consent response');
        }
      }
      final response = await _api.dio.put(
        '/user/profile',
        data: {
          'height': height,
          'weight': weight,
          'age': age,
          'gender': gender,
        },
      );
      if (!mounted) return false;
      final profile = UserProfile.fromJson(
        response.data as Map<String, dynamic>,
      );
      state = state.copyWith(profile: profile, isLoading: false);
      return true;
    } on DioException catch (error) {
      if (!mounted) return false;
      final data = error.response?.data;
      final message = data is Map<String, dynamic>
          ? (data['detail'] as String?) ?? '保存资料失败，请重试'
          : '保存资料失败，请检查网络后重试';
      state = state.copyWith(isLoading: false, error: message);
      return false;
    } catch (_) {
      if (!mounted) return false;
      state = state.copyWith(isLoading: false, error: '保存资料失败，请重试');
      return false;
    }
  }
}

final userProvider = StateNotifierProvider<UserNotifier, UserState>((ref) {
  final api = ref.read(apiClientProvider);
  return UserNotifier(api);
});
