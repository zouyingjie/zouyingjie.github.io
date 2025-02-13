---
title: 【动手实验】TCP 连接的建立与关闭抓包分析
date: 2023-09-02 09:17:14
tags:
  - 计算机网络
  - 动手实验
categories:
  - 计算机网络
  - 动手实验
description: 握个手，好朋友
---

本篇是基于[知识星球程序员踩坑案例分享](https://wx.zsxq.com/group/15552551584552)中的作业进行的复现和总结，对 TCP 连接的建立和关闭进行抓包分析和理论总结， 原文参见[TCP 连接的建立和关闭 —— 强烈建议新手看看](https://articles.zsxq.com/id_ppf2tv11zc64.html)。

## 实验环境

这里使用两台位于同一子网的腾讯云服务器，IP 分别是 node2（172.19.0.12）和 node3（172.19.0.15），内核版本均为 5.15.0-130-generic。

```shell
# node02
$ uname -a
Linux node2 5.15.0-130-generic #140-Ubuntu SMP Wed Dec 18 17:59:53 UTC 2024 x86_64 x86_64 x86_64 GNU/Linux

$ ip -4 addr
1: lo: <LOOPBACK,UP,LOWER_UP> mtu 65536 qdisc noqueue state UNKNOWN group default qlen 1000
    inet 127.0.0.1/8 scope host lo
       valid_lft forever preferred_lft forever
2: eth0: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 8500 qdisc mq state UP group default qlen 1000
    altname enp0s5
    altname ens5
    inet 172.19.0.12/20 metric 100 brd 172.19.15.255 scope global eth0
       valid_lft forever preferred_lft forever


# node03
$ uname -a
Linux node3 5.15.0-130-generic #140-Ubuntu SMP Wed Dec 18 17:59:53 UTC 2024 x86_64 x86_64 x86_64 GNU/Linux

$ ip -4 addr
1: lo: <LOOPBACK,UP,LOWER_UP> mtu 65536 qdisc noqueue state UNKNOWN group default qlen 1000
    inet 127.0.0.1/8 scope host lo
       valid_lft forever preferred_lft forever
2: eth0: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 8500 qdisc mq state UP group default qlen 1000
    altname enp0s5
    altname ens5
    inet 172.19.0.15/20 metric 100 brd 172.19.15.255 scope global eth0
       valid_lft forever preferred_lft forever
```

## 启动服务

首先我们使用 nc(netcat) 作为服务端，在 node2 监听 9527 端口：

```
# ubuntu @ node2 in ~ [10:40:58]
$ nc -k -l 172.19.0.12  9527
```
该命令表示在 IP 地址 172.19.0.12 的 9527 端口上持续监听（等待连接并接收数据）。参数含义如下：

- `-k`	保持连接（Keep Listening），在客户端断开后继续监听端口。
- `-l`	监听模式（Listen Mode），启动服务器等待连接。

启动成功后用 netstat 命令查看 socket 的连接状态：

```
$ sudo netstat -anpo | grep Recv-Q; sudo netstat -anpo | grep 9527
Proto Recv-Q Send-Q Local Address           Foreign Address         State       PID/Program name     Timer
tcp        0      0 172.19.0.12:9527        0.0.0.0:*               LISTEN      13504/nc             off (0.00/0/0)
```
netstat 命令的各个参数含义如下：

- `-a`	显示所有连接和监听的套接字。
- `-n`	显示 IP 地址和端口号，不解析主机名。
- `-o`	显示进程 ID（PID）和计时器信息。
- `-p`	显示进程名称。

可以看到 9527 端口处于 LISTEN 状态，表示正在监听端口，等待连接请求。

## 连接建立

在客户端请求 node2 之前，我们先在 node2 开启 tcpdump 抓包：

```bash
# ubuntu @ node2 in ~ [10:38:33]
$ sudo tcpdump -s0 -X -nn "tcp port 9527" -w tcp.pcap --print
tcpdump: listening on eth0, link-type EN10MB (Ethernet), snapshot length 262144 bytes
```
命令各个参数含义为：

- `-s0`	捕获完整数据包（默认 -s 只抓取前 68/96 字节），0 代表不截断。
- `-X`	以十六进制（hex）+ ASCII 格式打印数据包内容。
- `-nn`	不解析主机名和端口（-n 不解析 IP，-nn 也不解析端口）。
- `"tcp port 9527"`	仅捕获 TCP 端口 9527 的流量。
- `-w tcp.pcap`	将捕获的数据包写入 tcp.pcap 文件（可用 wireshark 或 tcpdump -r tcp.pcap 查看）。
- `--print`	同时在终端打印数据包内容（类似 -X，但 --print 仅在 -w 选项启用时生效）。

接下来我们在 node3 上使用 nc 连接 node2 的 9527 端口：

```
# ubuntu @ node3 in ~ [10:41:48]
$ nc 172.19.0.12 9527
```

我们分别在 node2 和 node3 上使用 netstat 命令查看 socket 的连接状态：

```bash
# node2
$ sudo netstat -anpo | grep -E "Recv-Q|9527"
Proto Recv-Q Send-Q Local Address           Foreign Address         State       PID/Program name     Timer
tcp        0      0 172.19.0.12:9527        0.0.0.0:*               LISTEN      13504/nc             off (0.00/0/0)
tcp        0      0 172.19.0.12:9527        172.19.0.15:48868       ESTABLISHED 13504/nc             off (0.00/0/0)


# node3
$ sudo netstat -anpo | grep -E "Recv-Q|9527"
Proto Recv-Q Send-Q Local Address           Foreign Address         State       PID/Program name     Timer
tcp        0      0 172.19.0.15:48868       172.19.0.12:9527        ESTABLISHED 17255/nc             off (0.00/0/0)
```

可以看到 node2 和 node3 中都有一条端口为 9527 处于 ESTABLISHED 状态的连接，表示连接已建立。 tcpdump 命令也会输出三次握手的数据包详情。

```
$ sudo tcpdump -s0 -X -nn "tcp port 9527" -w tcp.pcap --print
tcpdump: listening on eth0, link-type EN10MB (Ethernet), snapshot length 262144 bytes
10:54:13.960797 IP 172.19.0.15.48868 > 172.19.0.12.9527: Flags [S], seq 2713301685, win 59220, options [mss 8460,sackOK,TS val 2002430584 ecr 0,nop,wscale 7], length 0
	0x0000:  4500 003c 3a31 4000 4006 a849 ac13 000f  E..<:1@.@..I....
	0x0010:  ac13 000c bee4 2537 a1b9 b2b5 0000 0000  ......%7........
	0x0020:  a002 e754 92b3 0000 0204 210c 0402 080a  ...T......!.....
	0x0030:  775a aa78 0000 0000 0103 0307            wZ.x........
10:54:13.960874 IP 172.19.0.12.9527 > 172.19.0.15.48868: Flags [S.], seq 3309498602, ack 2713301686, win 59136, options [mss 8460,sackOK,TS val 556655863 ecr 2002430584,nop,wscale 7], length 0
	0x0000:  4500 003c 0000 4000 4006 e27a ac13 000c  E..<..@.@..z....
	0x0010:  ac13 000f 2537 bee4 c542 f0ea a1b9 b2b6  ....%7...B......
	0x0020:  a012 e700 5870 0000 0204 210c 0402 080a  ....Xp....!.....
	0x0030:  212d e4f7 775a aa78 0103 0307            !-..wZ.x....
10:54:13.961020 IP 172.19.0.15.48868 > 172.19.0.12.9527: Flags [.], ack 1, win 463, options [nop,nop,TS val 2002430584 ecr 556655863], length 0
	0x0000:  4500 0034 3a32 4000 4006 a850 ac13 000f  E..4:2@.@..P....
	0x0010:  ac13 000c bee4 2537 a1b9 b2b6 c542 f0eb  ......%7.....B..
	0x0020:  8010 01cf 05fa 0000 0101 080a 775a aa78  ............wZ.x
	0x0030:  212d e4f7                                !-..
```

### 三次握手抓包 & TCP 协议头解析

我们将抓包文件拖入 Wireshark 中来分析三次握手的过程。

![](https://pub-08b57ed9c8ce4fadab4077a9d577e857.r2.dev/tcp-handshake-01.png)

首先回顾下 TCP 协议头格式：

![](https://nmap.org/book/images/hdr/MJB-TCP-Header-800x564.png)

图片来自 [TCP/IP Reference](https://nmap.org/book/tcpip-ref.html)

像序列号、端口信息、FLAG 等字段都比较熟悉了，我们这里重点看下 Options 的各个字段，完整的 Option 字段可以参考 [Transmission Control Protocol (TCP) Parameters](https://www.iana.org/assignments/tcp-parameters/tcp-parameters.xhtml)，这里我们只关注包中出现的最常见的几个字段：

![](https://pub-08b57ed9c8ce4fadab4077a9d577e857.r2.dev/tcp-handshake-02.png)

- **MSS（Maximum Segment Size）** 该字段只能在 SYN 包中，用来告知对方自己可以接收的最大数据包，这里指的是 TCP 包中 data 的大小，不包含 TCP 头数据。[RFC 6691](https://www.rfc-editor.org/rfc/rfc6691) 中规定了 MSS 的值为 MTU 减去 IP 固定头大小（20 字节）和 TCP 固定头大小（20字节），不包含任何 Option 字段。从 ``ip -4 addr`` 命令中可以看到网卡的 MTU 大小为 8500，因此 MSS 大小为 8500 - 20 - 20 = 8460，和抓包中显示的 MSS 大小一致。

```
# ubuntu @ node3 in ~ [10:41:48]
$ ip -4 addr
...
2: eth0: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 8500 qdisc mq state UP group default qlen 1000
...

```

- **SACK（Selective Acknowledgment）**  选择性确认。用来告知对方自己可以接收的 TCP 数据包的序列号范围，从而减少传输的数据量，提高传输效率。

在 Linux 内核中，使用 ``net.ipv4.tcp_sack`` 参数来控制是否开启 SACK ，默认是开启的，可以通过 ``sysctl net.ipv4.tcp_sack`` 命令查看：

```bash
$ sysctl net.ipv4.tcp_sack
net.ipv4.tcp_sack = 1
```

- **TS（Timestamp）** 时间戳标记。内核用来计算 RTT（Round-Trip Time），即数据包从发送端到接收端的时间。在内核中可以使用 ``net.ipv4.tcp_timestamps`` 参数来控制是否开启该选项。

```bash
$ sysctl net.ipv4.tcp_timestamps
net.ipv4.tcp_timestamps = 1
```
- **NOP（No Operation）** NOP 一般用来占位对齐，因为 TCP 头大小必须是 4 字节的倍数。因此当 TCP 固定头 + Option 字段长度不为 4 字节的倍数时，一般会填充 NOP 字段。

- **WScale（Window Scale）** 窗口缩放因子。TCP 的 window 窗口字段大小是 16bit，其最大值为 65536 ，也就是说 TCP 包能传输的最大数据为 65536 byte / 1024 = 64KB。在硬件设备和网络如此发达的今天，这个窗口大小显然有点太小了，为此 [RFC 7323](https://www.rfc-editor.org/rfc/rfc7323) 中提出了 WScale 选项，用来扩展 window 字段的大小。 


  WScale Option 中有 shift.count 值，顾名思义就是移位数，表示 2 的多少次方，虽然 shift.count 占了 1 个字节，但 RFC 规定只能使用后 4 位，其最大值为 1110，也就是 14。结合最大 window 值为 64KB，在 WScale 的帮助下，最大窗口大小可以达到 64KB * （2^14） = 1048576KB = 1GB。

![](https://pub-08b57ed9c8ce4fadab4077a9d577e857.r2.dev/tcp-window-scale.png)

在我们的抓包中，可以看到 WScale 选项的值为 7，因此 window * (2^7) 才是真正的 window 大小。

![](https://pub-08b57ed9c8ce4fadab4077a9d577e857.r2.dev/tcp-wscale-02.png)

需要注意的是，WScale 只会在携带这个选项的包之后生效，因此发送第一个 SYN 包时是没有生效的，在第三次握手时该选项才生效，可以看到 window 值为 463，而计算后的 window 值为 463 * (2^7) = 463 * 128 = 59264。

![](https://pub-08b57ed9c8ce4fadab4077a9d577e857.r2.dev/tcp-wscale-03.png)

在 Linux 内核中，可以通过 ``net.ipv4.tcp_window_scaling`` 参数来控制是否开启 WScale 选项。

```bash
$ sysctl net.ipv4.tcp_window_scaling
net.ipv4.tcp_window_scaling = 1
```

### SYN-SENT 状态抓包

前文抓包我们看到的是 LISTEN 和 ESTABLISHED 状态的 socket，除了这两种状态，连接建立时还会经历 SYN-SENT 和 SYN-RECV 状态。

![](https://pub-08b57ed9c8ce4fadab4077a9d577e857.r2.dev/tcp-handshake-state.png)
图片来自 [TCP/IP Guide](http://www.tcpipguide.com/free/t_TCPOperationalOverviewandtheTCPFiniteStateMachineF-2.htm)

这里通过 iptables 拦截握手包来看下 SYN-SENT 和 SYN-RECV 状态的 socket，首先在 node2 上使用 iptables 规则，将访问 9527 的端口包丢弃掉，命令如下：

```bash
sudo iptables -A INPUT -p tcp --dport 9527 -j DROP
```

然后在 node3 再次执行 nc 命令连接服务，这次带上参数 -w 3600，表示连接超时时间为 3600 秒，命令如下：

```bash
nc -w 3600 172.19.0.12 9527
```

请求发出后，tcpdump 抓包会打印 SYN 包和后续的重传包，用 Wireshark 打开抓包文件：

![](https://pub-08b57ed9c8ce4fadab4077a9d577e857.r2.dev/tcp-handshake-03.png)

可以看到 SYN 包一共有 6 次重传，共传了 7 个包。Linux 的 SYN 最大重传次数是由内核参数 ``net.ipv4.tcp_syn_retries`` 控制的，默认值为 6。

```bash
# ubuntu @ node3 in ~ [16:26:35] C:130
$ sysctl net.ipv4.tcp_syn_retries
net.ipv4.tcp_syn_retries = 6
```

重传的超时 RTO 时间初始值通常在 1s 左右，按照指数级增长，因此重传时间间隔大约为 1s、2s、4s、8s、16s、32s。从抓包中也可以看到，在 1.02，3.03，7.726s，15.15，31.58，65.11s 发生了重传，因此默认情况下，一个 TCP 连接的超时时间会大于 64s。

在重传期间，查看 node3 的 netstat 信息可以看到 SYN-SENT 状态的 socket，表示连接正在等待 SYN 包的响应。

```
# ubuntu @ node3 in ~ [16:26:35] C:130
$ while true; do sudo netstat -anpo | grep 9527; sleep 1; done
tcp        0      1 172.19.0.15:44004       172.19.0.12:9527        SYN_SENT    3066236/nc           on (0.77/0/0)
tcp        0      1 172.19.0.15:44004       172.19.0.12:9527        SYN_SENT    3066236/nc           on (1.78/1/0)
tcp        0      1 172.19.0.15:44004       172.19.0.12:9527        SYN_SENT    3066236/nc           on (0.76/1/0)
tcp        0      1 172.19.0.15:44004       172.19.0.12:9527        SYN_SENT    3066236/nc           on (3.76/2/0)
tcp        0      1 172.19.0.15:44004       172.19.0.12:9527        SYN_SENT    3066236/nc           on (2.74/2/0)
tcp        0      1 172.19.0.15:44004       172.19.0.12:9527        SYN_SENT    3066236/nc           on (1.72/2/0)
tcp        0      1 172.19.0.15:44004       172.19.0.12:9527        SYN_SENT    3066236/nc           on (0.70/2/0)
tcp        0      1 172.19.0.15:44004       172.19.0.12:9527        SYN_SENT    3066236/nc           on (7.88/3/0)
tcp        0      1 172.19.0.15:44004       172.19.0.12:9527        SYN_SENT    3066236/nc           on (6.86/3/0)
tcp        0      1 172.19.0.15:44004       172.19.0.12:9527        SYN_SENT    3066236/nc           on (5.84/3/0)
tcp        0      1 172.19.0.15:44004       172.19.0.12:9527        SYN_SENT    3066236/nc           on (4.82/3/0)
tcp        0      1 172.19.0.15:44004       172.19.0.12:9527        SYN_SENT    3066236/nc           on (3.80/3/0)
tcp        0      1 172.19.0.15:44004       172.19.0.12:9527        SYN_SENT    3066236/nc           on (2.78/3/0)
tcp        0      1 172.19.0.15:44004       172.19.0.12:9527        SYN_SENT    3066236/nc           on (1.76/3/0)
tcp        0      1 172.19.0.15:44004       172.19.0.12:9527        SYN_SENT    3066236/nc           on (0.75/3/0)
tcp        0      1 172.19.0.15:44004       172.19.0.12:9527        SYN_SENT    3066236/nc           on (15.92/4/0)
tcp        0      1 172.19.0.15:44004       172.19.0.12:9527        SYN_SENT    3066236/nc           on (14.90/4/0)
tcp        0      1 172.19.0.15:44004       172.19.0.12:9527        SYN_SENT    3066236/nc           on (13.88/4/0)
tcp        0      1 172.19.0.15:44004       172.19.0.12:9527        SYN_SENT    3066236/nc           on (12.86/4/0)
tcp        0      1 172.19.0.15:44004       172.19.0.12:9527        SYN_SENT    3066236/nc           on (11.84/4/0)
tcp        0      1 172.19.0.15:44004       172.19.0.12:9527        SYN_SENT    3066236/nc           on (10.83/4/0)
tcp        0      1 172.19.0.15:44004       172.19.0.12:9527        SYN_SENT    3066236/nc           on (9.81/4/0)
tcp        0      1 172.19.0.15:44004       172.19.0.12:9527        SYN_SENT    3066236/nc           on (8.79/4/0)
tcp        0      1 172.19.0.15:44004       172.19.0.12:9527        SYN_SENT    3066236/nc           on (7.77/4/0)
tcp        0      1 172.19.0.15:44004       172.19.0.12:9527        SYN_SENT    3066236/nc           on (6.75/4/0)
tcp        0      1 172.19.0.15:44004       172.19.0.12:9527        SYN_SENT    3066236/nc           on (5.73/4/0)
tcp        0      1 172.19.0.15:44004       172.19.0.12:9527        SYN_SENT    3066236/nc           on (4.71/4/0)
tcp        0      1 172.19.0.15:44004       172.19.0.12:9527        SYN_SENT    3066236/nc           on (3.70/4/0)
tcp        0      1 172.19.0.15:44004       172.19.0.12:9527        SYN_SENT    3066236/nc           on (2.68/4/0)
tcp        0      1 172.19.0.15:44004       172.19.0.12:9527        SYN_SENT    3066236/nc           on (1.65/4/0)
tcp        0      1 172.19.0.15:44004       172.19.0.12:9527        SYN_SENT    3066236/nc           on (0.64/4/0)
tcp        0      1 172.19.0.15:44004       172.19.0.12:9527        SYN_SENT    3066236/nc           on (31.74/5/0)
```
最后一列是 Timer 计时器，格式为 ``timer(a/b/c)``，timer取值有四种
- on 超时计时器
- off 没有计时器
- keepalive keepalive 计时器
- timewait TIME_WAIT 计时器

对于超时计时器，a 表示当前计时器剩余时间，b 表示当前计时器重传次数，c 表示已发送的保活探测次数，比如命令中一行时 `(1.72/2/0)`，1.72 表示在等 1.72 秒进行重传，2 表示已经重传了两次。

node2 使用 iptables 屏蔽了所有 9527 端口的包，因此 node2 是没有收到过 SYN 包的，因此不会有任何 socket 信息。

### SYN-RECV 状态抓包

我们在修改下 node3 的 iptables 规则，将源端口为 9527 的包丢弃掉，命令如下：

```bash
# --sport 9527 表示源端口为 9527 的包被匹配，也就是 node2 发来的 ACK 包会被拦截
sudo iptables -A INPUT -p tcp --sport 9527 -j DROP
```

为了避免 SYN 重传，这里使用 namp 命令执行访问，命令如下：

```bash
sudo nmap -sS 172.19.0.12 -p 9527
```

node02 抓包如下：

![](https://pub-08b57ed9c8ce4fadab4077a9d577e857.r2.dev/tcp-handshake-04.png)

可以看到 SYN-ACK 重传了 5 次，这是由内核参数 ``net.ipv4.tcp_synack_retries`` 控制的，默认值为 5，重传时间也是从 1s 开始逐渐翻倍，成指数级增长。

```bash
$ sysctl net.ipv4.tcp_synack_retries
net.ipv4.tcp_synack_retries = 5
```

重传过程中，查看 node2 的 netstat 信息可以看到 SYN-RECV 状态的 socket，表示连接正在等待 SYN-ACK 包的响应。

```bash
$ $ while true; do sudo netstat -anpo | grep SYN_RECV; sleep 1; done
tcp        0      0 172.19.0.12:9527        172.19.0.15:48803       SYN_RECV    -                    on (1.24/1/0)
tcp        0      0 172.19.0.12:9527        172.19.0.15:48803       SYN_RECV    -                    on (0.22/1/0)
tcp        0      0 172.19.0.12:9527        172.19.0.15:48803       SYN_RECV    -                    on (3.22/2/0)
tcp        0      0 172.19.0.12:9527        172.19.0.15:48803       SYN_RECV    -                    on (2.20/2/0)
tcp        0      0 172.19.0.12:9527        172.19.0.15:48803       SYN_RECV    -                    on (1.18/2/0)
tcp        0      0 172.19.0.12:9527        172.19.0.15:48803       SYN_RECV    -                    on (0.16/2/0)
tcp        0      0 172.19.0.12:9527        172.19.0.15:48803       SYN_RECV    -                    on (7.34/3/0)
tcp        0      0 172.19.0.12:9527        172.19.0.15:48803       SYN_RECV    -                    on (6.32/3/0)

```

### SYN Flood 攻击

上面实验可以看到在 SYN-ACK 包重传期间，始终会占用服务器的资源。如果有恶意攻击者不断发送 SYN 包，同时 SYN-ACK 拒绝接收 SYN-ACK 包，服务器就会有大量处于 SYN-RECV 状态的连接消耗资源，这里简要解释下其原理。

在三次握手过程中，Linux 会维护两个队列分别是：

- SYN Queue 半连接队列
- Accept Queue 全连接队列

三次握手过程中，两个队列作用如下：

- 客户端向服务端发送 SYN 包
- 服务端收到 SYN 包后，将 socket 信息放入 SYN Queue 队列，然后发送 SYN-ACK 包
- 客户端收到 SYN-ACK 包后，发送 ACK 包，客户端进入 ESTABLISHED 状态
- 服务端收到 ACK 包后，将 socket 状态变为 ESTABLISHED，并从 SYN Queue 队列中移除放入 Accept Queue 队列

![](https://pub-08b57ed9c8ce4fadab4077a9d577e857.r2.dev/tcp-synqueue-01.jpg)
图片来自：[从一次线上问题说起，详解 TCP 半连接队列、全连接队列
](https://www.51cto.com/article/687595.html)


![](https://pub-08b57ed9c8ce4fadab4077a9d577e857.r2.dev/syn-queue-02.jpeg)

图片来自[Cloudflare Blog: SYN Packet Handling in the Wild](https://blog.cloudflare.com/syn-packet-handling-in-the-wild/?utm_source=chatgpt.com/)

如果服务器收到大量的 SYN 包，同时 SYN-ACK 包没有被正常接收，就会有大量处于 SYN-RECV 状态的 socket 占满 SYN Queue 队列，导致无法正常处理新的 SYN 包，这就是所谓的 SYN Flood 攻击。

![](https://pub-08b57ed9c8ce4fadab4077a9d577e857.r2.dev/syn-queue-03.jpeg)

图片来自[Cloudflare Blog: SYN Packet Handling in the Wild](https://blog.cloudflare.com/syn-packet-handling-in-the-wild/?utm_source=chatgpt.com/)

这里有几个内核参数需要了解下：

- ``net.ipv4.tcp_max_syn_backlog``：SYN Queue 队列的最大长度，默认值为 256。表示收到 SYN 包但尚未完成三次握手的 socket 数量，也就是处于 SYN-RECV 状态的 socket 最大数量。

- ``net.core.somaxconn``：Accept Queue 队列的最大长度，默认值为 4096。表示已经完成三次握手处于 ESTABLISHED 状态但还未被应用层 accept 的 socket 最大数量。

- ``net.ipv4.tcp_syncookies`` 表示是否开启 SYN Cookie 机制，默认值为 1 表示开启。
  
```bash
$ sysctl net.ipv4.tcp_max_syn_backlog
net.ipv4.tcp_max_syn_backlog = 256

$ sysctl net.core.somaxconn
net.core.somaxconn = 4096

$ sysctl net.ipv4.tcp_syncookies
net.ipv4.tcp_syncookies = 1
```

socket 的队列长度可以在调用 listen 系统调试时设置：

```c
listen(server_fd, 128);  // 128 表示 backlog 长度，也就是半连接队列长度
```

然后内核的计算方法是：

> min_syn_queue = min(backlog, net.core.somaxconn, net.ipv4.tcp_max_syn_backlog)
>
> min_accept_queue = min(backlog, net.core.somaxconn)

这里我们修改下 node2 默认的最大队列长度看下包是怎么被处理的。

**原实验用了 nc 验证 SYN Queue 的队列长度，但笔者在做实验时发现 nc 的 SYN-Queue 默认长度为 1，无法复现实验中的效果。**
```bash
$ ss -ltn
State    Recv-Q   Send-Q     Local Address:Port      Peer Address:Port   Process
LISTEN   0        1            172.19.0.12:9526           0.0.0.0:*
```
在 ChatGPT 帮助下了解到，对于网络 socket 来说，nc 在调用 listen 时，默认的 backlog 长度为 1，因此无法复现实验中的效果。查看 nc 的源码也可以验证这一点。

```c
// 源码地址
// https://github.com/openbsd/src/blob/d800967ee04b1c92ceefa78494d0ff66606a806d/usr.bin/nc/netcat.c#L1072

/*
 * local_listen()
 * Returns a socket listening on a local port, binds to specified source
 * address. Returns -1 on failure.
 */
int
local_listen(const char *host, const char *port, struct addrinfo hints)
{
	// 代码省略

	if (!uflag && s != -1) {
    // 调用 listen 时，默认的 backlog 长度为 1
		if (listen(s, 1) == -1)
			err(1, "listen");
	}
 // 代码省略

	return s;
}
```

基于 nc 的问题，后续操作我们使用 python 程序作为服务端的实现。

```python
import socket
import time 

def start_server(host, port, backlog):
    print(f"Starting server on {host}:{port} with backlog {backlog}")
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind((host, port))
    # 只 listen，不做 accept，让全连接队列占满
    server.listen(backlog)

    while True:
        time.sleep(1)

if __name__ == '__main__':
    # backlog 长度为 8
    start_server('172.19.0.12', 9527, 8)
```
首先我们修改下 node2 的参数，关闭 SYN Cookie 机制，修改队列的最大长度


```bash
$ sudo sysctl -w net.ipv4.tcp_syncookies=0 net.ipv4.tcp_max_syn_backlog=4 net.core.somaxconn=8
net.ipv4.tcp_syncookies = 0 # 关闭 SYN Cookie 机制
net.ipv4.tcp_max_syn_backlog = 4 # 最大半连接队列长度为 4
net.core.somaxconn = 8 # 最大全连接队列长度为 8
```

启动服务端程序后，使用 nmap 命令循环发送 SYN 包，命令如下：

```bash
# 在 node2 启动服务端
$ python3 server.py
Starting server on 172.19.0.12:9527 with backlog 8

# 在 node3 使用 nmap 命令发送 SYN 包
while true; do sudo  nmap -sS 172.19.0.12 -p 9527; done
```

此时在 node2 可以看到 SYN-RECV 状态的 socket 数量为 4，表示半连接队列被占满。

```bash
$ ss -nlt state syn-recv
Recv-Q     Send-Q         Local Address:Port         Peer Address:Port     Process
0          0                172.19.0.12:9527          172.19.0.15:58404
0          0                172.19.0.12:9527          172.19.0.15:62220
0          0                172.19.0.12:9527          172.19.0.15:37746
0          0                172.19.0.12:9527          172.19.0.15:54045
```

使用 netstat -s 命令可以看到被丢弃的 syn 包

```bash
# ubuntu @ node2 in ~ [11:57:24]
$ sudo netstat -s | grep -E "LISTEN|overflowed"
    352 SYNs to LISTEN sockets dropped

# ubuntu @ node2 in ~ [11:57:27]
$ sudo netstat -s | grep -E "LISTEN|overflowed"
    354 SYNs to LISTEN sockets dropped

# ubuntu @ node2 in ~ [11:57:28]
$ sudo netstat -s | grep -E "LISTEN|overflowed"
    363 SYNs to LISTEN sockets dropped
```

接下来我们使用测试脚本验证下 Accept Queue 队列的限制情况。测试脚本会发起 10 次请求，打满全连接队列。

```python
import socket
import time

def connect_and_hold(host, port, count):
    cli_list = []
    try:
        # 连接 10 次
        for i in range(count):
            cli = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            cli.connect((host, port))
            cli_list.append(cli)
    except Exception as e:
        print(f"Failed to connect: {e}")

    while True:
        time.sleep(1)

if __name__ == '__main__':
    connect_and_hold('172.19.0.12', 9527, 10)
```

首先我们需要清理下 node3 的 iptables 规则，将之前添加的 DROP ACK 包的规则删除，从而可以让客户端能够发起第三次握手。 命令如下

```bash
# node3  清理 iptables
$ sudo iptables -D INPUT -p tcp --sport 9527 -j DROP

# 在 node2 启动服务端
$ python3 server.py
Starting server on 172.19.0.12:9527 with backlog 8

# 在 node3 启动客户端
$ python3 client.py

# 分别执行 netstat 命令统计 socket 数量
$ sudo netstat -anpo | grep -E "Recv-Q|9527"

```
下面是 node2、node3 的 netstat 统计结果：

```bash
# node2
$ sudo netstat -anpo | grep -E "Recv-Q|9527"
Proto Recv-Q Send-Q Local Address           Foreign Address         State       PID/Program name     Timer
tcp        9      0 172.19.0.12:9527        0.0.0.0:*               LISTEN      123347/python3       off (0.00/0/0)
tcp        0      0 172.19.0.12:9527        172.19.0.15:41088       ESTABLISHED -                    off (0.00/0/0)
tcp        0      0 172.19.0.12:9527        172.19.0.15:41074       ESTABLISHED -                    off (0.00/0/0)
tcp        0      0 172.19.0.12:9527        172.19.0.15:41058       ESTABLISHED -                    off (0.00/0/0)
tcp        0      0 172.19.0.12:9527        172.19.0.15:41064       ESTABLISHED -                    off (0.00/0/0)
tcp        0      0 172.19.0.12:9527        172.19.0.15:41060       ESTABLISHED -                    off (0.00/0/0)
tcp        0      0 172.19.0.12:9527        172.19.0.15:41048       ESTABLISHED -                    off (0.00/0/0)
tcp        0      0 172.19.0.12:9527        172.19.0.15:41106       ESTABLISHED -                    off (0.00/0/0)
tcp        0      0 172.19.0.12:9527        172.19.0.15:41082       ESTABLISHED -                    off (0.00/0/0)
tcp        0      0 172.19.0.12:9527        172.19.0.15:41094       ESTABLISHED -                    off (0.00/0/0)

$ ss -atnp | grep -E "Recv-Q|9527"
State  Recv-Q Send-Q Local Address:Port    Peer Address:Port Process
LISTEN 9      8        172.19.0.12:9527         0.0.0.0:*     users:(("python3",pid=123347,fd=3))
ESTAB  0      0        172.19.0.12:9527     172.19.0.15:41088
ESTAB  0      0        172.19.0.12:9527     172.19.0.15:41074
ESTAB  0      0        172.19.0.12:9527     172.19.0.15:41058
ESTAB  0      0        172.19.0.12:9527     172.19.0.15:41064
ESTAB  0      0        172.19.0.12:9527     172.19.0.15:41060
ESTAB  0      0        172.19.0.12:9527     172.19.0.15:41048
ESTAB  0      0        172.19.0.12:9527     172.19.0.15:41106
ESTAB  0      0        172.19.0.12:9527     172.19.0.15:41082
ESTAB  0      0        172.19.0.12:9527     172.19.0.15:41094

# node3
$ sudo netstat -anpo | grep -E "Recv-Q|9527"
Proto Recv-Q Send-Q Local Address           Foreign Address         State       PID/Program name     Timer
tcp        0      0 172.19.0.15:41082       172.19.0.12:9527        ESTABLISHED 125328/python3       off (0.00/0/0)
tcp        0      0 172.19.0.15:41064       172.19.0.12:9527        ESTABLISHED 125328/python3       off (0.00/0/0)
tcp        0      0 172.19.0.15:41074       172.19.0.12:9527        ESTABLISHED 125328/python3       off (0.00/0/0)
tcp        0      0 172.19.0.15:41094       172.19.0.12:9527        ESTABLISHED 125328/python3       off (0.00/0/0)
tcp        0      0 172.19.0.15:41088       172.19.0.12:9527        ESTABLISHED 125328/python3       off (0.00/0/0)
tcp        0      0 172.19.0.15:41058       172.19.0.12:9527        ESTABLISHED 125328/python3       off (0.00/0/0)
tcp        0      1 172.19.0.15:41114       172.19.0.12:9527        SYN_SENT    125328/python3       on (4.72/4/0)
tcp        0      0 172.19.0.15:41048       172.19.0.12:9527        ESTABLISHED 125328/python3       off (0.00/0/0)
tcp        0      0 172.19.0.15:41106       172.19.0.12:9527        ESTABLISHED 125328/python3       off (0.00/0/0)
tcp        0      0 172.19.0.15:41060       172.19.0.12:9527        ESTABLISHED 125328/python3       off (0.00/0/0)

$ ss -atnp | grep -E "Recv-Q|9527"
State  Recv-Q Send-Q Local Address:Port    Peer Address:Port Process
ESTAB    0      0        172.19.0.15:41082    172.19.0.12:9527  users:(("python3",pid=125328,fd=8))
ESTAB    0      0        172.19.0.15:41064    172.19.0.12:9527  users:(("python3",pid=125328,fd=6))
ESTAB    0      0        172.19.0.15:41074    172.19.0.12:9527  users:(("python3",pid=125328,fd=7))
ESTAB    0      0        172.19.0.15:41094    172.19.0.12:9527  users:(("python3",pid=125328,fd=10))
ESTAB    0      0        172.19.0.15:41088    172.19.0.12:9527  users:(("python3",pid=125328,fd=9))
ESTAB    0      0        172.19.0.15:41058    172.19.0.12:9527  users:(("python3",pid=125328,fd=4))
SYN-SENT 0      1        172.19.0.15:41114    172.19.0.12:9527  users:(("python3",pid=125328,fd=12))
ESTAB    0      0        172.19.0.15:41048    172.19.0.12:9527  users:(("python3",pid=125328,fd=3))
ESTAB    0      0        172.19.0.15:41106    172.19.0.12:9527  users:(("python3",pid=125328,fd=11))
ESTAB    0      0        172.19.0.15:41060    172.19.0.12:9527  users:(("python3",pid=125328,fd=5))
```

我们来分析下统计结果：

1. node2 有 9 个 ESTABLISHED 状态的 socket。

2. node3 有 9 个 ESTABLISHED 状态的 socket；1 个 SYN_SENT 状态的 socket，计时器显示器正在被重传。由此我们可以知道，当全连接队列被占满后，即使半连接队列不满，也会拒绝新的连接，将 SYN 包 Drop 掉。（从 v4.10 版本开始，参考 [提交](https://github.com/torvalds/linux/commit/5ea8ea2cb7f1d0db15762c9b0bb9e7330425a071)）

3. node2 的最大全连接队列长度为 8，但实际有 9 个 ESTABLISHED 状态的 socket。这是因为 Linux 内核的判断全连接队列的逻辑是 > 而不是 >=。5.15.0-130-generic 内核代码如下：

```c
// 源码地址
// https://elixir.bootlin.com/linux/v5.15.130/source/include/net/sock.h#L980
/* Note: If you think the test should be:
 *	return READ_ONCE(sk->sk_ack_backlog) >= READ_ONCE(sk->sk_max_ack_backlog);
 * Then please take a look at commit 64a146513f8f ("[NET]: Revert incorrect accept queue backlog changes.")
 */
static inline bool sk_acceptq_is_full(const struct sock *sk)
{
	return READ_ONCE(sk->sk_ack_backlog) > READ_ONCE(sk->sk_max_ack_backlog);
}
```

之所以这样做，是为了避免在 backlog 设置为 0 时，依然可以有一个连接进入全连接队列，具体可以查看以下 commit 信息：

```
https://github.com/torvalds/linux/commit/64a146513f8f12ba204b7bf5cb7e9505594ead42

[NET]: Revert incorrect accept queue backlog changes.
This reverts two changes:

8488df8
248f067

A backlog value of N really does mean allow "N + 1" connections
to queue to a listening socket.  This allows one to specify
"0" as the backlog and still get 1 connection.

Noticed by Gerrit Renker and Rick Jones.

Signed-off-by: David S. Miller <davem@davemloft.net>
```

4. 查看服务端 Listen 状态的 socket 时，Recv-Q 显示为 9，表示当前全连接队列长度为 9，Send-Q 显示为 8，表示全连接队列最大长度为 8。而 netstat 的攻击结果，Recv-Q 显示为 9，但 Send-Q 显示为 0。根据原文是因为 netstat 的数据源问题，作者最终推荐优先使用 ss 命令，这里不在做进一步的调研。

关于半连接、全连接队列的分析可以参考笔者的另一篇文章[【动手实验】TCP半连接队列、全连接队列实战分析](https://zouyingjie.github.io/posts/TCP半连接队列全连接队列实战分析/)，这里不在赘述。

## 连接关闭

分析完了 TCP 连接建立的过程，我们再来分析下 TCP 连接关闭的过程。


我们继续使用 nc 作为工具，首先启动服务端和客户端。

```
# node2 使用 nc 启动服务端
$ nc -k -l 172.19.0.12  9527

# node3 使用 nc 启动客户端
$ nc 172.19.0.12 9527
```

完成后查看服务端和客户端的状态信息：

```bash
# node2 服务端
$ ss -atnp | grep -E "Recv-Q|9527"
State  Recv-Q Send-Q Local Address:Port    Peer Address:Port Process
LISTEN 0      1        172.19.0.12:9527         0.0.0.0:*     users:(("nc",pid=147133,fd=3))
ESTAB  0      0        172.19.0.12:9527     172.19.0.15:42526 users:(("nc",pid=147133,fd=4))

# node3 客户端
$ ss -atnp | grep -E "Recv-Q|9527"
State  Recv-Q Send-Q Local Address:Port    Peer Address:Port Process
ESTAB  0      0        172.19.0.15:42526    172.19.0.12:9527  users:(("nc",pid=149072,fd=3))
```

### 正常关闭

我们首先在 node2 执行抓包，然后在客户端按照 ctrl+c 关闭连接，然后执行 netstat 命令查看服务端的状态信息：

```bash
# node2 抓包
$ sudo tcpdump -s0 -X -nn "tcp port 9527" -w tcp-handshake-03.pcap --print
tcpdump: listening on eth0, link-type EN10MB (Ethernet), snapshot length 262144 bytes

# node2 服务端
Proto Recv-Q Send-Q Local Address           Foreign Address         State       PID/Program name     Timer
tcp        0      0 172.19.0.12:9527        0.0.0.0:*               LISTEN      147133/nc            off (0.00/0/0)
tcp        0      0 172.19.0.12:9527        172.19.0.15:41492       ESTABLISHED 147133/nc            off (0.00/0/0)

# node3 客户端
$ sudo netstat -anpo | grep Recv-Q; sudo netstat -anpo | grep 9527
Proto Recv-Q Send-Q Local Address           Foreign Address         State       PID/Program name     Timer
tcp        0      0 172.19.0.15:41492       172.19.0.12:9527        TIME_WAIT   -                    timewait (58.92/0/0)

$ sudo netstat -anpo | grep Recv-Q; sudo netstat -anpo | grep 9527
Proto Recv-Q Send-Q Local Address           Foreign Address         State       PID/Program name     Timer
tcp        0      0 172.19.0.15:41492       172.19.0.12:9527        TIME_WAIT   -                    timewait (47.42/0/0)


$ sudo netstat -anpo | grep Recv-Q; sudo netstat -anpo | grep 9527
Proto Recv-Q Send-Q Local Address           Foreign Address         State       PID/Program name     Timer
tcp        0      0 172.19.0.15:41492       172.19.0.12:9527        TIME_WAIT   -                    timewait (36.56/0/0)


$ sudo netstat -anpo | grep Recv-Q; sudo netstat -anpo | grep 9527
Proto Recv-Q Send-Q Local Address           Foreign Address         State       PID/Program name     Timer
tcp        0      0 172.19.0.15:41492       172.19.0.12:9527        TIME_WAIT   -                    timewait (24.22/0/0)

```

抓包结果如图：

![](https://pub-08b57ed9c8ce4fadab4077a9d577e857.r2.dev/tcp-handshake-05.png)

我们来简要分析下上述过程：

1. 连接断开的很快，从抓包结果可以看出耗时大约 0.0019s，因此服务端执行 netstat 已经查不到连接了。

2. 四次握手只有 3 个包，因为服务端没有数据需要处理，所以在对客户端的 FIN 进行 ACK 时，把 FIN 也捎带上了。

3. 客户端收到了服务端的 FIN 并发送了 ACK 后进入 TIME_WAIT 状态，从 netstat 输出结果看有一个定时器正在执行，当定时器到时间后连接会完全关闭。Linux 默认 MSL（Maximum Segment Lifetime）为 30s，所以默认的 TIME_WAIT 时间为 2*MSL=60s，这样做有两个好处：

- 旧连接的端口在 60s 内无法被再次使用
- 超过 60s 后旧连接的包都会消失，新的连接如果使用相同的端口，不会被旧数据污染




上面是正常关闭的情况，接下来我们利用 iptables 拦截相关的包，来观察下 FIN_WAIT1，FIN_WAIT2，CLOSING，LAST_ACK 状态的 socket。

### FIN_WAIT1