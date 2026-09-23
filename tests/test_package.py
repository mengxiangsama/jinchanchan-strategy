import importlib.util
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "skills" / "jinchanchan-strategy"
spec = importlib.util.spec_from_file_location("validator", ROOT / "scripts" / "validate.py")
validator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validator)
installer_spec = importlib.util.spec_from_file_location("installer", ROOT / "scripts" / "install.py")
installer = importlib.util.module_from_spec(installer_spec)
installer_spec.loader.exec_module(installer)


class PackageTests(unittest.TestCase):
    def run_install(self, directory):
        return subprocess.run([sys.executable, str(ROOT / "scripts" / "install.py"),
                               "--destination", str(directory)], cwd=tempfile.gettempdir(),
                              capture_output=True, text=True)

    def test_package_valid(self):
        self.assertTrue(validator.validate())

    def test_install_matches_source_with_spaces(self):
        with tempfile.TemporaryDirectory(prefix="jcc-install-") as temporary:
            root = Path(temporary) / "skills with spaces"
            result = self.run_install(root)
            self.assertEqual(result.returncode, 0, result.stderr)
            installed = root / SOURCE.name
            ignored = {"__pycache__", ".DS_Store", ".jinchanchan-cache"}
            expected = {p.relative_to(SOURCE) for p in SOURCE.rglob("*") if p.is_file()
                        and not ignored.intersection(p.relative_to(SOURCE).parts)}
            actual = {p.relative_to(installed) for p in installed.rglob("*") if p.is_file()}
            self.assertEqual(expected, actual)
            for relative in expected:
                self.assertEqual((SOURCE / relative).read_bytes(), (installed / relative).read_bytes())
            self.assertTrue(validator.validate(installed))
            cache = subprocess.run([sys.executable, str(installed / "scripts" / "cache.py"),
                                    "--cache-dir", str(root / "empty cache"), "list"],
                                   capture_output=True, text=True)
            self.assertEqual(cache.returncode, 0, cache.stderr)
            self.assertFalse((root / "empty cache").exists())

    def test_existing_install_untouched(self):
        with tempfile.TemporaryDirectory(prefix="jcc-existing-") as temporary:
            root = Path(temporary)
            target = root / SOURCE.name
            target.mkdir()
            marker = target / "custom.txt"
            marker.write_text("keep user edits", encoding="utf-8")
            self.assertNotEqual(self.run_install(root).returncode, 0)
            self.assertEqual(marker.read_text(), "keep user edits")
            self.assertEqual(list(target.iterdir()), [marker])

    def test_install_excludes_local_cache(self):
        with tempfile.TemporaryDirectory(prefix="jcc-cache-install-") as temporary:
            source = Path(temporary) / "source" / SOURCE.name
            shutil.copytree(SOURCE, source)
            private_cache = source / ".jinchanchan-cache"
            private_cache.mkdir()
            (private_cache / "local.json").write_text("local evidence", encoding="utf-8")
            with patch.object(installer, "SOURCE", source):
                target = installer.install(Path(temporary) / "installed")
            self.assertFalse((target / ".jinchanchan-cache").exists())
            self.assertTrue((target / "scripts" / "cache.py").is_file())

    @unittest.skipIf(sys.platform == "win32", "Symlink creation requires extra Windows privileges")
    def test_dangling_symlink_not_followed(self):
        with tempfile.TemporaryDirectory(prefix="jcc-symlink-") as temporary:
            root = Path(temporary)
            target = root / SOURCE.name
            target.symlink_to(root / "missing")
            self.assertNotEqual(self.run_install(root).returncode, 0)
            self.assertTrue(target.is_symlink())
            self.assertFalse((root / "missing").exists())

    def test_broken_reference_rejected(self):
        with tempfile.TemporaryDirectory(prefix="jcc-links-") as temporary:
            target = Path(temporary) / SOURCE.name
            shutil.copytree(SOURCE, target)
            (target / "references" / "research.md").unlink()
            with self.assertRaises(ValueError):
                validator.validate(target)

    def test_empty_destination_rejected(self):
        self.assertNotEqual(self.run_install("").returncode, 0)


if __name__ == "__main__":
    unittest.main()
