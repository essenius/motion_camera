# Motion camera

App to control a Pi camera on a Raspberry Pi. It was tested on a Pi Zero 2 W with a Pi Camera 1.3.

After starting up it will get into a mode that starts recording when motion is detected, and stops if there are 10 seconds without motion, or after 5 minutes (whichever comes first). It is set to 15 frames per second as I've found empirically that this is the maximum that the Pi Zero 2 can handle.

- The live feed is avaible at `http://name_of_pi:5000/feed`.
- You can start/stop capturing by `http://name_of_pi:5000/start` and `http://name_of_pi:5000/stop`.
- You can start/stop saving to file by `http://name_of_pi:5000/save` and `http://name_of_pi:5000/nosave`.
- The index `http://name_of_pi:5000/` gives a rudimentary menu.
  
I'm saving my videos directly to a samba share so I don't need to use the Pi's SD card, but the application doesn't force you to.

## Structure

The application uses Flask as the web server and consists of several classes:

### Configurator
Grabbing the command line parameters and/or configuration file, setting up logging
Start the app with `motion_camera.py --log=info` for the 'info' level. You can also use `debug`, `warning`, `error` or `critical`. Default is `warning`. 
To prevent too much noise during debugging, logging level of dependencies (picamera2, cv2, flask and werkzeug) is put to `info` when choosing `debug`.
The `libcamera` log level follows this dependency level, unless the setting `LIBCAMERA_LOG_LEVELS` was set.

Run `motion_camera.py -h` to get help about command line parameters. All options except `config` are also available in config files. There is a default config file putting log level on `info`.

### Synchronizer
Synchronizes the calling thread by waiting for the next sample time, and skipping samples if necessary (with large overruns).

### Camera Handler
Manages RGB frame capture from the camera (in a native size, 1296x972 for the PiCamera 1.3) and reduces its size if desired (to keep motion detection processing fast enough). 

### Video Recorder
Manage recording of frames to a video file, including creation of a file with a unique name (`cam_yyyy-mm-dd_HH-mm-ss.mp4`). It also keeps track of the duration of the video so a duration timeout can be managed.

### Motion Handler
Capture the camera feed using the camera handler, detect motion and drives the video recorder. It detects motion by capturing a reference frame, converting that to grayscale, skipping a few frames, then capturing another frame, converting that to grayscale as well, and calculating the mean squared error between the two grayscale images. If that exceeds the threshold, there is motion. When motion is detected, a message is overlayed on the frame, and a recording thread is started if it wasn't running already.
We handle detected motion in the following frame, to reduce the processor load per frame. 

The recording thread leverages the video recorder class to do the recording, and it determines when to stop recording (if no motion is detected within the threshold, or the max video duration has been hit).

### Live Feed Handler
Provides the `/feed` handler: Displays the live feed at the right sampling rate.

### Motion Camera
Main application, and the MotionCamera class managing Flask, the endpoints and the other objects. 
It also contains a signal handler to make sure that pressing Ctrl-C is handled gracefully.
