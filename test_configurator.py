# Copyright 2025 Rik Essenius
#
#   Licensed under the Apache License, Version 2.0 (the "License"); you may not use this file
#   except in compliance with the License. You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software distributed under the License
#   is distributed on an "AS IS" BASIS WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and limitations under the License.

import unittest
from unittest.mock import patch, mock_open, MagicMock
from configurator import Configurator, ValidateNumber
from io import StringIO
import logging 
from types import SimpleNamespace
from contextlib import ExitStack
import argparse
import os

class TestConfigurator(unittest.TestCase):
    def test_configurator_get_parser_options_defaults(self):
        test_args = ["motion_camera.py"]
        with patch("sys.argv", test_args):
            options, unknown_options = Configurator.get_parser_options()
            self.assertEqual(options.directory, "/media/cam")
            self.assertEqual(options.motion_interval, 10)
            self.assertEqual(options.max_duration, 600)
            self.assertEqual(options.log, "warning")
            self.assertEqual(options.port, 5000)
            self.assertEqual(options.rate, 15)
            self.assertEqual(options.frame_size, (800, 600))
            self.assertEqual(options.mse_threshold, 15.0)
            self.assertFalse(options.verbose)
            self.assertFalse(options.no_auto_start)
            self.assertEqual(unknown_options, [])

    def test_configurator_get_parser_options_with_args(self):
        test_args = [
            "motion_camera.py",
            "--directory", "/tmp/cam",
            "--motion-interval", "5",
            "--max-duration", "300",
            "--log", "info",
            "--port", "8080",
            "--rate", "30",
            "--frame-size", "640x480",
            "--mse-threshold", "10.0",
            "--verbose",
            "--no-auto-start",
            "--extra-option", "value"
        ]
        with patch("sys.argv", test_args):
            options, unknown_options = Configurator.get_parser_options()
            self.assertEqual(options.config, "motion_camera.conf")
            self.assertEqual(options.directory, "/tmp/cam")
            self.assertEqual(options.motion_interval, 5)
            self.assertEqual(options.max_duration, 300)
            self.assertEqual(options.log, "info")
            self.assertEqual(options.port, 8080)
            self.assertEqual(options.rate, 30)
            self.assertEqual(options.frame_size, (640, 480))
            self.assertEqual(options.mse_threshold, 10.0)
            self.assertTrue(options.verbose)
            self.assertTrue(options.no_auto_start)
            self.assertEqual(unknown_options, ["--extra-option", "value"])

    def test_configurator_get_parser_options_invalid_size(self):
        test_args = [
            "motion_camera.py",
            "--frame-size", "invalid_size"
        ]

        with patch("sys.argv", test_args):
            with patch("sys.stderr", new_callable=StringIO) as mock_stderr:
                with self.assertRaises(SystemExit):
                    Configurator.get_parser_options()
                error_message = mock_stderr.getvalue()
                self.assertIn("Invalid frame size: 'invalid_size'", error_message)

                test_args[2] = "0x-1"
                with self.assertRaises(SystemExit):
                    Configurator.get_parser_options()
                error_message = mock_stderr.getvalue()
                self.assertIn("Invalid frame size: '0x-1'", error_message)


    def test_configurator_get_parser_options_with_config_file(self):
        mock_config = """
        [DEFAULT]
        config = bogus.conf
        directory = /mock/directory
        motion-interval = 20
        max_duration = 120
        log = debug
        port = 8081
        rate = 25
        frame-size = 1024 x 768
        mse-threshold = 12.5
        verbose = true
        no-auto-start = true
        """

        # Patch the open() function to return the mock configuration
        with patch("builtins.open", mock_open(read_data=mock_config)):
            with patch("sys.argv", ["motion_camera.py", "-l", "INFO", "--no-verbose" ]):
                options, unknown_options = Configurator.get_parser_options()

                # Assertions to verify the parsed configuration
                self.assertEqual(options.config, "motion_camera.conf") # ignore config file 
                self.assertEqual(options.directory, "/mock/directory")
                self.assertEqual(options.motion_interval, 20)
                self.assertEqual(options.max_duration, 120)
                self.assertEqual(options.log, "INFO") #override config file
                self.assertEqual(options.port, 8081)
                self.assertEqual(options.rate, 25)
                self.assertEqual(options.frame_size, (1024, 768))
                self.assertEqual(options.mse_threshold, 12.5)
                self.assertFalse(options.verbose) # override config file
                self.assertTrue(options.no_auto_start)        
                self.assertEqual(unknown_options, [])

    def test_configurator_get_parser_options_mutual_exclusive(self):
        # Patch the open() function to return the mock configuration
        with patch("sys.argv", ["motion_camera.py", "--verbose", "--no-verbose" ]):
            with patch("sys.stderr", new_callable=StringIO) as mock_stderr:
                with self.assertRaises(SystemExit) as context:
                    _ = Configurator.get_parser_options()
                self.assertEqual(context.exception.code, 2)
                error_message = mock_stderr.getvalue()
                self.assertIn("not allowed with argument", error_message)

    def test_configurator_get_parser_options_too_low_value(self):
        # Patch the open() function to return the mock configuration
        with patch("sys.argv", ["motion_camera.py", "--motion-interval", "0" ]):
            with patch("sys.stderr", new_callable=StringIO) as mock_stderr:
                with self.assertRaises(SystemExit) as context:
                    _ = Configurator.get_parser_options()
                self.assertEqual(context.exception.code, 2)
                error_message = mock_stderr.getvalue()
                self.assertIn("Expected type int not less than 1 but got 0", error_message)

    def test_configurator_get_parser_options_too_high_value(self):
        # Patch the open() function to return the mock configuration
        with patch("sys.argv", ["motion_camera.py", "--mse-threshold", "100000" ]):
            with patch("sys.stderr", new_callable=StringIO) as mock_stderr:
                with self.assertRaises(SystemExit) as context:
                    _ = Configurator.get_parser_options()
                self.assertEqual(context.exception.code, 2)
                error_message = mock_stderr.getvalue()
                self.assertIn("Expected type float between 1 and 65025 but got 100000", error_message)

    def test_configurator_get_parser_options_invalid_value(self):
        # Patch the open() function to return the mock configuration
        with patch("sys.argv", ["motion_camera.py", "--mse-threshold", "q" ]):
            with patch("sys.stderr", new_callable=StringIO) as mock_stderr:
                with self.assertRaises(SystemExit) as context:
                    _ = Configurator.get_parser_options()
                self.assertEqual(context.exception.code, 2)
                error_message = mock_stderr.getvalue()
                self.assertIn("Expected type float between 1 and 65025 but got q", error_message)

    @patch.dict("os.environ", {}, clear=True)
    def test_configurator_set_logging(self):
        with patch("logging.basicConfig") as mock_basic_config:
            options = SimpleNamespace(log="DEBUG", verbose=False)
            Configurator.set_logging(options)
            FORMAT = "%(asctime)s %(name)-15s %(levelname)-8s: %(message)s"
            mock_basic_config.assert_called_once_with(level=logging.DEBUG, format=FORMAT)
            self.assertIsNone(os.environ.get(Configurator.LIBCAMERA_LOG_LEVELS))
            options.log = "INFO"
            Configurator.set_logging(options)
            mock_basic_config.assert_called_with(level=logging.INFO, format=FORMAT)
            self.assertIsNone(os.environ.get(Configurator.LIBCAMERA_LOG_LEVELS))
            options.log = "WARNING"
            Configurator.set_logging(options)
            mock_basic_config.assert_called_with(level=logging.WARNING, format=FORMAT)
            self.assertEqual(os.environ.get(Configurator.LIBCAMERA_LOG_LEVELS), "RPI:WARN,Camera:WARN,RPiSdn:WARN")
            del os.environ[Configurator.LIBCAMERA_LOG_LEVELS]
            options.log = "ERROR"
            Configurator.set_logging(options)
            mock_basic_config.assert_called_with(level=logging.ERROR, format=FORMAT)
            self.assertEqual(os.environ.get(Configurator.LIBCAMERA_LOG_LEVELS), "RPI:ERROR,Camera:ERROR,RPiSdn:ERROR")
            del os.environ[Configurator.LIBCAMERA_LOG_LEVELS]
            options.log = "CRITICAL"
            Configurator.set_logging(options)
            mock_basic_config.assert_called_with(level=logging.CRITICAL, format=FORMAT)
            self.assertEqual(os.environ.get(Configurator.LIBCAMERA_LOG_LEVELS), "RPI:FATAL,Camera:FATAL,RPiSdn:FATAL")
            del os.environ[Configurator.LIBCAMERA_LOG_LEVELS]

            # now check if another option causes an error with a message
            options.log = "BOGUS"
            with self.assertRaises(SystemExit) as context:
                Configurator.set_logging(options)
            self.assertGreaterEqual(str(context.exception).find("Unrecognized log level 'BOGUS' -- must be one of: critical | error | warning | info | debug"), 0)
            self.assertIsNone(os.environ.get(Configurator.LIBCAMERA_LOG_LEVELS))
            


    def patch_os_functions(self, scenario=""):
        """Helper method to patch os functions."""

        def mock_abspath(path):
            """Mock function to simulate os.path.abspath."""
            if path.startswith("/"):
                return path
            return "/mock/" + path

        scenario_parts = [part.strip() for part in scenario.lower().split("&")]

        stack = ExitStack()
        stack.mocks = {}

        stack.mocks["path"] = {
            "exists": MagicMock(return_value = "non_existing" not in scenario_parts),
            "isdir": MagicMock(return_value = "not_a_directory" not in scenario_parts),
            "abspath": MagicMock(side_effect=mock_abspath),
    }
        for mock_name, mock_obj in stack.mocks["path"].items():
            stack.enter_context(patch(f"os.path.{mock_name}", mock_obj))

        stack.mocks["access"] = stack.enter_context(patch("os.access", return_value = "no_access" not in scenario_parts))
        available_mb = 0 if "no_space" in scenario_parts else 1024
        stack.mocks["statvfs"] = stack.enter_context(patch("os.statvfs", return_value = MagicMock(f_bavail = available_mb, f_frsize = 1024 * 1024)))
        stack.mocks["w_ok"] = stack.enter_context(patch("os.W_OK", 2))
        return stack

    def test_configurator_validate_directory_ok(self):
        # Test valid directory
        full_dir = "/mock/valid/directory"
        stack = self.patch_os_functions()
        with stack:
            result = Configurator.validate_directory("valid/directory")
            self.assertEqual(result, full_dir)
            mock_path = stack.mocks["path"]
            mock_path["exists"].assert_called_once_with(full_dir)
            mock_path["isdir"].assert_called_once_with(full_dir)
            stack.mocks["access"].assert_called_once_with(full_dir, stack.mocks["w_ok"])
            stack.mocks["statvfs"].assert_called_once_with(full_dir)

    def validate_directory_test_helper(self, scenario, expectations):
        stack = self.patch_os_functions(scenario=scenario)
        with stack:
            with self.assertRaises(SystemExit) as context:
                Configurator.validate_directory("/directory")
            self.assertIn(expectations["message"], str(context.exception))

            for mock_name, call_count in expectations["calls"].items():
                mock = stack.mocks["path"].get(mock_name) or stack.mocks.get(mock_name)
                if mock:
                    self.assertEqual(mock.call_count, call_count)

    def test_configurator_validate_directory_non_existing(self):
        self.validate_directory_test_helper(
            scenario="non_existing & not_a_directory & no_access & no_space",
            expectations={
                "message": "Directory '/directory' does not exist.",
                "calls": {"exists": 1, "isdir": 0, "access": 0, "statvfs": 0}
            }
        )

    def test_configurator_validate_directory_not_a_directory(self):
        self.validate_directory_test_helper(
            scenario = "not_a_directory & no_access",
            expectations = {
                "message": "File '/directory' is not a directory.",
                "calls": {"exists": 1, "isdir": 1, "access": 0, "statvfs": 0}
            }
        )

    def test_configurator_validate_directory_no_access(self):
        self.validate_directory_test_helper(
            scenario="no_access & no_space",
            expectations={
                "message": "Directory '/directory' is not writable. Please check permissions.",
                "calls": {"exists": 1, "isdir": 1, "access": 1, "statvfs": 0}
            }
        )

    def test_configurator_validate_directory_no_space(self):
        self.validate_directory_test_helper(
            scenario="no_space",
            expectations={
                "message": "Directory '/directory' has less than 1 GB of free space. Please ensure sufficient space is available.",
                "calls": {"exists": 1, "isdir": 1, "access": 1, "statvfs": 1}
            }
        )

    def test_validate_number_class(self):

        greater_only = ValidateNumber(max_value=100)
        self.assertIsNone(greater_only.min_value)
        self.assertEqual(greater_only.max_value, 100)
        self.assertEqual(greater_only.type, int)
        self.assertIn("high", greater_only.limit_type)
        self.assertNotIn("low", greater_only.limit_type)
        self.assertEqual(greater_only.condition, " not greater than 100")

        greater_only(99)
        # floats get converted to ints, and this is still converted to 100
        greater_only(100.999999)

        with self.assertRaises(argparse.ArgumentTypeError) as context:
            greater_only(101)
        self.assertEqual(str(context.exception), "Expected type int not greater than 100 but got 101.")

        with self.assertRaises(argparse.ArgumentTypeError) as context:
            greater_only("q")
        self.assertEqual(str(context.exception), "Expected type int not greater than 100 but got q.")

        no_limits = ValidateNumber()
        self.assertIsNone(no_limits.min_value)
        self.assertIsNone(no_limits.max_value)
        self.assertEqual(no_limits.type, int)
        self.assertEqual(no_limits.condition, "")
        self.assertEqual(no_limits.limit_type, [])
        no_limits(-1e99)
