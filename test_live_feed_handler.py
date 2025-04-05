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
from live_feed_handler import LiveFeedHandler
import time

class TestLiveFeedHandler(unittest.TestCase):
    """Test the LiveFeedHandler class and its methods."""

    def setUp(self):
        """Mock the logger the CameraHandler."""
        # we need to patch the logger here as it is instantiated in the __init__ method
        # We can't use the @patch decorator in the setup method
        self.patcher_logger = patch("live_feed_handler.logging.getLogger")
        self.mock_get_logger = self.patcher_logger.start()
        self.mock_logger = MagicMock()
        self.mock_get_logger.return_value = self.mock_logger
        
        self.mock_camera_handler = MagicMock()
        self.mock_camera_handler.frame = "mock_frame"
        self.mock_cv2 = MagicMock()
        self.mock_cv2.imencode.return_value = (True, MagicMock(tobytes=MagicMock(return_value=b"image_content")))
        self.live_feed_handler = LiveFeedHandler(self.mock_camera_handler, self.mock_cv2)

    def tearDown(self):
        """Stop all patchers to clean up the test environment."""
        self.patcher_logger.stop()

    @patch("live_feed_handler.Synchronizer.wait_for_next_sampling")
    def test_live_feed_handler_happy_path(self, mock_wait_for_next_sampling):
        """Test the happy path of the live feed handler."""
        # make the first call to wait_for_next_sampling set the terminate flag, so we exit the loop
        def side_effect(*args, **kwargs):            
            self.live_feed_handler.terminate = True
            return time.time() 
        
        mock_wait_for_next_sampling.side_effect = side_effect
        
        self.assertFalse(self.live_feed_handler.terminate, "terminate should be False by default")
        feed_generator = self.live_feed_handler.generate_feed()
        result = next(feed_generator)
        self.assertTrue(result.startswith(b"--frame\r\nContent-Type: image/jpeg\r\n\r\n"))
        self.assertTrue(result.endswith(b"\r\n"))
        self.assertIn(b"image_content", result)
        self.assertFalse(self.live_feed_handler.terminate, "terminate should still be False as the wait is after the yield")
        self.mock_cv2.imencode.assert_called_once_with(".jpg", self.mock_camera_handler.frame)
        mock_wait_for_next_sampling.assert_not_called()
        message = next(feed_generator)
        self.assertEqual(message, b"--frame\r\nContent-Type: text/plain\r\n\r\nLive feed terminated.\r\n\r\n")
        self.assertTrue(self.live_feed_handler.terminate, "terminate should be True after the first wait (ending the loop)")
        mock_wait_for_next_sampling.assert_called_once()
        with self.assertRaises(StopIteration):
            next(feed_generator)

    def test_live_feed_handler_unhappy_path(self):
        """Test the unhappy path of the live feed handler (i.e. an exception occurs)."""
        # Simulate an exception in the live feed
        self.live_feed_handler.cv2.imencode.side_effect = Exception("Test exception")

        self.assertFalse(self.live_feed_handler.terminate, "terminate should be False by default")

        feed_generator = self.live_feed_handler.generate_feed()
        # the first call to next should yield the error message
        error = next(feed_generator)
        self.assertEqual(error, (b"--frame\r\nContent-Type: text/plain\r\n\r\nLive feed terminated due to error: Test exception.\r\n\r\n"))
        with self.assertRaises(StopIteration):
            next(feed_generator)

        self.mock_logger.error.assert_called_once()
        self.mock_logger.error.assert_called_once_with("Live feed error: Test exception.")
        self.mock_logger.info.assert_called_once_with("Live feed terminated")
        self.assertFalse(self.live_feed_handler.terminate, "terminate should not be True after an exception")

