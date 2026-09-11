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

    def run_command(self, command, cwd=None):
        return subprocess.run(
            command,
            cwd=str(cwd or self.workspace),
            env=self.env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

    def run_ghar(self, *args):
        return self.run_command(
            [sys.executable, str(self.ghar)] + list(args),
            cwd=self.ghar_root,
        )

    def create_repo(self, name, files=None):
        repo = self.ghar_root / name
        repo.mkdir()
        result = self.run_command(["git", "init", "-q"], cwd=repo)
        self.assertEqual(result.returncode, 0, result.stderr)
        for relative_path, contents in (files or {}).items():
            path = repo / relative_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(contents)
        return repo


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


class RepositoryDiscoveryTests(GharIntegrationTest):
    def test_list_discovers_repositories_but_not_internal_directories(self):
        (self.ghar_root / ".git").mkdir()
        self.create_repo("alpha", {".alpharc": "alpha\n"})
        self.create_repo("bravo", {"config": "bravo\n"})

        result = self.run_ghar("list")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(set(result.stdout.splitlines()), {"alpha", "bravo"})
        self.assertNotIn("bin", result.stdout.splitlines())
        self.assertNotIn(".git", result.stdout.splitlines())


class RepositoryClassificationTests(GharIntegrationTest):
    def test_dotfile_repository_is_installed_as_a_collection(self):
        repo = self.create_repo("shell", {".shellrc": "settings\n"})

        result = self.run_ghar("install", "shell")

        target = self.home / ".shellrc"
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(target.is_symlink())
        self.assertEqual(Path(os.readlink(str(target))), repo / ".shellrc")

    def test_regular_file_repository_is_installed_as_one_directory(self):
        repo = self.create_repo("theme", {"colors.conf": "blue\n"})

        result = self.run_ghar("install", "theme")

        target = self.home / ".theme"
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(target.is_symlink())
        self.assertEqual(Path(os.readlink(str(target))), repo)
        self.assertFalse((self.home / "colors.conf").exists())

    def test_repository_metadata_is_not_installed(self):
        repo = self.create_repo(
            "editor",
            {
                ".editorrc": "editor\n",
                ".gitignore": "ignored\n",
                ".gitmodules": "modules\n",
                ".travis.yml": "language: python\n",
                "README.md": "documentation\n",
            },
        )

        result = self.run_ghar("install", "editor")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            {path.name for path in self.home.iterdir()},
            {".editorrc"},
        )
        self.assertEqual(
            Path(os.readlink(str(self.home / ".editorrc"))),
            repo / ".editorrc",
        )

    def test_gitconfig_is_treated_as_user_configuration(self):
        repo = self.create_repo("git-config", {".gitconfig": "[user]\n"})

        result = self.run_ghar("install", "git-config")

        target = self.home / ".gitconfig"
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(target.is_symlink())
        self.assertEqual(Path(os.readlink(str(target))), repo / ".gitconfig")


class InstallationTests(GharIntegrationTest):
    def test_install_links_a_directory_when_the_home_directory_is_absent(self):
        repo = self.create_repo(
            "application",
            {".config/application/settings.ini": "enabled=true\n"},
        )

        result = self.run_ghar("install", "application")

        target = self.home / ".config"
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(target.is_symlink())
        self.assertEqual(Path(os.readlink(str(target))), repo / ".config")

    def test_install_recurses_through_existing_home_directories(self):
        repo = self.create_repo(
            "application",
            {".config/application/settings.ini": "enabled=true\n"},
        )
        (self.home / ".config" / "application").mkdir(parents=True)

        result = self.run_ghar("install", "application")

        target = self.home / ".config" / "application" / "settings.ini"
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(target.is_symlink())
        self.assertEqual(
            Path(os.readlink(str(target))),
            repo / ".config" / "application" / "settings.ini",
        )

    def test_install_is_idempotent(self):
        repo = self.create_repo("shell", {".shellrc": "settings\n"})
        first = self.run_ghar("install", "shell")
        target = self.home / ".shellrc"
        original_link = os.readlink(str(target))

        second = self.run_ghar("install", "shell")

        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertIn("ok\t{}".format(target), second.stdout)
        self.assertEqual(os.readlink(str(target)), original_link)
        self.assertEqual(Path(original_link), repo / ".shellrc")

    def test_install_preserves_files_and_foreign_symlinks(self):
        self.create_repo(
            "conflicts",
            {".existing-file": "replacement\n", ".existing-link": "replacement\n"},
        )
        file_target = self.home / ".existing-file"
        file_target.write_text("keep me\n")
        foreign_source = self.workspace / "foreign"
        foreign_source.write_text("foreign\n")
        link_target = self.home / ".existing-link"
        link_target.symlink_to(foreign_source)

        result = self.run_ghar("install", "conflicts")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(file_target.read_text(), "keep me\n")
        self.assertEqual(Path(os.readlink(str(link_target))), foreign_source)
        self.assertIn("{} exists".format(file_target), result.stdout)
        self.assertIn("can't handle non-ghar symlinks", result.stdout)
        self.assertIn(str(link_target), result.stdout)
        self.assertIn("error: conflicts is not fully installed", result.stdout)

    def test_install_can_select_repositories(self):
        alpha = self.create_repo("alpha", {".alpha": "alpha\n"})
        self.create_repo("bravo", {".bravo": "bravo\n"})

        result = self.run_ghar("install", "alpha")

        alpha_target = self.home / ".alpha"
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(alpha_target.is_symlink())
        self.assertEqual(Path(os.readlink(str(alpha_target))), alpha / ".alpha")
        self.assertFalse((self.home / ".bravo").exists())
        self.assertNotIn("bravo", result.stdout)


class IgnoreFileTests(GharIntegrationTest):
    def test_gharignore_honors_globs_comments_and_blank_lines(self):
        repo = self.create_repo(
            "ignored-files",
            {
                ".gharignore": "# Local-only files\n\n*.txt\n.secret\n",
                ".keep": "installed\n",
                ".secret": "private\n",
                "notes.txt": "notes\n",
            },
        )

        result = self.run_ghar("install", "ignored-files")

        keep_target = self.home / ".keep"
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(keep_target.is_symlink())
        self.assertEqual(Path(os.readlink(str(keep_target))), repo / ".keep")
        self.assertFalse((self.home / ".secret").exists())
        self.assertFalse((self.home / "notes.txt").exists())
        self.assertFalse((self.home / ".gharignore").exists())
        self.assertEqual(result.stdout.count(" skip\t"), 3)


if __name__ == "__main__":
    unittest.main()
