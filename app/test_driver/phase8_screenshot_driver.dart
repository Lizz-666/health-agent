import 'dart:io';

import 'package:integration_test/integration_test_driver_extended.dart';

Future<void> main() async {
  final output = Directory(
    Platform.environment['PHASE8_SCREENSHOT_DIR'] ?? 'build/phase8-screenshots',
  );
  if (output.existsSync()) {
    output.deleteSync(recursive: true);
  }
  output.createSync(recursive: true);

  await integrationDriver(
    onScreenshot: (name, bytes, [args]) async {
      if (!RegExp(r'^\d{2}-[a-z0-9-]+$').hasMatch(name)) {
        throw StateError('Invalid Phase 8 screenshot name');
      }
      await File(
        '${output.path}${Platform.pathSeparator}$name.png',
      ).writeAsBytes(bytes, flush: true);
      return bytes.isNotEmpty;
    },
    writeResponseOnFailure: true,
  );
}
