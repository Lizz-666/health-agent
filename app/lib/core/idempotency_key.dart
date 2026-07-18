// app/lib/core/idempotency_key.dart
//
// Stable client-side idempotency keys for the three side-effecting posture
// endpoints (photo analysis, goal confirmation, safety signal reporting).
//
// Hard contract (Task 8B, spec §8.5 / §10.0):
//  - Each user action generates exactly one UUID v4 (1..64 chars; v4 = 36
//    chars, well within the server's max_length=64).
//  - The same key must survive one Dio network retry belonging to the same
//    user action. The existing ApiClient 401 interceptor at
//    core/api_client.dart retries via `dio.fetch(error.requestOptions)`,
//    which preserves the original request body -- so embedding the key in
//    the body (rather than regenerating per attempt) is what makes the retry
//    idempotent.
//  - A new user action MUST generate a new key; never reuse a key across
//    actions and never derive uniqueness from a wall-clock timestamp alone.
import 'package:uuid/uuid.dart';

/// Generate a fresh UUID v4 idempotency key for one user action.
///
/// Call this exactly once per user-initiated action (e.g. once per "confirm
/// goals" button press, once per "report safety signal" submission, once per
/// "analyze photo" upload) and embed the returned value in the request body.
/// Dio's built-in 401-token-refresh retry reuses the same body, so the same
/// key is replayed automatically on a retry belonging to the same action.
String newIdempotencyKey() {
  return const Uuid().v4();
}
