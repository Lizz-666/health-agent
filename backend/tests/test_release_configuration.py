from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
ANDROID_APP = REPO_ROOT / "app" / "android" / "app"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_release_build_never_uses_debug_signing():
    gradle = _text(ANDROID_APP / "build.gradle.kts")

    assert 'signingConfig = signingConfigs.getByName("debug")' not in gradle
    assert "ANDROID_RELEASE_STORE_FILE" in gradle
    assert "ANDROID_RELEASE_STORE_PASSWORD" in gradle
    assert "ANDROID_RELEASE_KEY_ALIAS" in gradle
    assert "ANDROID_RELEASE_KEY_PASSWORD" in gradle
    assert "Release signing is not configured" in gradle


def test_release_manifest_disables_cleartext_and_camera_permission():
    manifest = _text(ANDROID_APP / "src" / "main" / "AndroidManifest.xml")

    assert 'android:usesCleartextTraffic="false"' in manifest
    assert "android.permission.CAMERA" not in manifest


def test_debug_manifest_retains_local_http_and_optional_camera_development():
    manifest = _text(ANDROID_APP / "src" / "debug" / "AndroidManifest.xml")

    assert 'android:usesCleartextTraffic="true"' in manifest
    assert "android.permission.CAMERA" in manifest
    assert 'tools:replace="android:usesCleartextTraffic"' in manifest


def test_profile_manifest_retains_local_http_without_camera_permission():
    manifest = _text(ANDROID_APP / "src" / "profile" / "AndroidManifest.xml")

    assert 'android:usesCleartextTraffic="true"' in manifest
    assert "android.permission.CAMERA" not in manifest
    assert 'tools:replace="android:usesCleartextTraffic"' in manifest
