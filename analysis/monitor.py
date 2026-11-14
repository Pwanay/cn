import json
import os
import re
import subprocess
import threading
import time

import diagnose
from diagnose import ROOT, SRC_IP, DST_IP, PORT, api_get, api_pin, route_name

SAMPLE_RE = re.compile(r"seq=(\d+) (?:rtt=([\d.]+) ms|LOST)")


class Monitor:
    def __init__(self, net, consec_lost=5, cooldown=30, probe_timeout=0.3, survey_count=20):
        self.net = net
        self.consec_lost = consec_lost
        self.cooldown = cooldown
        self.probe_timeout = probe_timeout
        self.survey_count = survey_count

        self.active = None
        self.baseline = {}
        self.bad_until = {}
        self.lost_run = 0
        self.samples, self.events = [], []
        self.proc = None
        self.thread = None
        self.running = False
        self.t0 = None

    def start(self):
        results, best = diagnose.run(self.net, self.survey_count)
        if best is None:
            print("Monitor not started: no working path.")
            return False
        self.baseline = {tuple(r["path"]): r for r in results}
        self.active = best["path"]
        client = os.path.join(ROOT, "udp", "client.py")
        self.proc = self.net.get("h1").popen(
            ["python3", "-u", client, DST_IP, str(PORT), "1000000", str(self.probe_timeout)],
            stdout=subprocess.PIPE, text=True)
        self.t0 = time.time()
        self.running = True
        self._event("start", f"monitoring {route_name(self.active)}")
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()
        return True

    def mark(self, text):
        self._event("mark", text)

    def stop(self):
        self.running = False
        if self.proc:
            self.proc.terminate()
        if self.thread:
            self.thread.join(timeout=3)
        os.makedirs(f"{ROOT}/results", exist_ok=True)
        fname = f"{ROOT}/results/monitor_{time.strftime('%Y%m%d_%H%M%S')}.json"
        with open(fname, "w") as f:
            json.dump({"events": self.events, "samples": self.samples,
                       "baseline": {route_name(list(k)): v for k, v in self.baseline.items()}},
                      f, indent=2)
        print(f"Monitor stopped. Saved {fname}")
        return fname

    def _now(self):
        return round(time.time() - self.t0, 3)

    def _event(self, kind, detail):
        self.events.append({"t": self._now(), "kind": kind, "detail": detail})
        print(f"[monitor t={self._now():.1f}s] {kind.upper()}: {detail}")

    def _paths(self):
        try:
            return api_get(f"/paths?src={SRC_IP}&dst={DST_IP}")["paths"]
        except Exception:
            return None

    def _loop(self):
        last_check = 0.0
        for line in self.proc.stdout:
            if not self.running:
                break
            m = SAMPLE_RE.search(line)
            if not m:
                continue
            rtt = float(m.group(2)) if m.group(2) else None
            self.samples.append({"t": self._now(), "seq": int(m.group(1)), "rtt": rtt,
                                 "path": route_name(self.active)})
            self.lost_run = self.lost_run + 1 if rtt is None else 0

            reason = None
            if self.lost_run >= self.consec_lost:
                reason = f"{self.lost_run} consecutive probes lost"
            elif time.time() - last_check > 1.0:
                last_check = time.time()
                paths = self._paths()
                if paths is not None and self.active not in paths:
                    reason = "active path no longer exists in the topology (link down)"
            if reason:
                self._failover(reason)

    def _failover(self, reason):
        old = self.active
        self.bad_until[tuple(old)] = time.time() + self.cooldown
        self.lost_run = 0
        now = time.time()
        others = [p for p in (self._paths() or [])
                  if p != old and self.bad_until.get(tuple(p), 0) < now]
        if not others:
            self._event("no-alternative", f"{route_name(old)} failed ({reason}), no other path available")
            self.bad_until[tuple(old)] = 0
            time.sleep(2)
            return

        def score(p):                               
            b = self.baseline.get(tuple(p))
            return (b["loss_pct"], b["rtt_avg"] or 1e9) if b else (100.0, 1e9)
        new = min(others, key=score)
        try:
            api_pin(new)
        except Exception as e:
            self._event("error", f"could not pin {route_name(new)}: {e}")
            return
        self.active = new
        self._event("failover", f"{route_name(old)} => {route_name(new)}  ({reason})")