import json
from urllib.parse import parse_qs

import networkx as nx

from os_ken.base import app_manager
from os_ken.controller import ofp_event
from os_ken.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER, set_ev_cls
from os_ken.lib import hub
from os_ken.lib.packet import arp, ethernet, ipv4, packet
from os_ken.ofproto import ofproto_v1_3
from os_ken.topology import event
from os_ken.topology.api import get_link, get_switch

ETH_ARP = 0x0806
ETH_IPV4 = 0x0800
BROADCAST = "ff:ff:ff:ff:ff:ff"
API_HOST, API_PORT = "127.0.0.1", 8080
PIN_PRIORITY = 20


class ApiError(Exception):
    pass


class Controller(app_manager.OSKenApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.datapaths = {}
        self.graph = nx.Graph()
        self.link_ports = {}
        self.switch_ports = {}
        self.mac_loc = {}
        self.ip_mac = {}
        hub.spawn(self._start_api)

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        dp = ev.msg.datapath
        ofp, parser = dp.ofproto, dp.ofproto_parser
        self.datapaths[dp.id] = dp
        actions = [parser.OFPActionOutput(ofp.OFPP_CONTROLLER, ofp.OFPCML_NO_BUFFER)]
        self.add_flow(dp, 0, parser.OFPMatch(), actions)

    def add_flow(self, dp, priority, match, actions, idle_timeout=0):
        ofp, parser = dp.ofproto, dp.ofproto_parser
        inst = [parser.OFPInstructionActions(ofp.OFPIT_APPLY_ACTIONS, actions)]
        dp.send_msg(parser.OFPFlowMod(datapath=dp, priority=priority, match=match,
                                      instructions=inst, idle_timeout=idle_timeout))

    @set_ev_cls([event.EventSwitchEnter, event.EventSwitchLeave,
                 event.EventLinkAdd, event.EventLinkDelete])
    def topology_changed(self, ev):
        self.rebuild_topology()

    def rebuild_topology(self):
        graph = nx.Graph()
        link_ports = {}
        switch_ports = {}
        for sw in get_switch(self):
            graph.add_node(sw.dp.id)
            switch_ports[sw.dp.id] = [p.port_no for p in sw.ports
                                      if p.port_no < ofproto_v1_3.OFPP_MAX]
        for link in get_link(self):
            a, b = link.src.dpid, link.dst.dpid
            graph.add_edge(a, b)
            link_ports[(a, b)] = link.src.port_no
        self.graph, self.link_ports, self.switch_ports = graph, link_ports, switch_ports
        links = sorted({tuple(sorted(k)) for k in link_ports})
        self.logger.info("TOPOLOGY switches=%s links=%s", sorted(graph.nodes), links)

    def edge_ports(self):
        """Ports that face hosts: every port not used by a switch-to-switch link."""
        used = {}
        for (a, _), port in self.link_ports.items():
            used.setdefault(a, set()).add(port)
        return {dpid: set(ports) - used.get(dpid, set())
                for dpid, ports in self.switch_ports.items()}

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def packet_in_handler(self, ev):
        msg = ev.msg
        dp = msg.datapath
        dpid = dp.id
        in_port = msg.match["in_port"]

        if not self.link_ports:
            return

        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocols(ethernet.ethernet)[0]
        if eth.ethertype not in (ETH_ARP, ETH_IPV4):
            return

        is_edge = in_port in self.edge_ports().get(dpid, set())
        if is_edge:
            self.mac_loc[eth.src] = (dpid, in_port)
            a = pkt.get_protocol(arp.arp)
            ip = pkt.get_protocol(ipv4.ipv4)
            if a:
                self.ip_mac[a.src_ip] = a.src_mac
            elif ip:
                self.ip_mac[ip.src] = eth.src

        if eth.dst == BROADCAST:
            if is_edge:
                self.flood_edges(msg, dpid, in_port)
            return

        if eth.dst not in self.mac_loc:
            return
        out_port = self.install_path(dpid, eth.dst)
        if out_port is None:
            return
        ofp, parser = dp.ofproto, dp.ofproto_parser
        dp.send_msg(parser.OFPPacketOut(
            datapath=dp, buffer_id=ofp.OFP_NO_BUFFER, in_port=in_port,
            actions=[parser.OFPActionOutput(out_port)], data=msg.data))

    def flood_edges(self, msg, src_dpid, in_port):
        for dpid, ports in self.edge_ports().items():
            dp = self.datapaths.get(dpid)
            if dp is None:
                continue
            out = [p for p in ports if not (dpid == src_dpid and p == in_port)]
            if not out:
                continue
            ofp, parser = dp.ofproto, dp.ofproto_parser
            dp.send_msg(parser.OFPPacketOut(
                datapath=dp, buffer_id=ofp.OFP_NO_BUFFER, in_port=ofp.OFPP_CONTROLLER,
                actions=[parser.OFPActionOutput(p) for p in out], data=msg.data))

    def install_rules(self, path, dst_mac, dst_port, priority, idle_timeout):
        """Install a rule on every switch of `path` that forwards dst_mac along it."""
        out_at_src = None
        for i, dpid in enumerate(path):
            out = dst_port if i == len(path) - 1 else self.link_ports[(dpid, path[i + 1])]
            dp = self.datapaths[dpid]
            parser = dp.ofproto_parser
            self.add_flow(dp, priority, parser.OFPMatch(eth_dst=dst_mac),
                          [parser.OFPActionOutput(out)], idle_timeout=idle_timeout)
            if i == 0:
                out_at_src = out
        return out_at_src

    def install_path(self, src_dpid, dst_mac):
        """Default forwarding: shortest path, same route in both directions."""
        dst_dpid, dst_port = self.mac_loc[dst_mac]
        try:
            a, b = sorted((src_dpid, dst_dpid))
            path = nx.shortest_path(self.graph, a, b)
            if src_dpid != a:
                path = path[::-1]
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return None
        self.logger.info("PATH to %s: %s", dst_mac, " -> ".join(f"s{d}" for d in path))
        return self.install_rules(path, dst_mac, dst_port, priority=10, idle_timeout=30)

    def _host(self, ip):
        mac = self.ip_mac.get(ip)
        if mac is None or mac not in self.mac_loc:
            raise ApiError(f"host {ip} not seen yet (send some traffic, e.g. a ping, first)")
        dpid, port = self.mac_loc[mac]
        return mac, dpid, port

    def api_topology(self):
        links = []
        for (a, b), port in sorted(self.link_ports.items()):
            if a < b and (b, a) in self.link_ports:
                links.append({"a": a, "a_port": port, "b": b, "b_port": self.link_ports[(b, a)]})
        hosts = {ip: {"mac": mac, "dpid": self.mac_loc[mac][0], "port": self.mac_loc[mac][1]}
                 for ip, mac in self.ip_mac.items() if mac in self.mac_loc}
        return {"switches": sorted(self.graph.nodes), "links": links, "hosts": hosts}

    def api_paths(self, src_ip, dst_ip):
        _, s_dpid, _ = self._host(src_ip)
        _, d_dpid, _ = self._host(dst_ip)
        paths = sorted(nx.all_simple_paths(self.graph, s_dpid, d_dpid),
                       key=lambda p: (len(p), p))
        return {"src": src_ip, "dst": dst_ip, "paths": paths}

    def api_pin(self, req):
        src_mac, s_dpid, s_port = self._host(req["src"])
        dst_mac, d_dpid, d_port = self._host(req["dst"])
        path = [int(x) for x in req["path"]]
        if path[0] != s_dpid or path[-1] != d_dpid:
            raise ApiError("path must start at the source's switch and end at the destination's")
        for a, b in zip(path, path[1:]):
            if (a, b) not in self.link_ports:
                raise ApiError(f"no link between s{a} and s{b}")
        self.install_rules(path, dst_mac, d_port, PIN_PRIORITY, 0)
        self.install_rules(path[::-1], src_mac, s_port, PIN_PRIORITY, 0)
        self.logger.info("PINNED %s <-> %s via %s", req["src"], req["dst"],
                         " -> ".join(f"s{d}" for d in path))
        return {"pinned": path}

    def wsgi_app(self, environ, start_response):
        status, body = "200 OK", None
        try:
            method, route = environ["REQUEST_METHOD"], environ["PATH_INFO"]
            qs = parse_qs(environ.get("QUERY_STRING", ""))
            if method == "GET" and route == "/topology":
                body = self.api_topology()
            elif method == "GET" and route == "/paths":
                body = self.api_paths(qs["src"][0], qs["dst"][0])
            elif method == "POST" and route == "/path":
                n = int(environ.get("CONTENT_LENGTH") or 0)
                body = self.api_pin(json.loads(environ["wsgi.input"].read(n)))
            else:
                status, body = "404 Not Found", {"error": "unknown endpoint"}
        except ApiError as e:
            status, body = "400 Bad Request", {"error": str(e)}
        except (KeyError, IndexError, ValueError) as e:
            status, body = "400 Bad Request", {"error": f"bad request: {e!r}"}
        start_response(status, [("Content-Type", "application/json")])
        return [json.dumps(body).encode()]

    def _start_api(self):
        server = hub.WSGIServer((API_HOST, API_PORT), self.wsgi_app)
        self.logger.info("REST API listening on http://%s:%d", API_HOST, API_PORT)
        server.serve_forever()