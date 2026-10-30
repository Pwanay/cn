Network Diagnostic and Path Analysis Tool

1. Project Overview

The Network Diagnostic and Path Analysis Tool is a Computer Networks project that uses Mininet, Software-Defined Networking (SDN), and socket programming to study network performance.

The project creates a network with two hosts and four switches. It provides two different communication paths between the hosts. These paths have different network conditions, such as delay and packet loss.

The tool uses UDP client-server communication to measure network performance. It aims to help identify network problems and understand how changing paths can affect communication.

2. Problem Statement

In a computer network, problems such as high delay, packet loss, and link failure can affect communication between devices.

Traditional networks may require manual changes to routing configurations when network conditions change.

Our project explores how SDN and network monitoring can help analyse network conditions and select suitable paths for communication.

3. Project Objectives

- Create a network topology using Mininet.
- Establish two different paths between two hosts.
- Use OpenFlow-based switches and an SDN controller.
- Measure network performance using UDP socket programming.
- Monitor parameters such as Round Trip Time (RTT) and packet loss.
- Study the effect of different network conditions on communication.
- Explore dynamic path selection and recovery through SDN.

4. System Architecture

The project is divided into three main modules.

Part A – Network Topology and Path Selection

This module creates the network topology using Mininet.

- Two hosts: h1 and h2.
- Four switches: s1, s2, s3, and s4.
- Two communication paths:

Path A: h1 → s1 → s2 → s4 → h2

Path B: h1 → s1 → s3 → s4 → h2

Different delay and packet-loss conditions are configured for the paths. The topology uses OpenFlow 1.3 switches and connects to an SDN controller.

Part B – SDN Controller and Path Analysis

This module is responsible for controlling the network through an SDN controller.

Its intended functions include:

- Communicating with OpenFlow switches.
- Monitoring network conditions.
- Analysing the available paths.
- Updating forwarding rules based on network conditions.
- Supporting dynamic path selection and recovery.

Part C – UDP-Based Network Diagnostics

This module uses UDP sockets to measure network performance.

It consists of:

UDP Server
- Listens for incoming UDP packets.
- Receives packets from the client.
- Sends the received data back to the client.

UDP Client
- Sends packets to the server.
- Measures Round Trip Time (RTT).
- Identifies lost packets.
- Calculates packet-loss percentage.
- Displays minimum, average, and maximum RTT.

5. Technologies Used

| Technology | Purpose |
|---|---|
| Python | Implementation of topology and socket programs |
| Mininet | Network topology creation and simulation |
| Open vSwitch | Software-based network switches |
| OpenFlow 1.3 | Communication between controller and switches |
| SDN Controller | Network control and path management |
| UDP Sockets | Network communication and diagnostics |
| Linux / Ubuntu | Development and testing environment |

6. Network Configuration

The topology contains two hosts and four switches.

| Component | Configuration |
|---|---|
| Host h1 | 10.0.0.1/24 |
| Host h2 | 10.0.0.2/24 |
| Switches | s1, s2, s3, s4 |
| Controller | 127.0.0.1:6653 |
| OpenFlow version | OpenFlow 1.3 |
| Path A delay | 5 ms on configured inter-switch links |
| Path A packet loss | 0% |
| Path B delay | 20 ms on configured inter-switch links |
| Path B packet loss | 5% |

These are the configured link conditions. Actual measured performance will be added after testing.

7. Project Folder Structure

The project contains the following main program files:

CN_Project13/
│
├── topology.py
├── topology_backup.py
├── server.py
├── client.py
│
└── README.md

The SDN controller files and any additional modules will be included as they are integrated into the project.

8. How to Run the Project

Step 1: Start Open vSwitch

```bash
sudo systemctl start openvswitch-switch
```

Check its status:

```bash
sudo systemctl is-active openvswitch-switch
```
Step 2: Start the SDN Controller

Start the controller using the appropriate command for the controller implementation integrated into the project.

The controller should listen on port 6653.

Step 3: Start the Mininet Topology

Open a terminal and run:

```bash
cd ~/CN_Project13
sudo python3 topology.py
```
Step 4: Test Network Connectivity

Inside the Mininet CLI, run:

```bash
nodes
```

```bash
net
```

```bash
pingall
```
Step 5: Test Path Selection

Inside the Mininet CLI, run:

```bash
path a
```

```bash
path b
```

These commands select the predefined paths in the current topology implementation.

Step 6: Test UDP Communication

Start the UDP server on h2 from the Mininet CLI:

```bash
h2 python3 server.py
```

Open another terminal and start the Mininet topology CLI, then run the client on h1:

```bash
h1 python3 client.py 10.0.0.2 5000 20 1.0
```

The client displays packet RTT and the final packet-loss and RTT summary.


9. Performance Evaluation

The project evaluates network performance using the following parameters:

- Round Trip Time (RTT): Time taken for a packet to travel to the destination and return.
- Packet Loss:Percentage of packets that do not reach the destination and return successfully.
- Average RTT: Average time taken for successful packet exchanges.
- Minimum and Maximum RTT: Lowest and highest measured round-trip times.

Path A and Path B will be compared under their configured network conditions.

Actual measurements and comparison tables will be added after testing.

10. Challenging Scenario

The project aims to demonstrate a challenging network condition such as packet loss.

The network can be tested under different loss conditions to observe how communication is affected.

The SDN controller's response, including path changes or recovery, will be documented after the relevant functionality is implemented and tested.

11. Expected Outcome

The expected outcome is a working network diagnostic system that:

- Creates and manages a network using Mininet.
- Provides two alternative communication paths.
- Measures network performance using UDP.
- Analyses the effects of delay and packet loss.
- Uses SDN to support network management and dynamic path selection.

12. Team Contributions

| Module | Responsibility |
| Part A | Mininet topology and path selection |
| Part B | SDN controller and path analysis |
| Part C | UDP client-server communication and performance measurement |
| Integration | Combining modules, testing, and documentation |

13. Conclusion

This project demonstrates how Mininet, SDN, and socket programming can be used together to study network behaviour.

By creating alternative paths and measuring parameters such as RTT and packet loss, the project helps us understand the importance of network monitoring and path management.

It also explores how SDN can help networks respond to changing conditions and improve communication reliability.
