// app/test/core/idempotency_key_test.dart
import 'package:flutter_test/flutter_test.dart';
import 'package:posture_app/core/idempotency_key.dart';

void main() {
  group('newIdempotencyKey', () {
    test('returns a non-empty string of <=64 chars', () {
      final key = newIdempotencyKey();
      expect(key, isNotEmpty);
      expect(key.length, lessThanOrEqualTo(64));
    });

    test('matches the canonical UUID v4 format', () {
      final key = newIdempotencyKey();
      // 8-4-4-4-12 hex, version nibble = 4, variant in [89ab].
      expect(
        RegExp(
          r'^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$',
        ).hasMatch(key),
        isTrue,
        reason: 'key was: $key',
      );
    });

    test('produces 1000 distinct values for 1000 calls', () {
      final keys = <String>{};
      for (var i = 0; i < 1000; i++) {
        keys.add(newIdempotencyKey());
      }
      expect(keys.length, 1000);
    });

    test(
      'two calls in the same frame differ (no timestamp-only derivation)',
      () {
        final a = newIdempotencyKey();
        final b = newIdempotencyKey();
        expect(a, isNot(equals(b)));
      },
    );
  });
}
