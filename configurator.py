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

import logging
import configparser
import argparse

class Configurator:
    """Class to handle the configuration of the application."""

    @staticmethod
    def set_logging(options):
        """Setup logging and logging level for the application, based on command line parameters."""
        levels = { "critical": logging.CRITICAL, "error": logging.ERROR, "warning": logging.WARNING, "info": logging.INFO, "debug": logging.DEBUG  }
        level = levels.get(options.log.lower())
        if level is None:
            raise SystemExit(f"Unrecognized log level '{options.log}' -- must be one of: {' | '.join(levels.keys())}")
        
        logging.basicConfig(format="%(asctime)s %(name)-15s %(levelname)-8s: %(message)s", level=level)
        # make the dependencies less chatty when debugging, except if the user wants verbose output
        if level == logging.DEBUG and not options.verbose:
            logging.getLogger("picamera2").setLevel(logging.INFO)
            logging.getLogger("cv2").setLevel(logging.INFO)
            logging.getLogger("flask").setLevel(logging.INFO)
            logging.getLogger("werkzeug").setLevel(logging.INFO)

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
                                                       type=int, help="Seconds to look for new motion once triggered (10)")
        parser.add_argument("-m", "--max-duration",    default=config.getint("DEFAULT", "max_duration", fallback=600), 
                                                       type=int, help="Max duration of video in seconds (600)")
        parser.add_argument("-n", "--no-auto-start",   default=config.getboolean("DEFAULT", "no-auto-start", fallback=False), 
                                                       action="store_true", help="Do not start capturing video on startup, disable storing")
        parser.add_argument("-l", "--log",             default=config.get("DEFAULT", "log", fallback="warning"), 
                                                       help=("Logging level: critical|error|warning|info|debug (warning)"))
        parser.add_argument("-p", "--port",            default=config.getint("DEFAULT", "port", fallback=5000), 
                                                       type=int, help="Port to run the Flask server on (5000)")
        parser.add_argument("-r", "--rate",            default=config.getint("DEFAULT", "rate", fallback=15), 
                                                       type=int, help="Frames per second for video recording (15)")
        parser.add_argument("-s", "--frame-size",      default=config.get("DEFAULT", "frame-size", fallback="800 x 600"), 
                                                       help="Frame size (width x height) for video recording (800 x 600)")
        parser.add_argument("-t", "--mse-threshold",   default=config.getfloat("DEFAULT", "mse-threshold", fallback=15.0), 
                                                       type=float, help="Mean squared error threshold to trigger motion (15)")
        
        verbose_default  = config.getboolean("DEFAULT", "verbose", fallback=False)
        group = parser.add_mutually_exclusive_group()
        group.add_argument("-v", "--verbose",         default=verbose_default, action="store_true", help="Enable verbose output for dependencies when debugging")
        group.add_argument("--no-verbose",            default=verbose_default, action="store_false", dest = "verbose", help="Disable verbose output for dependencies when debugging")
        
        known_options, unknown_options = parser.parse_known_args()

        # Convert frame_size to a tuple of integers
        try:
            dimensions = known_options.frame_size.split("x")
            known_options.frame_size = tuple(map(int, dimensions))
        except ValueError:
            raise SystemExit(f"Invalid frame size format: '{known_options.frame_size}'. Expected format: width x height (use quotes if you use spaces).")
        return known_options, unknown_options

