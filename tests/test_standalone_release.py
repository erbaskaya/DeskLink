"""Focused regression checks for the new no-Python-on-client release process."""
from pathlib import Path
import unittest
import sys
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app_identity import APP_VERSION, DEFAULT_RELAY, bundled_brand_asset
from build_standalone import command_for_platform

class StandaloneReleaseTests(unittest.TestCase):
    def test_default_cloudflare_connection_and_version(self):
        self.assertEqual(APP_VERSION, "0.4.0")
        self.assertEqual(DEFAULT_RELAY, "wss://desklink-relay.erbaskayam.workers.dev/ws")
        from desktop import DEFAULT_URL, validate_server_url
        self.assertEqual(DEFAULT_URL, DEFAULT_RELAY)
        self.assertTrue(validate_server_url(DEFAULT_URL)[0])

    def test_brand_files_exist_and_have_native_formats(self):
        for name, expected in [('DeskLink-icon-256.png', 'PNG'), ('DeskLink.ico', 'ICO'),
                               ('DeskLink.icns', 'ICNS'), ('DeskLink-logo-dark.png', 'PNG')]:
            with self.subTest(asset=name):
                path = bundled_brand_asset(name)
                self.assertTrue(path.is_file())
                with Image.open(path) as img:
                    self.assertEqual(img.format, expected)

    def test_build_script_includes_app_icon_and_python(self):
        source = (ROOT / 'build_standalone.py').read_text(encoding='utf-8')
        for item in ('--onefile', '--onedir', 'PyInstaller', '--windowed', 'DeskLink.icns',
                     'DeskLink.ico', '--add-data'):
            self.assertIn(item, source)

    def test_ui_embeds_logo_and_uses_asset_resolver(self):
        source = (ROOT / 'desktop.py').read_text(encoding='utf-8')
        self.assertIn('DeskLink-logo-dark.png', source)
        self.assertIn('DeskLink-icon-256.png', source)
        self.assertIn('self.set_brand_icon(self.root)', source)
        self.assertNotIn('screen_guard', source)

    def test_actions_builds_all_three_platform_artifacts(self):
        workflow = (ROOT / '.github/workflows/desktop-binaries.yml').read_text(encoding='utf-8')
        for x in ('windows-latest','macos-15-intel','macos-15','DeskLink-Windows-x64',
                  'DeskLink-macOS-', 'upload-artifact@v4'):
            self.assertIn(x, workflow)

    def test_build_only_on_target_os(self):
        with self.assertRaisesRegex(RuntimeError, '.exe'):
            command_for_platform('linux')

if __name__ == '__main__':
    unittest.main()
