# Motion camera

App to control a Pi camera on a Raspberry Pi. I've tested it on a Pi Zero 2 W with a Pi Camera 1.3.

After starting up it will get into a mode that starts recording when motion is detected, and stops if there are 10 seconds without motion, or after 5 minutes (whichever comes first).
It is set to 15 frames per second as I've found empirically that this is the max that the Pi Zero can handle.

- The live feed is avaible at `http://name_of_pi:5000/feed`.
- You can start/stop capturing by `http://name_of_pi:5000/start` and `http://name_of_pi:5000/stop`.
- You can start/stop saving to file by `http://name_of_pi:5000/save` and `http://name_of_pi:5000/nosave`.

I'm saving my videos directly to a samba share so I don't need to use the Pi's SD card.

## Structure

The application uses Flask as the web server and consists of several classes:

### Timer
Synchronizes the calling thread by waiting for the next sample time, and skipping samples if necessary (large overruns)

### Camera Handler
Manages RGB frame capture from the camera (in the native size of 1296x972) and reduces its size to 800x600 in order to keep motion detection processing fast enough. 

### Video Recorder
Manage recording of frames to a video file, including creation of a file with a unique name (`cam_yyyy-mm-dd_HH-mm-ss.mp4`). It also keeps track of the duration of the video so a duration timeout can be managed.

### Motion Handler
Capture the camera feed using the camera handler, detect motion and drives the video recorder. It detects motion by capturing a reference frame, converting that to grayscale, skipping a few frames, then capturing another frame, converting that to grayscale as well, and calculating the mean squared error between the two grayscale images. If that exceeds the threshold, there is motion. When motion is detected, a message is overlayed on the frame, and a recording thread is started if it wasn't running already. 

The recording thread leverages the video recorder to do the recording, and it determines when to stop recording (if no motion is detected within the threshold, or the max video duration has been hit).

### Live Feed Handler
Provides the `/feed` handler: Displays the live feed at the right sampling rate.

### Motion Camera App
The controller managing Flask, the endpoints and the other objects. It also contains a signal handler to make sure that pressing Ctrl-C is handled gracefully.

### Logging

the `set_logging` function sets up logging, capturing the logging level from the command line. Start the app with `motion_camera.py --log=INFO` for the INFO level. You can also use DEBUG, WARNING, ERROR or CRITICAL. Default is WARNING. To prevent too much noise during debugging, logging level of dependencies (picamera2, cv2, flask and werkzeug) is put to INFO when choosing DEBUG.
