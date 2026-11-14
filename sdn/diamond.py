import os
import sys

from mininet.net import Mininet
from mininet.node import RemoteController, OVSSwitch
from mininet.link import TCLink
from mininet.cli import CLI
from mininet.log import setLogLevel

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "analysis"))


class DiamondCLI(CLI):
    monitor = None

    def do_diagnose(self, line):
        "diagnose [N] : probe every path between h1 and h2 and pin the best one"
        import diagnose
        diagnose.run(self.mn, int(line.strip() or 30))

    def do_monitor(self, line):
        "monitor start | stop | mark TEXT : continuous probing with automatic failover"
        parts = line.split(None, 1)
        cmd = parts[0] if parts else ""
        if cmd == "start":
            if self.monitor:
                print("monitor already running")
                return
            import monitor
            self.monitor = monitor.Monitor(self.mn)
            if not self.monitor.start():
                self.monitor = None
        elif cmd == "mark" and self.monitor:
            self.monitor.mark(parts[1] if len(parts) > 1 else "mark")
        elif cmd == "stop" and self.monitor:
            self.monitor.stop()
            self.monitor = None
        else:
            print("usage: monitor start | stop | mark TEXT")

    def _stop_monitor(self):
        if self.monitor:
            self.monitor.stop()
            self.monitor = None

    def do_EOF(self, line):
        self._stop_monitor()
        return super().do_EOF(line)

    def do_exit(self, line):
        self._stop_monitor()
        return super().do_exit(line)



DEMO_PATHS = {
    "a": {"s1": [(1, 2), (2, 1)], "s2": [(1, 2), (2, 1)], "s4": [(1, 3), (3, 1)]},
    "b": {"s1": [(1, 3), (3, 1)], "s3": [(1, 2), (2, 1)], "s4": [(2, 3), (3, 2)]},
}


def _demo_clear(cli):
    """Remove only the manual in_port rules (the controller's rules are untouched)."""
    for sw, ports in {"s1": [1, 2, 3], "s2": [1, 2], "s3": [1, 2], "s4": [1, 2, 3]}.items():
        for in_port in ports:
            cli.mn.get(sw).cmd(f'ovs-ofctl -O OpenFlow13 del-flows {sw} "in_port={in_port}"')


def _demo_do_path(self, line):
    "path a|b|off : install Path A or Path B by hand, or remove the manual rules"
    which = line.strip().lower()
    if which not in ("a", "b", "off"):
        print("usage: path a|b|off")
        return
    _demo_clear(self)
    if which == "off":
        return
    for sw, pairs in DEMO_PATHS[which].items():
        for in_p, out_p in pairs:
            self.mn.get(sw).cmd(f'ovs-ofctl -O OpenFlow13 add-flow {sw} '
                                f'"in_port={in_p},actions=output:{out_p}"')


def _demo_do_probe(self, line):
    "probe [N] : start the echo server on h2 and run N probes from h1 (default 20)"
    h1, h2 = self.mn.get("h1"), self.mn.get("h2")
    h2.cmd("pkill -f server.py")
    h2.cmd(f'python3 "{ROOT}/udp/server.py" 5000 &')
    print(h1.cmd(f'python3 "{ROOT}/udp/client.py" 10.0.0.2 5000 {line.strip() or 20}'))


DiamondCLI.do_path = _demo_do_path
DiamondCLI.do_probe = _demo_do_probe


def build():
    net = Mininet(controller=None, link=TCLink,
                  switch=lambda name, **kw: OVSSwitch(name, protocols="OpenFlow13", **kw),
                  autoSetMacs=True)

    net.addController("c0", controller=RemoteController, ip="127.0.0.1", port=6653)

    h1 = net.addHost("h1", ip="10.0.0.1/24")
    h2 = net.addHost("h2", ip="10.0.0.2/24")
    s1, s2, s3, s4 = [net.addSwitch(n, dpid=f"{i:016x}")
                      for i, n in enumerate(["s1", "s2", "s3", "s4"], start=1)]


    net.addLink(h1, s1, port2=1)
    net.addLink(h2, s4, port2=3)


    net.addLink(s1, s2, port1=2, port2=1, delay="5ms", loss=0)
    net.addLink(s2, s4, port1=2, port2=1, delay="5ms", loss=0)


    net.addLink(s1, s3, port1=3, port2=1, delay="20ms", loss=5)
    net.addLink(s3, s4, port1=2, port2=2, delay="20ms", loss=5)

    return net


if __name__ == "__main__":
    setLogLevel("info")
    net = build()
    net.start()
    DiamondCLI(net)
    net.stop()