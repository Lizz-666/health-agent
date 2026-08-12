import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:posture_app/core/constants.dart';
import 'package:posture_app/screens/auth/login_screen.dart';

void main() {
  testWidgets('build selects the configured authentication flow', (
    tester,
  ) async {
    await tester.pumpWidget(
      const ProviderScope(child: MaterialApp(home: LoginScreen())),
    );
    if (AppConstants.controlledTrialAuth) {
      expect(AppConstants.controlledTrialConfigurationValid, isTrue);
      expect(find.byKey(const Key('trial-account-input')), findsOneWidget);
      expect(find.byKey(const Key('login-phone-input')), findsNothing);
    } else {
      expect(find.byKey(const Key('trial-account-input')), findsNothing);
      expect(find.byKey(const Key('login-phone-input')), findsOneWidget);
    }
  });
}
