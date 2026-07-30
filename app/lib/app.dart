// app/lib/app.dart
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'core/theme.dart';
import 'models/agent.dart';
import 'providers/auth_provider.dart';
import 'providers/user_provider.dart';
import 'screens/agent/agent_screen.dart';
import 'screens/auth/login_screen.dart';
import 'screens/onboarding/onboarding_screen.dart';
import 'screens/home/home_screen.dart';
import 'screens/today/today_screen.dart';
import 'screens/issues/issue_list_screen.dart';
import 'screens/issues/issue_detail_screen.dart';
import 'screens/test/self_test_screen.dart';
import 'screens/test/photo_test_screen.dart';
import 'screens/result/result_screen.dart';
import 'screens/history/history_screen.dart';
import 'screens/plan/plan_screen.dart';
import 'screens/profile/profile_screen.dart';
import 'screens/profile/posture_profile_screen.dart';
import 'screens/profile/health_profile_screen.dart';
import 'screens/profile/weight_trend_screen.dart';
import 'screens/profile/activity_grid_screen.dart';
import 'screens/search/search_screen.dart';

final _rootNavigatorKey = GlobalKey<NavigatorState>();

class ResultRouteArgs {
  final String assessmentId;
  final String result;
  final String suggestion;

  const ResultRouteArgs({
    required this.assessmentId,
    required this.result,
    required this.suggestion,
  });
}

ResultRouteArgs? parseResultRouteExtra(Object? extra) {
  if (extra is! Map<String, dynamic>) return null;
  final assessmentId = extra['assessmentId'];
  final result = extra['result'];
  final suggestion = extra['suggestion'];
  if (assessmentId is! String || assessmentId.trim().isEmpty) return null;
  if (result is! String ||
      !const {'normal', 'mild', 'moderate', 'severe'}.contains(result)) {
    return null;
  }
  if (suggestion != null && suggestion is! String) return null;
  return ResultRouteArgs(
    assessmentId: assessmentId,
    result: result,
    suggestion: suggestion as String? ?? '',
  );
}

class _AuthNotifier extends ChangeNotifier {
  final Ref _ref;
  _AuthNotifier(this._ref) {
    _ref.listen(authProvider, (_, _) => notifyListeners());
    _ref.listen(userProvider, (_, _) => notifyListeners());
  }
}

final _authNotifierProvider = Provider<_AuthNotifier>(
  (ref) => _AuthNotifier(ref),
);

final routerProvider = Provider<GoRouter>((ref) {
  final notifier = ref.watch(_authNotifierProvider);

  return GoRouter(
    navigatorKey: _rootNavigatorKey,
    initialLocation: '/login',
    refreshListenable: notifier,
    redirect: (context, state) {
      final authState = ref.read(authProvider);
      final userState = ref.read(userProvider);
      final onLogin = state.matchedLocation == '/login';
      final onOnboarding = state.matchedLocation == '/onboarding';

      if (!authState.isLoggedIn && !onLogin) return '/login';
      if (authState.isLoggedIn && onLogin) return '/today';
      if (authState.isLoggedIn &&
          userState.profile != null &&
          userState.profile!.hasProfile != true &&
          !onOnboarding) {
        return '/onboarding';
      }
      return null;
    },
    routes: [
      GoRoute(path: '/login', builder: (_, _) => const LoginScreen()),
      GoRoute(path: '/onboarding', builder: (_, _) => const OnboardingScreen()),
      GoRoute(path: '/', redirect: (_, _) => '/posture'),
      StatefulShellRoute.indexedStack(
        builder: (_, _, navigationShell) =>
            AppShell(navigationShell: navigationShell),
        branches: [
          StatefulShellBranch(
            routes: [
              GoRoute(path: '/today', builder: (_, _) => const TodayScreen()),
            ],
          ),
          StatefulShellBranch(
            routes: [
              GoRoute(path: '/plan', builder: (_, _) => const PlanScreen()),
            ],
          ),
          StatefulShellBranch(
            routes: [
              GoRoute(
                path: '/agent',
                builder: (_, state) {
                  AgentRouteContext? routeContext;
                  try {
                    routeContext = AgentRouteContext.fromQuery(
                      state.uri.queryParameters,
                    );
                  } on FormatException {
                    routeContext = null;
                  }
                  return AgentScreen(routeContext: routeContext);
                },
              ),
            ],
          ),
          StatefulShellBranch(
            routes: [
              GoRoute(
                path: '/profile',
                builder: (_, _) => const ProfileScreen(),
                routes: [
                  GoRoute(
                    path: 'posture',
                    builder: (_, _) => const PostureProfileScreen(),
                  ),
                  GoRoute(
                    path: 'health',
                    builder: (_, _) => const HealthProfileScreen(),
                  ),
                  GoRoute(
                    path: 'weight',
                    builder: (_, _) => const WeightTrendScreen(),
                  ),
                  GoRoute(
                    path: 'grid',
                    builder: (_, _) => const ActivityGridScreen(),
                  ),
                ],
              ),
            ],
          ),
        ],
      ),
      GoRoute(path: '/posture', builder: (_, _) => const HomeScreen()),
      // History remains reachable (moved out of the bottom nav to make room
      // for the Phase 4 计划 tab).
      GoRoute(path: '/history', builder: (_, _) => const HistoryScreen()),
      GoRoute(
        path: '/issues/:category',
        builder: (_, state) =>
            IssueListScreen(category: state.pathParameters['category'] ?? ''),
      ),
      GoRoute(
        path: '/issue/:id/detail',
        builder: (_, state) =>
            IssueDetailScreen(issueId: state.pathParameters['id'] ?? ''),
      ),
      GoRoute(
        path: '/issue/:id/test',
        builder: (_, state) =>
            SelfTestScreen(issueId: state.pathParameters['id'] ?? ''),
      ),
      GoRoute(
        path: '/issue/:id/photo',
        builder: (_, state) =>
            PhotoTestScreen(issueId: state.pathParameters['id'] ?? ''),
      ),
      GoRoute(
        path: '/issue/:id/result',
        builder: (_, state) {
          final args = parseResultRouteExtra(state.extra);
          if (args == null) {
            return const HomeScreen();
          }
          return ResultScreen(
            issueId: state.pathParameters['id'] ?? '',
            assessmentId: args.assessmentId,
            result: args.result,
            suggestion: args.suggestion,
          );
        },
      ),
      GoRoute(path: '/search', builder: (_, _) => const SearchScreen()),
    ],
  );
});

class PostureApp extends ConsumerWidget {
  const PostureApp({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final router = ref.watch(routerProvider);
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
          navigationShell.goBranch(
            index,
            initialLocation: index == navigationShell.currentIndex,
          );
        },
        destinations: const [
          NavigationDestination(
            icon: Icon(Icons.today_outlined),
            selectedIcon: Icon(Icons.today),
            label: '今日',
          ),
          NavigationDestination(
            icon: Icon(Icons.fitness_center_outlined),
            selectedIcon: Icon(Icons.fitness_center),
            label: '计划',
          ),
          NavigationDestination(
            icon: Icon(Icons.auto_awesome_outlined),
            selectedIcon: Icon(Icons.auto_awesome),
            label: 'Agent',
          ),
          NavigationDestination(
            icon: Icon(Icons.person_outlined),
            selectedIcon: Icon(Icons.person),
            label: '我的',
          ),
        ],
      ),
    );
  }
}
