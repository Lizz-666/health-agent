// app/lib/screens/onboarding/onboarding_screen.dart
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../providers/user_provider.dart';

class OnboardingScreen extends ConsumerStatefulWidget {
  const OnboardingScreen({super.key});
  @override
  ConsumerState<OnboardingScreen> createState() => _OnboardingScreenState();
}

class _OnboardingScreenState extends ConsumerState<OnboardingScreen> {
  final _pageController = PageController();
  int _currentPage = 0;
  double _height = 170;
  double _weight = 65;
  int _age = 25;
  String? _gender;
  String? _nickname;

  void _next() {
    if (_currentPage < 3) {
      _pageController.nextPage(duration: const Duration(milliseconds: 300), curve: Curves.easeInOut);
    }
  }

  Future<void> _finish() async {
    final ok = await ref.read(userProvider.notifier).updateProfile(
      height: _height, weight: _weight, age: _age, gender: _gender, nickname: _nickname);
    if (ok && mounted) context.go('/');
  }

  Future<void> _skip() async {
    if (mounted) context.go('/');
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: SafeArea(
        child: Column(
          children: [
            LinearProgressIndicator(value: (_currentPage + 1) / 5),
            Expanded(
              child: PageView(
                controller: _pageController,
                onPageChanged: (i) => setState(() => _currentPage = i),
                children: [
                  _buildSliderPage('你的身高？', 'cm', _height, 100, 220,
                      (v) => _height = v, Icons.height),
                  _buildSliderPage('你的体重？', 'kg', _weight, 30, 200,
                      (v) => _weight = v, Icons.monitor_weight_outlined),
                  _buildNumberPage('你的年龄？', _age, 13, 120,
                      (v) => _age = v),
                  _buildGenderPage(),
                ],
              ),
            ),
            Padding(
              padding: const EdgeInsets.all(24),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  TextButton(onPressed: _skip, child: const Text('稍后完善')),
                  Row(
                    children: List.generate(5, (i) => Container(
                      margin: const EdgeInsets.symmetric(horizontal: 4),
                      width: 8, height: 8,
                      decoration: BoxDecoration(
                        shape: BoxShape.circle,
                        color: i == _currentPage ? const Color(0xFFE94560) : const Color(0xFF0F3460),
                      ),
                    )),
                  ),
                  _currentPage < 3
                      ? ElevatedButton(onPressed: _next, child: const Text('下一步'))
                      : ElevatedButton(onPressed: _finish, child: const Text('完成')),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildSliderPage(String title, String unit, double value, double min,
      double max, ValueChanged<double> onChanged, IconData icon) {
    return Padding(
      padding: const EdgeInsets.all(32),
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Icon(icon, size: 64, color: const Color(0xFFE94560)),
          const SizedBox(height: 24),
          Text(title, style: const TextStyle(fontSize: 24, fontWeight: FontWeight.bold)),
          const SizedBox(height: 8),
          Text('${value.toInt()} $unit',
              style: const TextStyle(fontSize: 32, color: Color(0xFFE94560))),
          Slider(value: value, min: min, max: max, onChanged: onChanged),
          Text(
            unit == 'cm' ? '范围: ${min.toInt()}-${max.toInt()}cm' : '范围: ${min.toInt()}-${max.toInt()}kg',
            style: const TextStyle(color: Color(0xFF8892B0)),
          ),
        ],
      ),
    );
  }

  Widget _buildNumberPage(String title, int value, int min, int max, ValueChanged<int> onChanged) {
    return Padding(
      padding: const EdgeInsets.all(32),
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          const Icon(Icons.calendar_today, size: 64, color: Color(0xFFE94560)),
          const SizedBox(height: 24),
          Text(title, style: const TextStyle(fontSize: 24, fontWeight: FontWeight.bold)),
          const SizedBox(height: 8),
          Text('$value 岁', style: const TextStyle(fontSize: 32, color: Color(0xFFE94560))),
          Slider(value: value.toDouble(), min: min.toDouble(), max: max.toDouble(),
              onChanged: (v) => onChanged(v.toInt())),
        ],
      ),
    );
  }

  Widget _buildGenderPage() {
    return Padding(
      padding: const EdgeInsets.all(32),
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          const Icon(Icons.person, size: 64, color: Color(0xFFE94560)),
          const SizedBox(height: 24),
          const Text('你的性别？', style: TextStyle(fontSize: 24, fontWeight: FontWeight.bold)),
          const SizedBox(height: 32),
          Row(
            children: [
              Expanded(
                child: _genderCard('男', 'male', Icons.male),
              ),
              const SizedBox(width: 16),
              Expanded(
                child: _genderCard('女', 'female', Icons.female),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _genderCard(String label, String value, IconData icon) {
    final selected = _gender == value;
    return GestureDetector(
      onTap: () => setState(() => _gender = value),
      child: Container(
        padding: const EdgeInsets.all(24),
        decoration: BoxDecoration(
          color: selected ? const Color(0xFFE94560) : const Color(0xFF16213E),
          borderRadius: BorderRadius.circular(16),
          border: Border.all(color: selected ? const Color(0xFFE94560) : const Color(0xFF0F3460), width: 2),
        ),
        child: Column(
          children: [
            Icon(icon, size: 48, color: Colors.white),
            const SizedBox(height: 8),
            Text(label, style: const TextStyle(fontSize: 20)),
          ],
        ),
      ),
    );
  }

  @override
  void dispose() {
    _pageController.dispose();
    super.dispose();
  }
}
