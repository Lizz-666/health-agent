// app/test/models/issue_test.dart
import 'package:flutter_test/flutter_test.dart';
import 'package:posture_app/models/issue.dart';

Map<String, dynamic> _legacyTest() => {
  'name': '靠墙站立',
  'steps': ['背靠墙站立', '观察后脑勺接触'],
  'positive_sign': '后脑勺无法贴墙',
  'image_key': 'wall-stand',
  'tools_needed': '墙面',
};

Map<String, dynamic> _extendedTest() => {
  ..._legacyTest(),
  'preparation': '脱鞋，自然站立',
  'correct_posture': '脚跟、臀部、上背、后脑勺四点贴墙',
  'common_errors': ['弓腰', '撅下巴前伸'],
  'stop_conditions': ['出现剧烈疼痛', '头晕'],
  'safety_notes': ['若有不适停止'],
  'content_version': '2026-07-11-v1',
  'source': {
    'identifier': 'https://example.com/guide',
    'type': 'L1',
    'version': '2024 ed.',
    'reviewed_at': '2026-07-01',
    'scope': '成人颈部体态筛查',
    'license': 'CC-BY-4.0',
  },
};

void main() {
  group('SelfTest.fromJson (legacy shape)', () {
    final t = SelfTest.fromJson(_legacyTest());

    test('parses the 5 base fields', () {
      expect(t.name, '靠墙站立');
      expect(t.steps, ['背靠墙站立', '观察后脑勺接触']);
      expect(t.positiveSign, '后脑勺无法贴墙');
      expect(t.imageKey, 'wall-stand');
      expect(t.toolsNeeded, '墙面');
    });

    test('extended fields default to empty / null (backward compat)', () {
      expect(t.preparation, '');
      expect(t.correctPosture, '');
      expect(t.commonErrors, isEmpty);
      expect(t.stopConditions, isEmpty);
      expect(t.safetyNotes, isEmpty);
      expect(t.contentVersion, isNull);
      expect(t.source, isNull);
    });
  });

  group('SelfTest.fromJson (extended shape)', () {
    final t = SelfTest.fromJson(_extendedTest());

    test('parses all extended fields', () {
      expect(t.preparation, '脱鞋，自然站立');
      expect(t.correctPosture, '脚跟、臀部、上背、后脑勺四点贴墙');
      expect(t.commonErrors, ['弓腰', '撅下巴前伸']);
      expect(t.stopConditions, ['出现剧烈疼痛', '头晕']);
      expect(t.safetyNotes, ['若有不适停止']);
      expect(t.contentVersion, '2026-07-11-v1');
    });

    test('keeps base fields intact', () {
      expect(t.name, '靠墙站立');
      expect(t.imageKey, 'wall-stand');
      expect(t.steps.length, 2);
    });

    test('parses structured source as a Map', () {
      expect(t.source, isA<Map<String, dynamic>>());
      expect(t.source!['identifier'], 'https://example.com/guide');
      expect(t.source!['type'], 'L1');
      expect(t.source!['version'], '2024 ed.');
    });

    test('rejects partial extended content without stop conditions', () {
      final partial = _extendedTest()..remove('stop_conditions');
      expect(() => SelfTest.fromJson(partial), throwsA(isA<FormatException>()));
    });
  });

  test(
    'IssueDetail.fromJson maps the self_tests list through SelfTest.fromJson',
    () {
      final detail = IssueDetail.fromJson({
        'id': 'HN-01',
        'name_cn': '头部前倾',
        'name_en': 'Forward Head',
        'category': 'head_neck',
        'aliases': ['探颈'],
        'definition': '...',
        'severity_levels': ['mild', 'moderate', 'severe'],
        'causes': [],
        'self_tests': [_extendedTest()],
        'corrections': [],
        'consequences': [],
        'red_flags': [],
        'related_issues': [],
      });
      expect(detail.selfTests.length, 1);
      expect(detail.selfTests.first.stopConditions, ['出现剧烈疼痛', '头晕']);
      expect(detail.selfTests.first.contentVersion, '2026-07-11-v1');
    },
  );
}
