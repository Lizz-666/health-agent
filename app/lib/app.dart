// app/lib/app.dart
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'core/theme.dart';
import 'providers/auth_provider.dart';
import 'providers/user_provider.dart';
import 'screens/auth/login_screen.dart';
import 'screens/onboarding/onboarding_screen.dart';
import 'screens/home/home_screen.dart';
import 'screens/issues/issue_list_screen.dart';
import 'screens/issues/issue_detail_screen.dart';
import 'screens/test/self_test_screen.dart';
import 'screens/test/photo_test_screen.dart';
import 'screens/result/result_screen.dart';
import 'screens/history/history_screen.dart';
import 'screens/profile/profile_screen.dart';
import 'screens/profile/posture_profile_screen.dart';

final _rootNavigatorKey = GlobalKey<NavigatorState>();

class PostureApp extends ConsumerWidget {
  const PostureApp({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final authState = ref.watch(authProvider);
    final userState = ref.watch(userProvider);

    final router = GoRouter(
      navigatorKey: _rootNavigatorKey,
      initialLocation: '/login',
      redirect: (context, state) {
        final onLogin = state.matchedLocation == '/login';
        final onOnboarding = state.matchedLocation == '/onboarding';
        if (!authState.isLoggedIn && !onLogin) return '/login';
        if (authState.isLoggedIn && onLogin) return '/';
        if (authState.isLoggedIn && userState.profile?.hasProfile != true && !onOnboarding) {
          return '/onboarding';
        }
        return null;
      },
      routes: [
        GoRoute(path: '/login', builder: (_, __) => const LoginScreen()),
        GoRoute(path: '/onboarding', builder: (_, __) => const OnboardingScreen()),
        StatefulShellRoute.indexedStack(
          builder: (_, __, navigationShell) =>
              AppShell(navigationShell: navigationShell),
          branches: [
            StatefulShellBranch(routes: [
              GoRoute(path: '/', builder: (_, __) => const HomeScreen()),
            ]),
            StatefulShellBranch(routes: [
              GoRoute(path: '/history', builder: (_, __) => const HistoryScreen()),
            ]),
            StatefulShellBranch(routes: [
              GoRoute(
                path: '/profile',
                builder: (_, __) => const ProfileScreen(),
                routes: [
                  GoRoute(
                    path: 'posture',
                    builder: (_, __) => const PostureProfileScreen(),
                  ),
                ],
              ),
            ]),
          ],
        ),
        GoRoute(
          path: '/issues/:category',
          builder: (_, state) =>
              IssueListScreen(category: state.pathParameters['category']!),
        ),
        GoRoute(
          path: '/issues/:id/detail',
          builder: (_, state) =>
              IssueDetailScreen(issueId: state.pathParameters['id']!),
        ),
        GoRoute(
          path: '/issues/:id/test',
          builder: (_, state) =>
              SelfTestScreen(issueId: state.pathParameters['id']!),
        ),
        GoRoute(
          path: '/issues/:id/photo',
          builder: (_, state) =>
              PhotoTestScreen(issueId: state.pathParameters['id']!),
        ),
        GoRoute(
          path: '/issues/:id/result',
          builder: (_, state) {
            final extra = state.extra as Map<String, dynamic>;
            return ResultScreen(
              issueId: state.pathParameters['id']!,
              assessmentId: extra['assessmentId'] as String,
              result: extra['result'] as String,
              suggestion: extra['suggestion'] as String,
            );
          },
        ),
      ],
    );

    return MaterialApp.router(
      title: '体态分析',
      theme: AppTheme.darkTheme,
      routerConfig: router,
      debugShowCheckedModeBanner: false,
    );
  }
}

class AppShell extends StatelessWidget {
  final StatefulNavigationShell navigationShell;
  const AppShell({super.key, required this.navigationShell});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: navigationShell,
      bottomNavigationBar: NavigationBar(
        selectedIndex: navigationShell.currentIndex,
        onDestinationSelected: (index) {
          navigationShell.goBranch(index, initialLocation: index == navigationShell.currentIndex);
        },
        destinations: const [
          NavigationDestination(icon: Icon(Icons.home_outlined), selectedIcon: Icon(Icons.home), label: '首页'),
          NavigationDestination(icon: Icon(Icons.history_outlined), selectedIcon: Icon(Icons.history), label: '历史'),
          NavigationDestination(icon: Icon(Icons.person_outlined), selectedIcon: Icon(Icons.person), label: '我的'),
        ],
      ),
    );
  }
}
