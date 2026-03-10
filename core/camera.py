import cv2
import threading
import time
from config import CAMERA_WIDTH, CAMERA_HEIGHT, CAMERA_FPS, MIRROR_FEED

class WebcamStream:
    def __init__(self, src=0):
        self.src = src
        self.cap = cv2.VideoCapture(self.src)
        
        # Configure camera
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, CAMERA_WIDTH)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAMERA_HEIGHT)
        self.cap.set(cv2.CAP_PROP_FPS, CAMERA_FPS)
        
        # Read first frame
        self.ret, self.frame = self.cap.read()
        self.stopped = False
        
        # Stats
        self.width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        self.height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    def start(self):
        """Starts the thread to read frames from the video stream."""
        if not self.cap.isOpened():
            print("Error: Could not open camera.")
            return self
            
        t = threading.Thread(target=self.update, args=())
        t.daemon = True
        t.start()
        return self

    def update(self):
        """Keep looping infinitely until the thread is stopped."""
        while True:
            if self.stopped:
                self.cap.release()
                return

            ret, frame = self.cap.read()
            if ret:
                if MIRROR_FEED:
                    frame = cv2.flip(frame, 1)
                self.ret = ret
                self.frame = frame
            else:
                self.stopped = True

    def read(self):
        """Return the most recent frame."""
        return self.frame

    def stop(self):
        """Indicate that the thread should be stopped."""
        self.stopped = True
