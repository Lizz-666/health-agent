// app/test/screens/profile_screen_test.dart
//
// Phase 2 Task 6: ProfileScreen (My page) entry list and route wiring.
// Verifies the three Phase 2 health entries are present alongside the posture
// entry (kept separate), and that each entry navigates to its /profile
// sub-route. No real API calls; the health sub-pages are stubbed in the test
// router so navigation can be asserted without providers.
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:posture_app/screens/profile/profile_screen.dart';

Widget _page(String label) => Scaffold(body: Center(child: Text(label)));

GoRouter _router() => GoRouter(
      initialLocation: '/profile',
      routes: [
        GoRoute(
          path: '/profile',
          builder: (_, _) => const ProfileScreen(),
          routes: [
            GoRoute(
              path: 'posture',
              builder: (_, _) => _page('POSTURE_PAGE'),
            ),
            GoRoute(
              path: 'health',
              builder: (_, _) => _page('HEALTH_PAGE'),
            ),
            GoRoute(
              path: 'weight',
              builder: (_, _) => _page('WEIGHT_PAGE'),
            ),
            GoRoute(
              path: 'grid',
              builder: (_, _) => _page('GRID_PAGE'),
            ),
          ],
        ),
      ],
    );

Future<void> _pump(WidgetTester tester) async {
  // Tall surface so the full My-page list (avatar + info + menu + logout) is
  // hit-testable without scrolling.
  tester.view.devicePixelRatio = 1;
  tester.view.physicalSize = const Size(800, 1400);
  addTearDown(tester.view.resetDevicePixelRatio);
  addTearDown(tester.view.resetPhysicalSize);
  await tester.pumpWidget(
    ProviderScope(child: MaterialApp.router(routerConfig: _router())),
  );
}

void main() {
  testWidgets('My page lists posture + three Phase 2 health entries', (
    tester,
  ) async {
    await _pump(tester);
    await tester.pumpAndSettle();

    expect(find.text('我的体态档案'), findsOneWidget);
    expect(find.text('健康档案'), findsOneWidget);
    expect(find.text('体重趋势'), findsOneWidget);
    expect(find.text('活动记录'), findsOneWidget);
  });

  testWidgets('tapping 健康档案 navigates to /profile/health', (tester) async {
    await _pump(tester);
    await tester.pumpAndSettle();

    await tester.tap(find.text('健康档案'));
    await tester.pumpAndSettle();

    expect(find.text('HEALTH_PAGE'), findsOneWidget);
  });

  testWidgets('tapping 体重趋势 navigates to /profile/weight', (tester) async {
    await _pump(tester);
    await tester.pumpAndSettle();

    await tester.tap(find.text('体重趋势'));
    await tester.pumpAndSettle();

    expect(find.text('WEIGHT_PAGE'), findsOneWidget);
  });

  testWidgets('tapping 活动记录 navigates to /profile/grid', (tester) async {
    await _pump(tester);
    await tester.pumpAndSettle();

    await tester.tap(find.text('活动记录'));
    await tester.pumpAndSettle();

    expect(find.text('GRID_PAGE'), findsOneWidget);
  });

  testWidgets('posture entry still present and separate from health', (
    tester,
  ) async {
    await _pump(tester);
    await tester.pumpAndSettle();

    await tester.tap(find.text('我的体态档案'));
    await tester.pumpAndSettle();
    expect(find.text('POSTURE_PAGE'), findsOneWidget);
    expect(find.text('HEALTH_PAGE'), findsNothing);
  });
}
