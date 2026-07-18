// app/lib/widgets/posture_status_badge.dart
//
// State-display widgets for the three orthogonal posture state dimensions
// introduced by Task 8B: severity (nullable), certainty, risk_tier
// (spec §6.1 / §11.1 / §12.4). Used by the posture profile, result and
// priority UIs in Task 8C.
//
// Safety contract (Task 8C, spec §11.2 / §12):
//  - Safety state MUST be conveyed by icon + label + color together, never
//    by color alone (restricted and red_flag share no icon or label).
//  - combined_severity == null surfaces as "无合并结论"; never coerced to a
//    default severity.
//  - mild surfaces with the literal label "轻度" (the legacy ResultBadge did
//    not handle mild).
//  - restricted is product-policy language ("仅提供教育，建议专业评估"),
//    never clinical red-flag language; red_flag explicitly tells the user to
//    stop planning and seek escalation. This widget does NOT modify the
//    legacy ResultBadge (which still handles the older 3-state result string
//    for back-compat screens).
//
// Layout: flat Container with r=8 corners (no nested Card), single Icon +
// Text row, single-line by default.
import 'package:flutter/material.dart';

import '../core/constants.dart';
import '../models/posture_profile.dart';

// ---------------------------------------------------------------------------
// Severity (combined_severity is always nullable per spec §11.1)
// ---------------------------------------------------------------------------

String severityLabel(PostureSeverity? severity) {
  switch (severity) {
    case PostureSeverity.normal:
      return '正常';
    case PostureSeverity.mild:
      return '轻度';
    case PostureSeverity.moderate:
      return '中度';
    case PostureSeverity.severe:
      return '严重';
    case null:
      return '无合并结论';
  }
}

IconData severityIcon(PostureSeverity? severity) {
  switch (severity) {
    case PostureSeverity.normal:
      return Icons.check_circle;
    case PostureSeverity.mild:
      return Icons.info;
    case PostureSeverity.moderate:
      return Icons.warning_amber;
    case PostureSeverity.severe:
      return Icons.cancel;
    case null:
      return Icons.help_outline;
  }
}

Color severityColor(PostureSeverity? severity) {
  switch (severity) {
    case PostureSeverity.normal:
      return const Color(AppConstants.normalColor);
    case PostureSeverity.mild:
      return const Color(AppConstants.accentLight);
    case PostureSeverity.moderate:
      return const Color(AppConstants.moderateColor);
    case PostureSeverity.severe:
      return const Color(AppConstants.severeColor);
    case null:
      return const Color(AppConstants.textMuted);
  }
}

class SeverityBadge extends StatelessWidget {
  final PostureSeverity? severity;
  final double size;

  const SeverityBadge({super.key, required this.severity, this.size = 14});

  @override
  Widget build(BuildContext context) {
    return _Badge(
      icon: severityIcon(severity),
      text: severityLabel(severity),
      color: severityColor(severity),
      iconSize: size,
      fontSize: size,
    );
  }
}

PostureSeverity? postureSeverityFromResult(String result) {
  switch (result) {
    case 'normal':
      return PostureSeverity.normal;
    case 'mild':
      return PostureSeverity.mild;
    case 'moderate':
      return PostureSeverity.moderate;
    case 'severe':
      return PostureSeverity.severe;
    default:
      return null;
  }
}

/// Displays the strict assessment-result enum without coercing unknown values
/// to a healthy state. Unlike the legacy badge, this also supports `mild`.
class AssessmentResultBadge extends StatelessWidget {
  final String result;
  final double size;

  const AssessmentResultBadge({
    super.key,
    required this.result,
    this.size = 14,
  });

  @override
  Widget build(BuildContext context) {
    final severity = postureSeverityFromResult(result);
    if (severity == null) {
      return _Badge(
        icon: Icons.error_outline,
        text: '结果不可用',
        color: const Color(AppConstants.textMuted),
        iconSize: size,
        fontSize: size,
      );
    }
    return SeverityBadge(severity: severity, size: size);
  }
}

// ---------------------------------------------------------------------------
// Certainty
// ---------------------------------------------------------------------------

String certaintyLabel(Certainty certainty) {
  switch (certainty) {
    case Certainty.confirmed:
      return '已确认（来源一致）';
    case Certainty.provisional:
      return '建议重新评估';
    case Certainty.conflict:
      return '来源不一致，无合并结论';
  }
}

IconData certaintyIcon(Certainty certainty) {
  switch (certainty) {
    case Certainty.confirmed:
      return Icons.check_circle_outline;
    case Certainty.provisional:
      return Icons.help_outline;
    case Certainty.conflict:
      return Icons.compare_arrows;
  }
}

Color certaintyColor(Certainty certainty) {
  switch (certainty) {
    case Certainty.confirmed:
      return const Color(AppConstants.normalColor);
    case Certainty.provisional:
      return const Color(AppConstants.moderateColor);
    case Certainty.conflict:
      return const Color(AppConstants.severeColor);
  }
}

class CertaintyBadge extends StatelessWidget {
  final Certainty certainty;
  final double size;

  const CertaintyBadge({super.key, required this.certainty, this.size = 13});

  @override
  Widget build(BuildContext context) {
    return _Badge(
      icon: certaintyIcon(certainty),
      text: certaintyLabel(certainty),
      color: certaintyColor(certainty),
      iconSize: size,
      fontSize: size,
    );
  }
}

// ---------------------------------------------------------------------------
// Risk tier — restricted vs red_flag MUST differ by icon AND label.
// ---------------------------------------------------------------------------

String riskTierLabel(RiskTier riskTier) {
  switch (riskTier) {
    case RiskTier.normal:
      return '风险：正常';
    case RiskTier.cautious:
      return '风险：谨慎';
    case RiskTier.restricted:
      // Product-policy language, NOT clinical red-flag language.
      return '受限：仅提供教育，建议专业评估';
    case RiskTier.redFlag:
      return '风险信号：停止规划，建议就医升级';
  }
}

IconData riskTierIcon(RiskTier riskTier) {
  switch (riskTier) {
    case RiskTier.normal:
      return Icons.verified_user;
    case RiskTier.cautious:
      return Icons.info;
    case RiskTier.restricted:
      return Icons.block;
    case RiskTier.redFlag:
      return Icons.emergency;
  }
}

Color riskTierColor(RiskTier riskTier) {
  switch (riskTier) {
    case RiskTier.normal:
      return const Color(AppConstants.normalColor);
    case RiskTier.cautious:
      return const Color(AppConstants.accentLight);
    case RiskTier.restricted:
      return const Color(AppConstants.moderateColor);
    case RiskTier.redFlag:
      return const Color(AppConstants.severeColor);
  }
}

class RiskTierBadge extends StatelessWidget {
  final RiskTier riskTier;
  final double size;

  const RiskTierBadge({super.key, required this.riskTier, this.size = 13});

  @override
  Widget build(BuildContext context) {
    return _Badge(
      icon: riskTierIcon(riskTier),
      text: riskTierLabel(riskTier),
      color: riskTierColor(riskTier),
      iconSize: size,
      fontSize: size,
    );
  }
}

// ---------------------------------------------------------------------------
// Shared flat badge: single Icon + single Text, color as label + icon tint,
// light fill of the same color, r=8 corners, no nested cards.
// ---------------------------------------------------------------------------

class _Badge extends StatelessWidget {
  final IconData icon;
  final String text;
  final Color color;
  final double iconSize;
  final double fontSize;

  const _Badge({
    required this.icon,
    required this.text,
    required this.color,
    required this.iconSize,
    required this.fontSize,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.18),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: color, width: 1),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, color: color, size: iconSize),
          const SizedBox(width: 6),
          Flexible(
            child: Text(
              text,
              style: TextStyle(
                color: color,
                fontWeight: FontWeight.w600,
                fontSize: fontSize,
              ),
              overflow: TextOverflow.ellipsis,
              maxLines: 2,
            ),
          ),
        ],
      ),
    );
  }
}
