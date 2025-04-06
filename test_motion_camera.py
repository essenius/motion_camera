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
from motion_camera import MotionCamera
from motion_camera import main_helper
import os
import sys
import signal
import time

sys.modules['flask'] = MagicMock()
sys.modules['picamera2'] = MagicMock()
sys.modules['cv2'] = MagicMock()
sys.modules['werkzeug'] = MagicMock()
sys.modules['werkzeug.serving'] = MagicMock()

class TestMotionCamera(unittest.TestCase):
    """Test the MotionCamera class and its methods."""

    @classmethod
    def setUpClass(cls):
        """Set up the test environment by mocking necessary components."""
        cls.mock_flask = sys.modules['flask']
        cls.mock_picamera2 = sys.modules['picamera2']
        cls.mock_cv2 = sys.modules['cv2']
        cls.mock_werkzeug = sys.modules['werkzeug']
        cls.mock_werkzeug_serving = sys.modules['werkzeug.serving']

    @classmethod
    def tearDownClass(cls):
        """Clean up the test environment by removing mocks from sys.modules."""
        del sys.modules['flask']
        del sys.modules['picamera2']
        del sys.modules['cv2']
        del sys.modules['werkzeug']
        del sys.modules['werkzeug.serving']


    def setUp(self):
        """Set up the test environment by patching necessary components."""
        # we need to patch the logger here as it is instantiated in the __init__ method
        # We can't use the @patch decorator in the setup method
        self.patcher_logger = patch("motion_camera.logging.getLogger")
        self.mock_get_logger = self.patcher_logger.start()
        self.mock_logger = MagicMock()
        self.mock_get_logger.return_value = self.mock_logger
        
        self.patcher_camera_handler = patch("motion_camera.CameraHandler")
        self.patcher_video_recorder = patch("motion_camera.VideoRecorder")
        self.patcher_motion_handler = patch("motion_camera.MotionHandler")
        self.patcher_live_feed_handler = patch("motion_camera.LiveFeedHandler")

        self.mock_camera_handler = self.patcher_camera_handler.start()
        self.mock_camera_handler.return_value.storage_enabled = False
        self.mock_video_recorder = self.patcher_video_recorder.start()
        self.mock_motion_handler = self.patcher_motion_handler.start()
        self.mock_live_feed_handler = self.patcher_live_feed_handler.start()
        self.mock_live_feed_handler.return_value.terminate = False

        # we don't patch motion_camera.make_server due to lazy loading
        self.patcher_make_server = patch("werkzeug.serving.make_server")
        self.mock_make_server = self.patcher_make_server.start()
        self.mock_server = MagicMock()
        self.mock_make_server.return_value = self.mock_server

        self.mock_options = MagicMock()
        self.mock_options.rate = 25.0
        self.mock_options.verbose = False
        self.mock_options.no_auto_start = False

    def tearDown(self):
        """Stop all patchers to clean up the test environment."""
        self.patcher_logger.stop()
        self.patcher_camera_handler.stop()
        self.patcher_video_recorder.stop()
        self.patcher_motion_handler.stop()
        self.patcher_live_feed_handler.stop()

    def test_motion_camera_happy_path(self):
        """Test the happy path of the MotionCamera class.
        This test checks if the MotionCamera class is initialized correctly and if the methods work as expected.
        """
        # the with command triggers __enter__ and __exit__ methods
        with MotionCamera(self.mock_options) as motion_camera:
            # Check if the logger is initialized correctly
            self.mock_get_logger.assert_called_once_with(motion_camera.__class__.__name__)
            self.mock_logger.debug.assert_called_with(f"{motion_camera.__class__.__name__} initialized")
            self.mock_logger.warning.assert_not_called()
            self.mock_motion_handler.terminate = False

            # Check if the handlers are initialized correctly
            self.assertIsInstance(motion_camera.camera_handler, self.mock_camera_handler.return_value.__class__)
            self.assertIsInstance(motion_camera.motion_handler, self.mock_motion_handler.return_value.__class__)
            self.assertIsInstance(motion_camera.live_feed_handler, self.mock_live_feed_handler.return_value.__class__)

            def mock_capture_camera_feed():
                while not motion_camera.motion_handler.terminate:
                    time.sleep(1)  # Simulate some work

            self.mock_motion_handler.return_value.capture_camera_feed = mock_capture_camera_feed

            motion_camera.run()
            self.mock_server.serve_forever.assert_called_once()
            self.assertFalse(motion_camera.live_feed_handler.terminate)
            self.assertTrue(motion_camera.motion_handler.storage_enabled)
            self.assertFalse(motion_camera.motion_handler.terminate)
            _ = motion_camera.stop_capture()
            response = motion_camera.flask.Response.call_args.kwargs["response"]
            self.assertIn("Camera feed stopped", response)
            self.assertTrue(motion_camera.motion_handler.terminate)
            self.assertTrue(motion_camera.live_feed_handler.terminate)
            _ = motion_camera.disable_video_storage()
            response = motion_camera.flask.Response.call_args.kwargs["response"]
            self.assertIn("Video storage disabled", response)
            self.assertFalse(motion_camera.motion_handler.storage_enabled)

            motion_camera.log_server_ready()
            self.mock_logger.info.assert_called_with("Flask server is ready to receive requests.")

            _ = motion_camera.index()
            response = motion_camera.flask.Response.call_args.kwargs["response"]

            self.assertIn("The system is idle", response)
            self.assertIn("live feed is stopped", response)
            self.assertIn("storage is disabled", response)
            self.assertIn("<li><a href='/feed'>Show live feed</a></li>", response)
            self.assertIn("<li><a href='/endfeed'>Stop live feed</a></li>", response)
            self.assertIn("<li><a href='/start'>Start capturing video</a></li>", response)
            self.assertIn("<li><a href='/stop'>Stop capturing video</a></li>", response)
            self.assertIn("<li><a href='/save'>Enable video storage</a></li>", response)
            self.assertIn("<li><a href='/nosave'>Disable video storage</a></li>", response)


        self.mock_logger.debug.assert_called_with("Exiting MotionCamera")
        self.mock_logger.info.assert_called_with("Camera feed stopped")

    def test_motion_camera_signal_handling(self):
        """Test if the MotionCamera class handles signals correctly."""
        with MotionCamera(self.mock_options) as motion_camera:
            # Ensure terminate is initially False
            self.assertFalse(motion_camera.terminate)

            with self.assertRaises(SystemExit):
                # Send SIGINT to the current process
                os.kill(os.getpid(), signal.SIGINT)

            # Check if the signal handler set terminate to True
            self.assertTrue(motion_camera.terminate)

            with self.assertRaises(SystemExit):
                motion_camera.initialize_with_interrupt(motion_camera._import_flask)

            self.mock_logger.warning.assert_called_with("Initialization interrupted by SIGINT/SIGTERM signal")

    def test_motion_camera_live_feed(self):
        """Test if the live feed function of the MotionCamera class works correctly."""
        def mock_generate_feed():
            yield b"test1"

        generator = mock_generate_feed()
        self.mock_live_feed_handler.return_value.generate_feed = MagicMock(return_value=generator)

        with patch("flask.Response") as mock_response_class:
            mock_response_instance = MagicMock()
            mock_response_class.return_value = mock_response_instance

            with MotionCamera(self.mock_options) as motion_camera:
                response = motion_camera.live_feed()

                mock_response_class.assert_called_once_with(
                    response=generator,
                    mimetype="multipart/x-mixed-replace; boundary=frame"
                )
             
                self.assertEqual(response, mock_response_instance)
                self.mock_live_feed_handler.return_value.generate_feed.assert_called_once()

                # Consume the generator to ensure it is executed
                self.assertEqual(b'test1', next(generator))

                self.assertFalse(motion_camera.live_feed_handler.terminate)
                _ = motion_camera.end_feed()
                response_args = motion_camera.flask.Response.call_args.kwargs["response"]
                self.assertIn("Live feed terminated", response_args)
                self.assertTrue(motion_camera.live_feed_handler.terminate)



        
