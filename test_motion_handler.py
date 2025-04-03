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
from motion_handler import MotionHandler
from io import StringIO
import logging 
from types import SimpleNamespace
from datetime import datetime
import numpy
import time

class TestMotionHandler(unittest.TestCase):

    def setUp(self):
        # Common mocks
        self.mock_camera_handler = MagicMock()
        self.mock_camera_handler.capture_frame.return_value = numpy.array([[0, 1], [2, 3]])  

        self.mock_video_recorder = MagicMock()
        self.mock_video_recorder.recording_active = False
        self.mock_cv2 = MagicMock()
        self.mock_cv2.subtract.return_value = numpy.array([[10, 10], [10, 10]])
        self.mock_cv2.cvtColor.return_value = numpy.array([[10, 11], [12, 13]])
        self.mock_cv2.putText.return_value = None
        self.mock_cv2.COLOR_RGB2GRAY = 42

        # Mock options
        self.mock_options = MagicMock()
        self.mock_options.mse_threshold = 12
        self.mock_options.motion_interval = 10
        self.mock_options.frame_size = (800, 600)

        # Create MotionHandler instance
        self.motion_handler = MotionHandler(
            self.mock_camera_handler,
            self.mock_video_recorder,
            self.mock_options,
            self.mock_cv2
        )

    def test_motion_handler_init(self):
        self.assertEqual(self.motion_handler.mse_motion_threshold, 12)
        self.assertEqual(self.motion_handler.motion_interval, 10)
        self.assertEqual(self.motion_handler.camera_handler, self.mock_camera_handler)
        self.assertEqual(self.motion_handler.video_recorder, self.mock_video_recorder)
        self.assertEqual(self.motion_handler.cv2, self.mock_cv2)
        self.assertFalse(self.motion_handler.storage_enabled, "storage_enabled should be False by default")
        self.assertIsNone(self.motion_handler.start_video_thread, "start_video_thread should be None by default")
        self.assertFalse(self.motion_handler.terminate, "terminate should be False by default")
        self.assertFalse(self.motion_handler.motion_detected, "motion_detected should be False by default")
        self.assertIsNone(self.motion_handler.last_motion_time, "last_motion_time should be None by default")

    def test_motion_handler_mean_squared_error(self):
        frame1 = numpy.array([[0, 0], [0, 0]])
        frame2 = numpy.array([[10, 10], [10, 10]])
        
        mse = self.motion_handler.mean_squared_error(frame1, frame2)
        self.assertEqual(mse, 100.0)  # 4 pixels, each with a difference of 10, so 10^2 * 4 / 4 = 100.0
        self.mock_cv2.subtract.assert_called_once_with(frame1, frame2)

    @patch("motion_handler.Thread")
    def test_motion_handler_handle_frame(self, mock_thread_class):
        mock_thread_instance = MagicMock()
        mock_thread_class.return_value = mock_thread_instance

        self.motion_handler.storage_enabled = True
        self.motion_handler.frame_count = 0
        self.motion_handler.reference_frame = None
        for i in range(4):
            self.motion_handler.handle_frame()
            self.assertEqual(self.motion_handler.frame_count, i + 1, f"frame_count should be {i+1} after handle_frame {i}")
            self.assertIsNone(self.motion_handler.reference_frame, f"reference_frame should still be None after handle_frame {i}")
        self.motion_handler.handle_frame()
        self.assertEqual(self.motion_handler.frame_count, 0, "frame_count should be reset after 5th handle_frame")
        self.assertIsNotNone(self.motion_handler.reference_frame, "reference_frame should be set after 5th handle_frame")
        self.assertFalse(self.motion_handler.motion_detected, "Still no motion detected after 4 cycles")
        self.mock_cv2.subtract.assert_not_called() # as mean_squared_error is not called
        self.assertFalse(self.motion_handler.motion_detected, "motion_detected should still be False")

        for i in range(5):
            self.motion_handler.handle_frame()
        self.assertTrue(self.motion_handler.motion_detected, "motion_detected should be True after 10th handle_frame")
        self.assertIsNone(self.motion_handler.last_motion_time, "last_motion_time should still be None after 10th handle_frame")
        self.motion_handler.handle_frame()
        self.assertIsNotNone(self.motion_handler.last_motion_time, "last_motion_time should be set after 11th handle_frame (handling motion detected in 10th)")
        self.mock_cv2.putText.assert_called_once()
        self.assertFalse(self.motion_handler.motion_detected, "motion_detected should be False after handling it")
        mock_thread_class.assert_called_once_with(target=self.motion_handler.store_video)
        mock_thread_instance.start.assert_called_once()
        
    def test_motion_handler_store_video(self):

        # The first call to is_segment_duration_exceeded should return False, so we start recording.
        # The second should stop it. With the third and fourth, we test the other conditions in recording_should_stop
        self.mock_video_recorder.is_segment_duration_exceeded.side_effect = [False, True, False, False]
        self.motion_handler.terminate = False

        self.motion_handler.last_motion_time = time.time()
        self.motion_handler.store_video()
        self.mock_video_recorder.start_recording.assert_called_once()
        self.mock_video_recorder.stop_recording.assert_called_once()
        self.mock_video_recorder.write_frame.assert_called_once()

        # simulate long time of no motion, so the recording should stop right away
        self.motion_handler.last_motion_time = time.time() - self.motion_handler.motion_interval - 1
        self.motion_handler.store_video()
        # No frame should be written
        self.mock_video_recorder.write_frame.assert_called_once()

        self.motion_handler.last_motion_time = time.time()
        
        # Force termination
        self.motion_handler.terminate = True
        self.motion_handler.store_video()
        # No frame should be written as we want the recording to stop
        self.mock_video_recorder.write_frame.assert_called_once()

    @patch("motion_handler.Synchronizer.wait_for_next_sampling")
    def test_motion_handler_capture_camera_feed(self, mock_wait_for_next_sampling):

        # make the first call to wait_for_next_sampling set the terminate flag, so we exit the loop
        def side_effect(*args, **kwargs):
            self.motion_handler.terminate = True
            return time.time() 
        
        mock_wait_for_next_sampling.side_effect = side_effect
        self.motion_handler.capture_camera_feed()
        self.mock_camera_handler.capture_frame.assert_called_once()
        self.assertEqual(self.motion_handler.frame_count, 1, "frame_count should not be reset after capture_camera_feed")
