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

class CameraHandler:
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
        self.frame = cv2.resize(full_frame, self.FRAME_SIZE, interpolation=cv2.INTER_LINEAR)
        return self.frame


class VideoRecorder:
    FPS = 14.0                  # Frames per second for the video
    FRAME_INTERVAL = 1 / FPS    # Interval between frames (in seconds)
    MAX_SEGMENT_DURATION = 600  # Maximum duration of a video segment (in seconds)

    def __init__(self, video_directory, frame_size):
        self.logger = logging.getLogger(self.__class__.__name__)
        self.video_directory = video_directory
        self.frame_size = frame_size
        self.fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        self.recording_active = False
        self.out = None
        self.start_time = None
        self.cleanup()

    def cleanup(self):
        self.frame_count = 0
        self.overruns = 0
        self.overrun_total = 0
        self.frame_start_time = None
        self.elapsed_time = 0
        self.time_to_wait = 0

    def create_video_file(self):
        now = datetime.datetime.now()
        filename = f"cam_{now.date()}_{now.hour:02}-{now.minute:02}-{now.second:02}.mp4"
        filepath = os.path.join(self.video_directory, filename)
        self.logger.info(f"Recording to {filepath}")
        return cv2.VideoWriter(filepath, self.fourcc, self.FPS, self.frame_size)

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
        average = 0 if self.overruns == 0 else self.overrun_total / self.overruns
        self.logger.info(f"Recording completed in {duration:.2f} seconds, {self.frame_count} frames, {self.overruns} overruns, total {self.overrun_total}, average {average}. Effective FPS: {self.frame_count / duration:.2f}.")
        self.logger.info(f"Average elapsed time: {self.elapsed_time} # {self.elapsed_time / self.frame_count:.3f} seconds. Average time to wait: {self.time_to_wait / self.frame_count:.3f} seconds.")

    def write_frame(self, frame):
        """Write a frame to the video file."""

        # Regulate FPS (except first frame)
        if self.frame_start_time is not None:
            elapsed_time = time.time() - self.frame_start_time
            self.elapsed_time += elapsed_time
            time_to_wait = self.FRAME_INTERVAL - elapsed_time
            if time_to_wait >= 0:
                self.time_to_wait += time_to_wait
                time.sleep(time_to_wait)
            else:
                self.overruns += 1
                self.overrun_total -= time_to_wait 

        self.frame_start_time = time.time()
        self.out.write(frame)
        self.frame_count += 1

class MotionHandler:
    MSE_MOTION_THRESHOLD = 15.0 # Minimum MSE value to trigger motion
    THRESHOLD_TIME = 10         # Time to keep recording after the last motion detection (in seconds)

    def __init__(self, camera_handler, video_recorder):
        """Initialize the motion handler with the video directory and camera handler."""
        self.logger = logging.getLogger(self.__class__.__name__)
        self.camera_handler = camera_handler
        self.storage_enabled = False
        self.video_recorder = video_recorder
        self.terminate = False
        self.motion_detected = False
        self.last_motion_time = None

    def __del__(self):
        self.logger.debug("Destroying MotionHandler")
        if self.start_video_thread is not None:
            self.start_video_thread.join()
            self.start_video_thread = None
        self.logger.debug("Destroyed MotionHandler")

    def recording_should_stop(self):
        if time.time() - self.last_motion_time > self.THRESHOLD_TIME:
            self.logger.info(f"No motion detected for {self.THRESHOLD_TIME} seconds. Stopping recording.")
            return True

        if self.video_recorder.is_segment_duration_exceeded():
            self.logger.info("Maximum segment duration reached. Stopping recording.")
            return True
        return False

    def store_video(self):
        """Start recording video when motion is detected."""
        self.video_recorder.start_recording()

        while not self.terminate:
            self.video_recorder.write_frame(self.camera_handler.frame)

            if self.recording_should_stop():
                break
            
        self.video_recorder.stop_recording()

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
        FRAME_SKIPS = 5 # reduce processing by skipping frames
        frame_count = 0
        reference_frame = None

        # skip the first few frames to allow the camera to adjust to lighting
        while not self.terminate:
            frame = self.camera_handler.capture_frame()
            frame_count += 1
            if frame_count == FRAME_SKIPS:
                gray_frame = cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY)
                if reference_frame is not None:
                    self.detect_motion(reference_frame, gray_frame)
                else:
                    self.logger.debug("Reference frame not set")
                reference_frame = gray_frame
                frame_count = 0

        self.logger.info("Camera capture terminated")

    def detect_motion(self, frame1_gray, frame2_gray):
        """Process motion detection by calculating MSE and acting on motion."""
        error = self.mean_squared_error(frame1_gray, frame2_gray)
        self.logger.debug(f"MSE: {error} Motion Detection Enabled: {self.storage_enabled} Recording: {self.video_recorder.recording_active}")
        self.motion_detected = error >= self.MSE_MOTION_THRESHOLD
        if self.motion_detected:
            self.display_motion_alert()
            self.last_motion_time = time.time()
            if self.storage_enabled and not self.video_recorder.recording_active:
                self.start_video_thread = Thread(target=self.store_video)
                self.start_video_thread.start()

    def display_motion_alert(self):
        """Overlay a motion detection message on the frame."""
        SCALE = 0.5
        THICKNESS = int(2 * SCALE)
        Y_OFFSET = THICKNESS * 25
        STARTPOINT = (10, Y_OFFSET)
        FONT = cv2.FONT_HERSHEY_SIMPLEX
        COLOR = (255, 255, 128) # light cyan
        cv2.putText(self.camera_handler.frame, "Motion detected", STARTPOINT, FONT, SCALE, COLOR, THICKNESS, cv2.LINE_AA)


class LiveFeedHandler:
    def __init__(self, camera_handler, fps):
        """Initialize the live feed handler with the camera handler and FPS."""
        self.logger = logging.getLogger(self.__class__.__name__)
        self.camera_handler = camera_handler
        self.frame_interval = 1 / fps
        self.terminate = False
        self.total_wait = 0
        self.waits = 0

    def generate_feed(self):
        """Generate the live feed using frames."""
        while not self.terminate:
            try:
                start_time = time.time()
                _, buffer = cv2.imencode(".jpg", self.camera_handler.frame)
                image_content = buffer.tobytes()
                yield (b"--frame\r\n"
                       b"Content-Type: image/jpeg\r\n\r\n" + image_content + b"\r\n")

                # Regulate FPS
                elapsed_time = time.time() - start_time
                time_to_wait = max(0, self.frame_interval - elapsed_time)
                if time_to_wait > 0:
                    time.sleep(time_to_wait)
                    self.total_wait += time_to_wait
                    self.waits += 1
                    if self.waits == 100:
                        self.logger.debug(f"Average wait time: {self.total_wait / self.waits:.3f} seconds")
                        self.waits = 0
                        self.total_wait = 0
                else:
                    self.logger.error(f"Frame generation took {elapsed_time:.3f} seconds.")
            except Exception as e:
                self.logger.error(f"Live feed error: {e}")
                break
        self.logger.info("Terminated live feed")


class MotionCameraApp:
    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)
        self.app = Flask(__name__)
        self.camera_handler = CameraHandler()
        self.video_recorder = VideoRecorder(video_directory="/media/cam", frame_size=self.camera_handler.FRAME_SIZE)
        self.motion_handler = MotionHandler(camera_handler=self.camera_handler, video_recorder=self.video_recorder)
        self.live_feed_handler = LiveFeedHandler(camera_handler=self.camera_handler, fps=self.video_recorder.FPS)
        self.detect_thread = None

        self.app.add_url_rule("/", "index", self.index)
        self.app.add_url_rule("/start", "start_live", self.start_capture)
        self.app.add_url_rule("/stop", "stop_live", self.stop_capture)
        self.app.add_url_rule("/feed", "feed", self.live_feed)
        self.app.add_url_rule("/nosave", "no_save", self.disable_video_storage)
        self.app.add_url_rule("/save", "save", self.enable_video_storage)

        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.logger.debug("Exiting MotionCameraApp")
        self.disable_video_storage()
        self.stop_capture()
        self.logger.info("Exited MotionCameraApp")

    def index(self):
        return "The system is running. For live feed, go to /livefeed"

    def start_capture(self):
        self.detect_thread = Thread(target=self.motion_handler.capture_camera_feed)
        self.detect_thread.daemon = True
        self.detect_thread.start()
        return "System started"

    def stop_capture(self):
        self.motion_handler.terminate = True
        if self.detect_thread != None:
            self.detect_thread.join()
            self.detect_thread = None
        self.live_feed_handler.terminate = True

        return "System stopped"

    def live_feed(self):
        return Response(self.live_feed_handler.generate_feed(), mimetype="multipart/x-mixed-replace; boundary=frame")

    def disable_video_storage(self):
        self.motion_handler.storage_enabled = False
        return "Storage of motion videos turned off"

    def enable_video_storage(self):
        self.motion_handler.storage_enabled = True
        return "Storage of motion videos turned on"

    def signal_handler(self, sig, frame):
        self.logger.info("signal handler called. Exiting..")
        raise SystemExit

    def run(self):
        self.logger.info(self.start_capture())
        self.logger.info(self.enable_video_storage())
        self.app.run(host="0.0.0.0", debug=False)


def set_logging():
    parser = argparse.ArgumentParser()
    parser.add_argument("-log", "--log", default="warning", help=("Provide logging level. Example --log debug, default='warning'"))

    options = parser.parse_args()
    levels = { 'critical': logging.CRITICAL, 'error': logging.ERROR, 'warn': logging.WARNING,
      'warning': logging.WARNING, 'info': logging.INFO, 'debug': logging.DEBUG  }
    level = levels.get(options.log.lower())
    if level is None:
        raise ValueError(
            f"log level given: {options.log}"
            f" -- must be one of: {' | '.join(levels.keys())}")
    # omitted %(name)s for brevity
    logging.basicConfig(format='%(asctime)s %(name)s %(levelname)-8s: %(message)s', level=level)
    # make the dependencies less chatty when debugging
    if level == logging.DEBUG:
        logging.getLogger('picamera2').setLevel(logging.INFO)
        logging.getLogger('cv2').setLevel(logging.INFO)
        logging.getLogger('flask').setLevel(logging.INFO)
        logging.getLogger('werkzeug').setLevel(logging.INFO)

if __name__ == "__main__":
    set_logging()

    with MotionCameraApp() as app:
        app.run()
