// app/lib/providers/user_provider.dart
import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../core/api_client.dart';
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
  }) =>
      UserState(
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
      final profile = UserProfile.fromJson(resp.data as Map<String, dynamic>);
      state = state.copyWith(profile: profile, isLoading: false);
    } on DioException catch (e) {
      final data = e.response?.data;
      final msg = (data is Map<String, dynamic>)
          ? (data['detail'] as String?) ?? '获取用户信息失败'
          : '获取用户信息失败';
      state = state.copyWith(isLoading: false, error: msg);
    } catch (e) {
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
      final profile = UserProfile.fromJson(resp.data as Map<String, dynamic>);
      state = state.copyWith(profile: profile, isLoading: false);
      return true;
    } on DioException catch (e) {
      final data = e.response?.data;
      final msg = (data is Map<String, dynamic>)
          ? (data['detail'] as String?) ?? '更新失败'
          : '更新失败';
      state = state.copyWith(isLoading: false, error: msg);
      return false;
    } catch (e) {
      state = state.copyWith(isLoading: false, error: '更新失败');
      return false;
    }
  }
}

final userProvider = StateNotifierProvider<UserNotifier, UserState>((ref) {
  final api = ref.read(apiClientProvider);
  return UserNotifier(api);
});
