// app/lib/screens/profile/profile_screen.dart
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../providers/auth_provider.dart';
import '../../providers/user_provider.dart';

class ProfileScreen extends ConsumerWidget {
  const ProfileScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final profile = ref.watch(userProvider).profile;

    return Scaffold(
      appBar: AppBar(title: const Text('个人中心')),
      body: ListView(
        children: [
          // 头像区
          Container(
            padding: const EdgeInsets.all(24),
            child: Row(
              children: [
                const CircleAvatar(
                  radius: 30,
                  backgroundColor: Color(0xFF0F3460),
                  child: Icon(Icons.person, size: 36, color: Color(0xFF8892B0)),
                ),
                const SizedBox(width: 16),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(profile?.phone ?? '未登录',
                          style: const TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
                      const Text('普通用户', style: TextStyle(color: Color(0xFF8892B0))),
                    ],
                  ),
                ),
              ],
            ),
          ),
          // 基本信息
          Card(
            margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text('基本信息', style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold)),
                  const SizedBox(height: 12),
                  _infoRow('身高', '${profile?.height ?? "未填写"} cm', () => _editField(context, ref, '身高', 'cm', (profile?.height ?? 170).toInt(), 100, 220, (v) => _updateProfile(ref, height: v.toDouble()))),
                  _infoRow('体重', '${profile?.weight ?? "未填写"} kg', () => _editField(context, ref, '体重', 'kg', (profile?.weight ?? 65).toInt(), 30, 200, (v) => _updateProfile(ref, weight: v.toDouble()))),
                  _infoRow('年龄', '${profile?.age ?? "未填写"} 岁', () => _editField(context, ref, '年龄', '岁', profile?.age ?? 25, 12, 120, (v) => _updateProfile(ref, age: v))),
                  _infoRow('性别', profile?.gender == 'male' ? '男' : profile?.gender == 'female' ? '女' : '未填写',
                      () => _editGender(context, ref)),
                ],
              ),
            ),
          ),
          // 菜单
          Card(
            margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
            child: Column(
              children: [
                _menuItem('我的体态档案', Icons.assignment, () => context.push('/profile/posture')),
                const Divider(height: 1),
                _menuItem('评估历史', Icons.history, () => context.push('/history')),
                const Divider(height: 1),
                _menuItem('关于', Icons.info_outline, () => _showAbout(context)),
              ],
            ),
          ),
          const SizedBox(height: 24),
          // 退出登录
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16),
            child: SizedBox(
              width: double.infinity,
              child: OutlinedButton(
                onPressed: () async {
                  await ref.read(authProvider.notifier).logout();
                  if (context.mounted) context.go('/login');
                },
                style: OutlinedButton.styleFrom(foregroundColor: const Color(0xFFFF1744)),
                child: const Text('退出登录'),
              ),
            ),
          ),
          const SizedBox(height: 32),
        ],
      ),
    );
  }

  Widget _infoRow(String label, String value, VoidCallback onTap) {
    return InkWell(
      onTap: onTap,
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 10),
        child: Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Text(label, style: const TextStyle(color: Color(0xFF8892B0))),
            Row(
              children: [
                Text(value, style: const TextStyle(fontSize: 15)),
                const SizedBox(width: 4),
                const Icon(Icons.edit, size: 16, color: Color(0xFF8892B0)),
              ],
            ),
          ],
        ),
      ),
    );
  }

  Widget _menuItem(String title, IconData icon, VoidCallback onTap) {
    return ListTile(
      leading: Icon(icon, color: const Color(0xFFE94560)),
      title: Text(title),
      trailing: const Icon(Icons.chevron_right, color: Color(0xFF8892B0)),
      onTap: onTap,
    );
  }

  void _updateProfile(WidgetRef ref, {double? height, double? weight, int? age, String? gender}) {
    ref.read(userProvider.notifier).updateProfile(
      height: height, weight: weight, age: age, gender: gender);
  }

  void _editField(BuildContext context, WidgetRef ref, String label, String unit, int value, int min, int max, ValueChanged<int> onSave) {
    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text('$label'),
        content: StatefulBuilder(
          builder: (_, setDialogState) {
            int temp = value;
            return Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Text('$temp $unit', style: const TextStyle(fontSize: 24, fontWeight: FontWeight.bold)),
                Slider(
                  value: temp.toDouble(), min: min.toDouble(), max: max.toDouble(),
                  onChanged: (v) => setDialogState(() => temp = v.toInt()),
                ),
              ],
            );
          },
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('取消')),
          ElevatedButton(onPressed: () { onSave(value); Navigator.pop(ctx); }, child: const Text('保存')),
        ],
      ),
    );
  }

  void _editGender(BuildContext context, WidgetRef ref) {
    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('性别'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            ListTile(title: const Text('男'), onTap: () { _updateProfile(ref, gender: 'male'); Navigator.pop(ctx); }),
            ListTile(title: const Text('女'), onTap: () { _updateProfile(ref, gender: 'female'); Navigator.pop(ctx); }),
          ],
        ),
      ),
    );
  }

  void _showAbout(BuildContext context) {
    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('关于体态分析'),
        content: const Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text('版本: 1.0.0 MVP', style: TextStyle(fontSize: 16)),
            SizedBox(height: 12),
            Text('本 App 内容基于公开医学文献，仅供健康科普与自我管理参考，不能替代专业医疗诊断与治疗。如有持续疼痛、麻木、畸形或其他异常，请及时就医。',
                style: TextStyle(height: 1.5)),
          ],
        ),
        actions: [
          ElevatedButton(onPressed: () => Navigator.pop(ctx), child: const Text('知道了')),
        ],
      ),
    );
  }
}
