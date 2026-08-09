// app/lib/screens/auth/login_screen.dart
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../core/constants.dart';
import '../../providers/auth_provider.dart';

class LoginScreen extends ConsumerStatefulWidget {
  const LoginScreen({super.key});

  @override
  ConsumerState<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends ConsumerState<LoginScreen> {
  final _phoneController = TextEditingController();
  final _codeController = TextEditingController();

  @override
  void dispose() {
    _phoneController.dispose();
    _codeController.dispose();
    super.dispose();
  }

  Future<void> _sendCode() async {
    final phone = _phoneController.text.trim();
    if (phone.length != 11 || !RegExp(r'^1[3-9]\d{9}$').hasMatch(phone)) {
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(const SnackBar(content: Text('请输入正确的手机号')));
      return;
    }
    await ref.read(authProvider.notifier).sendCode(phone);
  }

  Future<void> _login() async {
    final phone = _phoneController.text.trim();
    final code = _codeController.text.trim();
    if (code.length < 4) {
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(const SnackBar(content: Text('请输入验证码')));
      return;
    }
    final ok = await ref.read(authProvider.notifier).login(phone, code);
    if (ok && mounted) {
      final state = ref.read(authProvider);
      if (state.isNewUser) {
        context.go('/onboarding');
      } else {
        context.go('/today');
      }
    }
  }

  Future<void> _devLogin() async {
    final ok = await ref
        .read(authProvider.notifier)
        .devLogin(AppConstants.devAdminPhone, AppConstants.devAdminPassword);
    if (ok && mounted) {
      final state = ref.read(authProvider);
      if (state.isNewUser) {
        context.go('/onboarding');
      } else {
        context.go('/today');
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final state = ref.watch(authProvider);
    return Scaffold(
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(32),
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                const Icon(
                  Icons.accessibility_new,
                  size: 80,
                  color: Color(0xFFE94560),
                ),
                const SizedBox(height: 16),
                const Text(
                  '体态分析',
                  style: TextStyle(fontSize: 28, fontWeight: FontWeight.bold),
                ),
                const SizedBox(height: 8),
                const Text(
                  '了解你的身体，科学改善体态',
                  style: TextStyle(color: Color(0xFF8892B0)),
                ),
                const SizedBox(height: 48),
                TextField(
                  key: const Key('login-phone-input'),
                  controller: _phoneController,
                  keyboardType: TextInputType.phone,
                  maxLength: 11,
                  decoration: const InputDecoration(
                    labelText: '手机号',
                    counterText: '',
                  ),
                ),
                const SizedBox(height: 16),
                Row(
                  children: [
                    Expanded(
                      child: TextField(
                        key: const Key('login-code-input'),
                        controller: _codeController,
                        keyboardType: TextInputType.number,
                        maxLength: 6,
                        decoration: const InputDecoration(
                          labelText: '验证码',
                          counterText: '',
                        ),
                      ),
                    ),
                    const SizedBox(width: 12),
                    SizedBox(
                      width: 120,
                      height: 48,
                      child: ElevatedButton(
                        key: const Key('login-send-code'),
                        onPressed: state.countdown > 0 || state.isLoading
                            ? null
                            : _sendCode,
                        style: ElevatedButton.styleFrom(
                          backgroundColor: const Color(0xFF0F3460),
                        ),
                        child: Text(
                          state.countdown > 0 ? '${state.countdown}s' : '发送验证码',
                          style: const TextStyle(fontSize: 13),
                        ),
                      ),
                    ),
                  ],
                ),
                if (state.error != null) ...[
                  const SizedBox(height: 12),
                  Text(
                    state.error!,
                    style: const TextStyle(color: Color(0xFFFF1744)),
                  ),
                ],
                const SizedBox(height: 24),
                SizedBox(
                  width: double.infinity,
                  height: 52,
                  child: ElevatedButton(
                    key: const Key('login-submit'),
                    onPressed: state.isLoading ? null : _login,
                    child: state.isLoading
                        ? const SizedBox(
                            width: 24,
                            height: 24,
                            child: CircularProgressIndicator(strokeWidth: 2),
                          )
                        : const Text('登录', style: TextStyle(fontSize: 18)),
                  ),
                ),
                const SizedBox(height: 24),
                const Text(
                  '首次验证将自动注册账号',
                  style: TextStyle(color: Color(0xFF8892B0), fontSize: 13),
                ),
                if (AppConstants.devAdminPhone.isNotEmpty &&
                    AppConstants.devAdminPassword.isNotEmpty) ...[
                  const SizedBox(height: 32),
                  const Divider(),
                  const SizedBox(height: 8),
                  const Text(
                    '开发环境',
                    style: TextStyle(color: Color(0xFF8892B0), fontSize: 12),
                  ),
                  const SizedBox(height: 8),
                  SizedBox(
                    width: double.infinity,
                    height: 44,
                    child: OutlinedButton(
                      key: const Key('login-dev-submit'),
                      onPressed: state.isLoading ? null : _devLogin,
                      style: OutlinedButton.styleFrom(
                        side: const BorderSide(color: Color(0xFF0F3460)),
                      ),
                      child: const Text(
                        '管理员快捷登录',
                        style: TextStyle(fontSize: 14),
                      ),
                    ),
                  ),
                ],
              ],
            ),
          ),
        ),
      ),
    );
  }
}
