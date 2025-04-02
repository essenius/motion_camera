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
import configparser
import argparse
import os

class ValidateNumber:
    def __init__(self, min_value=None, max_value=None, type=int):
        self.min_value = min_value
        self.max_value = max_value
        self.type = type
        self.limit_type = []
        if min_value is not None:
            self.limit_type.append("low")
        if max_value is not None:
            self.limit_type.append("high")

        self.condition = self.get_condition() 
        self.message_template = f"Expected type {type.__name__}{self.condition} but got {{value}}."

    def get_condition(self):
        """Get the condition for the specified limit type."""
        if len(self.limit_type) == 2:
            return f" between {self.min_value} and {self.max_value}"
        if "low" in self.limit_type:
            return f" not less than {self.min_value}"
        if "high" in self.limit_type:
            return f" not greater than {self.max_value}"
        return ""

    def validate(self, value):
        """Validate a numerical value to ensure it is within a specified range."""
        message = self.message_template.format(value=value)
        if "low" in self.limit_type and value < self.min_value:
            raise argparse.ArgumentTypeError(message)
        if "high" in self.limit_type and value > self.max_value:
            raise argparse.ArgumentTypeError(message)
    
    def __call__(self, value):
        try:
            value = self.type(value)
        except (ValueError, TypeError):
            raise argparse.ArgumentTypeError(self.message_template.format(value=value))
        self.validate(value)
        return self.type(value)

        
class Configurator:
    """Class to handle the configuration of the application."""

    @staticmethod
    def set_logging(options):
        """Setup logging and logging level for the application, based on command line parameters."""
        levels = { "critical": logging.CRITICAL, "error": logging.ERROR, "warning": logging.WARNING, "info": logging.INFO, "debug": logging.DEBUG  }
        level = levels.get(options.log.lower())
        if level is None:
            raise SystemExit(f"Unrecognized log level '{options.log}' -- must be one of: {' | '.join(levels.keys())}.")
        
        logging.basicConfig(format="%(asctime)s %(name)-15s %(levelname)-8s: %(message)s", level=level)
        # make the dependencies less chatty when debugging, except if the user wants verbose output
        if level == logging.DEBUG and not options.verbose:
            logging.getLogger("picamera2").setLevel(logging.INFO)
            logging.getLogger("cv2").setLevel(logging.INFO)
            logging.getLogger("flask").setLevel(logging.INFO)
            logging.getLogger("werkzeug").setLevel(logging.INFO)

    @staticmethod
    def validate_frame_size(value):
        try:
            width, height = map(int, value.split("x"))
            if width <= 0 or height <= 0:
                raise ValueError
            return width, height
        except ValueError:
            raise argparse.ArgumentTypeError(
                f"Invalid frame size: '{value}'. Expected format: width x height (e.g., 800x600)."
            )

    @staticmethod
    def get_parser_options():
        """Setup command line parser."""

        # As we can only parse the args once, we need two parsers: one to get the config file and one for the rest
        initial_parser = argparse.ArgumentParser(add_help = False)
        initial_parser.add_argument("-c", "--config", default="motion_camera.conf", help="Configuration file (motion_camera.conf)")
        initial_args, _ = initial_parser.parse_known_args()

        config = configparser.ConfigParser()
        config.read(initial_args.config)

        parser = argparse.ArgumentParser(parents=[initial_parser], description="Motion camera application. Values in parentheses are defaults when there is no config file.")
        parser.add_argument("-d", "--directory",       default=config.get("DEFAULT", "directory", fallback="/media/cam"), 
                                                       help="Directory to store videos (/media/cam).")
        parser.add_argument("-i", "--motion-interval", default=config.getint("DEFAULT", "motion-interval", fallback=10), 
                                                       type=ValidateNumber(1), help="Seconds to look for new motion once triggered (10)")
        parser.add_argument("-m", "--max-duration",    default=config.getint("DEFAULT", "max_duration", fallback=600), 
                                                       type=ValidateNumber(1), help="Max duration of video in seconds (600)")
        parser.add_argument("-n", "--no-auto-start",   default=config.getboolean("DEFAULT", "no-auto-start", fallback=False), 
                                                       action="store_true", help="Do not start capturing video on startup, disable storing")
        parser.add_argument("-l", "--log",             default=config.get("DEFAULT", "log", fallback="warning"), 
                                                       help=("Logging level: critical|error|warning|info|debug (warning)"))
        parser.add_argument("-p", "--port",            default=config.getint("DEFAULT", "port", fallback=5000), 
                                                       type=ValidateNumber(1024, 65535), help="Port to run the Flask server on (5000)")
        parser.add_argument("-r", "--rate",            default=config.getint("DEFAULT", "rate", fallback=15), 
                                                       type=ValidateNumber(1), help="Frames per second for video recording (15)")
        parser.add_argument("-s", "--frame-size",      default=config.get("DEFAULT", "frame-size", fallback="800 x 600"), 
                                                       type=Configurator.validate_frame_size, help="Frame size (width x height) for video recording (800 x 600)")
        parser.add_argument("-t", "--mse-threshold",   default=config.getfloat("DEFAULT", "mse-threshold", fallback=15.0), 
                                                       type=ValidateNumber(1, 65025, float), help="Mean squared error threshold to trigger motion (15)")
        
        verbose_default  = config.getboolean("DEFAULT", "verbose", fallback=False)
        group = parser.add_mutually_exclusive_group()
        group.add_argument("-v", "--verbose",         default=verbose_default, action="store_true", help="Enable verbose output for dependencies when debugging")
        group.add_argument("--no-verbose",            default=verbose_default, action="store_false", dest = "verbose", help="Disable verbose output for dependencies when debugging")
        
        known_options, unknown_options = parser.parse_known_args()
        
        return known_options, unknown_options
  

    @staticmethod
    def validate_directory(path):
        """Validate the path to ensure it exists, is a directoey, is writable, and has enough free space."""
        absolute_path = os.path.abspath(path)
        Configurator.check_path_exists(absolute_path)
        Configurator.check_path_is_directory(absolute_path)
        Configurator.check_path_is_writable(absolute_path)
        Configurator.check_path_has_free_space(absolute_path)
        return absolute_path

    @staticmethod
    def check_path_exists(absolute_path):
        """Check if the path exists."""
        if not os.path.exists(absolute_path):
            raise  SystemExit(f"Directory '{absolute_path}' does not exist. Please create it or specify a different directory.")
    
    @staticmethod
    def check_path_is_directory(absolute_path):
        """Check if the path is a directory."""
        if not os.path.isdir(absolute_path):
            raise  SystemExit(f"File '{absolute_path}' is not a directory.")
    
    @staticmethod
    def check_path_is_writable(absolute_path):
        """Check if the path is writable."""
        if not os.access(absolute_path, os.W_OK):
            raise  SystemExit(f"Directory '{absolute_path}' is not writable. Please check permissions.")
        
    @staticmethod
    def check_path_has_free_space(absolute_path):
        """Check if the directory has enough free space."""
        statvfs = os.statvfs(absolute_path)
        free_space = statvfs.f_bavail * statvfs.f_frsize
        if free_space < 1024 * 1024 * 1024:  # Less than 1 GB
            raise  SystemExit(f"Directory '{absolute_path}' has less than 1 GB of free space. Please ensure sufficient space is available.")
