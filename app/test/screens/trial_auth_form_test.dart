import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:posture_app/screens/auth/trial_auth_form.dart';

void main() {
  testWidgets('trial auth defaults to activation and exposes stable anchors', (
    tester,
  ) async {
    await tester.pumpWidget(
      const ProviderScope(child: MaterialApp(home: TrialAuthScreen())),
    );
    expect(find.byKey(const Key('trial-account-input')), findsOneWidget);
    expect(find.byKey(const Key('trial-invitation-input')), findsOneWidget);
    expect(find.byKey(const Key('trial-credential-input')), findsOneWidget);
    expect(find.byKey(const Key('trial-auth-submit')), findsOneWidget);
    expect(find.text('激活账号'), findsOneWidget);
  });

  testWidgets('login mode does not ask for an invitation', (tester) async {
    await tester.pumpWidget(
      const ProviderScope(child: MaterialApp(home: TrialAuthScreen())),
    );
    await tester.tap(find.text('登录').first);
    await tester.pump();
    expect(find.byKey(const Key('trial-invitation-input')), findsNothing);
    expect(find.text('登录'), findsWidgets);
  });

  testWidgets('invalid activation reports a Chinese validation error', (
    tester,
  ) async {
    await tester.pumpWidget(
      const ProviderScope(child: MaterialApp(home: TrialAuthScreen())),
    );
    await tester.tap(find.byKey(const Key('trial-auth-submit')));
    await tester.pump();
    expect(find.text('请输入有效的内测账号和凭据'), findsOneWidget);
  });

  testWidgets(
    '320x720 textScaler 2.0 no overflow, submit anchor still findable',
    (tester) async {
      tester.view.devicePixelRatio = 1;
      tester.view.physicalSize = const Size(320, 720);
      tester.platformDispatcher.textScaleFactorTestValue = 2.0;
      addTearDown(tester.view.resetDevicePixelRatio);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.platformDispatcher.clearTextScaleFactorTestValue);

      await tester.pumpWidget(
        const ProviderScope(child: MaterialApp(home: TrialAuthScreen())),
      );
      await tester.pumpAndSettle();

      expect(tester.takeException(), isNull);
      expect(find.byKey(const Key('trial-auth-submit')), findsOneWidget);
    },
  );

  testWidgets('submit button has accessible Semantics label', (tester) async {
    await tester.pumpWidget(
      const ProviderScope(child: MaterialApp(home: TrialAuthScreen())),
    );
    await tester.pumpAndSettle();

    final semantics = tester.getSemantics(
      find.byKey(const Key('trial-auth-submit')),
    );
    expect(
      semantics,
      isSemantics(
        label: '激活账号',
        isButton: true,
        hasEnabledState: true,
        isEnabled: true,
        hasTapAction: true,
      ),
    );
  });
}
