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

import time
from threading import Thread
import logging
from synchronizer import Synchronizer

class MotionHandler:
    """Class to handle motion detection and video storage."""

    def __init__(self, camera_handler, video_recorder, options, cv2):
        """Initialize the motion handler with the video directory and camera handler."""
        self.logger = logging.getLogger(self.__class__.__name__)
        self.logger.debug(f"Initializing {self.__class__.__name__}")
        self.camera_handler = camera_handler
        self.video_recorder = video_recorder
        self.cv2 = cv2
        self.storage_enabled = False
        self.start_video_thread = None
        self.terminate = False
        self.motion_detected = False
        self.last_motion_time = None
        self.mse_motion_threshold = options.mse_threshold
        self.motion_interval = options.motion_interval
        self.logger.debug(f"{self.__class__.__name__} initialized")

    def __del__(self):
        """Destroy the MotionHandler."""
        self.logger.debug("Destroying MotionHandler")
        if self.start_video_thread is not None:
            self.start_video_thread.join()
            self.start_video_thread = None
        self.logger.debug(f"Destroyed {self.__class__.__name__}")

    def mean_squared_error(self, frame1, frame2):
        """Calculate the mean squared error between two grayscale frames."""
        import numpy # the only time we need it, so lazy load it
        height, width = frame1.shape
        frame_size = float(height * width)
        diff = self.cv2.subtract(frame1, frame2)
        err = numpy.sum(diff ** 2)
        return err / frame_size

    def capture_camera_feed(self):
        """Capture the camera feed to detect motion."""
        self.frame_count = 0
        self.reference_frame = None
        start_time = time.time()

        # skip the first few frames to allow the camera to adjust to lighting
        # then continuously capture frames and check for motion once every few frames to reduce processing load

        while not self.terminate:
            self.handle_frame()
            start_time = Synchronizer.wait_for_next_sampling(start_time, label=self.__class__.__name__)

        self.logger.info("Camera capture terminated.")

    def handle_frame(self):
        FRAME_SKIPS = 5
        frame = self.camera_handler.capture_frame()
        # we handle the motion in the next loop after detecting to keep the loops fast enough. One frame difference shouldn't matter
        self.handle_motion()
        self.frame_count += 1
        if self.frame_count == FRAME_SKIPS:
            gray_frame = self.cv2.cvtColor(src = frame, code = self.cv2.COLOR_RGB2GRAY)
            self.detect_motion(self.reference_frame, gray_frame)
            self.reference_frame = gray_frame
            self.frame_count = 0

    def detect_motion(self, frame1_gray, frame2_gray):
        """Check if there is any motion by calculating mean squared error."""
        if (frame1_gray is None) or (frame2_gray is None):
            return
        error = self.mean_squared_error(frame1_gray, frame2_gray)
        self.motion_detected = error >= self.mse_motion_threshold
        self.logger.debug(f"MSE: {error:.2f} {' - Motion' if self.motion_detected else ''}{' - Recording' if self.video_recorder.recording_active else ''}")

    def display_motion_alert(self):
        """Overlay a motion detection message on the frame."""
        SCALE = 0.5
        THICKNESS = int(2 * SCALE)
        Y_OFFSET = THICKNESS * 25
        STARTPOINT = (10, Y_OFFSET)
        FONT = self.cv2.FONT_HERSHEY_SIMPLEX
        COLOR = (255, 255, 128) # light cyan
        self.cv2.putText(img = self.camera_handler.frame, text = "Motion detected", org = STARTPOINT,
            fontFace = FONT, fontScale = SCALE, color = COLOR, thickness = THICKNESS, lineType = self.cv2.LINE_AA)

    def handle_motion(self):
        """Handle motion detection by displaying an alert and starting video storage if it isn't already running."""
        if not self.motion_detected:
            return
        self.display_motion_alert()
        self.logger.debug("Motion detected")
        self.last_motion_time = time.time()
        if self.storage_enabled and not self.video_recorder.recording_active:
            self.logger.debug("Starting video storage.")
            self.start_video_thread = Thread(target=self.store_video)
            self.start_video_thread.start()
        self.motion_detected = False

    def recording_should_stop(self):
        """Check if the recording should stop based on the terminate flag, threshold time and segment duration."""
        if time.time() - self.last_motion_time > self.motion_interval:
            self.logger.info(f"No motion detected for {self.motion_interval} seconds. Stopping recording.")
            return True

        if self.terminate:
            self.logger.info("Termination request. Stopping recording.")
            return True

        if self.video_recorder.is_segment_duration_exceeded():
            self.logger.info("Maximum segment duration reached. Stopping recording.")
            return True

        return False

    def store_video(self):
        """Record a video when motion is detected."""
        self.video_recorder.start_recording()

        while not self.recording_should_stop():
            self.video_recorder.write_frame(self.camera_handler.frame)

        self.video_recorder.stop_recording()
