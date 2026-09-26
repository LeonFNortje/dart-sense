import threading
import time

import cv2
import numpy as np
from ultralytics import YOLO

from get_scores import GetScores
from training_data import TrainingRecorder
from video_processing import WEIGHTS, LatestFrameReader, _select_device

DISPLAY_SIZE = 720 # side of the square image sent to the web UI
REPEAT_THRESHOLD = 3 # frames (of the last 5) a dart must be seen in before it counts


class DetectionEngine:
    """Runs YOLO on the camera stream in a background thread and turns detections into visits.

    The engine never changes the match itself: it calls on_visit(darts) when a visit is complete and
    the darts have been pulled out, and on_announce(darts) when three darts (or a finish/bust) are seen.
    """

    def __init__(self, model_dir=WEIGHTS):
        self.model = YOLO(model_dir)
        self.device = _select_device()
        print(f'Running model on {self.device}')
        self.predict = GetScores(model_dir)
        self.recorder = TrainingRecorder()
        self.lock = threading.RLock()
        self.frame_ready = threading.Condition()
        self.jpeg = None
        self.thread = None
        self.running = False
        self.display_mode = 'imageplane' # or 'boardplane'
        self.reset_visit()
        self.user_calibration = -np.ones((6, 2))
        self.live = {'board_found': False, 'fps': 0.0, 'calibration': [], 'darts': [], 'boxes': [], 'connected': False, 'error': None}

    # ---- lifecycle ----
    def start(self, source, evaluate, on_announce, on_visit):
        self.stop()
        self.evaluate, self.on_announce, self.on_visit = evaluate, on_announce, on_visit
        self.running = True
        self.thread = threading.Thread(target=self._run, args=(source,), daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False
        if self.thread is not None:
            self.thread.join(timeout=3)
            self.thread = None

    # ---- visit state ----
    def reset_visit(self, wait_for_clear=False):
        with self.lock:
            self.dart_coords = [] # boardplane coords of the darts in this visit
            self.darts = [] # their labels, e.g. 'T20'
            self.announced = False
            self.ignore_until_clear = wait_for_clear # after a manual commit, don't score darts still in the board
            self.pred_queue = -np.ones((5, 3, 2))
            self.pred_queue_count = 0
            self.H = None
            self.snapshot = None # (frame, calibration, homography) of the last frame with this visit's darts in the board
            self.corrected = False # the user moved, added or deleted a point in this visit

    def _record_visit(self):
        # save the visit as training data, with the final (possibly corrected) dart positions as labels
        if self.snapshot is None or not self.dart_coords:
            return
        square, calibration, H = self.snapshot
        darts = self.predict.transform_to_boardplane(np.linalg.inv(H), np.array(self.dart_coords), square.shape[0])
        self.recorder.record(square, calibration, darts, self.corrected)

    def commit_now(self):
        # commit the detected darts immediately, e.g. after a bounce-out; darts left in the board are then ignored
        with self.lock:
            darts = list(self.darts)
            self._record_visit()
            self.reset_visit(wait_for_clear=True)
        self.on_visit(darts)

    def add_dart(self):
        with self.lock:
            if len(self.dart_coords) < 3:
                self.dart_coords.append(np.array([0.5, 0.5]))
                self.corrected = True
                self._rescore()

    def move_point(self, kind, index, x, y):
        # x, y are normalised coordinates of the displayed image
        with self.lock:
            if kind == 'dart' and index < len(self.dart_coords):
                if self.display_mode == 'boardplane':
                    self.dart_coords[index] = np.array([x, y])
                elif self.H is not None:
                    self.dart_coords[index] = self.predict.transform_to_boardplane(self.H, np.array([[x, y]]), self.crop_size)[0]
                self.corrected = True
                self._rescore()
            elif kind == 'calibration' and self.display_mode == 'imageplane':
                self.user_calibration[index] = [x, y]
                self.corrected = True

    def delete_point(self, kind, index):
        with self.lock:
            if kind == 'dart' and index < len(self.dart_coords):
                self.dart_coords.pop(index)
                self.corrected = True
                self._rescore()
            elif kind == 'calibration':
                self.user_calibration[index] = -1
                self.corrected = True

    def _rescore(self):
        self.darts = list(self.predict.score(np.array(self.dart_coords))[0]) if self.dart_coords else []

    # ---- detection loop ----
    def _run(self, source):
        # keeps (re)connecting until stopped, so the phone can be started or restarted mid-match
        while self.running:
            try:
                reader = LatestFrameReader('http://' + source + '/video')
            except ConnectionError as e:
                self.live.update(connected=False, error=str(e), board_found=False)
                time.sleep(2)
                continue
            self.live.update(connected=True, error=None)
            self._read_frames(reader)
            reader.stop()
            self.live.update(connected=False, error='stream ended', board_found=False)

    def _read_frames(self, reader):
        prev = time.time()
        for frame in reader.frames():
            if not self.running:
                break
            if frame is None:
                continue
            h, w = frame.shape[:2]
            s = min(h, w)
            square = frame[(h-s)//2:(h-s)//2+s, (w-s)//2:(w-s)//2+s]
            self.crop_size = s
            result = self.model(square, imgsz=800, verbose=False, device=self.device)[0]
            now = time.time()
            fps = round(1 / max(now - prev, 1e-6), 1)
            prev = now
            self._pending = []
            with self.lock:
                self._process(result, square, fps)
            for callback, args in self._pending: # run outside the lock so match updates can't deadlock with the UI
                callback(*args)

    def _process(self, result, square, fps):
        calibration, dart_coords = self.predict.process_yolo_output(result)
        calibration = np.where(self.user_calibration == -1, calibration, self.user_calibration)
        boxes = [{'cls': int(c), 'conf': round(float(p), 2), 'x': float(b[0]), 'y': float(b[1])}
                 for c, p, b in zip(result.boxes.cls.cpu().numpy(), result.boxes.conf.cpu().numpy(), result.boxes.xywhn.cpu().numpy())]
        board_found = np.count_nonzero(np.all(calibration != -1, axis=1)) >= 4

        if not board_found:
            self.H = None
            self._publish(cv2.resize(square, (DISPLAY_SIZE, DISPLAY_SIZE)), fps, False, [], [], boxes)
            return

        self.H = self.predict.find_homography(calibration, self.crop_size)[0]
        board_darts = self.predict.transform_to_boardplane(self.H, dart_coords, self.crop_size) if len(dart_coords) else np.empty((0, 2))
        self._track(board_darts)
        self._rescore()

        if not self.ignore_until_clear and self.darts and not self.announced:
            self.snapshot = (square, calibration, self.H) # frames after the announcement may show hands pulling darts

        if not self.ignore_until_clear and self.darts:
            ev = self.evaluate(self.darts)
            if (len(self.darts) == 3 or ev['bust'] or ev['checkout']) and not self.announced:
                self.announced = True
                self._pending.append((self.on_announce, (list(self.darts),)))
            elif len(self.darts) < 3 and not (ev['bust'] or ev['checkout']):
                self.announced = False # a dart was deleted by hand

        # overlays in display coordinates (0-1)
        if self.display_mode == 'boardplane':
            img = cv2.warpPerspective(square, self.H, (self.crop_size, self.crop_size))
            img = cv2.resize(img, (DISPLAY_SIZE, DISPLAY_SIZE))
            self._draw_board_outline(img)
            cal_points = [(i, *self.predict.boardplane_calibration_coords[i]) for i in range(6) if np.all(calibration[i] != -1)]
            darts_disp = [tuple(d) for d in self.dart_coords]
        else:
            img = cv2.resize(square, (DISPLAY_SIZE, DISPLAY_SIZE))
            cal_points = [(i, *calibration[i]) for i in range(6) if np.all(calibration[i] != -1)]
            darts_disp = [tuple(d) for d in self.predict.transform_to_boardplane(np.linalg.inv(self.H), np.array(self.dart_coords), self.crop_size)] if self.dart_coords else []
        self._publish(img, fps, True, cal_points, darts_disp, boxes)

    def _track(self, board_darts):
        # a dart counts once it's seen in the same place in REPEAT_THRESHOLD of the last 5 frames
        slot = self.pred_queue_count % 5
        self.pred_queue[slot] = -1
        if len(board_darts):
            self.pred_queue[slot][:min(3, len(board_darts))] = board_darts[:3]
        self.pred_queue_count += 1

        clear_frames = sum(np.all(f == -1) for f in self.pred_queue)
        if self.ignore_until_clear:
            if clear_frames >= REPEAT_THRESHOLD:
                self.reset_visit()
            return
        if self.announced:
            if clear_frames >= REPEAT_THRESHOLD: # darts pulled out: the visit is complete
                darts = list(self.darts)
                self._record_visit()
                self.reset_visit()
                self._pending.append((self.on_visit, (darts,)))
            return
        if len(self.dart_coords) >= 3:
            return

        preds = [p for f in self.pred_queue for p in f if not np.any(p == -1)]
        groups = []
        for p in preds:
            for g in groups:
                if np.linalg.norm(g[0] - p) < 0.01:
                    g.append(p)
                    break
            else:
                groups.append([p])
        for g in sorted(groups, key=len, reverse=True):
            if len(g) < REPEAT_THRESHOLD or len(self.dart_coords) >= 3:
                break
            mean = np.mean(g, axis=0)
            if all(np.linalg.norm(c - mean) > 0.01 for c in self.dart_coords):
                self.dart_coords.append(mean)

    def _draw_board_outline(self, img):
        c = DISPLAY_SIZE / 2
        radii = self.predict.scoring_radii * DISPLAY_SIZE
        for r in radii[1:]:
            cv2.circle(img, (int(c), int(c)), int(round(r)), (80, 90, 255), 1, cv2.LINE_AA)
        for angle in np.arange(9, 360, 18):
            a = np.deg2rad(angle)
            p1 = (int(c + radii[2] * np.cos(a)), int(c + radii[2] * np.sin(a)))
            p2 = (int(c + radii[-1] * np.cos(a)), int(c + radii[-1] * np.sin(a)))
            cv2.line(img, p1, p2, (80, 90, 255), 1, cv2.LINE_AA)

    def _publish(self, img, fps, board_found, cal_points, darts_disp, boxes):
        ok, buf = cv2.imencode('.jpg', img, [cv2.IMWRITE_JPEG_QUALITY, 80])
        self.live.update(
            board_found=board_found, fps=fps, boxes=boxes,
            calibration=[{'index': int(i), 'x': float(x), 'y': float(y)} for i, x, y in cal_points],
            darts=[{'label': self.darts[i] if i < len(self.darts) else '', 'x': float(x), 'y': float(y)} for i, (x, y) in enumerate(darts_disp)],
        )
        with self.frame_ready:
            self.jpeg = buf.tobytes()
            self.frame_ready.notify_all()

    def visit_state(self):
        with self.lock:
            return {'darts': list(self.darts), 'waiting_for_clear': self.announced or self.ignore_until_clear}
