---
title: "【深入理解 Linux 网络】关键术语"
date: 2025-07-30T11:18:08+08:00
tags:
  - Linux
  - 计算机网络
categories:
  - 计算机网络
source: "https://blog.csdn.net/Ahri_J/article/details/149772425"
---
**本系列文章**

- [【深入理解 Linux 网络】关键术语](/posts/深入理解-linux-网络-关键术语/)
- [【深入理解 Linux 网络】内核初始化流程](/posts/深入理解-linux-网络-内核初始化流程/)
- [【深入理解 Linux 网络】收包原理与内核实现（上）从网卡到协议层](/posts/深入理解-linux-网络-收包原理上/)
- [【深入理解 Linux 网络】收包原理与内核实现（中）TCP 传输层处理](/posts/深入理解-linux-网络-收包原理中/)
- 【深入理解 Linux 网络】收包原理与内核实现（下）应用层读取与 epoll 实现（待完善）
- [【深入理解 Linux 网络】数据发送处理流程与内核实现](/posts/深入理解-linux-网络-数据发包原理/)
- 【深入理解 Linux 网络】配置调优与性能优化（待完善）

---

系统理解一个领域的核心就是理解该领域的关键概念。以下术语构成了
 Linux
网络内核的核心概念体系，理解它们有助于深入掌握网络实现原理，作为备忘整理与此。

### 硬件层面术语

<table><thead><tr><th>术语</th><th>英文全称</th><th>核心概念</th><th>在网络中的作用</th><th>关键特征</th></tr></thead><tbody><tr><td><strong>PCI</strong></td><td>Peripheral Component Interconnect</td><td>外设总线标准</td><td>连接网卡与CPU/内存的高速通道</td><td>支持DMA、中断、热插拔</td></tr><tr><td><strong>PCIe</strong></td><td>PCI Express</td><td>PCI的串行版本</td><td>提供更高带宽的网卡连接</td><td>点对点连接、多通道并行</td></tr><tr><td><strong>BAR</strong></td><td>Base Address Register</td><td>PCI设备地址寄存器</td><td>映射网卡寄存器到内存空间</td><td>6个BAR，定义MMIO区域</td></tr><tr><td><strong>MMIO</strong></td><td>Memory-Mapped I/O</td><td>内存映射IO</td><td>CPU通过内存访问方式控制网卡</td><td>统一地址空间、高效访问</td></tr><tr><td><strong>DMA</strong></td><td>Direct Memory Access</td><td>直接内存访问</td><td>网卡直接读写内存，绕过CPU</td><td>减少CPU负载、提高吞吐量</td></tr><tr><td><strong>IOMMU</strong></td><td>Input-Output Memory Management Unit</td><td>IO内存管理单元</td><td>为设备提供虚拟地址转换</td><td>内存保护、虚拟化支持</td></tr></tbody></table>

### 中断
处理术语

<table><thead><tr><th>术语</th><th>英文全称</th><th>核心概念</th><th>在网络中的作用</th><th>关键特征</th></tr></thead><tbody><tr><td><strong>硬中断</strong></td><td>Hardware Interrupt / IRQ</td><td>硬件向CPU发送的信号</td><td>网卡通知CPU有数据到达</td><td>立即响应、抢占式、短时间处理</td></tr><tr><td><strong>软中断</strong></td><td>Software Interrupt / SoftIRQ</td><td>内核延迟处理机制</td><td>处理网络数据包的主要方式</td><td>可调度、批量处理、NET_RX/NET_TX</td></tr><tr><td><strong>MSI</strong></td><td>Message Signaled Interrupts</td><td>消息信令中断</td><td>替代传统引脚中断的现代方式</td><td>通过内存写操作触发中断</td></tr><tr><td><strong>MSI-X</strong></td><td>MSI Extended</td><td>MSI的扩展版本</td><td>支持多队列网卡的多中断</td><td>每个队列独立中断、更好的CPU分布</td></tr><tr><td><strong>NAPI</strong></td><td>New API</td><td>Linux网络轮询机制</td><td>高负载时用轮询替代中断</td><td>中断+轮询混合、避免中断风暴</td></tr></tbody></table>

### 内存
管理术语

<table><thead><tr><th>术语</th><th>英文全称</th><th>核心概念</th><th>在网络中的作用</th><th>关键特征</th></tr></thead><tbody><tr><td><strong>Ring Buffer</strong></td><td>Circular Buffer</td><td>环形缓冲区</td><td>网卡与驱动间的数据交换结构</td><td>固定大小、无锁、生产者消费者模型</td></tr><tr><td><strong>skb</strong></td><td>Socket Buffer</td><td>网络数据包结构</td><td>Linux内核网络数据的统一表示</td><td>分层结构、元数据+数据、可克隆</td></tr><tr><td><strong>skb_shared_info</strong></td><td>-</td><td>skb共享信息</td><td>存储分片、GSO等扩展信息</td><td>支持零拷贝、分片重组</td></tr><tr><td><strong>DMA映射</strong></td><td>DMA Mapping</td><td>DMA地址转换</td><td>将虚拟地址转换为设备可访问地址</td><td>一致性内存、流式映射</td></tr><tr><td><strong>Page Pool</strong></td><td>-</td><td>页面池</td><td>预分配网络接收缓冲区</td><td>减少内存分配开销、提高性能</td></tr><tr><td><strong>SLUB</strong></td><td>-</td><td>Linux内存分配器</td><td>为skb等小对象提供高效分配</td><td>对象复用、CPU本地缓存</td></tr></tbody></table>

### 网络驱动术语

<table><thead><tr><th>术语</th><th>英文全称</th><th>核心概念</th><th>在网络中的作用</th><th>关键特征</th></tr></thead><tbody><tr><td><strong>网络驱动</strong></td><td>Network Driver</td><td>硬件抽象层</td><td>连接硬件网卡与内核网络栈</td><td>实现net_device_ops、管理硬件</td></tr><tr><td><strong>net_device</strong></td><td>Network Device</td><td>网络设备结构</td><td>内核中网络接口的抽象</td><td>包含操作函数、统计信息、配置参数</td></tr><tr><td><strong>netdev_ops</strong></td><td>Network Device Operations</td><td>网络设备操作集</td><td>定义网络接口的标准操作</td><td>open/close、xmit、ioctl等</td></tr><tr><td><strong>ethtool</strong></td><td>Ethernet Tool</td><td>网络工具接口</td><td>用户空间配置和查询网络设备</td><td>统计信息、参数配置、诊断功能</td></tr><tr><td><strong>多队列</strong></td><td>Multi-Queue</td><td>多发送/接收队列</td><td>利用多CPU并行处理网络数据</td><td>RSS、XPS、每CPU队列</td></tr><tr><td><strong>RSS</strong></td><td>Receive Side Scaling</td><td>接收端扩展</td><td>将接收流量分散到多个CPU</td><td>基于哈希、负载均衡、提高并发</td></tr></tbody></table>

### 协议
栈术语

<table><thead><tr><th>术语</th><th>英文全称</th><th>核心概念</th><th>在网络中的作用</th><th>关键特征</th></tr></thead><tbody><tr><td><strong>netfilter</strong></td><td>-</td><td>网络过滤框架</td><td>提供防火墙、NAT等功能的钩子</td><td>5个钩子点、可插拔模块</td></tr><tr><td><strong>iptables</strong></td><td>-</td><td>防火墙工具</td><td>基于netfilter的用户空间配置工具</td><td>表/链结构、规则匹配</td></tr><tr><td><strong>路由</strong></td><td>Routing</td><td>数据包转发决策</td><td>决定数据包的下一跳地址</td><td>路由表、策略路由、多路径</td></tr><tr><td><strong>邻居子系统</strong></td><td>Neighbor Subsystem</td><td>ARP/NDP管理</td><td>维护IP地址到MAC地址的映射</td><td>邻居缓存、状态机、老化机制</td></tr><tr><td><strong>协议栈</strong></td><td>Protocol Stack</td><td>分层网络处理</td><td>实现TCP/IP等网络协议</td><td>分层设计、数据封装/解封装</td></tr><tr><td><strong>Socket</strong></td><td>-</td><td>网络编程接口</td><td>应用程序访问网络的标准API</td><td>文件描述符、多种类型、缓冲区</td></tr></tbody></table>

### 性能优化
术语

<table><thead><tr><th>术语</th><th>英文全称</th><th>核心概念</th><th>在网络中的作用</th><th>关键特征</th></tr></thead><tbody><tr><td><strong>TSO</strong></td><td>TCP Segmentation Offload</td><td>TCP分段卸载</td><td>硬件替代软件进行TCP分段</td><td>减少CPU负载、大包处理</td></tr><tr><td><strong>GSO</strong></td><td>Generic Segmentation Offload</td><td>通用分段卸载</td><td>软件延迟分段到发送时</td><td>提高协议栈效率、支持多协议</td></tr><tr><td><strong>LRO</strong></td><td>Large Receive Offload</td><td>大包接收卸载</td><td>硬件将小包聚合成大包</td><td>减少中断次数、提高吞吐量</td></tr><tr><td><strong>GRO</strong></td><td>Generic Receive Offload</td><td>通用接收卸载</td><td>软件实现的LRO</td><td>更通用、更可控</td></tr><tr><td><strong>Checksum Offload</strong></td><td>-</td><td>校验和卸载</td><td>硬件计算/验证校验和</td><td>减少CPU计算负担</td></tr><tr><td><strong>VLAN Offload</strong></td><td>-</td><td>VLAN卸载</td><td>硬件处理VLAN标签</td><td>硬件插入/剥离VLAN头</td></tr></tbody></table>

### 虚拟化
相关术语

<table><thead><tr><th>术语</th><th>英文全称</th><th>核心概念</th><th>在网络中的作用</th><th>关键特征</th></tr></thead><tbody><tr><td><strong>SR-IOV</strong></td><td>Single Root I/O Virtualization</td><td>单根IO虚拟化</td><td>一个物理网卡虚拟出多个VF</td><td>硬件虚拟化、直通性能</td></tr><tr><td><strong>VF</strong></td><td>Virtual Function</td><td>虚拟功能</td><td>SR-IOV创建的虚拟网卡</td><td>独立的PCI功能、直接分配给VM</td></tr><tr><td><strong>PF</strong></td><td>Physical Function</td><td>物理功能</td><td>SR-IOV的主功能</td><td>管理VF、提供配置接口</td></tr><tr><td><strong>Bridge</strong></td><td>Network Bridge</td><td>网络桥接</td><td>连接不同网络段</td><td>二层转发、MAC地址学习</td></tr><tr><td><strong>VETH</strong></td><td>Virtual Ethernet</td><td>虚拟以太网</td><td>虚拟的网络接口对</td><td>容器网络、命名空间通信</td></tr><tr><td><strong>TAP/TUN</strong></td><td>-</td><td>虚拟网络设备</td><td>用户空间程序访问网络栈</td><td>TAP二层、TUN三层</td></tr></tbody></table>

### 调试与监控术语

<table><thead><tr><th>术语</th><th>英文全称</th><th>核心概念</th><th>在网络中的作用</th><th>关键特征</th></tr></thead><tbody><tr><td><strong>proc文件系统</strong></td><td>-</td><td>内核信息接口</td><td>通过文件系统暴露内核状态</td><td>/proc/net/*、运行时查看</td></tr><tr><td><strong>sysfs</strong></td><td>-</td><td>系统文件系统</td><td>设备和驱动信息接口</td><td>/sys/class/net/*、配置参数</td></tr><tr><td><strong>tracepoint</strong></td><td>-</td><td>内核跟踪点</td><td>内核函数执行的观察点</td><td>动态跟踪、性能分析</td></tr><tr><td><strong>perf</strong></td><td>Performance</td><td>性能分析工具</td><td>网络性能热点分析</td><td>CPU采样、事件计数、调用图</td></tr><tr><td><strong>tcpdump</strong></td><td>-</td><td>数据包捕获工具</td><td>网络流量分析和调试</td><td>libpcap、过滤表达式</td></tr><tr><td><strong>ss</strong></td><td>Socket Statistics</td><td>Socket统计工具</td><td>查看网络连接状态</td><td>替代netstat、更高效</td></tr></tbody></table>

### 现代网络技术术语

<table><thead><tr><th>术语</th><th>英文全称</th><th>核心概念</th><th>在网络中的作用</th><th>关键特征</th></tr></thead><tbody><tr><td><strong>XDP</strong></td><td>eXpress Data Path</td><td>快速数据路径</td><td>在驱动层进行高速包处理</td><td>eBPF、零拷贝、可编程</td></tr><tr><td><strong>eBPF</strong></td><td>extended Berkeley Packet Filter</td><td>扩展包过滤器</td><td>内核态可编程执行环境</td><td>安全沙箱、即时编译、多用途</td></tr><tr><td><strong>DPDK</strong></td><td>Data Plane Development Kit</td><td>数据面开发套件</td><td>用户空间高性能网络处理</td><td>轮询模式、大页内存、CPU绑定</td></tr><tr><td><strong>AF_XDP</strong></td><td>Address Family XDP</td><td>XDP地址族</td><td>用户空间零拷贝网络接口</td><td>与XDP配合、高吞吐量</td></tr><tr><td><strong>io_uring</strong></td><td>-</td><td>异步IO接口</td><td>高效的异步网络IO</td><td>环形队列、批量提交</td></tr><tr><td><strong>BPF Maps</strong></td><td>-</td><td>BPF数据结构</td><td>eBPF程序的数据存储和通信</td><td>多种类型、用户内核空间共享</td></tr></tbody></table>
