"""Static review of Windows BAT startup and independent live Python probe.

The BAT launchers require a real Windows execution test.
"""
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]


class WindowsStartupTests(unittest.TestCase):
    def setUp(self):
        self.runner = (ROOT / 'desklink_run.bat').read_text(encoding='utf-8')

    def test_direct_runtime_probe_is_actual_python_code(self):
        code = 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)'
        self.assertIn(code, self.runner)
        result = subprocess.run([sys.executable, '-c', code], check=False)
        self.assertEqual(result.returncode, 0)

    def test_pymanager_direct_runtime_invocation(self):
        self.assertIn('call :probe py -3.13', self.runner)
        self.assertIn('call :probe py -3.14', self.runner)
        self.assertIn('call :probe python', self.runner)
        self.assertIn('if defined PY_EXEC goto python_ready', self.runner)
        self.assertIn('%PY_EXEC% "%~dp0desklink_bootstrap.py" %ROLE%', self.runner)

    def test_no_reinstallation_and_diagnostic_report(self):
        self.assertNotIn('py install 3.13', self.runner)
        self.assertIn('set "PYTHON_MANAGER_AUTOMATIC_INSTALL=false"', self.runner)
        self.assertIn('py list --format=exe >> "%LOG%" 2>&1', self.runner)
        self.assertIn('py -3.13 -c "import sys;print(sys.executable);print(sys.version)"', self.runner)
        self.assertIn('DeskLink-python-tani-log.txt', self.runner)

    def test_batch_entrypoints_pause_on_failure(self):
        for filename, mode in (
            ('BASLAT-TEST-SUNUCU.bat', 'server'),
            ('BASLAT-WINDOWS.bat', 'client'),
        ):
            script = (ROOT / filename).read_text(encoding='utf-8')
            self.assertIn('desklink_run.bat" ' + mode, script)
            self.assertIn('pause >nul', script)
        diagnostic = (ROOT / 'PYTHON-TANI.bat').read_text(encoding='utf-8')
        self.assertIn('desklink_run.bat" diagnostic', diagnostic)
        self.assertIn('pause', diagnostic)


if __name__ == '__main__':
    unittest.main()
