// app/lib/main.dart
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'app.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  // Hive 初始化将在 Task 15 的 sync 服务中添加
  runApp(const ProviderScope(child: PostureApp()));
}
