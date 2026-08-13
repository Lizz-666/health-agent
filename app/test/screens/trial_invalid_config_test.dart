import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:posture_app/core/constants.dart';
import 'package:posture_app/screens/auth/login_screen.dart';

void main() {
  testWidgets('controlled-trial build fails closed with unsafe configuration', (
    tester,
  ) async {
    await tester.pumpWidget(
      const ProviderScope(child: MaterialApp(home: LoginScreen())),
    );
    if (AppConstants.controlledTrialAuth) {
      expect(AppConstants.controlledTrialConfigurationValid, isFalse);
      expect(find.text('内测配置无效，应用已停止登录'), findsOneWidget);
      expect(find.byKey(const Key('trial-auth-submit')), findsNothing);
      expect(find.byKey(const Key('login-submit')), findsNothing);
    } else {
      expect(find.text('内测配置无效，应用已停止登录'), findsNothing);
      expect(find.byKey(const Key('login-submit')), findsOneWidget);
    }
  });

  testWidgets('320x720 textScaler 2.0 no overflow on invalid-config state', (
    tester,
  ) async {
    tester.view.devicePixelRatio = 1;
    tester.view.physicalSize = const Size(320, 720);
    tester.platformDispatcher.textScaleFactorTestValue = 2.0;
    addTearDown(tester.view.resetDevicePixelRatio);
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.platformDispatcher.clearTextScaleFactorTestValue);

    await tester.pumpWidget(
      const ProviderScope(child: MaterialApp(home: LoginScreen())),
    );
    await tester.pumpAndSettle();

    expect(tester.takeException(), isNull);
  });
}
