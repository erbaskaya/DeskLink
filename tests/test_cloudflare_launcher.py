import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class CloudflareLauncherRegression(unittest.TestCase):
    def test_windows_child_batch_tools_are_called(self):
        # In a Windows .bat, directly invoking npm.cmd without CALL exits the caller.
        source = (ROOT / 'CLOUDFLARE-KUR-WINDOWS.bat').read_text(encoding='ascii')
        for line in source.splitlines():
            clean = line.strip().lower()
            if clean.startswith(('npm ', 'npx ')):
                self.fail(f'Potentially closing Windows parent batch: {line!r}')
        self.assertIn('call npm --version', source)
        self.assertIn('call npm install --no-audit --no-fund', source)
        self.assertIn('call npx wrangler login', source)
        self.assertIn('call npx wrangler deploy', source)

    def test_windows_launcher_has_explicit_pause_paths(self):
        source = (ROOT / 'CLOUDFLARE-KUR-WINDOWS.bat').read_text(encoding='ascii').lower()
        self.assertGreaterEqual(source.count('pause >nul'), 2)
        self.assertIn(':nonode', source)
        self.assertIn(':failure', source)


if __name__ == '__main__':
    unittest.main()
