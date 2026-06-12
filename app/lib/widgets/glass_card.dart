// app/lib/widgets/glass_card.dart
import 'dart:ui';
import 'package:flutter/material.dart';
import '../core/constants.dart';

class GlassCard extends StatelessWidget {
  final Widget child;
  final EdgeInsetsGeometry? padding;
  final EdgeInsetsGeometry? margin;
  final double borderRadius;
  final bool dark;

  const GlassCard({
    super.key,
    required this.child,
    this.padding = const EdgeInsets.all(20),
    this.margin,
    this.borderRadius = 20,
    this.dark = false,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: margin,
      child: ClipRRect(
        borderRadius: BorderRadius.circular(borderRadius),
        child: BackdropFilter(
          filter: ImageFilter.blur(sigmaX: 12, sigmaY: 12),
          child: Container(
            padding: padding,
            decoration: BoxDecoration(
              color: dark
                  ? const Color(AppConstants.primaryColor).withValues(alpha: 0.5)
                  : const Color(0x40FFFFFF),
              borderRadius: BorderRadius.circular(borderRadius),
              border: Border.all(
                color: dark
                    ? const Color(0x1AFFFFFF)
                    : const Color(AppConstants.glassBorder),
                width: 1,
              ),
            ),
            child: child,
          ),
        ),
      ),
    );
  }
}
