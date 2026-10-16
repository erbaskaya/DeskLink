"""Tests for the new no-venv startup path."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import desklink_bootstrap as boot


class BootstrapTests(unittest.TestCase):
    def test_separate_role_paths_prevent_shared_venv_collision(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = boot.target_dir(Path(tmp), "client")
            b = boot.target_dir(Path(tmp), "server")
            self.assertNotEqual(a, b)
            self.assertIn("client", a.parts)
            self.assertIn("server", b.parts)
            self.assertNotIn(".venv", str(a))
            self.assertNotIn(".venv", str(b))

    def test_runtime_environment_prepend_only(self):
        with patch.dict(os.environ, {"PYTHONPATH": "existing_libs"}):
            env = boot.runtime_env(Path("custom-packages"))
            self.assertEqual(env["PYTHONPATH"], "custom-packages" + os.pathsep + "existing_libs")
            self.assertEqual(env["PYTHONUTF8"], "1")
            self.assertEqual(env["PYTHONUNBUFFERED"], "1")

    def test_expected_imports_for_each_mode(self):
        self.assertIn("import tkinter", boot.import_command("client")[-1])
        self.assertIn("import pynput", boot.import_command("client")[-1])
        self.assertNotIn("import pynput", boot.import_command("server")[-1])
        self.assertIn("import websockets", boot.import_command("server")[-1])

    def test_ensure_deps_skips_pip_when_packages_available(self):
        with tempfile.TemporaryDirectory() as tmp:
            reporter = Mock()
            with patch.object(boot, "imports_ok", return_value=(True, "")):
                with patch.object(boot, "run_stream") as run:
                    target, env = boot.ensure_deps("server", Path(tmp), reporter)
                    run.assert_not_called()
            self.assertTrue(target.is_dir())
            self.assertTrue(env["PYTHONPATH"].startswith(str(target)))

    def test_failed_command_is_returned_and_logged(self):
        with tempfile.TemporaryDirectory() as tmp:
            rep = boot.Reporter("client", Path(tmp))
            try:
                code = boot.run_stream([sys.executable, "-c", "raise RuntimeError('sample test error')"], rep, boot.runtime_env(Path(tmp)))
                self.assertNotEqual(code, 0)
                self.assertIn("sample test error", rep.log_path.read_text(encoding="utf-8"))
            finally:
                rep.close()

    def test_modules_import_for_live_server_bootstrap(self):
        # Check real subprocess validation path: server-only modules on host.
        code, output = boot.imports_ok("server", boot.runtime_env(Path("__unused__")))
        self.assertTrue(code, output)


if __name__ == "__main__":
    unittest.main()
