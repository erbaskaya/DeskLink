"""Cross-OS helpers and intentional rollback of the screen loop guard."""
from __future__ import annotations

import inspect
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from control import InputController
from desktop import DeskLinkApp, NetworkManager, is_trusted_lan_ip, validate_server_url
import platform_support as platforms

ROOT = Path(__file__).resolve().parents[1]


class LanTests(unittest.TestCase):
    def test_lan_ip_allowlist(self):
        for host in ('192.168.1.123', '172.16.0.10', '172.31.255.254', '10.17.4.5', 'fd00::1234'):
            with self.subTest(host=host):
                self.assertTrue(is_trusted_lan_ip(host))
        for host in ('8.8.8.8', '1.1.1.1', '192.0.2.1', '172.32.0.1', '203.0.113.2', 'evil.example', 'fe80::1'):
            with self.subTest(host=host):
                self.assertFalse(is_trusted_lan_ip(host))

    def test_lan_ws_only_with_explicit_private_ip(self):
        self.assertTrue(validate_server_url('ws://192.168.1.50:8765')[0])
        self.assertTrue(validate_server_url('ws://[fd00::1]:8765')[0])
        self.assertFalse(validate_server_url('ws://8.8.8.8:8765')[0])
        self.assertFalse(validate_server_url('ws://my-lan-router.local:8765')[0])
        self.assertTrue(validate_server_url('wss://relay.example.com')[0])


class MacPermissionTests(unittest.TestCase):
    def test_windows_returns_unknown_permissions(self):
        with patch.object(platforms, 'is_macos', return_value=False):
            self.assertEqual(platforms.mac_permission_status(), {'screen': None, 'accessibility': None})
            self.assertIsNone(platforms.request_screen_capture_permission())
            self.assertFalse(platforms.open_mac_privacy_settings('screen'))

    def test_mac_native_permission_preflight(self):
        with patch.object(platforms, 'is_macos', return_value=True), patch.object(platforms, '_native_bool', side_effect=[True, False]) as fn:
            self.assertEqual(platforms.mac_permission_status(), {'screen': True, 'accessibility': False})
            self.assertEqual(fn.call_args_list[0].args[1], 'CGPreflightScreenCaptureAccess')
            self.assertEqual(fn.call_args_list[1].args[1], 'AXIsProcessTrusted')

    def test_mac_permission_request_only_when_asked(self):
        with patch.object(platforms, 'is_macos', return_value=True), patch.object(platforms, '_native_bool', return_value=False) as fn:
            self.assertFalse(platforms.request_screen_capture_permission())
            fn.assert_called_once_with(platforms.CORE_GRAPHICS, 'CGRequestScreenCaptureAccess')

    def test_open_mac_privacy_settings(self):
        with patch.object(platforms, 'is_macos', return_value=True), patch.object(platforms.subprocess, 'Popen') as run:
            self.assertTrue(platforms.open_mac_privacy_settings('accessibility'))
            self.assertIn('Privacy_Accessibility', run.call_args.args[0][1])
            self.assertFalse(platforms.open_mac_privacy_settings('untrusted-value'))
            self.assertEqual(run.call_count, 1)

    def test_missing_permissions_are_only_definite_denials(self):
        self.assertEqual(platforms.missing_host_permissions({'screen': False, 'accessibility': True}),
                         ('Ekran ve Sistem Sesi Kaydı',))
        self.assertEqual(platforms.missing_host_permissions({'screen': True, 'accessibility': False}),
                         ('Erişilebilirlik',))
        self.assertEqual(platforms.missing_host_permissions({'screen': None, 'accessibility': None}), ())

    def test_mac_missing_accessibility_rejects_control_request(self):
        app = DeskLinkApp.__new__(DeskLinkApp)
        app.root = Mock()
        app.mac_permissions_var = Mock()
        with patch('desktop.is_macos', return_value=True), \
             patch('desktop.mac_permission_status', return_value={'screen': True, 'accessibility': False}), \
             patch('desktop.messagebox.showwarning') as warning:
            self.assertFalse(app.mac_host_permissions_ok())
            warning.assert_called_once()

    def test_mac_host_both_permissions_allows_control(self):
        app = DeskLinkApp.__new__(DeskLinkApp)
        app.root = Mock()
        app.mac_permissions_var = Mock()
        with patch('desktop.is_macos', return_value=True), \
             patch('desktop.mac_permission_status', return_value={'screen': True, 'accessibility': True}), \
             patch('desktop.messagebox.showwarning') as warning:
            self.assertTrue(app.mac_host_permissions_ok())
            warning.assert_not_called()

    def test_mac_config_path_uses_application_support(self):
        with patch.object(platforms.sys, 'platform', 'darwin'):
            self.assertIn('Application Support', str(platforms.settings_file()))
            self.assertEqual(platforms.ui_font(), 'Helvetica Neue')

    def test_mac_modifier_keys(self):
        self.assertEqual(InputController.KEY_MAP['meta_l'], 'cmd_l')
        self.assertEqual(InputController.KEY_MAP['option_l'], 'alt_l')
        controller = InputController.__new__(InputController)
        controller.Key = Mock(spec=['cmd', 'ctrl', 'alt'])
        self.assertEqual(controller.key_value('meta_l'), controller.Key.cmd)


class PackagingTests(unittest.TestCase):
    def test_rollback_is_not_conditional(self):
        self.assertFalse((ROOT / 'screen_guard.py').exists())
        source = inspect.getsource(NetworkManager.capture_stream)
        self.assertIn('capturer.grab(capturer.primary_monitor)', source)
        for legacy in ('exclude_viewer_from_capture', 'mask_remote_viewer_windows',
                       'visible_remote_viewer_rects', 'screen_guard'):
            self.assertNotIn(legacy, source)
            self.assertNotIn(legacy, (ROOT / 'desktop.py').read_text(encoding='utf-8'))

    @unittest.skipIf(sys.platform == 'win32',
                     'POSIX executable permission checks are not meaningful on Windows')
    def test_mac_scripts_are_valid_shell_and_executable(self):
        for name in ('MAC-BASLAT.command', 'MAC-TEST-SUNUCU.command',
                     'MAC-LAN-TEST-SUNUCU.command', 'MAC-APP-OLUSTUR.command', 'mac_run.sh'):
            with self.subTest(name=name):
                script = ROOT / name
                self.assertTrue(script.is_file())
                self.assertTrue(script.stat().st_mode & 0o111)
                result = subprocess.run(['bash', '-n', str(script)], capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_mac_launcher_uses_bootstrap_and_does_not_reinstall_python(self):
        runner = (ROOT / 'mac_run.sh').read_text(encoding='utf-8')
        self.assertIn('desklink_bootstrap.py', runner)
        self.assertIn('import tkinter', runner)
        self.assertNotIn('brew install', runner)
        self.assertNotIn('python -m venv', runner)

    def test_mac_app_builder_bundles_application(self):
        runner = (ROOT / 'MAC-APP-OLUSTUR.command').read_text(encoding='utf-8')
        self.assertIn('build_standalone.py', runner)
        builder = (ROOT / 'build_standalone.py').read_text(encoding='utf-8')
        for required in ('--windowed', '--onedir', 'mss.darwin',
                         'pynput.keyboard._darwin', 'pynput.mouse._darwin',
                         'DeskLink.icns'):
            self.assertIn(required, builder)

    def test_lan_server_requires_opt_in(self):
        bootstrap = (ROOT / 'desklink_bootstrap.py').read_text(encoding='utf-8')
        self.assertIn('DESKLINK_LAN_TEST', bootstrap)
        self.assertIn('"0.0.0.0"', bootstrap)
        self.assertIn('"127.0.0.1"', bootstrap)
        for name in ('LAN-TEST-SUNUCU-WINDOWS.bat', 'MAC-LAN-TEST-SUNUCU.command'):
            self.assertIn('DESKLINK_LAN_TEST=1', (ROOT / name).read_text(encoding='utf-8').replace('"', ''))


if __name__ == '__main__':
    unittest.main()
