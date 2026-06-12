// app/lib/models/token.dart
class TokenResponse {
  final String accessToken;
  final String refreshToken;
  final String tokenType;
  final bool isNewUser;

  TokenResponse({
    required this.accessToken,
    required this.refreshToken,
    this.tokenType = 'bearer',
    this.isNewUser = false,
  });

  factory TokenResponse.fromJson(Map<String, dynamic> json) => TokenResponse(
    accessToken: (json['access_token'] as String?) ?? '',
    refreshToken: (json['refresh_token'] as String?) ?? '',
    tokenType: (json['token_type'] as String?) ?? 'bearer',
    isNewUser: (json['is_new_user'] as bool?) ?? false,
  );
}
