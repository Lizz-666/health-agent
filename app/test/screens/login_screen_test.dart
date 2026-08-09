// app/test/screens/login_screen_test.dart
//
// Phase 8 Task 3 automation-anchor contract for the login screen. The screen
// exposes stable keys so the real-HTTP core-journey driver
// (integration_test/phase8_core_journey_test.dart) can locate the phone /
// code inputs and the login actions without depending on visible copy.
//
// This is a focused widget test. It does not perform authentication over the
// network; the login screen fires no request on load, so pumping it under a
// plain ProviderScope is sufficient to assert that the anchors render.
//
// Note: `login-dev-submit` only renders when DEV_ADMIN_PHONE /
// DEV_ADMIN_PASSWORD build-time defines are set. Under `flutter test` those
// defines are empty, so the developer shortcut block is intentionally hidden
// here; the dev-login anchor is exercised by the integration driver, which is
// built with the synthetic dart-defines.
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:posture_app/screens/auth/login_screen.dart';

Widget _wrap() => const ProviderScope(child: MaterialApp(home: LoginScreen()));

void main() {
  testWidgets('login screen exposes stable automation anchors', (tester) async {
    await tester.pumpWidget(_wrap());
    await tester.pump();

    expect(find.byKey(const Key('login-phone-input')), findsOneWidget);
    expect(find.byKey(const Key('login-code-input')), findsOneWidget);
    expect(find.byKey(const Key('login-send-code')), findsOneWidget);
    expect(find.byKey(const Key('login-submit')), findsOneWidget);
  });

  testWidgets('phone/code anchors are editable text fields', (tester) async {
    await tester.pumpWidget(_wrap());
    await tester.pump();

    await tester.enterText(
      find.byKey(const Key('login-phone-input')),
      '13900000008',
    );
    await tester.enterText(find.byKey(const Key('login-code-input')), '123456');
    await tester.pump();

    expect(find.text('13900000008'), findsOneWidget);
    expect(find.text('123456'), findsOneWidget);
  });

  testWidgets('login submit anchor is the 登录 action', (tester) async {
    await tester.pumpWidget(_wrap());
    await tester.pump();

    final submit = find.byKey(const Key('login-submit'));
    expect(submit, findsOneWidget);
    expect(
      find.descendant(of: submit, matching: find.text('登录')),
      findsOneWidget,
    );
  });
}
