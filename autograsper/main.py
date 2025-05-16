import sys
import threading
import time
import cv2
import logging

import os

from flask import Flask, Response

from coordinator import DataCollectionCoordinator
from custom_graspers.my_custom_grasper import MyCustomGrasper
from utils import load_config


# Configure logging.
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")

# Create the Flask application.
app = Flask(__name__)

# Global reference to the coordinator (set in main()).
global_coordinator = None


@app.route("/video_feed")
def video_feed():
    """
    Route that streams the video feed as an MJPEG stream.
    """
    return Response(
        generate_frames(), mimetype="multipart/x-mixed-replace; boundary=frame"
    )


def generate_frames():
    """
    Generator function that continuously retrieves image frames from the
    coordinator's UI update queue, encodes them as JPEG, and yields them.
    """
    while not global_coordinator.shutdown_event.is_set():
        ui_msg = global_coordinator.get_ui_update(timeout=0.1)
        if ui_msg and ui_msg.get("type") == "image_update":
            frame = ui_msg.get("image")
            if frame is not None:
                # Encode frame as JPEG.
                ret, jpeg = cv2.imencode(".jpg", frame)
                if ret:
                    frame_bytes = jpeg.tobytes()
                    yield (
                        b"--frame\r\n"
                        b"Content-Type: image/jpeg\r\n\r\n" + frame_bytes + b"\r\n\r\n"
                    )
        else:
            # If no frame is available, sleep briefly.
            time.sleep(0.02)


def main():
    global global_coordinator

    config_path = os.path.join(os.getcwd(), "autograsper", "my_config.yaml")
    config = load_config(config_path)
    shutdown_event = threading.Event()

    grasper = MyCustomGrasper(config, shutdown_event=shutdown_event)

    global_coordinator = DataCollectionCoordinator(config, grasper, shutdown_event)
    global_coordinator.start()

    try:
        app.run(host="0.0.0.0", port=3000, debug=False, threaded=True)
    except Exception as e:
        logging.error("Flask app error: %s", e)
    finally:
        shutdown_event.set()
        global_coordinator.join()
        logging.info("Application shutdown complete.")
        sys.exit(0)


if __name__ == "__main__":
    main()
