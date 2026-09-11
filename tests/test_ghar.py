import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
GHAR_SOURCE = PROJECT_ROOT / "bin" / "ghar"
ARGPARSE_SOURCE = PROJECT_ROOT / "bin" / "argparse_ghar.py"


class GharIntegrationTest(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)

        self.workspace = Path(self.tempdir.name)
        self.ghar_root = self.workspace / "ghar"
        self.bin_dir = self.ghar_root / "bin"
        self.home = self.workspace / "home"
        self.bin_dir.mkdir(parents=True)
        self.home.mkdir()

        self.ghar = self.bin_dir / "ghar"
        shutil.copy2(str(GHAR_SOURCE), str(self.ghar))
        shutil.copy2(str(ARGPARSE_SOURCE), str(self.bin_dir / "argparse_ghar.py"))

        self.env = os.environ.copy()
        self.env.update({
            "HOME": str(self.home),
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_AUTHOR_NAME": "Ghar Tests",
            "GIT_AUTHOR_EMAIL": "ghar-tests@example.invalid",
            "GIT_COMMITTER_NAME": "Ghar Tests",
            "GIT_COMMITTER_EMAIL": "ghar-tests@example.invalid",
            "PYTHONDONTWRITEBYTECODE": "1",
        })

    def run_ghar(self, *args):
        return subprocess.run(
            [sys.executable, str(self.ghar)] + list(args),
            cwd=str(self.ghar_root),
            env=self.env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )


class StartupTests(GharIntegrationTest):
    def test_source_compiles_without_syntax_warnings(self):
        env = self.env.copy()
        env["PYTHONPYCACHEPREFIX"] = str(self.workspace / "pycache")
        result = subprocess.run(
            [
                sys.executable,
                "-Werror::SyntaxWarning",
                "-m",
                "py_compile",
                str(GHAR_SOURCE),
            ],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr)

    def test_help_is_available(self):
        result = self.run_ghar("--help")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("manage your dotfiles", result.stdout)
        self.assertIn("{list,add,pull,status,install,uninstall}", result.stdout)

    def test_no_repositories_prints_warning_and_command_help(self):
        result = self.run_ghar()

        self.assertEqual(result.returncode, 0)
        self.assertIn("No repos found in {}".format(self.ghar_root), result.stderr)
        self.assertIn("usage:", result.stdout)


if __name__ == "__main__":
    unittest.main()
