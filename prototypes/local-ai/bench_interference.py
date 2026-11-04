#!/usr/bin/env python3
"""What does an AI engine cost a game, per throttling profile? (Linux)

Runs frame_sim (a 144 Hz game's CPU side) alone and next to llama-server under
each profile, in shuffled rounds, and reports frame times and the AI's speed.

    bench_interference.py <cache dir> <model file> <out.jsonl>
        [--seconds 40] [--rounds 3] [--games medium,heavy] [--profiles a,b]
"""
import argparse
import json
import os
import random
import secrets
import signal
import socket
import statistics
import subprocess
import threading
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).parent
TICK = os.sysconf('SC_CLK_TCK')
LOW = ['chrt', '-i', '0', 'nice', '-n', '19', 'ionice', '-c', '3']
# 8 cores, 16 threads: 0xf0 is cores 4-7 (their second CCX on a Ryzen 3700X).
PROFILES = {
    'baseline': None,
    'naive-8t': {'wrap': [], 'args': ['-t', '8']},
    'idle-8t': {'wrap': LOW, 'args': ['-t', '8', '--poll', '0']},
    'idle-4t': {'wrap': LOW, 'args': ['-t', '4', '--poll', '0']},
    'idle-2t': {'wrap': LOW, 'args': ['-t', '2', '--poll', '0']},
    'idle-4t-pin': {'wrap': LOW, 'args': ['-t', '4', '--poll', '0', '-C', 'f0', '--cpu-strict', '1']},
    'paused': {'wrap': LOW, 'args': ['-t', '4', '--poll', '0'], 'paused': True},
}
GAMES = {
    'medium': {'threads': 4, 'target_ms': 4.0},
    'heavy': {'threads': 8, 'target_ms': 5.5},
}
PROMPT = (HERE / 'corpus' / 'page.txt').read_text()


def free_port():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


def frame_sim(sim, game, iters, seconds):
    out = subprocess.run([sim, '--iters', str(iters), '--threads', str(game['threads']), '--seconds', str(seconds)],
                         capture_output=True, text=True, check=True).stdout
    return json.loads(out)


def calibrate(sim, game):
    """Iterations so that a frame's work takes the target on the idle machine."""
    iters = int(subprocess.run([sim, '--calibrate', '--work-ms', str(game['target_ms'])],
                               capture_output=True, text=True, check=True).stdout)
    for _ in range(4):
        got = frame_sim(sim, game, iters, 4)['busy_p50']
        iters = int(iters * game['target_ms'] / got)
    return iters


def proc_cpu_seconds(pid):
    fields = Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()
    return (int(fields[11]) + int(fields[12])) / TICK


def rss_mb(pid, field='VmRSS'):
    """RssAnon is the memory really taken; RssFile (the mapped model) can be evicted."""
    for line in Path(f'/proc/{pid}/status').read_text().splitlines():
        if line.startswith(field):
            return int(line.split()[1]) / 1024
    return 0.0


class Engine:
    def __init__(self, engine_dir, model, profile, log):
        self.port, self.key = free_port(), secrets.token_hex(16)
        self.results, self.stop = [], threading.Event()
        cmd = profile['wrap'] + [str(engine_dir / 'llama-server'), '-m', str(model), '--host', '127.0.0.1',
                                 '--port', str(self.port), '--api-key', self.key, '-np', '1', '-c', '4096',
                                 '--threads-http', '1'] + profile['args']
        env = dict(os.environ, LD_LIBRARY_PATH=str(engine_dir))
        t = time.monotonic()
        self.proc = subprocess.Popen(cmd, env=env, stdout=log, stderr=log)
        while True:
            if self.proc.poll() is not None:
                raise RuntimeError('engine exited, see its log')
            try:
                urllib.request.urlopen(f'http://127.0.0.1:{self.port}/health', timeout=2)
                break
            except OSError:
                time.sleep(0.2)
        self.load_s = time.monotonic() - t
        self.thread = threading.Thread(target=self._loop, daemon=True)

    def _loop(self):
        body = json.dumps({'prompt': PROMPT, 'n_predict': 150, 'ignore_eos': True, 'cache_prompt': False}).encode()
        while not self.stop.is_set():
            req = urllib.request.Request(f'http://127.0.0.1:{self.port}/completion', data=body, headers={
                'Content-Type': 'application/json', 'Authorization': f'Bearer {self.key}'})
            try:
                with urllib.request.urlopen(req, timeout=600) as r:
                    self.results.append(json.load(r)['timings'])
            except OSError:
                return

    def close(self):
        self.stop.set()
        if self.proc.poll() is None:
            self.proc.send_signal(signal.SIGCONT)
            self.proc.kill()  # SIGTERM would wait for the generation to end
        self.proc.wait(timeout=30)


def run(args, game_name, game, iters, name, engine_dir, model, log):
    profile = PROFILES[name]
    engine = None
    row = {'game': game_name, 'profile': name, 'loadavg_before': os.getloadavg()[0]}
    try:
        if profile:
            engine = Engine(engine_dir, model, profile, log)
            row['load_s'] = round(engine.load_s, 2)
            if not profile.get('paused'):
                engine.thread.start()
                time.sleep(3)  # in full flight when the frames start
            else:
                os.kill(engine.proc.pid, signal.SIGSTOP)
            cpu0 = proc_cpu_seconds(engine.proc.pid)
        t0 = time.monotonic()
        row |= frame_sim(args.sim, game, iters, args.seconds)
        if engine:
            row['engine_cores'] = round((proc_cpu_seconds(engine.proc.pid) - cpu0) / (time.monotonic() - t0), 2)
            row['engine_rss_mb'] = round(rss_mb(engine.proc.pid))
            row['engine_anon_mb'] = round(rss_mb(engine.proc.pid, 'RssAnon'))
            done = engine.results
            if done:
                row['gen_tps'] = round(statistics.median(t['predicted_per_second'] for t in done), 1)
                row['prompt_tps'] = round(statistics.median(t['prompt_per_second'] for t in done), 1)
                row['requests'] = len(done)
    finally:
        if engine:
            engine.close()
    return row


def summary(rows):
    print(f"\n{'game':8}{'profile':14}{'fps':>7}{'1% low':>8}{'missed%':>9}{'p99 ms':>8}{'p99.9':>8}"
          f"{'AI tok/s':>10}{'cores':>7}{'RSS MB':>8}{'anon MB':>9}")
    for game in sorted({r['game'] for r in rows}):
        for name in PROFILES:
            sel = [r for r in rows if r['game'] == game and r['profile'] == name]
            if not sel:
                continue
            med = lambda key: statistics.median(r[key] for r in sel if key in r) if any(key in r for r in sel) else 0
            print(f"{game:8}{name:14}{med('fps'):7.1f}{med('one_pct_low_fps'):8.1f}{med('missed_pct'):9.2f}"
                  f"{med('busy_p99'):8.2f}{med('busy_p999'):8.2f}{med('gen_tps'):10.1f}{med('engine_cores'):7.2f}"
                  f"{med('engine_rss_mb'):8.0f}{med('engine_anon_mb'):9.0f}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument('cache', type=Path)
    p.add_argument('model')
    p.add_argument('out', type=Path)
    p.add_argument('--seconds', type=int, default=40)
    p.add_argument('--rounds', type=int, default=3)
    p.add_argument('--games', default='medium,heavy')
    p.add_argument('--profiles', default=','.join(PROFILES))
    args = p.parse_args()
    args.sim = str(args.cache / 'frame_sim')
    engine_dir = next(args.cache.glob('llama-b*/llama-b*'))
    model = args.cache / 'models' / args.model
    rng = random.Random(4717)
    rows = []
    with open(args.cache / 'engine.log', 'ab') as log, open(args.out, 'a') as out:
        for game_name in args.games.split(','):
            game = GAMES[game_name]
            iters = calibrate(args.sim, game)
            print('calibrated', game_name, iters, flush=True)
            for round_no in range(args.rounds):
                names = args.profiles.split(',')
                rng.shuffle(names)  # drift and neighbours do not favor a profile
                for name in names:
                    row = run(args, game_name, game, iters, name, engine_dir, model, log)
                    row['round'] = round_no
                    rows.append(row)
                    out.write(json.dumps(row) + '\n')
                    out.flush()
                    print(game_name, round_no, name, row.get('one_pct_low_fps'), row.get('gen_tps'), flush=True)
    summary(rows)


if __name__ == '__main__':
    main()
