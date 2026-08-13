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
import 'package:posture_app/core/api_client.dart';
import 'package:posture_app/providers/auth_provider.dart';
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

  testWidgets(
    '320x720 textScaler 2.0 no overflow, key anchors still findable',
    (tester) async {
      tester.view.devicePixelRatio = 1;
      tester.view.physicalSize = const Size(320, 720);
      tester.platformDispatcher.textScaleFactorTestValue = 2.0;
      addTearDown(tester.view.resetDevicePixelRatio);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.platformDispatcher.clearTextScaleFactorTestValue);

      await tester.pumpWidget(_wrap());
      await tester.pumpAndSettle();

      expect(tester.takeException(), isNull);
      expect(find.byKey(const Key('login-submit')), findsOneWidget);
      expect(find.byKey(const Key('login-send-code')), findsOneWidget);
    },
  );

  testWidgets('login submit button has accessible Semantics label', (
    tester,
  ) async {
    await tester.pumpWidget(_wrap());
    await tester.pumpAndSettle();

    final semantics = tester.getSemantics(
      find.byKey(const Key('login-submit')),
    );
    expect(
      semantics,
      isSemantics(
        label: '登录',
        isButton: true,
        hasEnabledState: true,
        isEnabled: true,
        hasTapAction: true,
      ),
    );
  });

  testWidgets('client incompatibility blocks authentication with stable copy', (
    tester,
  ) async {
    final api = ApiClient();
    await tester.pumpWidget(
      ProviderScope(
        overrides: [apiClientProvider.overrideWithValue(api)],
        child: const MaterialApp(home: LoginScreen()),
      ),
    );
    await tester.pump();

    api.onClientIncompatible?.call();
    await tester.pump();

    expect(find.byKey(const Key('client-incompatible-block')), findsOneWidget);
    expect(find.text('当前应用版本不兼容，请更新后重试'), findsOneWidget);
    expect(find.byKey(const Key('login-submit')), findsNothing);
    expect(find.byKey(const Key('trial-auth-submit')), findsNothing);
  });
}
