#!/usr/bin/env python

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

from picamera2 import Picamera2
import cv2
import numpy as np
import time
import datetime
import os
from flask import Flask, Response
from threading import Thread
import signal
import logging
import argparse


class Timer:
    """Class to handle sampling intervals (including overrun recovery)."""
    SAMPLING_RATE = 15.0                  # a.k.a. frames per second
    SAMPLING_INTERVAL = 1 / SAMPLING_RATE # interval between samples in seconds

    @staticmethod
    def wait_for_next_sampling(start_time, label=""):
        """Waits until the next sampling moment, based on the start time and interval. Returns the next sampling moment."""

        # If we don't have a start time, don't wait and make the next sample time 'now'.
        if (start_time is None):
            return time.time()

        elapsed_time = time.time() - start_time
        time_to_wait = Timer.SAMPLING_INTERVAL - elapsed_time
        if time_to_wait > 0:
            time.sleep(time_to_wait)
            return start_time + Timer.SAMPLING_INTERVAL

        # If the overrun is too large, skip the next sample to catch up.
        multiplier = int(-time_to_wait / Timer.SAMPLING_INTERVAL) + 1
        logging.getLogger("Timer").debug(f"Overrun {label}: {-time_to_wait:.3f} seconds. Multiplier: {multiplier}")
        return start_time + multiplier * Timer.SAMPLING_INTERVAL


class CameraHandler:
    """Class to handle the camera and capture frames."""
    FULL_SIZE = (1296, 972) # Supported size by the camera
    FRAME_SIZE = (800, 600) # Frame size to capture (lower, for performance reasons)

    def __init__(self):
        """Initialize the camera handler with the camera object and capture configuration."""
        self.logger = logging.getLogger(self.__class__.__name__)
        self.camera = Picamera2()
        self.capture_config = self.camera.create_preview_configuration(main={"size": self.FULL_SIZE, "format": "RGB888"})
        self.camera.start(self.capture_config)
        self.frame = None

    def __del__(self):
        """Stop the camera and close the connection when the object is deleted."""
        self.logger.debug("Destroying CameraHandler")
        self.camera.stop()
        self.camera.close()
        self.logger.debug("Destroyed CameraHandler")

    def capture_frame(self):
        """Capture a frame from the camera"""
        full_frame = self.camera.capture_array("main")
        self.frame = cv2.resize(src = full_frame, dsize = self.FRAME_SIZE, interpolation=cv2.INTER_LINEAR)
        return self.frame


class VideoRecorder:
    """Class to handle video recording and storage."""
    MAX_SEGMENT_DURATION = 600  # Maximum duration of a video segment (in seconds)

    def __init__(self, video_directory, frame_size):
        """Initialize the video recorder with the video directory and frame size."""
        self.logger = logging.getLogger(self.__class__.__name__)
        self.video_directory = video_directory
        self.frame_size = frame_size
        self.fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        self.recording_active = False
        self.out = None
        self.start_time = None
        self.cleanup()

    def cleanup(self):
        """Cleanup the video recorder state."""
        self.frame_count = 0
        self.overruns = 0
        self.overrun_total = 0
        self.frame_start_time = None
        self.elapsed_time = 0
        self.time_to_wait = 0

    def create_video_file(self):
        """Create a video file for recording."""
        now = datetime.datetime.now()
        filename = f"cam_{now.date()}_{now.hour:02}-{now.minute:02}-{now.second:02}.mp4"
        filepath = os.path.join(self.video_directory, filename)
        self.logger.info(f"Recording to {filepath}")
        return cv2.VideoWriter(filename = filepath, fourcc = self.fourcc, fps = Timer.SAMPLING_RATE, frameSize = self.frame_size)

    def is_segment_duration_exceeded(self):
        """Check if the maximum segment duration has been exceeded."""
        if not self.recording_active or self.start_time is None:
            return False
        return time.time() - self.start_time > self.MAX_SEGMENT_DURATION

    def start_recording(self):
        """Start recording video."""
        self.recording_active = True
        self.out = self.create_video_file()
        self.cleanup()
        self.logger.info("Recording started.")
        self.start_time = time.time()

    def stop_recording(self):
        """Stop recording video."""
        duration = time.time() - self.start_time
        if self.out:
            self.out.release()
        self.recording_active = False
        self.logger.info(f"Recording completed in {duration:.2f} seconds, {self.frame_count} frames. Effective FPS: {self.frame_count / duration:.2f}.")

    def write_frame(self, frame):
        """Write a frame to the video file."""

        self.frame_start_time = Timer.wait_for_next_sampling(start_time = self.frame_start_time, label="video recording")
        self.out.write(frame)
        self.frame_count += 1


class MotionHandler:
    """Class to handle motion detection and video storage."""
    MSE_MOTION_THRESHOLD = 15.0 # Minimum mean squared error value to trigger motion
    THRESHOLD_TIME = 10         # Time to keep recording after the last motion detection (in seconds)

    def __init__(self, camera_handler, video_recorder):
        """Initialize the motion handler with the video directory and camera handler."""
        self.logger = logging.getLogger(self.__class__.__name__)
        self.camera_handler = camera_handler
        self.storage_enabled = False
        self.video_recorder = video_recorder
        self.start_video_thread = None
        self.terminate = False
        self.motion_detected = False
        self.last_motion_time = None

    def __del__(self):
        """Destroy the MotionHandler."""
        self.logger.debug("Destroying MotionHandler")
        if self.start_video_thread is not None:
            self.start_video_thread.join()
            self.start_video_thread = None
        self.logger.debug("Destroyed MotionHandler")

    @staticmethod
    def mean_squared_error(frame1, frame2):
        """Calculate the mean squared error between two grayscale frames."""
        height, width = frame1.shape
        frame_size = float(height * width)
        diff = cv2.subtract(frame1, frame2)
        err = np.sum(diff ** 2)
        return err / frame_size

    def capture_camera_feed(self):
        """Capture the camera feed to detect motion."""
        FRAME_SKIPS = 5
        frame_count = 0
        reference_frame = None
        start_time = time.time()

        # skip the first few frames to allow the camera to adjust to lighting
        # then continuously capture frames and check for motion once every few frames to reduce processing load
        self.logger.info("Starting camera capture")
        while not self.terminate:
            frame = self.camera_handler.capture_frame()
            frame_count += 1
            if frame_count == FRAME_SKIPS:
                gray_frame = cv2.cvtColor(src = frame, code = cv2.COLOR_RGB2GRAY)
                if reference_frame is not None and self.detect_motion(reference_frame, gray_frame):
                    self.handle_motion()
                reference_frame = gray_frame
                frame_count = 0
            start_time = Timer.wait_for_next_sampling(start_time, label="camera capture")

        self.logger.info("Camera capture terminated.")

    def detect_motion(self, frame1_gray, frame2_gray):
        """Check if there is any motion by calculating mean squared error."""
        error = self.mean_squared_error(frame1_gray, frame2_gray)
        self.logger.debug(f"MSE: {error:.2f}; Recording: {self.video_recorder.recording_active}")
        self.motion_detected = error >= self.MSE_MOTION_THRESHOLD
        return self.motion_detected

    def display_motion_alert(self):
        """Overlay a motion detection message on the frame."""
        SCALE = 0.5
        THICKNESS = int(2 * SCALE)
        Y_OFFSET = THICKNESS * 25
        STARTPOINT = (10, Y_OFFSET)
        FONT = cv2.FONT_HERSHEY_SIMPLEX
        COLOR = (255, 255, 128) # light cyan
        cv2.putText(img = self.camera_handler.frame, text = "Motion detected", org = STARTPOINT,
                    fontFace = FONT, fontScale = SCALE, color = COLOR, thickness = THICKNESS, lineType = cv2.LINE_AA)

    def handle_motion(self):
        """Handle motion detection by displaying an alert and starting video storage if it isn't already running."""
        self.display_motion_alert()
        self.last_motion_time = time.time()
        if self.storage_enabled and not self.video_recorder.recording_active:
            self.start_video_thread = Thread(target=self.store_video)
            self.start_video_thread.start()

    def recording_should_stop(self):
        """Check if the recording should stop based on the terminate flag, threshold time and segment duration."""
        if time.time() - self.last_motion_time > self.THRESHOLD_TIME:
            self.logger.info(f"No motion detected for {self.THRESHOLD_TIME} seconds. Stopping recording.")
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


class LiveFeedHandler:
    """ Class to handle the live feed from the camera. """
    def __init__(self, camera_handler):
        """Initialize the live feed handler with the camera handler and FPS."""
        self.logger = logging.getLogger(self.__class__.__name__)
        self.camera_handler = camera_handler
        self.terminate = False

    def generate_feed(self):
        """Generate the live feed using frames."""
        start_time = time.time()
        while not self.terminate:
            try:
                _, buffer = cv2.imencode(".jpg", self.camera_handler.frame)
                # we need to send bytes, not Python strings
                image_content = buffer.tobytes()
                yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + image_content + b"\r\n")
                start_time = Timer.wait_for_next_sampling(start_time, label="live feed")

            except Exception as e:
                self.logger.error(f"Live feed error: {e}")
                break
        self.logger.info("Terminated live feed")


class MotionCameraApp:
    """Class to handle the motion camera application."""
    def __init__(self):
        """Initialize the MotionCameraApp."""
        self.logger = logging.getLogger(self.__class__.__name__)
        self.app = Flask(__name__)
        self.camera_handler = CameraHandler()
        self.video_recorder = VideoRecorder(video_directory="/media/cam", frame_size=self.camera_handler.FRAME_SIZE)
        self.motion_handler = MotionHandler(camera_handler=self.camera_handler, video_recorder=self.video_recorder)
        self.live_feed_handler = LiveFeedHandler(camera_handler=self.camera_handler)
        self.detect_thread = None

        self.app.add_url_rule(rule = "/", endpoint = "index", view_func = self.index)
        self.app.add_url_rule(rule = "/start", endpoint = "start_capture", view_func = self.start_capture)
        self.app.add_url_rule(rule = "/stop", endpoint = "stop_capture", view_func = self.stop_capture)
        self.app.add_url_rule(rule = "/feed", endpoint = "feed", view_func = self.live_feed)
        self.app.add_url_rule(rule = "/nosave", endpoint = "no_save", view_func = self.disable_video_storage)
        self.app.add_url_rule(rule = "/save", endpoint = "save", view_func = self.enable_video_storage)

        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)

    def __enter__(self):
        """Enter the MotionCameraApp."""
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        """Exit the MotionCameraApp."""
        self.logger.debug("Exiting MotionCameraApp")
        self.disable_video_storage()
        self.stop_capture()

        self.logger.info("Exited MotionCameraApp")

    def disable_video_storage(self):
        """Disable video storage."""
        self.motion_handler.storage_enabled = False
        return "Storage of motion videos turned off"

    def enable_video_storage(self):
        """Enable video storage."""
        self.motion_handler.storage_enabled = True
        return "Storage of motion videos turned on"

    def index(self):
        """Return the index page."""
        return "The system is running. For live feed, go to /livefeed"

    def live_feed(self):
        """Return the live camera feed."""
        return Response(response = self.live_feed_handler.generate_feed(), mimetype="multipart/x-mixed-replace; boundary=frame")

    def run(self):
        """Run the MotionCameraApp."""
        self.logger.info(self.start_capture())
        self.logger.info(self.enable_video_storage())
        try:
            self.app.run(host="0.0.0.0", debug=False)
        except SystemExit:
            self.logger.info("SystemExit received. Shutting down Flask server.")
            raise  # Re-raise the exception to allow the program to exit
        finally:
            self.logger.info("Flask server has stopped.")

    def signal_handler(self, sig, frame):
        """Handle the signal / terminate interrupts for gracefully exiting."""
        self.logger.info("signal handler called. Exiting..")
        raise SystemExit

    def start_capture(self):
        """Start capturing the camera feed."""
        self.detect_thread = Thread(target=self.motion_handler.capture_camera_feed)
        self.detect_thread.daemon = True
        self.detect_thread.start()
        return "System started"

    def stop_capture(self):
        """Stop capturing the camera feed."""
        self.motion_handler.terminate = True
        if self.detect_thread != None:
            self.detect_thread.join()
            self.detect_thread = None
        self.live_feed_handler.terminate = True

        return "System stopped"


def set_logging():
    """Setup logging and logging level for the application, based on command line parameters."""
    parser = argparse.ArgumentParser()
    parser.add_argument("-log", "--log", default="warning", help=("Provide logging level. Example --log debug, default='warning'"))

    options = parser.parse_args()
    levels = { "critical": logging.CRITICAL, "error": logging.ERROR, "warn": logging.WARNING,
      "warning": logging.WARNING, "info": logging.INFO, "debug": logging.DEBUG  }
    level = levels.get(options.log.lower())
    if level is None:
        raise ValueError(
            f"log level given: {options.log}"
            f" -- must be one of: {' | '.join(levels.keys())}")
    logging.basicConfig(format="%(asctime)s %(name)-15s %(levelname)-8s: %(message)s", level=level)
    # make the dependencies less chatty when debugging
    if level == logging.DEBUG:
        logging.getLogger("picamera2").setLevel(logging.INFO)
        logging.getLogger("cv2").setLevel(logging.INFO)
        logging.getLogger("flask").setLevel(logging.INFO)
        logging.getLogger("werkzeug").setLevel(logging.INFO)


if __name__ == "__main__":
    set_logging()
    with MotionCameraApp() as app:
        app.run()
