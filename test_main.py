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
from unittest.mock import patch, MagicMock
from motion_camera import main_helper

class TestMain(unittest.TestCase):

    def setUp(self):
        # Create patchers for all the mocks
        self.motion_camera_patcher = patch("motion_camera.MotionCamera")
        self.set_logging_patcher = patch("motion_camera.Configurator.set_logging")
        self.validate_directory_patcher = patch("motion_camera.Configurator.validate_directory")
        self.get_parser_options_patcher = patch("motion_camera.Configurator.get_parser_options")
        self.get_logger_patcher = patch("logging.getLogger")
        self.sys_argv_patcher = patch("sys.argv", [])

        # Start the patchers
        self.mock_motion_camera = self.motion_camera_patcher.start()
        self.mock_set_logging = self.set_logging_patcher.start()
        self.mock_validate_directory = self.validate_directory_patcher.start()
        self.mock_get_parser_options = self.get_parser_options_patcher.start()
        self.mock_get_logger = self.get_logger_patcher.start()
        self.mock_sys_argv = self.sys_argv_patcher.start()

        # Configure the mocks
        self.mock_options = MagicMock()
        self.mock_options.port = 5000
        self.mock_options.directory = "/home/user/videos"
        self.mock_options.log_level = "info"
        self.mock_unknown = ['unknown', 'unknown']
        self.mock_get_parser_options.return_value = (self.mock_options, self.mock_unknown)

        self.mock_motion_camera.__name__ = "MotionCamera"
        self.mock_app = MagicMock()
        self.mock_motion_camera.return_value = self.mock_app
        self.mock_app.__enter__.return_value = self.mock_app
        self.mock_app.__exit__.return_value = None

        self.mock_logger = MagicMock()
        self.mock_get_logger.return_value = self.mock_logger

    def tearDown(self):
        # Stop all patchers
        self.motion_camera_patcher.stop()
        self.set_logging_patcher.stop()
        self.validate_directory_patcher.stop()
        self.get_parser_options_patcher.stop()
        self.get_logger_patcher.stop()
        self.sys_argv_patcher.stop()


    def test_motion_camera_main_helper_happy_path(self):

        with patch("sys.argv", ["motion_camera.py", "--port", "5000", "--directory", "/home/user/videos", "-l", "info"]):
            main_helper()

        self.mock_get_parser_options.assert_called_once()
        self.mock_motion_camera.assert_called_once_with(self.mock_options)
        self.mock_app.terminate.assert_not_called()  # No exception raised in this test
        self.mock_logger.error.assert_not_called()
        self.mock_logger.info.assert_called_with("MotionCamera terminated.")
        self.mock_app.run.assert_called_once()

    def test_motion_camera_main_helper_systemexit_message(self):
        def side_effect(*args, **kwargs):
            raise SystemExit("Validation failed.")
        
        self.mock_validate_directory.side_effect = side_effect
        with patch("sys.argv", []):
            with self.assertRaises(SystemExit):
                main_helper()
        self.mock_logger.error.assert_called_with("Terminating. Validation failed.")
        self.mock_logger.info.assert_called_with("MotionCamera terminated.")
        self.mock_validate_directory.side_effect = None
