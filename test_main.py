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


class CustomMock(MagicMock):
    @property
    def __name__(self):
        return "MotionCamera"
    
class TestMain(unittest.TestCase):

    @patch("motion_camera.MotionCamera")
    @patch("motion_camera.Configurator.set_logging") 
    @patch("motion_camera.Configurator.validate_directory")
    @patch("motion_camera.Configurator.get_parser_options") 
    def test_motion_camera_main_helper(self, mock_get_parser_options, mock_validate_directory, mock_logging, mock_motion_camera):
        mock_options = MagicMock()
        mock_options.port = 5000
        mock_options.directory = "/home/user/videos"
        mock_options.log_level = "info"
        mock_unknown = ['unknown', 'unknown']
        mock_get_parser_options.return_value = (mock_options, mock_unknown)

        print("Mock parser return value (configured):", mock_get_parser_options.return_value)

        mock_motion_camera.__name__ = "MotionCamera"
        mock_motion_camera_instance = MagicMock()
        print("mock_motion_camera_instance:", mock_motion_camera_instance)
        print("mock_motion_camera:", mock_motion_camera)
        mock_motion_camera.return_value = mock_motion_camera_instance
        mock_motion_camera_instance.__enter__.return_value = mock_motion_camera_instance
        mock_motion_camera_instance.__exit__.return_value = None
        mock_app = mock_motion_camera.return_value

        from motion_camera import main_helper

        with patch("sys.argv", ["motion_camera.py", "--port", "5000", "--directory", "/home/user/videos", "-l", "info"]):
            main_helper()

        mock_get_parser_options.assert_called_once()

        mock_motion_camera.assert_called_once_with(mock_options)

        mock_app.run.assert_called_once()

        mock_app.terminate.assert_not_called()  # No exception raised in this test




        
