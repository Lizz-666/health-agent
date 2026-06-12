// app/lib/main.dart
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'app.dart';
import 'providers/auth_provider.dart';
import 'services/sync_service.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();

  FlutterError.onError = (details) {
    FlutterError.presentError(details);
    debugPrint('Flutter error: ${details.exceptionAsString()}');
  };
  PlatformDispatcher.instance.onError = (error, stack) {
    debugPrint('Uncaught error: $error\n$stack');
    return true;
  };

  final container = ProviderContainer();

  await container.read(authProvider.notifier).checkAuth();

  if (container.read(authProvider).isLoggedIn) {
    try {
      await container.read(syncServiceProvider).startupSync();
    } catch (e) {
      debugPrint('Startup sync failed: $e');
    }
  }

  runApp(
    UncontrolledProviderScope(
      container: container,
      child: const PostureApp(),
    ),
  );
}
