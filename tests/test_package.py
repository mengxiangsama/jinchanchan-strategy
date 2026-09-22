import importlib.util
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "skills" / "jinchanchan-strategy"
spec = importlib.util.spec_from_file_location("validator", ROOT / "scripts" / "validate.py")
validator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validator)


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
            expected = {p.relative_to(SOURCE) for p in SOURCE.rglob("*") if p.is_file()}
            actual = {p.relative_to(installed) for p in installed.rglob("*") if p.is_file()}
            self.assertEqual(expected, actual)
            for relative in expected:
                self.assertEqual((SOURCE / relative).read_bytes(), (installed / relative).read_bytes())
            self.assertTrue(validator.validate(installed))

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
