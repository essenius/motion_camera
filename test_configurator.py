import unittest
from unittest.mock import patch, mock_open
import time as Time
from configurator import Configurator
from io import StringIO
import logging 
from types import SimpleNamespace

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
            with self.assertRaises(SystemExit):
                Configurator.get_parser_options()

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

    def test_configurator_set_logging(self):
        with patch("logging.basicConfig") as mock_basic_config:
            options = SimpleNamespace(log="DEBUG", verbose=False)
            Configurator.set_logging(options)
            FORMAT = "%(asctime)s %(name)-15s %(levelname)-8s: %(message)s"
            mock_basic_config.assert_called_once_with(level=logging.DEBUG, format=FORMAT)
            options.log = "INFO"
            Configurator.set_logging(options)
            mock_basic_config.assert_called_with(level=logging.INFO, format=FORMAT)
            options.log = "WARNING"
            Configurator.set_logging(options)
            mock_basic_config.assert_called_with(level=logging.WARNING, format=FORMAT)
            options.log = "ERROR"
            Configurator.set_logging(options)
            mock_basic_config.assert_called_with(level=logging.ERROR, format=FORMAT)
            options.log = "CRITICAL"
            Configurator.set_logging(options)
            mock_basic_config.assert_called_with(level=logging.CRITICAL, format=FORMAT)

            # now check if another option causes an error with a message
            options.log = "BOGUS"
            with self.assertRaises(SystemExit) as context:
                Configurator.set_logging(options)
            self.assertGreaterEqual(str(context.exception).find("Unrecognized log level 'BOGUS' -- must be one of: critical | error | warning | info | debug"), 0)
            

