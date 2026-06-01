// app/lib/widgets/disclaimer_banner.dart
import 'package:flutter/material.dart';

class DisclaimerBanner extends StatelessWidget {
  const DisclaimerBanner({super.key});

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
      color: const Color(0xFF16213E),
      child: const Text(
        '本内容仅供参考，不能替代专业医疗诊断。如有不适请及时就医。',
        textAlign: TextAlign.center,
        style: TextStyle(color: Color(0xFF8892B0), fontSize: 12),
      ),
    );
  }
}
