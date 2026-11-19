[View Project Report (PDF)](AM557_AM517_AM520_report.pdf)

# Network Diagnostic and Path Analysis Tool

A Computer Networks project that combines **UDP socket programming**, **Mininet** and an **SDN controller (os-ken, OpenFlow 1.3)**. UDP probes measure round-trip time (RTT) and packet loss on two alternative paths between two hosts. The measurements are tied to the paths discovered by the controller, failed or degraded paths are detected, and traffic is moved to a better path through the controller.

## Architecture

```
                s2   (Path A: 5 ms, 0% loss)
              /    \
 h1 (10.0.0.1) - s1     s4 - h2 (10.0.0.2)
              \    /
                s3   (Path B: 20 ms, 5% loss)

 os-ken controller (sdn/cont.py)  <-- OpenFlow 1.3 (6653) -->  switches s1-s4
        ^
        | REST API (127.0.0.1:8080)
 diagnose / monitor (analysis/)  -->  UDP probes between h1 and h2 (port 5000)
```

| Part | Files | Role |
|---|---|---|
| UDP diagnostics | `udp/server.py`, `udp/client.py` | Echo server; client measures RTT and loss |
| Network and SDN | `sdn/diamond.py`, `sdn/cont.py` | Mininet topology; controller with topology discovery, loop-free forwarding and a path REST API |
| Analysis | `analysis/diagnose.py`, `analysis/monitor.py` | Probe and compare every path, pin the best one; continuous monitoring with failover and recovery |

## Requirements

- Linux (tested on Ubuntu 24.04, Python 3.12) with root access (`sudo`)
- Mininet and Open vSwitch
- Python packages from `requirements.txt`: `os-ken==3.1.1` and `networkx`

```bash
sudo apt install mininet openvswitch-switch python3-venv python3-pip git
git clone https://github.com/Pwanay/cn.git
cd cn
python3 -m venv ~/ryu-env
~/ryu-env/bin/pip install -r requirements.txt
```

os-ken is used instead of Ryu because Ryu does not install on Python 3.12, and version 3.1.1 is pinned because the newest release lacks its command-line manager.

## How to run

Use two terminals. All paths are relative to the repository root.

**Terminal 1: controller** (venv Python, no `sudo`, started from `sdn/`)

```bash
cd sdn
~/ryu-env/bin/python -m os_ken.cmd.manager cont.py --observe-links
```

It is ready when it prints `REST API listening on http://127.0.0.1:8080`.

**Terminal 2: network** (system Python, with `sudo`, started from the repository root)

```bash
sudo mn -c
sudo python3 sdn/diamond.py
```

Wait until the controller prints `TOPOLOGY switches=[1, 2, 3, 4]` with four links. At the `mininet>` prompt:

| Command | What it does |
|---|---|
| `diagnose [N]` | Probes every path with N probes (default 30), prints a comparison table, pins the best path |
| `monitor start` | Surveys the paths, pins the best, then probes continuously and fails over when the active path fails |
| `monitor mark TEXT` | Labels the timeline (for example `link-down`) |
| `monitor stop` | Stops and saves `results/monitor_<time>.json` |
| `path a\|b\|off`, `probe [N]` | Manual demo commands (manual path rules and plain probes); use them with the monitor stopped |

Inject faults with `link s1 s2 down` (hard failure) or
`sh tc qdisc change dev s1-eth2 root netem delay 5ms loss 50% && tc qdisc change dev s2-eth1 root netem delay 5ms loss 50%` (soft failure, link stays up).

**UDP tools on their own** (any machine, no Mininet needed)

```bash
python3 udp/server.py [port] [-v]                       # default port 5000, -v prints each probe
python3 udp/client.py <dest_ip> <port> [count] [timeout_s]
```

Exit Mininet with `exit`, then run `sudo mn -c` before the next session.

## Results (mean of 3 runs per condition)

| Condition | Static loss | Static RTT | Dynamic loss | Dynamic RTT | Dynamic outage |
|---|---|---|---|---|---|
| Normal | 16.3% | 81.4 ms | 0.0% | 21.2 ms | n/a |
| Soft failure (50% loss on Path A) | 70.0% | 21.4 ms (replies only) | 25.0% | 80.3 ms after failover | 2.8 s |
| Hard failure (link s1-s2 down) | 100% | no replies | 23.3% | 81.3 ms after failover | 0.6 s |

Static means a fixed route with no measurement and no rerouting; dynamic means `diagnose` and the monitor. For the failure rows, loss is counted over the first 100 probes after the fault. Raw results are in `results/final/`, and the full analysis is in the project report.

## Repository structure

```
sdn/            cont.py, diamond.py
udp/            server.py, client.py
analysis/       diagnose.py, monitor.py
results/final/  saved runs
requirements.txt
README.md
```

## Troubleshooting

- **`ModuleNotFoundError: No module named 'cont'`:** start the controller from inside `sdn/`.
- **`RTNETLINK answers: File exists`:** run `sudo mn -c` and start the topology again.
- **`diagnose` reports "host not seen yet":** make sure the controller is running, then try again.
- **The controller must not run under `sudo` or without the venv, and `diamond.py` must run under `sudo` with the system Python.**

## Limitations

- One host pair and two paths.
- Soft-failure detection relies on five consecutive lost probes, so a path that only becomes slow is not detected.
- Testing a recovered path uses live traffic, which costs a short burst of loss if the path is still bad.

## Team contributions

Pranay KR :- SDN controller and path analysis, report
Sharika Shetty :- udp probes, report
Saniya DS :- Mininet topology, report
