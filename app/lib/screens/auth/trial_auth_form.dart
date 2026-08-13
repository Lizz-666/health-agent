import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/constants.dart';
import '../../providers/auth_provider.dart';

enum TrialAuthAction { activate, login }

class TrialAuthScreen extends ConsumerStatefulWidget {
  const TrialAuthScreen({super.key});

  @override
  ConsumerState<TrialAuthScreen> createState() => _TrialAuthScreenState();
}

class _TrialAuthScreenState extends ConsumerState<TrialAuthScreen> {
  final _accountController = TextEditingController();
  final _credentialController = TextEditingController();
  final _invitationController = TextEditingController();
  TrialAuthAction _action = TrialAuthAction.activate;

  @override
  void dispose() {
    _accountController.dispose();
    _credentialController.dispose();
    _invitationController.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    final account = _accountController.text.trim();
    final credential = _credentialController.text;
    final invitation = _invitationController.text.trim();
    if (account.length < 4 || credential.length < 6) {
      _showError('请输入有效的内测账号和凭据');
      return;
    }
    if (_action == TrialAuthAction.activate && invitation.length < 32) {
      _showError('请输入有效的邀请码');
      return;
    }
    await ref
        .read(authProvider.notifier)
        .trialAuthenticate(
          activate: _action == TrialAuthAction.activate,
          accountName: account,
          credential: credential,
          invitationCode: invitation,
        );
  }

  void _showError(String message) {
    ScaffoldMessenger.of(
      context,
    ).showSnackBar(SnackBar(content: Text(message)));
  }

  @override
  Widget build(BuildContext context) {
    final state = ref.watch(authProvider);
    final activating = _action == TrialAuthAction.activate;
    return Scaffold(
      appBar: AppBar(title: const Text('受控内测')),
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(24),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 480),
              child: AutofillGroup(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    const Icon(Icons.verified_user_outlined, size: 56),
                    const SizedBox(height: 24),
                    SegmentedButton<TrialAuthAction>(
                      key: const Key('trial-auth-action'),
                      segments: const [
                        ButtonSegment(
                          value: TrialAuthAction.activate,
                          icon: Icon(Icons.key_outlined),
                          label: Text('激活'),
                        ),
                        ButtonSegment(
                          value: TrialAuthAction.login,
                          icon: Icon(Icons.login),
                          label: Text('登录'),
                        ),
                      ],
                      selected: {_action},
                      onSelectionChanged: state.isLoading
                          ? null
                          : (selection) {
                              setState(() => _action = selection.first);
                            },
                    ),
                    const SizedBox(height: 24),
                    TextField(
                      key: const Key('trial-account-input'),
                      controller: _accountController,
                      textInputAction: TextInputAction.next,
                      autofillHints: const [AutofillHints.username],
                      decoration: const InputDecoration(
                        labelText: '内测账号',
                        prefixIcon: Icon(Icons.person_outline),
                      ),
                    ),
                    if (activating) ...[
                      const SizedBox(height: 16),
                      TextField(
                        key: const Key('trial-invitation-input'),
                        controller: _invitationController,
                        textInputAction: TextInputAction.next,
                        autocorrect: false,
                        decoration: const InputDecoration(
                          labelText: '邀请码',
                          prefixIcon: Icon(Icons.vpn_key_outlined),
                        ),
                      ),
                    ],
                    const SizedBox(height: 16),
                    TextField(
                      key: const Key('trial-credential-input'),
                      controller: _credentialController,
                      obscureText: true,
                      enableSuggestions: false,
                      autocorrect: false,
                      autofillHints: const [AutofillHints.password],
                      onSubmitted: state.isLoading ? null : (_) => _submit(),
                      decoration: const InputDecoration(
                        labelText: '内测凭据',
                        prefixIcon: Icon(Icons.password),
                      ),
                    ),
                    if (state.error != null) ...[
                      const SizedBox(height: 12),
                      Semantics(
                        key: const Key('trial-auth-error-live'),
                        liveRegion: true,
                        label: '内测认证失败，请检查账号、凭据、邀请码和网络后重试。',
                        excludeSemantics: true,
                        child: const Text(
                          '内测认证失败，请检查账号、凭据、邀请码和网络后重试。',
                          style: TextStyle(
                            color: Color(AppConstants.severeColor),
                          ),
                        ),
                      ),
                    ],
                    const SizedBox(height: 24),
                    SizedBox(
                      height: 52,
                      child: Semantics(
                        excludeSemantics: true,
                        button: true,
                        enabled: !state.isLoading,
                        onTap: state.isLoading ? null : _submit,
                        label: state.isLoading
                            ? (activating ? '激活中，请稍候' : '登录中，请稍候')
                            : (activating ? '激活账号' : '登录'),
                        child: FilledButton.icon(
                          key: const Key('trial-auth-submit'),
                          onPressed: state.isLoading ? null : _submit,
                          icon: state.isLoading
                              ? const SizedBox.square(
                                  dimension: 20,
                                  child: CircularProgressIndicator(
                                    strokeWidth: 2,
                                  ),
                                )
                              : Icon(
                                  activating ? Icons.key_outlined : Icons.login,
                                ),
                          label: Text(activating ? '激活账号' : '登录'),
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}
