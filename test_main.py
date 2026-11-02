"""Offline application behavior checks."""

import os
import unittest
from unittest.mock import patch

from main import handle


class MainTest(unittest.TestCase):
    def test_defaults_and_platform_arguments(self):
        with patch.dict(os.environ, {}, clear=True):
            result = handle("job-1", "context", "header", "body")
        self.assertEqual(result, (True, "Example pipeline completed", "Example pipeline completed"))

    def test_explicit_configuration(self):
        with patch.dict(os.environ, {"SCRIPT_NAME": "example", "ENV_MODE": "test"}, clear=True):
            self.assertTrue(handle()[0])

    def test_unknown_script_fails(self):
        with patch.dict(os.environ, {"SCRIPT_NAME": "missing"}, clear=True):
            with self.assertRaisesRegex(ValueError, "SCRIPT_NAME"):
                handle()

    def test_example_rejects_other_modes(self):
        for mode in ("prod", "", "TEST"):
            with self.subTest(mode=mode), patch.dict(os.environ, {"ENV_MODE": mode}, clear=True):
                with self.assertRaisesRegex(ValueError, "ENV_MODE"):
                    handle()


if __name__ == "__main__":
    unittest.main()
