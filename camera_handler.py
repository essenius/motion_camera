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

import logging

# We lazy load PiCamera2 and OpenCV. On the Pi Zero, these imports can take a long time (up to half a minute) 
# and we want to avoid that, for example, if the user only asks for help. 

class CameraHandler:
    """Class to handle the camera and capture frames."""

    def __init__(self, camera_class, options, cv2):
        """Initialize the camera handler with the camera object and capture configuration."""
        self.logger = logging.getLogger(self.__class__.__name__)
        self.logger.debug(f"Initializing {self.__class__.__name__}")
        self.camera = None

        try:
            self.camera = camera_class()
        except Exception as e:
            raise SystemExit(f"Camera initialization failed: {e}")
        
        self.logger.debug("Created camera variable")
        self.cv2 = cv2
        self.frame_size = options.frame_size

        # Find the camera mode that is the closest one larger than the requested size 
        camera_modes = self.camera.sensor_modes
        self.logger.debug("retrieved camera modes")
        self.full_size = None
        sorted_modes = sorted(camera_modes, key=lambda mode: mode['size'][0] * mode['size'][1])
        for mode in sorted_modes:
            if mode['size'] >= self.frame_size:
                self.full_size = mode['size']
                self.logger.debug(f"Camera mode set to: {self.full_size}")
                break
        if self.full_size is None:
            raise SystemExit(f"Requested frame size {self.frame_size} is larger than the maximum supported size {sorted_modes[-1]['size']}.")
        self.capture_config = self.camera.create_preview_configuration(main={"size": self.full_size, "format": "RGB888"})
        self.camera.start(self.capture_config)
        self.frame = None
        self.logger.debug(f"Initialized {self.__class__.__name__}")

    def __del__(self):
        """Stop the camera and close the connection when the object is deleted."""
        self.logger.debug(f"Destroying {self.__class__.__name__}")
        if self.camera is not None:
            self.camera.stop()
            self.camera.close()
        self.logger.debug(f"Destroyed {self.__class__.__name__}")

    def capture_frame(self):
        """Capture a frame from the camera"""
        full_frame = self.camera.capture_array("main")
        # INTER_NEAREST is the fastest interpolation method. Aliasing is less of an issue than time usage.
        self.frame = self.cv2.resize(src = full_frame, dsize = self.frame_size, interpolation=self.cv2.INTER_NEAREST)
        return self.frame
