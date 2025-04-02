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
from datetime import datetime
import os
import logging
from synchronizer import Synchronizer

# We lazy OpenCV. On the Pi Zero, these imports can take a long time (total up to half a minute) 
# and we want to avoid that, for example, if the user only asks for help. 

class VideoRecorder:
    """Class to handle video recording and storage."""
    
    def __init__(self, options, cv2):
        """Initialize the video recorder with the video directory and frame size."""
        self.logger = logging.getLogger(self.__class__.__name__)
        self.logger.debug(f"Initializing {self.__class__.__name__}")
        self.cv2 = cv2
        self.frame_size = options.frame_size
        self.video_directory = options.directory
        self.max_segment_duration = options.max_duration
        self.fourcc = self.cv2.VideoWriter_fourcc(*"mp4v")
        self.recording_active = False
        self.out = None
        self.start_time = None
        self.cleanup()
        self.logger.debug(f"{self.__class__.__name__} initialized")

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
        now = datetime.now()
        filename = f"cam_{now.date()}_{now.hour:02}-{now.minute:02}-{now.second:02}.mp4"
        filepath = os.path.join(self.video_directory, filename)
        self.logger.info(f"Recording to {filepath}")
        try:
            video_writer = self.cv2.VideoWriter(filename = filepath, fourcc = self.fourcc, fps = Synchronizer.sampling_rate, frameSize = self.frame_size)
            if not video_writer.isOpened():
                raise SystemExit(f"Cannot open video file {filepath}.")
            return video_writer
        except Exception as e:
            raise SystemExit(f"Error creating video file {filepath}: {e}.")

    def is_segment_duration_exceeded(self):
        """Check if the maximum segment duration has been exceeded."""
        if not self.recording_active or self.start_time is None:
            return False
        return time.time() - self.start_time > self.max_segment_duration

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
        self.frame_start_time = Synchronizer.wait_for_next_sampling(start_time = self.frame_start_time, label=self.__class__.__name__)
        self.out.write(frame)
        self.frame_count += 1
