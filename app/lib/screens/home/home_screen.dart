// app/lib/screens/home/home_screen.dart
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:model_viewer_plus/model_viewer_plus.dart';
import '../../core/constants.dart';
import '../../providers/posture_state_provider.dart';
import '../../widgets/body_region_button.dart';

class HomeScreen extends ConsumerWidget {
  const HomeScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final postureStates = ref.watch(postureStateProvider);
    final assessedCount = postureStates.values.length;
    final problemCount = postureStates.values
        .where((s) => s.result == 'moderate' || s.result == 'severe')
        .length;

    return Scaffold(
      appBar: AppBar(title: const Text(AppConstants.appName), centerTitle: true),
      body: Column(
        children: [
          // 3D 模型区域
          Expanded(
            flex: 3,
            child: _buildModelViewer(),
          ),
          // 分类导航（2D降级/热点备选）
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.spaceEvenly,
              children: [
                BodyRegionButton(label: '头颈部', icon: Icons.face, onTap: () => context.push('/issues/head_neck')),
                BodyRegionButton(label: '肩胸部', icon: Icons.accessibility_new, onTap: () => context.push('/issues/shoulder_thorax')),
                BodyRegionButton(label: '骨盆腰', icon: Icons.charging_station, onTap: () => context.push('/issues/pelvis_spine')),
                BodyRegionButton(label: '下肢', icon: Icons.directions_walk, onTap: () => context.push('/issues/lower_limb')),
              ],
            ),
          ),
          // 综合评估按钮
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16),
            child: SizedBox(
              width: double.infinity,
              child: OutlinedButton.icon(
                onPressed: () => context.push('/issues/compound'),
                icon: const Icon(Icons.auto_awesome),
                label: const Text('综合评估'),
                style: OutlinedButton.styleFrom(
                  foregroundColor: const Color(AppConstants.accentColor),
                  side: const BorderSide(color: Color(AppConstants.accentColor)),
                  padding: const EdgeInsets.symmetric(vertical: 12),
                ),
              ),
            ),
          ),
          const SizedBox(height: 12),
          // 体态档案入口
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16),
            child: GestureDetector(
              onTap: () => context.push('/profile/posture'),
              child: Card(
                child: Padding(
                  padding: const EdgeInsets.all(16),
                  child: Row(
                    children: [
                      const Icon(Icons.assignment, color: Color(AppConstants.accentColor)),
                      const SizedBox(width: 12),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            const Text('我的体态档案', style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold)),
                            Text('已评估 $assessedCount/26 项，$problemCount 项需关注',
                                style: const TextStyle(color: Color(0xFF8892B0), fontSize: 13)),
                          ],
                        ),
                      ),
                      const Icon(Icons.chevron_right, color: Color(0xFF8892B0)),
                    ],
                  ),
                ),
              ),
            ),
          ),
          const SizedBox(height: 16),
        ],
      ),
    );
  }

  Widget _buildModelViewer() {
    try {
      return ModelViewer(
        src: 'assets/models/astronaut.glb',
        alt: '3D人体模型',
        autoRotate: true,
        cameraControls: true,
        backgroundColor: const Color(AppConstants.bgColor),
      );
    } catch (_) {
      return _buildFallback();
    }
  }

  Widget _buildFallback() {
    return const Center(
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Icon(Icons.accessibility_new, size: 80, color: Color(0xFF0F3460)),
          SizedBox(height: 12),
          Text('3D 模型加载中...', style: TextStyle(color: Color(0xFF8892B0))),
          Text('请使用上方的分类按钮导航', style: TextStyle(color: Color(0xFF8892B0), fontSize: 13)),
        ],
      ),
    );
  }
}
