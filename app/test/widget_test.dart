import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:posture_app/app.dart';

void main() {
  testWidgets('App renders without crash', (WidgetTester tester) async {
    await tester.pumpWidget(
      const ProviderScope(child: PostureApp()),
    );
    await tester.pumpAndSettle();
    expect(find.text('登录'), findsOneWidget);
  });
}
