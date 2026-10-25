import networkx as nx

from os_ken.base import app_manager
from os_ken.controller import ofp_event
from os_ken.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER, set_ev_cls
from os_ken.lib.packet import ethernet, packet
from os_ken.ofproto import ofproto_v1_3
from os_ken.topology import event
from os_ken.topology.api import get_link, get_switch

ETH_ARP = 0x0806
ETH_IPV4 = 0x0800
BROADCAST = "ff:ff:ff:ff:ff:ff"


class Controller(app_manager.OSKenApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.datapaths = {}       # dpid -> datapath
        self.graph = nx.Graph()   # switches as nodes, links as edges
        self.link_ports = {}      # (dpid_a, dpid_b) -> port on a that faces b
        self.switch_ports = {}    # dpid -> list of port numbers
        self.mac_loc = {}         

    # ---------- switch connection ----------
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

    # ---------- topology discovery ----------
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

    # ---------- packet handling ----------
    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def packet_in_handler(self, ev):
        msg = ev.msg
        dp = msg.datapath
        dpid = dp.id
        in_port = msg.match["in_port"]

        if not self.link_ports:      # topology not discovered yet: wait for LLDP
            return

        eth = packet.Packet(msg.data).get_protocols(ethernet.ethernet)[0]
        if eth.ethertype not in (ETH_ARP, ETH_IPV4):   # ignores LLDP, IPv6, ...
            return

        is_edge = in_port in self.edge_ports().get(dpid, set())
        if is_edge:
            self.mac_loc[eth.src] = (dpid, in_port)

        if eth.dst == BROADCAST:
            if is_edge:
                self.flood_edges(msg, dpid, in_port)
            return

        if eth.dst not in self.mac_loc:
            return                   # unknown unicast: drop, never flood

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

    def install_path(self, src_dpid, dst_mac):
        """Install rules along the shortest path to dst_mac; return out port at src_dpid."""
        dst_dpid, dst_port = self.mac_loc[dst_mac]
        try:
            path = nx.shortest_path(self.graph, src_dpid, dst_dpid)
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return None
        out_at_src = None
        for i, dpid in enumerate(path):
            out = dst_port if i == len(path) - 1 else self.link_ports[(dpid, path[i + 1])]
            dp = self.datapaths[dpid]
            parser = dp.ofproto_parser
            self.add_flow(dp, 10, parser.OFPMatch(eth_dst=dst_mac),
                          [parser.OFPActionOutput(out)], idle_timeout=30)
            if i == 0:
                out_at_src = out
        self.logger.info("PATH to %s: %s", dst_mac, " -> ".join(f"s{d}" for d in path))
        return out_at_src