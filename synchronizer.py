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

# We lazy load PiCamera2, OpenCV, NumPy and Flask. On the Pi Zero, these imports can take a long time (up to half a minute) 
# and we want to avoid that, for example, if the user only asks for help. 

class Synchronizer:
    """Class to handle sampling intervals (including overrun recovery)."""
    sampling_rate = 15.0                  # a.k.a. frames per second
    sampling_interval = 1 / sampling_rate # interval between samples in seconds

    @staticmethod
    def set_rate(rate):
        """Set the sampling rate and interval."""
        Synchronizer.sampling_rate = rate
        Synchronizer.sampling_interval = 1 / rate

    @classmethod
    def wait_for_next_sampling(cls, start_time, label=""):
        """Waits until the next sampling moment, based on the start time and interval. Returns the next sampling moment."""

        # If we don't have a start time, don't wait and make the next sample time 'now'.
        if (start_time is None):
            return time.time()

        elapsed_time = time.time() - start_time
        time_to_wait = Synchronizer.sampling_interval - elapsed_time
        if time_to_wait > 0:
            time.sleep(time_to_wait)
            return start_time + Synchronizer.sampling_interval

        # If the overrun is too large, skip the next sample to catch up.
        multiplier = int(-time_to_wait / Synchronizer.sampling_interval) + 1
        logging.getLogger(cls.__name__).debug(f"{label} overrun: {-time_to_wait:.3f} seconds ({-100 * time_to_wait / Synchronizer.sampling_interval:.0f}%). Multiplier: {multiplier}")
        return start_time + multiplier * Synchronizer.sampling_interval
