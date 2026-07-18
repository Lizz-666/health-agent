// app/test/models/assessment_test.dart
import 'package:flutter_test/flutter_test.dart';
import 'package:posture_app/models/assessment.dart';

Map<String, dynamic> _record({
  String id = 'rec-1',
  String issueId = 'HN-01',
  String issueName = '头部前倾',
  String? source,
  String? method,
  String result = 'moderate',
  String createdAt = '2026-07-11T10:00:00Z',
}) {
  final json = <String, dynamic>{
    'id': id,
    'issue_id': issueId,
    'issue_name': issueName,
    'result': result,
    'created_at': createdAt,
  };
  if (source != null) json['source'] = source;
  if (method != null) json['method'] = method;
  return json;
}

void main() {
  group('AssessmentRecord.fromJson', () {
    test(
      'prefers source and mirrors it to method when only source present',
      () {
        final r = AssessmentRecord.fromJson(_record(source: 'self_test'));
        expect(r.source, 'self_test');
        expect(r.method, 'self_test');
      },
    );

    test(
      'falls back to method and mirrors it to source for legacy payload',
      () {
        final r = AssessmentRecord.fromJson(_record(method: 'ai_photo'));
        expect(r.method, 'ai_photo');
        expect(r.source, 'ai_photo');
      },
    );

    test(
      'keeps both fields equal when both present and equal (Task 8A shape)',
      () {
        final r = AssessmentRecord.fromJson(
          _record(source: 'self_test', method: 'self_test'),
        );
        expect(r.source, 'self_test');
        expect(r.method, 'self_test');
      },
    );

    test('rejects source/method alias disagreement', () {
      expect(
        () => AssessmentRecord.fromJson(
          _record(source: 'ai_photo', method: 'self_test'),
        ),
        throwsA(isA<FormatException>()),
      );
    });

    test('trims whitespace on source/method', () {
      final r = AssessmentRecord.fromJson(_record(source: '  self_test  '));
      expect(r.source, 'self_test');
      expect(r.method, 'self_test');
    });

    test('throws FormatException when both source and method are missing', () {
      expect(
        () => AssessmentRecord.fromJson(_record()),
        throwsA(isA<FormatException>()),
      );
    });

    test('throws FormatException when created_at is missing', () {
      expect(
        () => AssessmentRecord.fromJson({
          'id': 'rec-1',
          'issue_id': 'HN-01',
          'issue_name': '头部前倾',
          'method': 'self_test',
          'result': 'moderate',
          // no created_at
        }),
        throwsA(isA<FormatException>()),
      );
    });

    test(
      'throws FormatException when created_at is unparseable (no DateTime.now fallback)',
      () {
        expect(
          () => AssessmentRecord.fromJson(
            _record(method: 'self_test', createdAt: 'not-a-date'),
          ),
          throwsA(isA<FormatException>()),
        );
      },
    );

    test('throws FormatException when id is missing', () {
      expect(
        () => AssessmentRecord.fromJson({
          'issue_id': 'HN-01',
          'issue_name': '头部前倾',
          'method': 'self_test',
          'result': 'moderate',
          'created_at': '2026-07-11T10:00:00Z',
        }),
        throwsA(isA<FormatException>()),
      );
    });

    test('throws FormatException when issue_id is blank', () {
      expect(
        () => AssessmentRecord.fromJson(
          _record(method: 'self_test', issueId: '   '),
        ),
        throwsA(isA<FormatException>()),
      );
    });

    test('throws FormatException when result is blank', () {
      expect(
        () =>
            AssessmentRecord.fromJson(_record(method: 'self_test', result: '')),
        throwsA(isA<FormatException>()),
      );
    });

    test('parses a complete record into the expected field values', () {
      final r = AssessmentRecord.fromJson(
        _record(source: 'ai_photo', method: 'ai_photo'),
      );
      expect(r.id, 'rec-1');
      expect(r.issueId, 'HN-01');
      expect(r.issueName, '头部前倾');
      expect(r.result, 'moderate');
      expect(r.createdAt, DateTime.parse('2026-07-11T10:00:00Z'));
    });
  });

  group('SelfAssessResult.fromJson', () {
    test('parses the four canonical fields', () {
      final r = SelfAssessResult.fromJson({
        'id': 'a-1',
        'issue_id': 'HN-01',
        'result': 'mild',
        'suggestion': '建议 X',
      });
      expect(r.id, 'a-1');
      expect(r.issueId, 'HN-01');
      expect(r.result, 'mild');
      expect(r.suggestion, '建议 X');
    });

    test('requires id', () {
      expect(
        () => SelfAssessResult.fromJson({
          'issue_id': 'HN-01',
          'result': 'mild',
          'suggestion': '',
        }),
        throwsA(isA<FormatException>()),
      );
    });

    test('requires issue_id', () {
      expect(
        () => SelfAssessResult.fromJson({
          'id': 'a-1',
          'result': 'mild',
          'suggestion': '',
        }),
        throwsA(isA<FormatException>()),
      );
    });

    test('requires result', () {
      expect(
        () => SelfAssessResult.fromJson({
          'id': 'a-1',
          'issue_id': 'HN-01',
          'suggestion': '',
        }),
        throwsA(isA<FormatException>()),
      );
    });

    test('allows empty suggestion (valid backend value)', () {
      final r = SelfAssessResult.fromJson({
        'id': 'a-1',
        'issue_id': 'HN-01',
        'result': 'normal',
        // suggestion omitted
      });
      expect(r.suggestion, '');
    });
  });
}
