import json
import os
import re
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
API = "http://127.0.0.1:8080"
SRC_IP, DST_IP, PORT = "10.0.0.1", "10.0.0.2", 5000


def api_get(route):
    with urllib.request.urlopen(API + route, timeout=5) as r:
        return json.load(r)


def api_pin(path):
    req = urllib.request.Request(
        API + "/path", method="POST",
        data=json.dumps({"src": SRC_IP, "dst": DST_IP, "path": path}).encode())
    with urllib.request.urlopen(req, timeout=5) as r:
        return json.load(r)


def route_name(path):
    return "->".join(f"s{d}" for d in path)


def parse_probe_output(text):
    m = re.search(r"sent=(\d+) received=(\d+) loss=([\d.]+)%", text)
    if not m:
        return None
    sent, received, loss = int(m.group(1)), int(m.group(2)), float(m.group(3))
    r = re.search(r"min/avg/max = ([\d.]+)/([\d.]+)/([\d.]+)", text)
    rtt = tuple(map(float, r.groups())) if r else (None, None, None)
    return {"sent": sent, "received": received, "loss_pct": loss,
            "rtt_min": rtt[0], "rtt_avg": rtt[1], "rtt_max": rtt[2]}


def run(net, count=30, timeout=1.0):
    h1, h2 = net.get("h1"), net.get("h2")

    h1.cmd(f"ping -c 2 -W 2 {DST_IP}")
    h2.cmd(f"ping -c 2 -W 2 {SRC_IP}")
    paths = api_get(f"/paths?src={SRC_IP}&dst={DST_IP}")["paths"]
    print(f"\nFound {len(paths)} path(s) between {SRC_IP} and {DST_IP}\n")

    h2.cmd("pkill -f server.py")
    h2.cmd(f'python3 "{ROOT}/udp/server.py" {PORT} &')
    time.sleep(0.5)

    results = []
    for path in paths:
        api_pin(path)
        time.sleep(0.5)
        out = h1.cmd(f'python3 "{ROOT}/udp/client.py" {DST_IP} {PORT} {count} {timeout}')
        stats = parse_probe_output(out) or {"sent": count, "received": 0, "loss_pct": 100.0,
                                            "rtt_min": None, "rtt_avg": None, "rtt_max": None}
        stats.update(path=path, route=route_name(path), hops=len(path),
                     status="DOWN" if stats["received"] == 0 else "UP")
        results.append(stats)

    up = [r for r in results if r["status"] == "UP"]
    best = min(up, key=lambda r: (r["loss_pct"], r["rtt_avg"])) if up else None

    print(f"{'Route':<12}{'Hops':<6}{'Status':<8}{'Loss %':<9}{'RTT min/avg/max (ms)':<26}")
    for r in results:
        rtt = ("-" if r["rtt_avg"] is None else
               f"{r['rtt_min']:.1f}/{r['rtt_avg']:.1f}/{r['rtt_max']:.1f}")
        mark = "  <- best" if r is best else ""
        print(f"{r['route']:<12}{r['hops']:<6}{r['status']:<8}{r['loss_pct']:<9.1f}{rtt:<26}{mark}")

    if best:
        api_pin(best["path"])
        print(f"\nPinned best path: {best['route']}")
    else:
        print("\nNo working path found.")
    return results, best