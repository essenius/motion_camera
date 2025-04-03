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
from video_recorder import VideoRecorder
from synchronizer import Synchronizer
from datetime import datetime
class TestVideoRecorder(unittest.TestCase):

    def setUp(self):
        # Mock cv2 and VideoWriter
        self.mock_cv2 = MagicMock()
        self.mock_video_writer = MagicMock()
        self.mock_video_writer.isOpened.return_value = True
        self.mock_video_writer.write.return_value = None
        self.mock_cv2.VideoWriter.return_value = self.mock_video_writer
        self.mock_cv2.VideoWriter_fourcc.return_value = "mock_fourcc"

        # Mock options
        self.mock_options = MagicMock()
        self.mock_options.directory = "test_directory"
        self.mock_options.max_duration = 10
        self.mock_options.frame_size = (800, 600)

        # Initialize VideoRecorder
        self.recorder = VideoRecorder(self.mock_options, self.mock_cv2)

        # Time-related mocks
        self.start_time_timestamp = 0
        self.start_time = datetime.fromtimestamp(self.start_time_timestamp)
        self.current_time = None
        self.TIME_DELAY = 0.01  # 10 ms


    def test_video_recorder_cannot_open_file(self):
        self.assertFalse(self.recorder.recording_active, "recording not active after initialization")

        # Test the initialization of the video writer
        self.mock_cv2.VideoWriter_fourcc.assert_called_once_with(*"mp4v")

        # the guard should kick in here
        self.assertFalse(self.recorder.is_segment_duration_exceeded(), "segment duration not exceeded when not recording")

        self.mock_video_writer.isOpened.return_value = False

        with self.assertRaises(SystemExit) as context:
            self.recorder.start_recording()
        self.assertIn("Cannot open video file", str(context.exception))

        self.assertFalse(self.recorder.recording_active, "recording not active after start_recording when file cannot be opened")

    def test_video_recorder_happy_path(self):

        Synchronizer.set_rate(25) 
        start_time_timestamp = 0
        start_time = datetime.fromtimestamp(start_time_timestamp)

        current_time = None
        TIME_DELAY = 0.01  # 10 ms

        def incrementing_time():
            nonlocal current_time
            current_time = start_time_timestamp
            while True:
                yield current_time
                current_time += TIME_DELAY

        time_generator = incrementing_time()

        def mock_sleep(seconds):
            nonlocal current_time
            sleep_time = round(seconds, 5)
            current_time += round(sleep_time, 5)

        with patch("video_recorder.datetime") as mock_datetime, \
             patch("video_recorder.time.time", side_effect=lambda: next(time_generator)), \
             patch("synchronizer.time.time", side_effect=lambda: next(time_generator)), \
             patch("synchronizer.time.sleep", side_effect=mock_sleep) as mock_sleep:
            mock_datetime.now.return_value = start_time

            self.recorder.start_recording()

            self.mock_cv2.VideoWriter.assert_called_once_with(
                filename="test_directory/cam_1970-01-01_01-00-00.mp4",
                fourcc="mock_fourcc",
                fps=25,
                frameSize=(800, 600)
            )
            self.assertTrue(self.recorder.recording_active, "recording active after start_recording")
            self.assertEqual(self.recorder.start_time, start_time.timestamp(), "start time set correctly")
            self.assertEqual(current_time, start_time.timestamp(), "current time set correctly")
            self.assertEqual(self.recorder.frame_count, 0, "frame count initialized to 0")
            self.assertIsNone(self.recorder.frame_start_time, "frame start time initialized to None")

            # write first frame
            self.recorder.write_frame(frame="test_frame")
            frame1_start_time = self.recorder.frame_start_time
            self.assertEqual(frame1_start_time, start_time_timestamp + TIME_DELAY, "frame 1 start time set correctly")
            self.mock_video_writer.write.assert_called_once_with("test_frame")
            self.assertEqual(self.recorder.frame_count, 1, "frame count incremented")
            self.assertEqual(mock_sleep.call_count, 0, "sleep not called for first frame")

            # now we are recording, so max segment duration can be calculated. We're still below the threshold
            self.assertFalse(self.recorder.is_segment_duration_exceeded(), "segment duration not exceeded when just recording")
            self.recorder.write_frame(frame="test_frame")
            self.assertEqual(frame1_start_time + Synchronizer.sampling_interval, self.recorder.frame_start_time, "frame 2 start time set correctly")

            self.assertEqual(self.mock_video_writer.write.call_count, 2, "write called twice")
            self.assertEqual(self.recorder.frame_count, 2, "frame count incremented to 2")

            actual_sleep_time = self.get_argument(mock_sleep, "sleep_time")

            # Define the expected value and delta
            expected_sleep_time = Synchronizer.sampling_interval - 2 * TIME_DELAY 
            delta = 1e-6  # Allowable tolerance

            # Assert that the actual sleep value is close to the expected value
            self.assertAlmostEqual(actual_sleep_time, expected_sleep_time, delta=delta, 
                                   msg=f"Expected sleep time {expected_sleep_time} ± {delta}, but got {actual_sleep_time}")
            
            self.recorder.stop_recording()
            self.assertFalse(self.recorder.recording_active, "recording not active after stop_recording")
            self.assertIsNone(self.recorder.out, "video writer closed after stop_recording")

    def get_argument(self, mock, argument_name=None):
        args, kwargs = mock.call_args
        # If a positional argument is provided, use it
        if len(args) > 0:
            return args[0]

        if argument_name in kwargs:
            return kwargs[argument_name]

        return None
            