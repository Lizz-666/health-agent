// app/lib/widgets/body_region_button.dart
import 'package:flutter/material.dart';
import '../core/constants.dart';

class BodyRegionButton extends StatelessWidget {
  final String label;
  final IconData icon;
  final VoidCallback onTap;

  const BodyRegionButton({
    super.key,
    required this.label,
    required this.icon,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.all(20),
        decoration: BoxDecoration(
          color: const Color(AppConstants.cardColor),
          borderRadius: BorderRadius.circular(16),
          border: Border.all(color: const Color(0xFF0F3460), width: 1),
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(icon, size: 36, color: const Color(AppConstants.accentColor)),
            const SizedBox(height: 8),
            Text(label, style: const TextStyle(fontSize: 14, color: Color(0xFFEAEAEA))),
          ],
        ),
      ),
    );
  }
}
