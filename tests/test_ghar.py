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


def symlinks_are_available():
    if not hasattr(os, "symlink"):
        return False
    with tempfile.TemporaryDirectory() as tempdir:
        root = Path(tempdir)
        file_target = root / "file-target"
        file_target.write_text("target\n")
        directory_target = root / "directory-target"
        directory_target.mkdir()
        try:
            os.symlink(str(file_target), str(root / "file-link"))
            os.symlink(str(directory_target), str(root / "directory-link"))
        except (NotImplementedError, OSError):
            return False
    return True


SYMLINKS_AVAILABLE = symlinks_are_available()
REQUIRES_SYMLINKS = unittest.skipUnless(
    SYMLINKS_AVAILABLE,
    "symbolic links are not available in this environment",
)


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

    def git(self, cwd, *args):
        result = self.run_command(["git"] + list(args), cwd=cwd)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result

    def commit_all(self, repo, message="test commit"):
        self.git(repo, "add", ".")
        self.git(repo, "commit", "-q", "-m", message)


class StartupTests(GharIntegrationTest):
    def test_executable_uses_python3(self):
        shebang = GHAR_SOURCE.read_text().splitlines()[0]

        self.assertEqual(shebang, "#!/usr/bin/env python3")

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

    def test_list_honors_root_repository_ignore_patterns(self):
        (self.ghar_root / ".gharignore").write_text(
            "# Non-repository directories\n\n.github\nbuild-*\n"
        )
        self.create_repo("dotfiles", {".dotfilerc": "visible\n"})
        (self.ghar_root / ".github").mkdir()
        (self.ghar_root / "build-output").mkdir()

        result = self.run_ghar("list")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines(), ["dotfiles"])


@REQUIRES_SYMLINKS
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


@REQUIRES_SYMLINKS
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


@REQUIRES_SYMLINKS
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

    def test_status_and_uninstall_treat_ignored_files_as_skipped(self):
        self.create_repo(
            "ignored-operations",
            {
                ".gharignore": "*.txt\n",
                ".keep": "installed\n",
                "notes.txt": "ignored\n",
            },
        )
        install = self.run_ghar("install", "ignored-operations")
        self.assertEqual(install.returncode, 0, install.stderr)

        status = self.run_ghar("install", "--status", "ignored-operations")
        uninstall = self.run_ghar("uninstall", "ignored-operations")

        self.assertEqual(status.returncode, 0, status.stderr)
        self.assertIn("ok\t{}".format(self.home / ".keep"), status.stdout)
        self.assertIn("skip\t{}".format(self.home / "notes.txt"), status.stdout)
        self.assertIn("skip\t{}".format(self.home / ".gharignore"), status.stdout)
        self.assertNotIn("not fully installed", status.stdout)

        self.assertEqual(uninstall.returncode, 0, uninstall.stderr)
        self.assertFalse((self.home / ".keep").exists())
        self.assertIn("skip\t{}".format(self.home / "notes.txt"), uninstall.stdout)
        self.assertIn("skip\t{}".format(self.home / ".gharignore"), uninstall.stdout)
        self.assertNotIn("is not installed", uninstall.stdout)

    def test_uninstall_preserves_a_link_that_becomes_ignored(self):
        repo = self.create_repo(
            "newly-ignored",
            {
                ".gharignore": "# Nothing ignored yet\n",
                ".legacy": "legacy\n",
            },
        )
        install = self.run_ghar("install", "newly-ignored")
        self.assertEqual(install.returncode, 0, install.stderr)
        target = self.home / ".legacy"
        self.assertTrue(target.is_symlink())
        (repo / ".gharignore").write_text(".legacy\n")

        status = self.run_ghar("install", "--status", "newly-ignored")
        uninstall = self.run_ghar("uninstall", "newly-ignored")

        self.assertEqual(status.returncode, 0, status.stderr)
        self.assertIn("skip\t{}".format(target), status.stdout)
        self.assertNotIn("not fully installed", status.stdout)
        self.assertEqual(uninstall.returncode, 0, uninstall.stderr)
        self.assertIn("skip\t{}".format(target), uninstall.stdout)
        self.assertNotIn("is not installed", uninstall.stdout)
        self.assertTrue(target.is_symlink())
        self.assertEqual(Path(os.readlink(str(target))), repo / ".legacy")


@REQUIRES_SYMLINKS
class StatusAndUninstallTests(GharIntegrationTest):
    def test_status_reports_installed_missing_and_conflicting_targets(self):
        self.create_repo(
            "status-repo",
            {
                ".installed": "installed\n",
                ".missing": "missing\n",
                ".conflict": "conflict\n",
            },
        )
        install = self.run_ghar("install", "status-repo")
        self.assertEqual(install.returncode, 0, install.stderr)
        (self.home / ".missing").unlink()
        (self.home / ".conflict").unlink()
        (self.home / ".conflict").write_text("local file\n")

        result = self.run_ghar("install", "--status", "status-repo")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("ok\t{}".format(self.home / ".installed"), result.stdout)
        self.assertIn("no such file\t{}".format(self.home / ".missing"), result.stdout)
        self.assertIn("file\t{}".format(self.home / ".conflict"), result.stdout)
        self.assertIn("error: status-repo is not fully installed", result.stdout)

    def test_uninstall_removes_owned_links_and_reports_repeated_removal(self):
        self.create_repo("shell", {".shellrc": "settings\n"})
        install = self.run_ghar("install", "shell")
        self.assertEqual(install.returncode, 0, install.stderr)
        target = self.home / ".shellrc"

        first = self.run_ghar("uninstall", "shell")
        second = self.run_ghar("uninstall", "shell")

        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertFalse(target.exists())
        self.assertIn("ok\t{}".format(target), first.stdout)
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertIn("{} no such file".format(target), second.stdout)
        self.assertIn("error: shell is not installed", second.stdout)

    def test_uninstall_preserves_files_and_foreign_symlinks(self):
        self.create_repo(
            "local-targets",
            {".local-file": "repository\n", ".local-link": "repository\n"},
        )
        file_target = self.home / ".local-file"
        file_target.write_text("local\n")
        foreign_source = self.workspace / "foreign-target"
        foreign_source.write_text("foreign\n")
        link_target = self.home / ".local-link"
        link_target.symlink_to(foreign_source)

        result = self.run_ghar("uninstall", "local-targets")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(file_target.read_text(), "local\n")
        self.assertTrue(link_target.is_symlink())
        self.assertEqual(Path(os.readlink(str(link_target))), foreign_source)
        self.assertIn("{} is not a ghar link".format(file_target), result.stdout)
        self.assertIn("can't handle non-ghar symlinks", result.stdout)


class GitCommandTests(GharIntegrationTest):
    def test_status_reports_clean_dirty_and_non_git_repositories(self):
        clean_repo = self.create_repo("clean", {".cleanrc": "clean\n"})
        self.commit_all(clean_repo)
        dirty_repo = self.create_repo("dirty", {".dirtyrc": "original\n"})
        self.commit_all(dirty_repo)
        (dirty_repo / ".dirtyrc").write_text("changed\n")
        non_git = self.ghar_root / "not-git"
        non_git.mkdir()
        (non_git / ".notes").write_text("notes\n")

        all_result = self.run_ghar("status")
        selected_result = self.run_ghar("status", "clean")

        self.assertEqual(all_result.returncode, 0, all_result.stderr)
        self.assertIn("clean: clean", all_result.stdout)
        self.assertIn("dirty: dirty", all_result.stdout)
        self.assertIn("not-git is not a git repo", all_result.stdout)
        self.assertEqual(selected_result.returncode, 0, selected_result.stderr)
        self.assertIn("clean: clean", selected_result.stdout)
        self.assertNotIn("dirty:", selected_result.stdout)
        self.assertNotIn("not-git", selected_result.stdout)

    def test_pull_updates_from_a_local_remote(self):
        remote = self.workspace / "remote.git"
        self.git(self.workspace, "init", "--bare", "-q", str(remote))

        seed = self.workspace / "seed"
        seed.mkdir()
        self.git(seed, "init", "-q")
        (seed / ".pulledrc").write_text("version one\n")
        self.commit_all(seed, "initial")
        self.git(seed, "remote", "add", "origin", str(remote))
        self.git(seed, "push", "-q", "-u", "origin", "HEAD")

        clone = self.ghar_root / "pulled"
        self.git(self.ghar_root, "clone", "-q", str(remote), str(clone))
        (seed / ".pulledrc").write_text("version two\n")
        self.commit_all(seed, "update")
        self.git(seed, "push", "-q")

        result = self.run_ghar("pull")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("pulled:", result.stdout)
        self.assertNotIn("b'", result.stdout)
        self.assertEqual((clone / ".pulledrc").read_text(), "version two\n")


class AddCommandTests(GharIntegrationTest):
    def test_add_clones_a_local_repository_with_the_requested_name(self):
        remote = self.workspace / "add-remote.git"
        self.git(self.workspace, "init", "--bare", "-q", str(remote))

        seed = self.workspace / "add-seed"
        seed.mkdir()
        self.git(seed, "init", "-q")
        (seed / ".addedrc").write_text("added\n")
        self.commit_all(seed, "initial")
        self.git(seed, "remote", "add", "origin", str(remote))
        self.git(seed, "push", "-q", "-u", "origin", "HEAD")

        result = self.run_ghar("add", str(remote), "added-dotfiles")

        clone = self.ghar_root / "added-dotfiles"
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(
            "git clone {} added-dotfiles".format(remote),
            result.stdout,
        )
        self.assertTrue((clone / ".git").is_dir())
        self.assertEqual((clone / ".addedrc").read_text(), "added\n")

        listed = self.run_ghar("list")
        self.assertEqual(listed.returncode, 0, listed.stderr)
        self.assertIn("added-dotfiles", listed.stdout.splitlines())


if __name__ == "__main__":
    unittest.main()
