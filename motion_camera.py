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

# We lazy load PiCamera2, OpenCV (cv2), Werkzeug and Flask. On the Pi Zero, these imports can take a long time (up to half a minute total) 
# and we want to avoid that, for example, if the user only asks for help. 

class MotionCamera:
    """Class to handle the motion camera application."""

    response_template = """
    <html>
        <head>
            <meta http-equiv="refresh" content="3;url={url}">
        </head>
        <body>
            <p>{message}</p>
            <p>Redirecting in 3 seconds...</p>
            <p>If the page does not refresh, <a href="{url}">go back</a>.</p>
        </body>
    </html>
    """

    def log_server_ready(self):
        """Log when the server is ready to handle requests."""
        self.logger.info("Flask server is ready to receive requests.")

    def _import_flask(self):
        """Perform the Flask import."""
        self.logger.info("Importing Flask")
        import flask
        return flask

    def _import_picamera2(self):
        """Perform the Picamera2 import."""
        self.logger.info("Importing Picamera2")
        from picamera2 import Picamera2
        return Picamera2

    def _import_cv2(self):
        """Perform the OpenCV (cv2) import."""
        self.logger.info("Importing OpenCV (cv2)")
        import cv2
        return cv2
    
    def __init__(self, options):
        """Initialize the MotionCameraApp."""
        self.logger = logging.getLogger(self.__class__.__name__)
        self.logger.debug(f"Initializing {self.__class__.__name__}")
        self.options = options
        Synchronizer.set_rate(options.rate)
        self.terminate = False
        signal.signal(signal.SIGINT, self.terminate_app)
        signal.signal(signal.SIGTERM, self.terminate_app)

        # Perform slow imports with interruption support
        self.flask = self.initialize_with_interrupt(self._import_flask)
        cv2 = self.initialize_with_interrupt(self._import_cv2)
        self.app = self.initialize_with_interrupt(self.flask.Flask, __name__)
        self.app.debug = options.verbose
        camera_class = self.initialize_with_interrupt(self._import_picamera2)

        # we use dependency injection to pass cv2 to the classes that need it. This makes sure we know where it's loaded and it's easier to test
        self.camera_handler = CameraHandler(camera_class=camera_class, options=options, cv2=cv2)
        video_recorder = VideoRecorder(options=options, cv2=cv2)
        self.motion_handler = MotionHandler(camera_handler=self.camera_handler, video_recorder=video_recorder, options=options, cv2=cv2)
        self.live_feed_handler = LiveFeedHandler(camera_handler=self.camera_handler, cv2=cv2)
        self.detect_thread = None

        self.app.add_url_rule(rule = "/", endpoint = "index", view_func = self.index)
        self.app.add_url_rule(rule = "/start", endpoint = "start_capture", view_func = self.start_capture)
        self.app.add_url_rule(rule = "/stop", endpoint = "stop_capture", view_func = self.stop_capture)
        self.app.add_url_rule(rule = "/feed", endpoint = "feed", view_func = self.live_feed)
        self.app.add_url_rule(rule = "/endfeed", endpoint = "end_feed", view_func = self.end_feed)
        self.app.add_url_rule(rule = "/nosave", endpoint = "no_save", view_func = self.disable_video_storage)
        self.app.add_url_rule(rule = "/save", endpoint = "save", view_func = self.enable_video_storage)

        self.app.before_first_request(self.log_server_ready)

        self.logger.debug(f"{self.__class__.__name__} initialized")

    def initialize_with_interrupt(self, cls, *args, **kwargs):
        """Initialize a class with interruption support."""
        if self.terminate:
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

    def html_response(self, message):
        """Return an HTML response."""
        with self.app.app_context():
            url = self.app.url_for('index')
            return self.flask.Response(response=MotionCamera.response_template.format(url=url, message=message), mimetype="text/html")
    

    def disable_video_storage(self):
        """Disable video storage."""
        self.motion_handler.storage_enabled = False
        return self.html_response("Video storage disabled")

    def enable_video_storage(self):
        """Enable video storage."""
        self.motion_handler.storage_enabled = True
        return self.html_response("Video storage enabled")

    def index(self):
        """Return the index page."""
        capture_status = "capturing" if not self.motion_handler.terminate else "idle"
        live_feed_status = "running" if not self.live_feed_handler.terminate else "stopped"
        storage_status = "enabled" if self.motion_handler.storage_enabled else "disabled"

        return (
            f"<p>The system is {capture_status}, live feed is {live_feed_status} and storage is {storage_status}. <br />"
            "<br />"
            "Your choices: </p>"
            "<ul>"
            "<li><a href='/feed'>Show live feed</a></li>" 
            "<li><a href='/endfeed'>Stop live feed</a></li>"
            "<li><a href='/start'>Start capturing video</a></li>"
            "<li><a href='/stop'>Stop capturing video</a></li>"
            "<li><a href='/save'>Enable video storage</a></li>"
            "<li><a href='/nosave'>Disable video storage</a></li>"
            "</ul>"
        )

    def live_feed(self):
        """Return the live camera feed."""
        self.live_feed_handler.terminate = False
        return self.flask.Response(response = self.live_feed_handler.generate_feed(), mimetype="multipart/x-mixed-replace; boundary=frame")

    def end_feed(self):
        """Return the live camera feed."""
        self.live_feed_handler.terminate = True
        return self.html_response("Live feed terminated")

    def run(self):
        """Run the MotionCameraApp."""
        self.logger.info(f"Running {self.__class__.__name__}")
        from werkzeug.serving import make_server  # Lazy load 
        self.logger.debug("Done loading werkzeug")

        # do this before starting the server, so the camera can settle in
        if not self.options.no_auto_start:
            message = self.start_capture()
            self.logger.info(message)

        self.logger.info(f"Starting Flask server on port {self.options.port}{' (debug mode)' if self.options.verbose else ''}")
        server = make_server("0.0.0.0", self.options.port, self.app, threaded=True)
        self.logger.info("Flask server is ready to receive requests.")

        # do this after creating the server, so we don't record the startup time while the camera settles in
        if not self.options.no_auto_start:
            message = self.enable_video_storage()
            self.logger.info(message)

        try:
            server.serve_forever()
        finally:
            self.logger.info("Flask server has stopped.")

    def terminate_app(self, sig=None, frame=None):
        """Handle the signal / terminate interrupts for gracefully exiting."""
        self.logger.info("signal handler called. Exiting..")
        self.terminate = True
        raise SystemExit

    def start_capture(self):
        """Start capturing the camera feed."""
        self.motion_handler.terminate = False
        self.detect_thread = Thread(target=self.motion_handler.capture_camera_feed)
        self.detect_thread.daemon = True
        self.detect_thread.start()
        return self.html_response("Camera feed started")

    def stop_capture(self):
        """Stop capturing the camera feed."""
        self.motion_handler.terminate = True

        if self.detect_thread != None:
            self.detect_thread.join()
            self.detect_thread = None
        self.live_feed_handler.terminate = True
        return self.html_response("Camera feed stopped")


def main_helper():
    """Main helper function to run the application."""
    # We don't have a logger yet, but we can get validation errors.
    # If a SystemExit is raised here, the program will terminate with a message.
    options, unknown_options = Configurator.get_parser_options()
    Configurator.set_logging(options)
    logger = logging.getLogger(MotionCamera.__name__)
    try:
        options.directory = Configurator.validate_directory(options.directory)
        logger.info(f"Starting {MotionCamera.__name__}")
        logger.debug(f"Options: {options}")
        if unknown_options:
            logger.warning(f"Ignoring unknown options: {unknown_options}")
        logger.debug("Completed configuration")
        with MotionCamera(options) as motion_camera:
            motion_camera.run()
    except SystemExit as e:
        if e is not None and str(e) != "":
            logger.error(f"Terminating. {e}")
            raise
    finally:
        logger.info(f"{MotionCamera.__name__} terminated.")

# Keep the main block as small as possible since that's hard to unit test
if __name__ == "__main__":
    main_helper() # pragma: no cover
