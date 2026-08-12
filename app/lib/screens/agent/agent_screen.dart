import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../models/agent.dart';
import '../../providers/agent_provider.dart';

class AgentScreen extends ConsumerStatefulWidget {
  const AgentScreen({super.key, required this.routeContext});

  /// Null means route parsing failed. In that case no Agent API is called.
  final AgentRouteContext? routeContext;

  @override
  ConsumerState<AgentScreen> createState() => _AgentScreenState();
}

class _AgentScreenState extends ConsumerState<AgentScreen> {
  final _messageController = TextEditingController();
  final _scrollController = ScrollController();
  String? _acceptedDisclosureBoundary;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _initialize());
  }

  @override
  void didUpdateWidget(covariant AgentScreen oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.routeContext != widget.routeContext) {
      WidgetsBinding.instance.addPostFrameCallback((_) => _initialize());
    }
  }

  void _initialize() {
    if (!mounted || widget.routeContext == null) return;
    final notifier = ref.read(agentProvider.notifier);
    notifier.setContext(widget.routeContext!);
    final status = ref.read(agentProvider).capabilitiesStatus;
    if (status == AgentLoadStatus.idle || status == AgentLoadStatus.loading) {
      notifier.loadCapabilities();
    }
  }

  @override
  void dispose() {
    _messageController.dispose();
    _scrollController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    if (widget.routeContext == null) {
      return Scaffold(
        appBar: AppBar(title: const Text('健康助手')),
        body: _CenteredState(
          icon: Icons.link_off,
          title: '健康助手入口无效',
          message: '上下文参数无法识别，未请求或发送任何健康数据。',
          actionLabel: '返回健康助手首页',
          onAction: () => context.go('/agent'),
        ),
      );
    }

    final state = ref.watch(agentProvider);
    return Scaffold(
      appBar: AppBar(
        title: const Text('健康助手'),
        actions: [
          PopupMenuButton<String>(
            key: const Key('agent-privacy-menu'),
            onSelected: (value) => _handleMenu(value, state),
            itemBuilder: (_) => [
              const PopupMenuItem(value: 'clear', child: Text('清除本地对话')),
              if (state.capabilities?.consentActive == true)
                const PopupMenuItem(value: 'withdraw', child: Text('撤回云端处理同意')),
              const PopupMenuItem(value: 'delete', child: Text('删除健康助手数据')),
            ],
          ),
        ],
      ),
      body: SafeArea(child: _body(state)),
    );
  }

  Widget _body(AgentState state) {
    switch (state.capabilitiesStatus) {
      case AgentLoadStatus.idle:
      case AgentLoadStatus.loading:
        return const _CenteredState(
          icon: Icons.auto_awesome_outlined,
          title: '检查健康助手可用状态',
          message: '不会在条件确认前调用云端模型。',
          loading: true,
        );
      case AgentLoadStatus.networkError:
        return _CenteredState(
          icon: Icons.cloud_off_outlined,
          title: '健康助手服务不可用',
          message: '无法连接健康助手服务，未执行任何操作。',
          actionLabel: '重试',
          onAction: () => ref.read(agentProvider.notifier).loadCapabilities(),
        );
      case AgentLoadStatus.parseError:
        return _CenteredState(
          icon: Icons.warning_amber_outlined,
          title: '健康助手响应无法验证',
          message: '响应格式异常，未执行任何操作。',
          actionLabel: '重试',
          onAction: () => ref.read(agentProvider.notifier).loadCapabilities(),
        );
      case AgentLoadStatus.unavailable:
        final capabilities = state.capabilities;
        if (capabilities?.resultCode == 'agent_consent_required' &&
            capabilities?.disclosure != null) {
          return _consentView(state, capabilities!.disclosure!);
        }
        return _CenteredState(
          icon: Icons.pause_circle_outline,
          title: '健康助手当前不可用',
          message: _capabilityMessage(capabilities?.resultCode),
          secondaryLabel: '查看体态工具',
          onSecondary: () => context.push('/posture'),
          actionLabel: '刷新状态',
          onAction: () => ref.read(agentProvider.notifier).loadCapabilities(),
        );
      case AgentLoadStatus.ready:
        return _conversationView(state);
    }
  }

  Widget _consentView(AgentState state, AgentDisclosure disclosure) {
    final boundary = state.capabilities!.boundaryId;
    final accepted = _acceptedDisclosureBoundary == boundary;
    return ListView(
      key: const Key('agent-consent-view'),
      padding: const EdgeInsets.all(16),
      children: [
        const Icon(Icons.privacy_tip_outlined, size: 48),
        const SizedBox(height: 12),
        Text('云端健康助手使用告知', style: Theme.of(context).textTheme.titleLarge),
        const SizedBox(height: 12),
        _InfoRow(label: '服务提供方', value: disclosure.providerNameZh),
        _InfoRow(label: '用途', value: _disclosureLabel(disclosure.purposeCode)),
        _InfoRow(
          label: '处理边界',
          value: _disclosureLabel(disclosure.processingBoundaryCode),
        ),
        _InfoRow(
          label: '发送范围',
          value: disclosure.dataScopeCodes.map(_disclosureLabel).join('、'),
        ),
        _InfoRow(
          label: '应用内留存',
          value: _disclosureLabel(disclosure.applicationRetentionCode),
        ),
        const SizedBox(height: 12),
        const Text(
          '健康助手仅用于一般健康与训练执行辅助，不提供医学诊断或治疗。'
          '你可以随时撤回同意或删除健康助手数据；聊天文本仅保存在当前应用内存中。',
        ),
        const SizedBox(height: 12),
        CheckboxListTile(
          key: const Key('agent-consent-checkbox'),
          value: accepted,
          contentPadding: EdgeInsets.zero,
          title: const Text('我已阅读并同意当前服务提供方和处理范围'),
          onChanged: state.busy
              ? null
              : (value) => setState(
                  () => _acceptedDisclosureBoundary = value == true
                      ? boundary
                      : null,
                ),
        ),
        if (state.errorMessage != null)
          _InlineError(_agentErrorMessage(state.errorCode)),
        const SizedBox(height: 8),
        Semantics(
          excludeSemantics: true,
          button: true,
          enabled: accepted && !state.busy,
          label: '同意并启用健康助手',
          onTap: accepted && !state.busy ? _grantConsent : null,
          child: FilledButton(
            key: const Key('agent-consent-grant'),
            onPressed: !accepted || state.busy ? null : _grantConsent,
            child: state.busy
                ? const SizedBox.square(
                    dimension: 20,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  )
                : const Text('同意并启用健康助手'),
          ),
        ),
        TextButton(
          onPressed: () => context.push('/posture'),
          child: const Text('暂不使用，查看体态工具'),
        ),
      ],
    );
  }

  Widget _conversationView(AgentState state) {
    final disclosure = state.capabilities!.disclosure;
    return Column(
      children: [
        MaterialBanner(
          leading: const Icon(Icons.auto_awesome_outlined),
          content: Text(
            'AI 辅助解释 · ${disclosure?.providerNameZh ?? "云端服务"}。'
            '安全判断与写入权限由服务器确定。',
            style: const TextStyle(fontSize: 12),
          ),
          actions: [
            TextButton(
              onPressed: () => _showDisclosure(disclosure),
              child: const Text('查看告知'),
            ),
          ],
        ),
        Expanded(
          child: ListView(
            key: const Key('agent-conversation'),
            controller: _scrollController,
            padding: const EdgeInsets.all(16),
            children: [
              if (state.context.entryType != AgentEntryType.general)
                _ContextCard(context: state.context),
              if (state.messages.isEmpty) ...[
                _QuickActions(onSelected: _quickAction),
                const SizedBox(height: 12),
              ],
              for (final item in state.messages) _MessageCard(item: item),
              if (state.pendingProposal != null)
                _ProposalCard(
                  proposal: state.pendingProposal!,
                  busy: state.busy,
                  onConfirm: () =>
                      ref.read(agentProvider.notifier).confirmProposal(),
                  onCancel: () =>
                      ref.read(agentProvider.notifier).cancelProposal(),
                ),
              if (state.errorMessage != null) ...[
                _InlineError(_agentErrorMessage(state.errorCode)),
                if (state.canRetry)
                  Align(
                    alignment: Alignment.centerLeft,
                    child: OutlinedButton.icon(
                      key: const Key('agent-retry-turn'),
                      onPressed: state.busy
                          ? null
                          : () => ref
                                .read(agentProvider.notifier)
                                .retryLastTurn(),
                      icon: const Icon(Icons.refresh),
                      label: const Text('明确重试'),
                    ),
                  ),
              ],
              if (state.busy)
                const Padding(
                  padding: EdgeInsets.all(16),
                  child: Center(child: CircularProgressIndicator()),
                ),
            ],
          ),
        ),
        _Composer(
          controller: _messageController,
          enabled: !state.busy && state.pendingProposal == null,
          onSend: _send,
        ),
      ],
    );
  }

  Future<void> _send() async {
    final message = _messageController.text;
    if (message.trim().isEmpty) return;
    final accepted = await ref
        .read(agentProvider.notifier)
        .sendMessage(message);
    if (accepted && mounted) {
      _messageController.clear();
      _scrollToBottom();
    }
  }

  Future<void> _grantConsent() async {
    setState(() => _acceptedDisclosureBoundary = null);
    await ref.read(agentProvider.notifier).grantConsent();
  }

  Future<void> _quickAction(String action) async {
    switch (action) {
      case 'posture':
        context.push('/posture');
        return;
      case 'today':
        await ref.read(agentProvider.notifier).sendMessage('请读取今天的训练安排。');
        break;
      case 'health':
        ref
            .read(agentProvider.notifier)
            .setContext(
              const AgentRouteContext(entryType: AgentEntryType.healthProfile),
            );
        await ref.read(agentProvider.notifier).sendMessage('请读取当前健康档案摘要。');
        break;
      case 'plan':
        await ref.read(agentProvider.notifier).sendMessage('请帮我准备一个训练计划草案。');
        break;
    }
    _scrollToBottom();
  }

  void _scrollToBottom() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!_scrollController.hasClients) return;
      _scrollController.animateTo(
        _scrollController.position.maxScrollExtent,
        duration: const Duration(milliseconds: 200),
        curve: Curves.easeOut,
      );
    });
  }

  Future<void> _handleMenu(String value, AgentState state) async {
    if (value == 'clear') {
      ref.read(agentProvider.notifier).clearConversation();
      return;
    }
    if (value == 'withdraw') {
      final confirmed = await _confirmDialog(
        title: '撤回云端处理同意？',
        body: '撤回后会立即清除本地对话并阻止新的云端健康助手调用。',
        confirmText: '撤回同意',
      );
      if (confirmed) {
        await ref.read(agentProvider.notifier).withdrawConsent();
      }
      return;
    }
    if (value == 'delete') {
      final confirmed = await _confirmDialog(
        title: '删除健康助手数据？',
        body: '将删除健康助手同意、审计和待确认提案，但不会删除健康、体态或训练记录。',
        confirmText: '删除健康助手数据',
      );
      if (confirmed) {
        await ref.read(agentProvider.notifier).deleteAgentData();
      }
    }
  }

  Future<bool> _confirmDialog({
    required String title,
    required String body,
    required String confirmText,
  }) async {
    return await showDialog<bool>(
          context: context,
          builder: (dialogContext) => AlertDialog(
            title: Text(title),
            content: Text(body),
            actions: [
              TextButton(
                onPressed: () => Navigator.pop(dialogContext, false),
                child: const Text('取消'),
              ),
              FilledButton(
                onPressed: () => Navigator.pop(dialogContext, true),
                child: Text(confirmText),
              ),
            ],
          ),
        ) ??
        false;
  }

  void _showDisclosure(AgentDisclosure? disclosure) {
    showDialog<void>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: const Text('健康助手服务告知'),
        content: Text(
          disclosure == null
              ? '当前服务告知不可用。'
              : '提供方：${disclosure.providerNameZh}\n'
                    '用途：${_disclosureLabel(disclosure.purposeCode)}\n'
                    '发送范围：${disclosure.dataScopeCodes.map(_disclosureLabel).join("、")}\n'
                    '聊天文本仅保存在当前应用内存中。',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(dialogContext),
            child: const Text('知道了'),
          ),
        ],
      ),
    );
  }
}

class _ContextCard extends StatelessWidget {
  const _ContextCard({required this.context});
  final AgentRouteContext context;

  @override
  Widget build(BuildContext context) {
    return Card(
      key: const Key('agent-context-card'),
      child: ListTile(
        leading: const Icon(Icons.link),
        title: Text(_entryLabel(this.context.entryType)),
        subtitle: const Text('使用当前已授权的上下文，不显示内部标识。'),
      ),
    );
  }
}

class _QuickActions extends StatelessWidget {
  const _QuickActions({required this.onSelected});
  final ValueChanged<String> onSelected;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('快捷入口', style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: 8),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: [
                ActionChip(
                  key: const Key('agent-quick-today'),
                  label: const Text('今天练什么'),
                  onPressed: () => onSelected('today'),
                ),
                ActionChip(
                  key: const Key('agent-quick-health'),
                  label: const Text('健康档案摘要'),
                  onPressed: () => onSelected('health'),
                ),
                ActionChip(
                  key: const Key('agent-quick-plan'),
                  label: const Text('准备计划草案'),
                  onPressed: () => onSelected('plan'),
                ),
                ActionChip(
                  key: const Key('agent-quick-posture'),
                  label: const Text('查看体态工具'),
                  onPressed: () => onSelected('posture'),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

class _MessageCard extends StatelessWidget {
  const _MessageCard({required this.item});
  final AgentConversationItem item;

  @override
  Widget build(BuildContext context) {
    final user = item.role == AgentConversationRole.user;
    final action = item.role == AgentConversationRole.action;
    return Align(
      alignment: user ? Alignment.centerRight : Alignment.centerLeft,
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 560),
        child: Card(
          color: user
              ? Theme.of(context).colorScheme.primaryContainer
              : action
              ? Theme.of(context).colorScheme.secondaryContainer
              : null,
          child: Padding(
            padding: const EdgeInsets.all(12),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(item.text),
                if (item.turn != null) ...[
                  const SizedBox(height: 6),
                  for (final display in item.turn!.displayData)
                    _ToolDisplayCard(display: display),
                ],
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _ToolDisplayCard extends StatelessWidget {
  const _ToolDisplayCard({required this.display});
  final AgentToolDisplay display;

  @override
  Widget build(BuildContext context) {
    final rows = <MapEntry<String, String>>[];
    _flatten(display.data, '', rows);
    final visibleRows = rows
        .where((row) => _isVisibleToolField(row.key))
        .take(24);
    return Container(
      margin: const EdgeInsets.only(top: 8),
      padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(
        border: Border.all(color: Theme.of(context).dividerColor),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            _toolLabel(display.toolName),
            style: const TextStyle(fontWeight: FontWeight.w600),
          ),
          const SizedBox(height: 4),
          if (visibleRows.isEmpty) const Text('暂无可展示的结构化数据'),
          for (final row in visibleRows)
            Text(
              '${_toolFieldLabel(row.key)}：${_toolFieldValue(row.value)}',
              style: const TextStyle(fontSize: 12),
            ),
        ],
      ),
    );
  }
}

class _ProposalCard extends StatelessWidget {
  const _ProposalCard({
    required this.proposal,
    required this.busy,
    required this.onConfirm,
    required this.onCancel,
  });

  final AgentProposal proposal;
  final bool busy;
  final VoidCallback onConfirm;
  final VoidCallback onCancel;

  @override
  Widget build(BuildContext context) {
    return Card(
      key: const Key('agent-proposal-card'),
      color: Theme.of(context).colorScheme.tertiaryContainer,
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              '待确认：${_actionLabel(proposal.action)}',
              style: Theme.of(context).textTheme.titleMedium,
            ),
            const SizedBox(height: 4),
            const Text('尚未执行。确认时服务器会重新检查最新权限、安全状态和上下文。'),
            const Divider(),
            for (final row in _proposalRows(proposal.diff))
              _InfoRow(label: row.key, value: row.value),
            Text(
              '有效期至 ${proposal.expiresAt.toLocal()}',
              style: Theme.of(context).textTheme.labelSmall,
            ),
            const SizedBox(height: 12),
            Row(
              children: [
                Expanded(
                  child: OutlinedButton(
                    key: const Key('agent-proposal-cancel'),
                    onPressed: busy ? null : onCancel,
                    child: const Text('取消'),
                  ),
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: FilledButton(
                    key: const Key('agent-proposal-confirm'),
                    onPressed: busy ? null : onConfirm,
                    child: const Text('确认执行'),
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

class _Composer extends StatelessWidget {
  const _Composer({
    required this.controller,
    required this.enabled,
    required this.onSend,
  });

  final TextEditingController controller;
  final bool enabled;
  final VoidCallback onSend;

  @override
  Widget build(BuildContext context) {
    return Material(
      elevation: 4,
      child: Padding(
        padding: const EdgeInsets.fromLTRB(12, 8, 12, 12),
        child: Row(
          children: [
            Expanded(
              child: TextField(
                key: const Key('agent-message-input'),
                controller: controller,
                enabled: enabled,
                minLines: 1,
                maxLines: 4,
                maxLength: 2000,
                decoration: InputDecoration(
                  hintText: enabled ? '输入一般健康或训练问题' : '请先处理待确认操作',
                  counterText: '',
                ),
                onSubmitted: enabled ? (_) => onSend() : null,
              ),
            ),
            const SizedBox(width: 8),
            Semantics(
              excludeSemantics: true,
              button: true,
              enabled: enabled,
              label: '发送消息',
              onTap: enabled ? onSend : null,
              child: IconButton.filled(
                key: const Key('agent-send'),
                onPressed: enabled ? onSend : null,
                icon: const Icon(Icons.send),
                tooltip: '发送',
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _CenteredState extends StatelessWidget {
  const _CenteredState({
    required this.icon,
    required this.title,
    required this.message,
    this.loading = false,
    this.actionLabel,
    this.onAction,
    this.secondaryLabel,
    this.onSecondary,
  });

  final IconData icon;
  final String title;
  final String message;
  final bool loading;
  final String? actionLabel;
  final VoidCallback? onAction;
  final String? secondaryLabel;
  final VoidCallback? onSecondary;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      key: const Key('agent-status-live'),
      liveRegion: true,
      child: Center(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(icon, size: 52),
              const SizedBox(height: 12),
              Text(title, style: Theme.of(context).textTheme.titleLarge),
              const SizedBox(height: 8),
              Text(message, textAlign: TextAlign.center),
              if (loading) ...[
                const SizedBox(height: 16),
                const CircularProgressIndicator(),
              ],
              if (actionLabel != null && onAction != null) ...[
                const SizedBox(height: 16),
                FilledButton(onPressed: onAction, child: Text(actionLabel!)),
              ],
              if (secondaryLabel != null && onSecondary != null)
                TextButton(
                  onPressed: onSecondary,
                  child: Text(secondaryLabel!),
                ),
            ],
          ),
        ),
      ),
    );
  }
}

class _InlineError extends StatelessWidget {
  const _InlineError(this.message);
  final String message;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      liveRegion: true,
      child: Card(
        color: Theme.of(context).colorScheme.errorContainer,
        child: Padding(
          padding: const EdgeInsets.all(12),
          child: Row(
            children: [
              const Icon(Icons.error_outline, semanticLabel: '错误'),
              const SizedBox(width: 8),
              Expanded(child: Text(message)),
            ],
          ),
        ),
      ),
    );
  }
}

class _InfoRow extends StatelessWidget {
  const _InfoRow({required this.label, required this.value});
  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 3),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(width: 112, child: Text(label)),
          Expanded(child: Text(value)),
        ],
      ),
    );
  }
}

void _flatten(
  Object? value,
  String prefix,
  List<MapEntry<String, String>> rows,
) {
  if (value == null || value is String || value is num || value is bool) {
    rows.add(MapEntry(prefix.isEmpty ? '值' : prefix, value?.toString() ?? '无'));
    return;
  }
  if (value is List) {
    if (value.isEmpty) {
      rows.add(MapEntry(prefix.isEmpty ? '列表' : prefix, '无'));
    } else {
      for (var index = 0; index < value.length && index < 12; index += 1) {
        _flatten(value[index], '$prefix[${index + 1}]', rows);
      }
    }
    return;
  }
  if (value is Map<String, dynamic>) {
    for (final entry in value.entries) {
      final key = prefix.isEmpty ? entry.key : '$prefix.${entry.key}';
      _flatten(entry.value, key, rows);
    }
  }
}

String _entryLabel(AgentEntryType entry) {
  switch (entry) {
    case AgentEntryType.general:
      return '一般对话';
    case AgentEntryType.healthProfile:
      return '当前健康档案';
    case AgentEntryType.postureIssue:
      return '当前体态问题';
    case AgentEntryType.trainingPlan:
      return '当前训练计划';
    case AgentEntryType.trainingSession:
      return '当前训练场次';
    case AgentEntryType.trainingExercise:
      return '当前处方动作';
  }
}

String _actionLabel(AgentActionType action) {
  switch (action) {
    case AgentActionType.upsertTodayCheckin:
      return '记录今日签到';
    case AgentActionType.createWeightRecord:
      return '记录体重';
    case AgentActionType.generateTrainingPlanDraft:
      return '生成训练计划草案';
    case AgentActionType.substituteTodayExercise:
      return '替换今日动作';
    case AgentActionType.recordTrainingFeedback:
      return '记录训练反馈';
  }
}

List<MapEntry<String, String>> _proposalRows(AgentActionDiff diff) {
  final rows = diff.displayRows;
  switch (diff.action) {
    case AgentActionType.generateTrainingPlanDraft:
      return rows
          .map(
            (row) => row.key == '目标'
                ? MapEntry(row.key, _proposalValueLabel(row.value))
                : row,
          )
          .toList(growable: false);
    case AgentActionType.substituteTodayExercise:
      return const [MapEntry('原动作', '当前处方动作'), MapEntry('替代动作', '已验证的候选替代动作')];
    case AgentActionType.recordTrainingFeedback:
      return rows
          .map((row) => MapEntry(row.key, _proposalValueLabel(row.value)))
          .toList(growable: false);
    case AgentActionType.upsertTodayCheckin:
    case AgentActionType.createWeightRecord:
      return rows;
  }
}

String _proposalValueLabel(String value) => switch (value) {
  'posture_improvement' => '体态改善',
  'fat_loss' => '减脂',
  'basic_strength' => '基础力量',
  'general_wellness' => '一般健康',
  'completed' => '已完成',
  'partial' => '部分完成',
  'too_busy' => '太忙未练',
  'intentional_rest' => '主动休息',
  _ => '未识别',
};

String _toolLabel(String tool) {
  const labels = {
    'get_health_profile_summary': '健康档案摘要',
    'get_today_checkin': '今日签到',
    'get_weight_trend_summary': '体重趋势摘要',
    'list_posture_issues': '体态问题目录',
    'get_posture_issue': '体态问题说明',
    'guide_posture_self_test': '体态自测说明',
    'get_posture_profile': '体态档案',
    'get_posture_priorities': '体态优先级',
    'get_training_draft': '训练计划草案',
    'get_active_training_plan': '当前训练计划',
    'get_today_training': '今日训练',
    'get_training_exercise': '当前处方动作',
  };
  return labels[tool] ?? '结构化结果';
}

String _toolFieldLabel(String field) {
  const labels = {
    'configured': '档案已配置',
    'profile_version': '档案版本',
    'readiness_code': '准备状态',
    'risk_version': '安全规则版本',
    'fitness_goal': '训练目标',
    'training_experience': '训练经验',
    'weekly_frequency': '每周频次',
    'session_duration_minutes': '单次时长（分钟）',
    'equipment_bodyweight': '可做自重训练',
    'equipment_resistance_band': '有弹力带',
    'pain_limitation_count': '疼痛/限制项数量',
    'allergies_count': '过敏项数量',
    'diet_exclusions_count': '饮食排除项数量',
    'restricted': '是否受限',
    'state': '今日状态',
    'local_date': '日期',
    'decision_gate': '安全校验',
    'change_reason': '变更原因',
    'session_id': '训练场次',
    'prescription_count': '动作数量',
    'exercise_ids': '动作标识',
    'substitution_applied': '已应用替换',
    'feedback_outcome_state': '完成反馈',
  };
  final indexed = RegExp(r'^(.*)(\[\d+\])$').firstMatch(field);
  final base = indexed?.group(1) ?? field;
  final suffix = indexed?.group(2) ?? '';
  return '${labels[base] ?? '其他信息'}$suffix';
}

String _toolFieldValue(String value) {
  const labels = {
    'true': '是',
    'false': '否',
    'ready': '已就绪',
    'basic_strength': '基础力量',
    'posture_improvement': '体态改善',
    'fat_loss': '减脂',
    'general_wellness': '一般健康',
    'beginner': '初学者',
    'experienced': '有训练经验',
    'session': '有训练安排',
    'rest_day': '休息日',
    'active_rest': '主动休息',
    'plan_complete': '计划已完成',
    'eligible': '已通过',
    'eligible_conservative': '保守条件通过',
    'clarification_required': '需要补充信息',
    'restricted': '受限',
    'red_flag': '已触发安全阻断',
    'null': '无',
  };
  final mapped = labels[value];
  if (mapped != null) return mapped;
  if (RegExp(r'^[a-z][a-z0-9_-]*$').hasMatch(value)) return '未识别';
  return value;
}

bool _isInternalToolField(String field) {
  final base = field.replaceAll(RegExp(r'\[\d+\]'), '').split('.').last;
  return base == 'id' ||
      base.endsWith('_id') ||
      base.endsWith('_ids') ||
      base == 'run_id' ||
      base == 'proposal_id' ||
      base == 'result_ref';
}

bool _isVisibleToolField(String field) {
  if (_isInternalToolField(field)) return false;
  final base = field.replaceAll(RegExp(r'\[\d+\]'), '').split('.').last;
  return const {
    'configured',
    'profile_version',
    'readiness_code',
    'risk_version',
    'fitness_goal',
    'training_experience',
    'weekly_frequency',
    'session_duration_minutes',
    'equipment_bodyweight',
    'equipment_resistance_band',
    'pain_limitation_count',
    'allergies_count',
    'diet_exclusions_count',
    'restricted',
    'state',
    'local_date',
    'decision_gate',
    'change_reason',
    'prescription_count',
    'substitution_applied',
    'feedback_outcome_state',
  }.contains(base);
}

String _capabilityMessage(String? code) => switch (code) {
  'agent_disabled' => '健康助手当前未启用，其他功能仍可正常使用。',
  'agent_privacy_gate_blocked' => '当前隐私条件未满足，健康助手保持关闭。',
  'agent_provider_unavailable' => '云端服务当前不可用，健康助手保持关闭。',
  _ => '健康助手当前不可用，未发送健康数据，也未执行任何操作。',
};

String _agentErrorMessage(String? code) => switch (code) {
  'agent_disclosure_stale' => '服务信息已更新，请重新阅读当前告知。',
  'agent_request_invalid' => '输入内容无法提交，请检查后重试。',
  'agent_network_error' => '健康助手请求失败，未执行任何操作。',
  'agent_response_invalid' => '健康助手响应无法验证，未执行任何操作。',
  _ => '健康助手请求未完成，未执行任何操作。',
};

String _disclosureLabel(String code) {
  const labels = {
    'agent_cloud_processing': '一般健康与训练执行的云端健康助手处理',
    'wellness_agent_assistance': '一般健康与训练执行辅助',
    'cloud_provider_china_mainland': '中国大陆云端模型服务',
    'cloud_model_processing': '在云端模型服务中处理最小必要上下文',
    'minimal_structured_health_context': '最小化结构化健康上下文',
    'structured_health_context': '最小化结构化健康上下文',
    'ephemeral_user_message': '本次用户消息（不作为应用聊天记录持久化）',
    'allowlisted_tool_metadata': '允许列表内的工具名称与结构化元数据',
    'no_chat_transcript_persistence': '不持久化聊天文本',
  };
  return labels[code] ?? '（未知项）';
}
