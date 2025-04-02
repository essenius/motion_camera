import unittest
from unittest.mock import patch, MagicMock
import time as Time
from camera_handler import CameraHandler
from io import StringIO
import logging 
from types import SimpleNamespace

class TestCameraHandler(unittest.TestCase):


    def test_camera_handler_happy_path(self):

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

