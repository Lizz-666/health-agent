// app/lib/models/user.dart
class UserProfile {
  final String id;
  final String phone;
  final String? nickname;
  final double? height;
  final double? weight;
  final int? age;
  final String? gender;
  final String membershipLevel;
  final String? createdAt;

  UserProfile({
    required this.id,
    required this.phone,
    this.nickname,
    this.height,
    this.weight,
    this.age,
    this.gender,
    this.membershipLevel = 'free',
    this.createdAt,
  });

  factory UserProfile.fromJson(Map<String, dynamic> json) => UserProfile(
    id: json['id'] as String,
    phone: json['phone'] as String,
    nickname: json['nickname'] as String?,
    height: (json['height'] as num?)?.toDouble(),
    weight: (json['weight'] as num?)?.toDouble(),
    age: json['age'] as int?,
    gender: json['gender'] as String?,
    membershipLevel: (json['membership_level'] as String?) ?? 'free',
    createdAt: json['created_at'] as String?,
  );

  Map<String, dynamic> toJson() => {
    'nickname': nickname,
    'height': height,
    'weight': weight,
    'age': age,
    'gender': gender,
  };

  bool get hasProfile =>
      height != null && weight != null && age != null && gender != null;
}
