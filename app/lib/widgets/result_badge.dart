// app/lib/widgets/result_badge.dart
import 'package:flutter/material.dart';
import '../core/constants.dart';

class ResultBadge extends StatelessWidget {
  final String result;
  final double size;

  const ResultBadge({super.key, required this.result, this.size = 16});

  Color get color {
    switch (result) {
      case 'normal':
        return const Color(AppConstants.normalColor);
      case 'moderate':
        return const Color(AppConstants.moderateColor);
      case 'severe':
        return const Color(AppConstants.severeColor);
      default:
        return const Color(0xFF8892B0);
    }
  }

  IconData get icon {
    switch (result) {
      case 'normal':
        return Icons.check_circle;
      case 'moderate':
        return Icons.warning_amber;
      case 'severe':
        return Icons.cancel;
      default:
        return Icons.help_outline;
    }
  }

  String get label {
    switch (result) {
      case 'normal':
        return '正常';
      case 'moderate':
        return '需关注';
      case 'severe':
        return '严重';
      default:
        return '未知';
    }
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.2),
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: color, width: 1),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, color: color, size: size),
          const SizedBox(width: 6),
          Text(
            label,
            style: TextStyle(
              color: color,
              fontWeight: FontWeight.bold,
              fontSize: size,
            ),
          ),
        ],
      ),
    );
  }
}
