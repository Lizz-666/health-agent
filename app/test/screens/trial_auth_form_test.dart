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
}
