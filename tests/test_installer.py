"""Tests for the installation script."""
import subprocess
import sys
import unittest
from typing import Any


class InstallerTests(unittest.TestCase):
    def test_installer_dry_run(self) -> None:
        result = subprocess.run(
            [sys.executable, "scripts/install.py", "--dry-run", "--local"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Dry run complete.", result.stdout)


if __name__ == "__main__":
    unittest.main()
