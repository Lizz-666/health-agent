// app/test/screens/posture_status_badge_test.dart
//
// Verifies the new PostureStatusBadge state-mapping logic. Safety contract
// (Task 8C, spec §11.2 / §12): restricted vs red_flag MUST be distinguishable
// by icon AND text, not color alone; combined_severity=null surfaces as
// "无合并结论"; mild surfaces as "轻度".
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:posture_app/models/posture_profile.dart';
import 'package:posture_app/widgets/posture_status_badge.dart';

void main() {
  group('severityLabel', () {
    test('normal -> 正常', () {
      expect(severityLabel(PostureSeverity.normal), '正常');
    });
    test('mild -> 轻度', () {
      expect(severityLabel(PostureSeverity.mild), '轻度');
    });
    test('moderate -> 中度', () {
      expect(severityLabel(PostureSeverity.moderate), '中度');
    });
    test('severe -> 严重', () {
      expect(severityLabel(PostureSeverity.severe), '严重');
    });
    test('null -> 无合并结论', () {
      expect(severityLabel(null), '无合并结论');
    });
  });

  group('severityIcon', () {
    test('distinct icons for normal and severe', () {
      expect(
        severityIcon(PostureSeverity.normal),
        isNot(severityIcon(PostureSeverity.severe)),
      );
    });
    test('null has its own icon (not normal)', () {
      expect(severityIcon(null), isNot(severityIcon(PostureSeverity.normal)));
    });
  });

  group('certaintyLabel', () {
    test('confirmed mentions source agreement', () {
      expect(certaintyLabel(Certainty.confirmed), contains('已确认'));
    });
    test('provisional -> 建议重新评估', () {
      expect(certaintyLabel(Certainty.provisional), contains('建议重新评估'));
    });
    test('conflict -> 来源不一致 / 无合并结论', () {
      final label = certaintyLabel(Certainty.conflict);
      expect(label, contains('来源不一致'));
      expect(label, contains('无合并结论'));
    });
  });

  group('riskTier — restricted vs red_flag distinction', () {
    test('labels are distinct and neither is empty', () {
      final restricted = riskTierLabel(RiskTier.restricted);
      final redFlag = riskTierLabel(RiskTier.redFlag);
      expect(restricted, isNotEmpty);
      expect(redFlag, isNotEmpty);
      expect(restricted, isNot(redFlag));
    });
    test('icons are distinct', () {
      expect(
        riskTierIcon(RiskTier.restricted),
        isNot(riskTierIcon(RiskTier.redFlag)),
      );
    });
    test('colors are distinct', () {
      expect(
        riskTierColor(RiskTier.restricted),
        isNot(riskTierColor(RiskTier.redFlag)),
      );
    });
    test(
      'restricted text mentions professional assessment, not clinical red flag',
      () {
        final label = riskTierLabel(RiskTier.restricted);
        expect(label, contains('专业评估'));
        expect(label.toLowerCase(), isNot(contains('red_flag')));
      },
    );
    test('red_flag text mentions stopping planning', () {
      expect(riskTierLabel(RiskTier.redFlag), contains('停止规划'));
    });
  });

  group('widget rendering', () {
    testWidgets('SeverityBadge(mild) renders icon + 轻度 without overflow', (
      tester,
    ) async {
      await _pump(tester, SeverityBadge(severity: PostureSeverity.mild));
      expect(find.textContaining('轻度'), findsOneWidget);
      expect(find.byType(Icon), findsOneWidget);
      expect(tester.takeException(), isNull);
    });

    testWidgets('SeverityBadge(null) renders 无合并结论', (tester) async {
      await _pump(tester, const SeverityBadge(severity: null));
      expect(find.textContaining('无合并结论'), findsOneWidget);
      expect(find.byType(Icon), findsOneWidget);
    });

    testWidgets('CertaintyBadge(conflict) renders 来源不一致', (tester) async {
      await _pump(tester, CertaintyBadge(certainty: Certainty.conflict));
      expect(find.textContaining('来源不一致'), findsOneWidget);
      expect(find.byType(Icon), findsOneWidget);
    });

    testWidgets(
      'RiskTierBadge restricted and red_flag render different text and icons',
      (tester) async {
        final restrictedKey = UniqueKey();
        final redFlagKey = UniqueKey();
        await tester.pumpWidget(
          MaterialApp(
            home: Scaffold(
              body: Column(
                children: [
                  KeyedSubtree(
                    key: restrictedKey,
                    child: RiskTierBadge(riskTier: RiskTier.restricted),
                  ),
                  KeyedSubtree(
                    key: redFlagKey,
                    child: RiskTierBadge(riskTier: RiskTier.redFlag),
                  ),
                ],
              ),
            ),
          ),
        );
        await tester.pumpAndSettle();

        final restrictedText = tester
            .widgetList<Text>(
              find.descendant(
                of: find.byKey(restrictedKey),
                matching: find.byType(Text),
              ),
            )
            .map((t) => t.data ?? '')
            .join();
        final redFlagText = tester
            .widgetList<Text>(
              find.descendant(
                of: find.byKey(redFlagKey),
                matching: find.byType(Text),
              ),
            )
            .map((t) => t.data ?? '')
            .join();
        expect(restrictedText, contains('专业评估'));
        expect(redFlagText, contains('停止规划'));
        expect(restrictedText, isNot(equals(redFlagText)));

        final restrictedIcon = tester.widget<Icon>(
          find.descendant(
            of: find.byKey(restrictedKey),
            matching: find.byType(Icon),
          ),
        );
        final redFlagIcon = tester.widget<Icon>(
          find.descendant(
            of: find.byKey(redFlagKey),
            matching: find.byType(Icon),
          ),
        );
        expect(restrictedIcon.icon, isNot(redFlagIcon.icon));
      },
    );
  });
}

Future<void> _pump(WidgetTester tester, Widget child) async {
  await tester.pumpWidget(
    MaterialApp(
      home: Scaffold(body: Center(child: child)),
    ),
  );
  await tester.pumpAndSettle();
}
