"""Saves frames from played games, with YOLO labels, as training data for the model (see Training in README.md)."""
import os
import queue
import threading
import time

import cv2
import numpy as np

DARTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'training', 'data', 'darts')
IMAGE_DIR = os.path.join(DARTS_DIR, 'images', 'collected')
LABEL_DIR = os.path.join(DARTS_DIR, 'labels', 'collected')
IMAGE_SIZE = 800 # the size the model is trained at
BOX = 0.025
UNTOUCHED_EVERY = 5 # visits nobody corrected mostly repeat what the model already knows, so keep only some


def yolo_label(calibration, darts):
    # calibration: (6, 2) normalised image coords, -1 where not found; darts: (n, 2) normalised image coords
    lines = []
    for i, point in enumerate(calibration):
        if np.all(point != -1):
            cls = i if i < 4 else i + 1 # points 0-3 are classes 0-3 (20, 3, 11, 6), 4-5 are classes 5-6 (9, 15)
            lines.append((cls, *point))
    lines += [(4, *d) for d in darts if 0 <= d[0] <= 1 and 0 <= d[1] <= 1]
    return ''.join(f'{c} {x:.6f} {y:.6f} {BOX} {BOX}\n' for c, x, y in lines)


class TrainingRecorder:
    def __init__(self):
        self.enabled = False
        self.saved = {'corrected': 0, 'auto': 0}
        self._untouched = 0
        self._queue = queue.Queue()
        threading.Thread(target=self._run, daemon=True).start()

    def record(self, image, calibration, darts, corrected):
        """Queue one committed visit; image is the square camera crop the coordinates are relative to."""
        if not self.enabled or len(darts) == 0:
            return
        if not corrected:
            self._untouched += 1
            if self._untouched % UNTOUCHED_EVERY:
                return
        kind = 'corrected' if corrected else 'auto'
        self.saved[kind] += 1
        self._queue.put((image.copy(), np.array(calibration), np.array(darts), kind))

    def _run(self):
        # disk writes happen here so they never slow down detection
        while True:
            image, calibration, darts, kind = self._queue.get()
            try:
                os.makedirs(IMAGE_DIR, exist_ok=True)
                os.makedirs(LABEL_DIR, exist_ok=True)
                name = f'web_{time.strftime("%Y%m%d_%H%M%S")}_{int(time.time() * 1000) % 1000:03d}_{kind}'
                cv2.imwrite(os.path.join(IMAGE_DIR, name + '.jpg'), cv2.resize(image, (IMAGE_SIZE, IMAGE_SIZE), interpolation=cv2.INTER_AREA),
                            [cv2.IMWRITE_JPEG_QUALITY, 95])
                with open(os.path.join(LABEL_DIR, name + '.txt'), 'w') as f:
                    f.write(yolo_label(calibration, darts))
            except OSError as e:
                print(f'Could not save training data: {e}')
