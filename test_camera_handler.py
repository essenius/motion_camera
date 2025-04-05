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
from unittest.mock import MagicMock
from camera_handler import CameraHandler

class TestCameraHandler(unittest.TestCase):
    """Test the CameraHandler class and its methods."""

    def test_camera_handler_happy_path(self):
        """Test the CameraHandler initialization and happy path."""
        mock_cv2 = MagicMock()
        mock_cv2.INTER_NEAREST = 0  # Use the actual value of INTER_NEAREST (typically 0)
        mock_cv2.resize.return_value = "mock_resized_frame"

        mock_camera_class = MagicMock()
        mock_camera_instance = MagicMock()
        mock_camera_class.return_value = mock_camera_instance

        mock_camera_instance.sensor_modes = [
            {'size': (640, 480)},
            {'size': (1920, 1080)},
            {'size': (1280, 720)},
        ]

        mock_camera_instance.create_preview_configuration.return_value = "mock_config"
        mock_camera_instance.start.return_value = None
        mock_camera_instance.stop.return_value = None

        # Mock options with a frame_size
        mock_options = MagicMock()
        mock_options.frame_size = (800, 600)

        handler = CameraHandler(mock_camera_class, mock_options, mock_cv2)

        mock_camera_class.assert_called_once()
        mock_camera_instance.create_preview_configuration.assert_called_once_with(
            main={"size": (1280, 720), "format": "RGB888"}
        )
        mock_camera_instance.start.assert_called_once_with("mock_config")
        self.assertEqual(handler.full_size, (1280, 720)) 

        # Test the capture_frame method
        mock_camera_instance.capture_array.return_value = "mock_full_frame"
        captured_frame = handler.capture_frame()
        mock_cv2.resize.assert_called_once_with(
            src="mock_full_frame", dsize=(800, 600), interpolation=mock_cv2.INTER_NEAREST
        )
        self.assertEqual(captured_frame, "mock_resized_frame")

       # Test the __del__ method
        del handler
        mock_camera_instance.stop.assert_called_once()
        mock_camera_instance.close.assert_called_once()

    def test_camera_handler_too_large_frame_size(self):
        """Test the CameraHandler initialization with a too large frame size."""
        mock_cv2 = MagicMock()
        mock_camera_class = MagicMock()
        mock_camera_instance = MagicMock()
        mock_camera_class.return_value = mock_camera_instance

        mock_camera_instance.sensor_modes = [
            {'size': (640, 480)},
            {'size': (1920, 1080)},
            {'size': (1280, 720)},
        ]

        mock_camera_instance.create_preview_configuration.return_value = "mock_config"
        mock_camera_instance.start.return_value = None
        mock_camera_instance.stop.return_value = None

        # Mock options with a frame_size
        mock_options = MagicMock()
        mock_options.frame_size = (8000, 6000)

        with self.assertRaisesRegex(SystemExit, "Requested frame size \(8000, 6000\) is larger than the maximum supported size \(1920, 1080\)."):
            _ = CameraHandler(mock_camera_class, mock_options, mock_cv2)

