from mininet.net import Mininet
from mininet.node import RemoteController, OVSSwitch
from mininet.link import TCLink
from mininet.cli import CLI
from mininet.log import setLogLevel



PATHS = {
    "a": {"s1": [(1, 2), (2, 1)], "s2": [(1, 2), (2, 1)], "s4": [(1, 3), (3, 1)]},
    "b": {"s1": [(1, 3), (3, 1)], "s3": [(1, 2), (2, 1)], "s4": [(2, 3), (3, 2)]},
}


class DiamondCLI(CLI):

    def do_path(self, line):
        "path a|b : clear all flow rules and install the chosen path"
        which = line.strip().lower()
        if which not in PATHS:
            print("usage: path a|b")
            return
        for name in ("s1", "s2", "s3", "s4"):
            self.mn.get(name).cmd(f"ovs-ofctl -O OpenFlow13 del-flows {name}")
        for name, pairs in PATHS[which].items():
            for in_p, out_p in pairs:
                self.mn.get(name).cmd(
                    f'ovs-ofctl -O OpenFlow13 add-flow {name} '
                    f'"in_port={in_p},actions=output:{out_p}"')


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

