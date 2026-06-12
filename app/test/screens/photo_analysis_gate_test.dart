import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:posture_app/core/constants.dart';
import 'package:posture_app/screens/test/photo_test_screen.dart';

void main() {
  group('Photo analysis gate', () {
    test('photoAnalysisEnabled defaults to false', () {
      expect(AppConstants.photoAnalysisEnabled, isFalse);
    });

    testWidgets('PhotoTestScreen shows unavailable message when disabled',
        (tester) async {
      await tester.pumpWidget(
        const MaterialApp(
          home: PhotoTestScreen(issueId: 'HN-01'),
        ),
      );
      await tester.pumpAndSettle();

      // Should show the unavailable notice in Chinese
      expect(find.text('照片分析在当前数据模式下未启用'), findsOneWidget);
      expect(find.textContaining('PHOTO_ANALYSIS_ENABLED'), findsNothing);

      // Should NOT show any actionable photo buttons
      expect(find.text('拍照'), findsNothing);
      expect(find.text('从相册选择'), findsNothing);
      expect(find.text('开始分析'), findsNothing);
    });
  });
}
