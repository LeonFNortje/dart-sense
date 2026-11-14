"""Dart Sense web UI: python app.py opens the scoring app in its own browser window."""
import argparse
import json
import logging
import os
import queue
import random
import shutil
import subprocess
import threading
import time
import urllib.request

from flask import Flask, Response, jsonify, request, send_from_directory
from werkzeug.serving import make_server

from engine import DetectionEngine
from match import Match

logging.getLogger('werkzeug').setLevel(logging.WARNING) # no per-request log lines
WEB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'web')
app = Flask(__name__, static_folder=None)
VOICE = 'gmw/en+Annie' # espeak-ng female variant
CALL_SCORE_BELOW = 120 # also call what the next player needs when they are this close
LEADER_AFTER_TURNS = 6 # start calling the leader after this many turns in a leg, across all players
BUST_CALL = 'Oh no - BUST!! that does not count!'
TURN_CALL_PAUSE = 1 # seconds between the phrases of a next player call
NAME_REPEAT_PAUSE = 2 # seconds before the name is called the last time


class Speaker:
    # pyttsx3 isn't thread safe, so all speech goes through one worker thread
    def __init__(self):
        self.enabled = True
        self.queue = queue.Queue()
        threading.Thread(target=self._run, daemon=True).start()

    def say(self, text):
        if self.enabled:
            self.queue.put(text)

    def pause(self, seconds):
        if self.enabled:
            self.queue.put(seconds)

    def clear(self):
        while not self.queue.empty():
            self.queue.get_nowait()

    def _run(self):
        try:
            import pyttsx3
            engine = pyttsx3.init()
        except Exception as e:
            print(f'Score calling disabled: {e}')
            return
        try:
            engine.setProperty('voice', VOICE)
        except Exception as e: # not every TTS backend has this voice, keep its default
            print(f'Using default voice: {e}')
        while True:
            item = self.queue.get()
            if isinstance(item, str):
                engine.say(item)
                engine.runAndWait()
            else:
                time.sleep(item)


class Session:
    def __init__(self):
        self.lock = threading.RLock()
        self.match = None
        self.engine = None
        self.version = 0
        self.message = None
        self.speaker = Speaker()

    def changed(self, message=None):
        self.version += 1
        if message:
            self.message = {'text': message, 'id': self.version}

    # called from the detection thread
    def evaluate(self, darts):
        m = self.match
        return m.evaluate(darts) if m else {'bust': False, 'checkout': False}

    def call_score(self, ev):
        if ev['bust']:
            self.speaker.say(BUST_CALL)
            self.speaker.say(BUST_CALL)
        else:
            self.speaker.say('Game shot' if ev['checkout'] else str(ev['scored']))

    def on_announce(self, darts):
        self.call_score(self.evaluate(darts))
        with self.lock:
            self.changed()

    def leaders(self):
        m = self.match
        turns = sum(v['set'] == m.set_no and v['leg'] == m.leg_no for v in m.history)
        lowest = [name for name, score in zip(m.players, m.scores) if score == min(m.scores)]
        return lowest if turns >= LEADER_AFTER_TURNS and len(lowest) < m.n else [] # nobody leads if everyone is level

    def call_next_player(self):
        m = self.match
        name, score = m.players[m.current], m.scores[m.current]
        leaders = self.leaders()
        first, last = name, name
        if leaders == [name]:
            first = f"{name} - you're the leader at {score}"
        elif leaders:
            lead = 'is the leader' if len(leaders) == 1 else 'are tied for the lead'
            first = f"{' and '.join(leaders)} {lead} at {min(m.scores)}, {name}"
        if score < CALL_SCORE_BELOW and leaders != [name]:
            last = f'{name}, {score} left to score'
        self.speaker.say(first)
        self.speaker.pause(TURN_CALL_PAUSE)
        self.speaker.say('next turn')
        self.speaker.pause(TURN_CALL_PAUSE)
        self.speaker.say(name)
        self.speaker.pause(NAME_REPEAT_PAUSE)
        self.speaker.say(last)

    def on_visit(self, darts, manual_points=None):
        with self.lock:
            if self.match is None or self.match.winner is not None:
                return
            name = self.match.players[self.match.current]
            visit = self.match.visit_from_darts(darts) if manual_points is None else self.match.visit_from_total(manual_points)
            if manual_points is not None:
                self.call_score(visit)
            event = visit['event']
            if event == 'match':
                self.speaker.say(f'and the match. {name} wins')
                self.changed(f'{name} wins the match!')
            elif event in ('leg', 'set'):
                starter = self.match.players[self.match.current]
                self.speaker.say(f'and the {event}. {starter} to throw first')
                self.changed(f'{name} wins the {event}!')
            else:
                self.call_next_player()
                self.changed()

    def state(self):
        with self.lock:
            game = self.match.state() if self.match else None
            message = self.message
        live = dict(self.engine.live) if self.engine else None
        visit = self.engine.visit_state() if self.engine else None
        if game and visit:
            visit['evaluation'] = self.match.evaluate(visit['darts']) if visit['darts'] else None
        recorder = self.engine.recorder if self.engine else None
        return {'game': game, 'live': live, 'visit': visit, 'message': message,
                'view': self.engine.display_mode if self.engine else 'imageplane',
                'training': dict(recorder.saved) if recorder and recorder.enabled else None}


session = Session()


def get_engine():
    if session.engine is None:
        session.engine = DetectionEngine()
    return session.engine


@app.get('/')
def index():
    return send_from_directory(WEB_DIR, 'index.html')


@app.get('/web/<path:path>')
def static_files(path):
    return send_from_directory(WEB_DIR, path)


@app.get('/stream.mjpg')
def stream():
    engine = get_engine()

    def frames():
        while True:
            with engine.frame_ready:
                engine.frame_ready.wait(timeout=1)
                jpeg = engine.jpeg
            if jpeg:
                yield b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + jpeg + b'\r\n'
    return Response(frames(), mimetype='multipart/x-mixed-replace; boundary=frame')


@app.get('/events')
def events():
    def stream_state():
        last = None
        while True:
            payload = json.dumps(session.state())
            if payload != last:
                last = payload
                yield f'data: {payload}\n\n'
            time.sleep(1 / 15)
    return Response(stream_state(), mimetype='text/event-stream', headers={'Cache-Control': 'no-cache'})


@app.post('/api/start')
def start():
    cfg = request.get_json()
    try:
        match = Match([p.strip() or f'Player {i+1}' for i, p in enumerate(cfg['players'])],
                      start_score=int(cfg['start_score']), target=int(cfg['target']), unit=cfg['unit'],
                      match_format=cfg['format'], in_mode=cfg['in_mode'], out_mode=cfg['out_mode'],
                      first_player=random.randrange(len(cfg['players'])))
    except (AssertionError, KeyError, ValueError) as e:
        return jsonify(error=str(e) or 'invalid settings'), 400
    session.speaker.enabled = bool(cfg.get('call_scores', True))
    engine = get_engine()
    engine.recorder.enabled = bool(cfg.get('save_training', False))
    with session.lock:
        session.match = match
        session.message = None
        session.changed()
    engine.reset_visit()
    engine.start(cfg['camera'], session.evaluate, session.on_announce, session.on_visit)
    session.speaker.say(f'{match.players[match.current]} to throw first. Game on')
    return jsonify(ok=True)


@app.post('/api/end')
def end():
    if session.engine:
        session.engine.stop()
    with session.lock:
        session.match = None
        session.changed()
    return jsonify(ok=True)


@app.post('/api/score')
def manual_score():
    if session.match is None:
        return jsonify(error='No match running'), 400
    try:
        points = int(request.get_json()['points'])
    except (KeyError, TypeError, ValueError):
        return jsonify(error='Enter a score from 0 to 180'), 400
    try:
        session.on_visit(None, manual_points=points) # Match validates the score before changing anything
    except ValueError as e:
        return jsonify(error=str(e)), 400
    session.engine.reset_visit(wait_for_clear=True)
    return jsonify(ok=True)


@app.post('/api/commit')
def commit():
    session.engine.commit_now()
    return jsonify(ok=True)


@app.post('/api/undo')
def undo():
    with session.lock:
        undone = session.match.undo() if session.match else False
        if undone:
            session.speaker.clear() # the queued calls were for the turn that was just undone
        session.changed()
    session.engine.reset_visit(wait_for_clear=True)
    return jsonify(ok=undone)


@app.post('/api/dart')
def dart_action():
    body = request.get_json()
    engine = session.engine
    action = body['action']
    if action == 'add':
        engine.add_dart()
    elif action == 'move':
        engine.move_point(body['kind'], int(body['index']), float(body['x']), float(body['y']))
    elif action == 'delete':
        engine.delete_point(body['kind'], int(body['index']))
    return jsonify(ok=True)


@app.post('/api/view')
def view():
    mode = request.get_json()['mode']
    if mode in ('imageplane', 'boardplane'):
        get_engine().display_mode = mode
    return jsonify(ok=True)


@app.get('/api/camera-check')
def camera_check():
    ip = request.args.get('ip', '')
    try:
        with urllib.request.urlopen(f'http://{ip}/shot.jpg', timeout=2) as r:
            return jsonify(ok=r.status == 200)
    except Exception as e:
        return jsonify(ok=False, error=str(e))


def float_on_hyprland(pid, window_class, width=1500, height=950):
    # tiling WMs would otherwise stretch the app window over the whole workspace; this only affects the running window
    for _ in range(50):
        time.sleep(0.2)
        try:
            clients = json.loads(subprocess.check_output(['hyprctl', 'clients', '-j']))
        except (subprocess.CalledProcessError, ValueError):
            return
        # chromium draws the window from a child process, so match the --app window class rather than the pid
        window = next((c for c in clients if c.get('pid') == pid or c.get('class', '').startswith(window_class)), None)
        if window:
            address = window['address']
            # Hyprland 0.56+ takes Lua dispatchers; older versions the classic syntax (the window keeps its requested size)
            out = subprocess.run(['hyprctl', 'dispatch', f'hl.dsp.window.float({{ action = "enable", window = "address:{address}" }})'],
                                 capture_output=True, text=True).stdout
            if 'error' in out:
                subprocess.run(['hyprctl', 'dispatch', 'setfloating', f'address:{address}'], stdout=subprocess.DEVNULL)
                subprocess.run(['hyprctl', 'dispatch', 'resizewindowpixel', f'exact {width} {height},address:{address}'], stdout=subprocess.DEVNULL)
            return


def open_window(url):
    # a dedicated profile makes the browser process exit when the window closes, which then ends the app
    profile = os.path.expanduser('~/.cache/dart-sense/browser-profile')
    for browser in ('chromium', 'google-chrome-stable', 'google-chrome'):
        if shutil.which(browser):
            proc = subprocess.Popen([browser, f'--app={url}', f'--user-data-dir={profile}', '--window-size=1500,950',
                                     '--no-first-run', '--no-default-browser-check'],
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if os.environ.get('HYPRLAND_INSTANCE_SIGNATURE') and shutil.which('hyprctl'):
                threading.Thread(target=float_on_hyprland, args=(proc.pid, 'chrome-127.0.0.1'), daemon=True).start()
            return proc
    import webbrowser
    webbrowser.open(url)
    return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--no-window', action='store_true', help="don't open an app window, just serve the UI")
    args = parser.parse_args()

    get_engine() # load the model up front
    server = make_server('127.0.0.1', args.port, app, threaded=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f'http://127.0.0.1:{args.port}/'
    print(f'Dart Sense running at {url}')

    window = None if args.no_window else open_window(url)
    try:
        if window is not None:
            window.wait()
        else:
            while True:
                time.sleep(3600)
    except KeyboardInterrupt:
        pass
    if session.engine:
        session.engine.stop()
    os._exit(0)


if __name__ == '__main__':
    main()
