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
import logging
from synchronizer import Synchronizer

class LiveFeedHandler:
    """ Class to handle the live feed from the camera. """

    def __init__(self, camera_handler, cv2):
        """Initialize the live feed handler with the camera handler and FPS."""
        self.logger = logging.getLogger(self.__class__.__name__)
        self.logger.debug(f"Initializing {self.__class__.__name__}")
        self.camera_handler = camera_handler
        self.cv2 = cv2
        self.terminate = False

    def generate_feed(self):
        """Generate the live feed using frames."""
        start_time = time.time()
        message = "Live feed terminated"
        error = ""
        while not self.terminate:
            try:
                _, buffer = self.cv2.imencode(".jpg", self.camera_handler.frame)
                # We need to send bytes, not Python strings
                image_content = buffer.tobytes()
                yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + image_content + b"\r\n")
                start_time = Synchronizer.wait_for_next_sampling(start_time, label=self.__class__.__name__)

            except Exception as e:
                error = " due to error: " + str(e)
                self.logger.error(f"Live feed error: {e}.")
                break
        self.logger.info(message)
        yield f"--frame\r\nContent-Type: text/plain\r\n\r\n{message}{error}.\r\n\r\n".encode("utf-8")
