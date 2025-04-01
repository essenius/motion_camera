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

import time
from threading import Thread
import signal
import logging

from configurator import Configurator
from synchronizer import Synchronizer
from camera_handler import CameraHandler
from video_recorder import VideoRecorder
from motion_handler import MotionHandler
from live_feed_handler import LiveFeedHandler

# We lazy Flask and Werkzeug as that can take some time and we want to avoid that, for example, if the user only asks for help. 

class MotionCamera:
    """Class to handle the motion camera application."""

    def log_server_ready(self):
        """Log when the server is ready to handle requests."""
        ready_time = time.time()
        self.logger.info(f"Flask server is ready to receive requests at {ready_time:.3f} seconds since start.")

    def __init__(self, options):
        """Initialize the MotionCameraApp."""
        self.logger = logging.getLogger(self.__class__.__name__)
        self.options = options
        Synchronizer.set_rate(options.rate)
        self.terminate_flag = False
        signal.signal(signal.SIGINT, self.terminate)
        signal.signal(signal.SIGTERM, self.terminate)
        from flask import Flask
        self.app = self.initialize_with_interrupt(Flask, __name__)
        self.camera_handler = self.initialize_with_interrupt(CameraHandler, options)
        self.video_recorder = self.initialize_with_interrupt(VideoRecorder, options)
        self.motion_handler = self.initialize_with_interrupt(MotionHandler, camera_handler=self.camera_handler, video_recorder=self.video_recorder, options=options)
        self.live_feed_handler = self.initialize_with_interrupt(LiveFeedHandler, camera_handler=self.camera_handler)
        self.detect_thread = None

        self.app.add_url_rule(rule = "/", endpoint = "index", view_func = self.index)
        self.app.add_url_rule(rule = "/start", endpoint = "start_capture", view_func = self.start_capture)
        self.app.add_url_rule(rule = "/stop", endpoint = "stop_capture", view_func = self.stop_capture)
        self.app.add_url_rule(rule = "/feed", endpoint = "feed", view_func = self.live_feed)
        self.app.add_url_rule(rule = "/nosave", endpoint = "no_save", view_func = self.disable_video_storage)
        self.app.add_url_rule(rule = "/save", endpoint = "save", view_func = self.enable_video_storage)

        self.app.before_first_request(self.log_server_ready)

        self.logger.debug(f"{self.__class__.__name__} initialized")

    def initialize_with_interrupt(self, cls, *args, **kwargs):
        """Initialize a class with interruption support."""
        if self.terminate_flag:
            self.logger.warning("Initialization interrupted by SIGINT/SIGTERM signal")
            raise SystemExit
        return cls(*args, **kwargs)
    
    def __enter__(self):
        """Enter MotionCamera."""
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        """Exit the MotionCameraApp."""
        self.logger.debug(f"Exiting {self.__class__.__name__}")
        self.disable_video_storage()
        self.stop_capture()
        self.logger.info(f"Exited {self.__class__.__name__}")

    def disable_video_storage(self):
        """Disable video storage."""
        self.motion_handler.storage_enabled = False
        return "Storage of motion videos disabled"

    def enable_video_storage(self):
        """Enable video storage."""
        self.motion_handler.storage_enabled = True
        return "Storage of motion videos enabled"

    def index(self):
        """Return the index page."""
        return "The system is running. For live feed, go to /livefeed"

    def live_feed(self):
        """Return the live camera feed."""
        from flask import Response
        self.live_feed_handler.terminate = False
        return Response(response = self.live_feed_handler.generate_feed(), mimetype="multipart/x-mixed-replace; boundary=frame")

    def run(self):
        """Run the MotionCameraApp."""
        from werkzeug.serving import make_server  # Lazy load 

        self.options.debug = options.verbose

        # do this before starting the server, so the camera can settle in
        if not options.no_auto_start:
            message = self.start_capture()
            self.logger.info(message)

        self.logger.info(f"Starting Flask server on port {options.port}{' (debug mode)' if options.verbose else ''}")
        server = make_server("0.0.0.0", options.port, self.app)
        self.logger.info("Flask server is ready to receive requests.")

        # do this after creating the server, so we don't record the startup time while the camera settles in
        if not options.no_auto_start:
            message = self.enable_video_storage()
            self.logger.info(message)

        try:
            server.serve_forever()
        finally:
            self.logger.info("Flask server has stopped.")

    def terminate(self, sig=None, frame=None):
        """Handle the signal / terminate interrupts for gracefully exiting."""
        self.logger.info("signal handler called. Exiting..")
        self.terminate_flag = True
        raise SystemExit

    def start_capture(self):
        """Start capturing the camera feed."""
        self.motion_handler.terminate = False
        self.detect_thread = Thread(target=self.motion_handler.capture_camera_feed)
        self.detect_thread.daemon = True
        self.detect_thread.start()
        return "Started capturing the camera feed"

    def stop_capture(self):
        """Stop capturing the camera feed."""
        self.motion_handler.terminate = True
        if self.detect_thread != None:
            self.detect_thread.join()
            self.detect_thread = None
        self.live_feed_handler.terminate = True
        return "Stopped capturing the camera feed"


if __name__ == "__main__":
    options, unknown_options = Configurator.get_parser_options()
    Configurator.set_logging(options)
    logger = logging.getLogger(MotionCamera.__name__)
    logger.info(f"Starting {MotionCamera.__name__}")
    logger.debug(f"Options: {options}")
    if unknown_options:
        logger.warning(f"Unknown options: {unknown_options}")
    logger.debug("Completed configuration")
    try:
        with MotionCamera(options) as motion_camera:
            motion_camera.run()
    except SystemExit as e:
        if e is not None and str(e) != "":
            logger.error(f"SystemExit: '{e}'")
        raise
                
    finally:
        logger.info(f"{MotionCamera.__name__} terminated")
