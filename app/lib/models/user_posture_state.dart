// app/lib/models/user_posture_state.dart
class UserPostureState {
  final String issueId;
  final String result;
  final String method;
  final DateTime updatedAt;
  bool synced;

  UserPostureState({
    required this.issueId,
    required this.result,
    required this.method,
    required this.updatedAt,
    this.synced = false,
  });

  Map<String, dynamic> toJson() => {
    'issueId': issueId,
    'result': result,
    'method': method,
    'updatedAt': updatedAt.toIso8601String(),
    'synced': synced,
  };

  factory UserPostureState.fromJson(Map<String, dynamic> json) =>
      UserPostureState(
        issueId: json['issueId'] as String,
        result: json['result'] as String,
        method: json['method'] as String,
        updatedAt: DateTime.parse(json['updatedAt'] as String),
        synced: (json['synced'] as bool?) ?? false,
      );
}
