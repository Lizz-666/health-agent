// app/lib/screens/test/photo_test_screen.dart
import 'dart:io';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:image_picker/image_picker.dart';
import 'package:dio/dio.dart';
import '../../core/api_client.dart';
import '../../providers/assessment_provider.dart';
import '../../providers/posture_state_provider.dart';

class PhotoTestScreen extends ConsumerStatefulWidget {
  final String issueId;
  const PhotoTestScreen({super.key, required this.issueId});

  @override
  ConsumerState<PhotoTestScreen> createState() => _PhotoTestScreenState();
}

class _PhotoTestScreenState extends ConsumerState<PhotoTestScreen> {
  final _picker = ImagePicker();
  File? _photo;
  bool _analyzing = false;

  Future<void> _pickPhoto(ImageSource source) async {
    final xFile = await _picker.pickImage(source: source, maxWidth: 1024, maxHeight: 1024);
    if (xFile == null) return;
    setState(() => _photo = File(xFile.path));
  }

  Future<void> _uploadAndAnalyze() async {
    if (_photo == null || _analyzing) return;
    setState(() => _analyzing = true);

    try {
      final api = ref.read(apiClientProvider);
      final stsResp = await api.dio.post('/upload/sts-token');
      final sts = stsResp.data as Map<String, dynamic>;

      final fileName = '${DateTime.now().millisecondsSinceEpoch}.jpg';
      final objectKey = '${sts['path_prefix']}$fileName';
      final formData = FormData.fromMap({
        'file': await MultipartFile.fromFile(_photo!.path, filename: fileName),
        'key': objectKey,
        'OSSAccessKeyId': sts['access_key_id'] ?? '',
        'policy': sts['policy'] ?? '',
        'Signature': sts['signature'] ?? '',
        'x-oss-security-token': sts['security_token'] ?? '',
      });
      final ossDio = Dio();
      await ossDio.post(
        'https://${sts['bucket']}.${sts['endpoint']}',
        data: formData,
        options: Options(headers: {
          'Content-Type': 'multipart/form-data',
        }),
      );

      final result = await ref
          .read(assessmentProvider.notifier)
          .submitPhotoAssess(widget.issueId, [objectKey]);

      if (result != null && mounted) {
        final aiLevel = result['result'] ?? 'normal';
        final aiSuggestion = result['suggestion'] ?? '';
        ref.read(postureStateProvider.notifier).updateState(
          issueId: widget.issueId,
          result: aiLevel,
          method: 'ai_photo',
        );
        if (mounted) {
          context.push('/issue/${widget.issueId}/result', extra: {
            'assessmentId': result['id'] ?? '',
            'result': aiLevel,
            'suggestion': aiSuggestion,
          });
        }
      }
    } on DioException catch (e) {
      final data = e.response?.data;
      final msg = (data is Map<String, dynamic>)
          ? (data['detail'] as String?) ?? '上传或分析失败，请重试'
          : '上传或分析失败，请重试';
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(msg)));
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('发生错误，请重试')),
        );
      }
    } finally {
      if (mounted) setState(() => _analyzing = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('AI 拍照分析')),
      body: _analyzing
          ? const Center(
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  CircularProgressIndicator(),
                  SizedBox(height: 16),
                  Text('AI 正在分析中...', style: TextStyle(fontSize: 18)),
                  SizedBox(height: 8),
                  Text('请耐心等待，最多约30秒', style: TextStyle(color: Color(0xFF8892B0))),
                ],
              ),
            )
          : _photo != null
              ? Column(
                  children: [
                    Expanded(child: Image.file(_photo!, fit: BoxFit.contain)),
                    Padding(
                      padding: const EdgeInsets.all(16),
                      child: Row(
                        children: [
                          Expanded(
                            child: OutlinedButton(
                              onPressed: () => setState(() => _photo = null),
                              child: const Text('重新选择'),
                            ),
                          ),
                          const SizedBox(width: 12),
                          Expanded(
                            child: ElevatedButton(
                              onPressed: _uploadAndAnalyze,
                              child: const Text('开始分析'),
                            ),
                          ),
                        ],
                      ),
                    ),
                  ],
                )
              : Padding(
                  padding: const EdgeInsets.all(32),
                  child: Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      const Icon(Icons.camera_alt, size: 80, color: Color(0xFFE94560)),
                      const SizedBox(height: 24),
                      const Text('AI 体态分析',
                          style: TextStyle(fontSize: 22, fontWeight: FontWeight.bold)),
                      const SizedBox(height: 8),
                      const Text('请保持自然站姿，全身入镜\n光线充足，背景简洁',
                          textAlign: TextAlign.center,
                          style: TextStyle(color: Color(0xFF8892B0))),
                      const SizedBox(height: 32),
                      Container(
                        height: 200,
                        decoration: BoxDecoration(
                          color: const Color(0xFF16213E),
                          borderRadius: BorderRadius.circular(12),
                        ),
                        child: const Center(
                          child: Icon(Icons.accessibility_new, size: 80, color: Color(0xFF0F3460)),
                        ),
                      ),
                      const SizedBox(height: 32),
                      SizedBox(
                        width: double.infinity, height: 52,
                        child: ElevatedButton.icon(
                          onPressed: () => _pickPhoto(ImageSource.camera),
                          icon: const Icon(Icons.camera),
                          label: const Text('拍照'),
                        ),
                      ),
                      const SizedBox(height: 12),
                      SizedBox(
                        width: double.infinity, height: 52,
                        child: ElevatedButton.icon(
                          onPressed: () => _pickPhoto(ImageSource.gallery),
                          icon: const Icon(Icons.photo_library),
                          label: const Text('从相册选择'),
                          style: ElevatedButton.styleFrom(
                            backgroundColor: const Color(0xFF0F3460),
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
    );
  }
}
