import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:posture_app/app.dart';
import 'package:posture_app/core/constants.dart';

void main() {
  testWidgets('App renders without crash', (WidgetTester tester) async {
    await tester.pumpWidget(const ProviderScope(child: PostureApp()));
    await tester.pumpAndSettle();
    expect(find.text('登录'), findsOneWidget);
  });

  test('core text and control colors meet WCAG AA contrast', () {
    const background = AppConstants.bgColor;
    for (final pair in <(int, int, String)>[
      (AppConstants.textColor, background, 'primary text'),
      (AppConstants.textMuted, background, 'secondary text'),
      (AppConstants.accentColor, background, 'outlined action'),
      (Colors.white.toARGB32(), AppConstants.accentColor, 'primary action'),
      (AppConstants.severeColor, background, 'severe status'),
      (AppConstants.moderateColor, background, 'warning status'),
      (
        AppConstants.navigationMuted,
        AppConstants.surfaceDark,
        'unselected navigation item',
      ),
      (
        AppConstants.accentLight,
        AppConstants.surfaceDark,
        'selected navigation item',
      ),
    ]) {
      expect(
        _contrastRatio(pair.$1, pair.$2),
        greaterThanOrEqualTo(4.5),
        reason: '${pair.$3} must remain readable',
      );
    }

    for (final color in [
      AppConstants.accentColor,
      AppConstants.severeColor,
      AppConstants.moderateColor,
      AppConstants.textMuted,
    ]) {
      final tintedBackground = _composite(color, background, 0.14);
      expect(
        _contrastRatio(color, tintedBackground),
        greaterThanOrEqualTo(4.5),
        reason: 'status text must remain readable on its tinted panel',
      );
    }
  });
}

double _contrastRatio(int first, int second) {
  final a = _relativeLuminance(first);
  final b = _relativeLuminance(second);
  return (math.max(a, b) + 0.05) / (math.min(a, b) + 0.05);
}

double _relativeLuminance(int color) {
  double channel(int shift) {
    final value = ((color >> shift) & 0xff) / 255;
    return value <= 0.04045
        ? value / 12.92
        : math.pow((value + 0.055) / 1.055, 2.4).toDouble();
  }

  return 0.2126 * channel(16) + 0.7152 * channel(8) + 0.0722 * channel(0);
}

int _composite(int foreground, int background, double opacity) {
  int channel(int shift) {
    final front = (foreground >> shift) & 0xff;
    final back = (background >> shift) & 0xff;
    return (front * opacity + back * (1 - opacity)).round();
  }

  return 0xff000000 | (channel(16) << 16) | (channel(8) << 8) | channel(0);
}
