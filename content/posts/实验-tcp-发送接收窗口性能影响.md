---
title: "【动手实验】发送接收窗口对 TCP 传输性能的影响"
date: 2025-07-17T11:35:31+08:00
draft: true
tags:
  - TCP
  - 动手实验
categories:
  - 计算机网络
source: "https://blog.csdn.net/Ahri_J/article/details/149417961"
---
### 环境准备

#### 服务器
信息

两台腾讯云机器 t04（172.19.0.4）、t11（172.19.0.11），系统为 Ubuntu 22.04，内核为 5.15.0-139-generic。默认 RT 在 0.16s 左右。

```
$ ping 172.19.0.4
PING 172.19.0.4 (172.19.0.4) 56(84) bytes of data.
64 bytes from 172.19.0.4: icmp_seq=1 ttl=64 time=0.195 ms
64 bytes from 172.19.0.4: icmp_seq=2 ttl=64 time=0.216 ms
64 bytes from 172.19.0.4: icmp_seq=3 ttl=64 time=0.253 ms
64 bytes from 172.19.0.4: icmp_seq=4 ttl=64 time=0.158 ms
64 bytes from 172.19.0.4: icmp_seq=5 ttl=64 time=0.164 ms
64 bytes from 172.19.0.4: icmp_seq=6 ttl=64 time=0.139 ms
64 bytes from 172.19.0.4: icmp_seq=7 ttl=64 time=0.134 ms
64 bytes from 172.19.0.4: icmp_seq=8 ttl=64 time=0.153 ms
64 bytes from 172.19.0.4: icmp_seq=9 ttl=64 time=0.157 ms
64 bytes from 172.19.0.4: icmp_seq=10 ttl=64 time=0.149 ms
64 bytes from 172.19.0.4: icmp_seq=11 ttl=64 time=0.148 ms
64 bytes from 172.19.0.4: icmp_seq=12 ttl=64 time=0.157 ms
64 bytes from 172.19.0.4: icmp_seq=13 ttl=64 time=0.151 ms
64 bytes from 172.19.0.4: icmp_seq=14 ttl=64 time=0.156 ms
64 bytes from 172.19.0.4: icmp_seq=15 ttl=64 time=0.156 ms
64 bytes from 172.19.0.4: icmp_seq=16 ttl=64 time=0.160 ms
64 bytes from 172.19.0.4: icmp_seq=17 ttl=64 time=0.159 ms
^C
--- 172.19.0.4 ping statistics ---
17 packets transmitted, 17 received, 0% packet loss, time 16382ms
rtt min/avg/max/mdev = 0.134/0.165/0.253/0.028 ms
```

#### 内核参数信息

内核默认参数值

```
$ sudo sysctl -a | egrep "rmem|wmem|tcp_mem|adv_win|moderate"
net.core.rmem_default = 212992
net.core.rmem_max = 212992
net.core.wmem_default = 212992
net.core.wmem_max = 212992
net.ipv4.tcp_adv_win_scale = 1
net.ipv4.tcp_mem = 41295	55062	82590
net.ipv4.tcp_moderate_rcvbuf = 1
net.ipv4.tcp_rmem = 4096	131072	6291456
net.ipv4.tcp_wmem = 4096	16384	4194304
net.ipv4.udp_rmem_min = 4096
net.ipv4.udp_wmem_min = 4096
vm.lowmem_reserve_ratio = 256	256	32	0	0
```

参数含义如下：

- 核心网络参数 (net.core.）

<table><thead><tr><th>参数名称</th><th>作用范围</th><th>默认行为</th><th>约束关系</th><th>配置值</th><th>影响</th></tr></thead><tbody><tr><td><code>net.core.rmem_default</code></td><td>所有协议套接字</td><td>未设置SO_RCVBUF时的默认接收缓冲区</td><td>UDP默认值，TCP有专门设置时被覆盖</td><td>212992 (208KB)</td><td>UDP接收缓冲区默认208KB</td></tr><tr><td><code>net.core.rmem_max</code></td><td>所有协议套接字</td><td>接收缓冲区的<strong>硬性上限</strong></td><td>覆盖所有协议的max设置</td><td>212992 (208KB)</td><td><strong>严重限制</strong>：TCP最大6MB被压缩到208KB</td></tr><tr><td><code>net.core.wmem_default</code></td><td>所有协议套接字</td><td>未设置SO_SNDBUF时的默认发送缓冲区</td><td>UDP默认值，TCP有专门设置时被覆盖</td><td>212992 (208KB)</td><td>UDP发送缓冲区默认208KB</td></tr><tr><td><code>net.core.wmem_max</code></td><td>所有协议套接字</td><td>发送缓冲区的<strong>硬性上限</strong></td><td>覆盖所有协议的max设置</td><td>212992 (208KB)</td><td><strong>严重限制</strong>：TCP最大4MB被压缩到208KB</td></tr></tbody></table>

- TCP专用参数 (net.ipv4.tcp_)

<table><thead><tr><th>参数名称</th><th>作用范围</th><th>格式说明</th><th>约束关系</th><th>配置值</th><th>实际效果</th></tr></thead><tbody><tr><td><code>net.ipv4.tcp_rmem</code></td><td>仅TCP连接</td><td><code>[最小值 默认值 最大值]</code></td><td>受<code>net.core.rmem_max</code>硬性限制</td><td><code>4096 131072 6291456</code></td><td>最小4KB，默认128KB，最大被限制到208KB</td></tr><tr><td><code>net.ipv4.tcp_wmem</code></td><td>仅TCP连接</td><td><code>[最小值 默认值 最大值]</code></td><td>受<code>net.core.wmem_max</code>硬性限制</td><td><code>4096 16384 4194304</code></td><td>最小4KB，默认16KB，最大被限制到208KB</td></tr><tr><td><code>net.ipv4.tcp_mem</code></td><td>全局TCP内存池</td><td><code>[低水位 压力位 高水位]</code> (页)</td><td>独立于单连接缓冲区设置</td><td><code>41295 55062 82590</code></td><td>全局限制161MB-215MB-323MB</td></tr><tr><td><code>net.ipv4.tcp_moderate_rcvbuf</code></td><td>TCP动态调整</td><td><code>0</code>=关闭，<code>1</code>=开启</td><td>在tcp_rmem范围内动态调整</td><td><code>1</code></td><td>开启动态调整，但被208KB限制</td></tr><tr><td><code>net.ipv4.tcp_adv_win_scale</code></td><td>TCP窗口计算</td><td>整数值</td><td>影响TCP窗口大小算法</td><td><code>1</code></td><td>适中的窗口缩放因子</td></tr></tbody></table>

- UDP专用参数 (net.ipv4.udp_）

<table><thead><tr><th>参数名称</th><th>作用范围</th><th>含义</th><th>约束关系</th><th>配置值</th><th>实际效果</th></tr></thead><tbody><tr><td><code>net.ipv4.udp_rmem_min</code></td><td>仅UDP连接</td><td>UDP接收缓冲区最小值</td><td>受<code>net.core.rmem_max</code>限制</td><td><code>4096</code></td><td>UDP最小接收缓冲区4KB</td></tr><tr><td><code>net.ipv4.udp_wmem_min</code></td><td>仅UDP连接</td><td>UDP发送缓冲区最小值</td><td>受<code>net.core.wmem_max</code>限制</td><td><code>4096</code></td><td>UDP最小发送缓冲区4KB</td></tr></tbody></table>

- 内存管理参数 (vm.）

<table><thead><tr><th>参数名称</th><th>作用范围</th><th>含义</th><th>配置值</th><th>影响</th></tr></thead><tbody><tr><td><code>vm.lowmem_reserve_ratio</code></td><td>系统内存管理</td><td>各内存区域预留比例</td><td><code>256 256 32 0 0</code></td><td>防止内存区域被耗尽</td></tr></tbody></table>

上述参数结合 Socket 编程，对缓冲区的影响如下：

- TCP Socket缓冲区行为

<table><thead><tr><th>场景</th><th>接收缓冲区 (SO_RCVBUF)</th><th>发送缓冲区 (SO_SNDBUF)</th></tr></thead><tbody><tr><td><strong>不调用setsockopt()</strong></td><td>默认：131072 (128KB)</td><td>默认：16384 (16KB)</td></tr><tr><td><strong>调用setsockopt(1MB)</strong></td><td>实际：~425984 (208KB×2)</td><td>实际：~425984 (208KB×2)</td></tr><tr><td><strong>调用setsockopt(100KB)</strong></td><td>实际：~200KB (100KB×2)</td><td>实际：~200KB (100KB×2)</td></tr><tr><td><strong>动态调整范围</strong></td><td>4KB - 208KB (被限制)</td><td>4KB - 208KB (被限制)</td></tr></tbody></table>

- UDP Socket缓冲区行为

<table><thead><tr><th>场景</th><th>接收缓冲区 (SO_RCVBUF)</th><th>发送缓冲区 (SO_SNDBUF)</th></tr></thead><tbody><tr><td><strong>不调用setsockopt()</strong></td><td>默认：212992 (208KB)</td><td>默认：212992 (208KB)</td></tr><tr><td><strong>调用setsockopt(1MB)</strong></td><td>实际：~425984 (208KB×2)</td><td>实际：~425984 (208KB×2)</td></tr><tr><td><strong>最小值保证</strong></td><td>不低于4KB</td><td>不低于4KB</td></tr></tbody></table>

- 参数间的优先级关系

```
1. net.core.*_max (硬性上限，覆盖一切)
   ↓
2. net.ipv4.tcp_*mem (TCP专用设置)
   ↓
3. net.ipv4.udp_*mem (UDP专用设置)
   ↓
4. net.core.*_default (通用默认值)
   ↓
5. 应用程序setsockopt()调用
```

#### 服务端启动

下面是生成测试文件和启动服务端的命令。

```bash
# 创建测试文件
# ubuntu @ t04 in ~/labs/01-bdp-tcp [10:32:12]
$ dd if=/dev/zero of=testfile  bs=1M count=2048
2048+0 records in
2048+0 records out
2147483648 bytes (2.1 GB, 2.0 GiB) copied, 8.3587 s, 257 MB/s

# ubuntu @ t04 in ~/labs/01-bdp-tcp [10:32:30]
$ ll
total 2.1G
-rw-rw-r-- 1 ubuntu ubuntu 2.0G Jul 15 10:32 testfile

# 启动服务端
# ubuntu @ t04 in ~/labs/01-bdp-tcp [10:32:50] C:1
$ python3 -m http.server 8089
Serving HTTP on 0.0.0.0 port 8089 (http://0.0.0.0:8089/) ...

$ netstat -antp | grep 8089
tcp        0      0 0.0.0.0:8089            0.0.0.0:*               LISTEN      12808/python3
```

### 实验分析

环境准备好有，我们利用 tc 工具调整 rtt、丢包率以及调节发送接收缓冲大小，来看下不同情况下的
 数据传输
效率。

###### 1. 默认 mem ，默认延迟

首先不做任何改动，内网下载 2GB 的文件，耗时 14s，吞吐为 975Mbps。

![](https://i-blog.csdnimg.cn/img_convert/ebcfbad72d1f0d698af1e8c8f607b674.png)

###### 2. 默认 mem，100ms 延迟

我们用 tc 将延迟增加到 100ms：

```bash
# 服务端机器添加 100ms 延迟
# ubuntu @ t04 in ~
$ sudo tc qdisc add dev eth0 root netem delay 100ms

# 添加完成后客户端执行 ping 操作，延迟已经变成 100ms 了。
# ubuntu @ t11 in ~ [10:10:05]
$ ping 172.19.0.4
PING 172.19.0.4 (172.19.0.4) 56(84) bytes of data.
64 bytes from 172.19.0.4: icmp_seq=1 ttl=64 time=100 ms
64 bytes from 172.19.0.4: icmp_seq=2 ttl=64 time=100 ms
```

再次执行下载并抓包，结果如下：

```
$ curl 172.19.0.4:8089/testfile > testfile
  % Total    % Received % Xferd  Average Speed   Time    Time     Time  Current
                                 Dload  Upload   Total   Spent    Left  Speed
100 2048M  100 2048M    0     0  27.4M      0  0:01:14  0:01:14 --:--:-- 27.0M
```

![](https://i-blog.csdnimg.cn/img_convert/3ea556e38624e9454cf9eb7afa2cadb6.png)

可以看到整个下载耗时为 1 分 14s，吞吐为 229Mbps，和默认延迟相比，传输速度慢了不少，打开 tcptrace 查看传输过程，可以看到每 100ms 会暂停一次，因为服务端要等到 ack 后才会滑动窗口继续发送数据。

![](https://i-blog.csdnimg.cn/img_convert/e5b8423dea2b82661c2a26a16afdaf49.png)

###### 3. 默认 mem，默认延迟，1% 与 20% 丢包

服务端设置 1% 的丢包率

```
# ubuntu @ t04 in ~
sudo tc qdisc add dev eth0 root netem loss 1%
```

再次执行下载并抓包，结果如下：

```
$ curl 172.19.0.4:8089/testfile > testfile
  % Total    % Received % Xferd  Average Speed   Time    Time     Time  Current
                                 Dload  Upload   Total   Spent    Left  Speed
100 2048M  100 2048M    0     0   185M      0  0:00:11  0:00:11 --:--:--  255M
```

![](https://i-blog.csdnimg.cn/img_convert/e0d79eafc7f3ff5375755cdf82af6ef8.png)
 可以看到整体耗时 10s，平均吞吐为 185MBps。因为带宽足够并且 RT 非常小， 虽然引发了重传，但并没有导致拥塞窗口的减少，整体的传输速度没有受到明显的影响。

我们将丢包率调大到 20% 再次执行下载并抓包

```
$ curl 172.19.0.4:8089/testfile > testfile
  % Total    % Received % Xferd  Average Speed   Time    Time     Time  Current
                                 Dload  Upload   Total   Spent    Left  Speed
  0 2048M    0 15.0M    0     0   579k      0  1:00:20  0:00:26  0:59:54  410k
```

这次下载耗时预计达到了 1 个小时，传输过程查看 cwnd 可以看到已经缩小到了 1,并且整个传输过程中几乎没有恢复过。

```
$ while true; do sudo ss -ti sport =  :8089 ; sleep 1; done;
State        Recv-Q        Send-Q                Local Address:Port                 Peer Address:Port         Process
ESTAB        0             33792                    172.19.0.4:8089                  172.19.0.11:46002
	 cubic wscale:7,7 rto:204 rtt:0.325/0.358 ato:40 mss:8448 pmtu:8500 rcvmss:536 advmss:8448 cwnd:1 ssthresh:2 bytes_sent:47062993 bytes_retrans:9648128 bytes_acked:37397969 bytes_received:87 segs_out:5623 segs_in:3496 data_segs_out:5622 data_segs_in:1 send 208Mbps lastsnd:172 lastrcv:91576 lastack:172 pacing_rate 499Mbps delivery_rate 520Mbps delivered:4472 busy:91572ms sndbuf_limited:9616ms(10.5%) unacked:2 retrans:1/1150 lost:1 sacked:1 rcv_space:57076 rcv_ssthresh:57076 notsent:16896 minrtt:0.067
State        Recv-Q        Send-Q                Local Address:Port                 Peer Address:Port         Process
ESTAB        0             59136                    172.19.0.4:8089                  172.19.0.11:46002
	 cubic wscale:7,7 rto:408 backoff:1 rtt:0.648/1.036 ato:40 mss:8448 pmtu:8500 rcvmss:536 advmss:8448 cwnd:1 ssthresh:2 bytes_sent:47919057 bytes_retrans:9800192 bytes_acked:38093521 bytes_received:87 segs_out:5725 segs_in:3559 data_segs_out:5724 data_segs_in:1 send 104Mbps lastsnd:48 lastrcv:92592 lastack:260 pacing_rate 375Mbps delivery_rate 814Mbps delivered:4556 busy:92588ms sndbuf_limited:9828ms(10.6%) unacked:3 retrans:1/1168 lost:1 sacked:2 rcv_space:57076 rcv_ssthresh:57076 notsent:33792 minrtt:0.067
State        Recv-Q        Send-Q                Local Address:Port                 Peer Address:Port         Process
ESTAB        0             8448                     172.19.0.4:8089                  172.19.0.11:46002
	 cubic wscale:7,7 rto:204 rtt:0.41/0.467 ato:40 mss:8448 pmtu:8500 rcvmss:536 advmss:8448 cwnd:2 ssthresh:2 bytes_sent:48088017 bytes_retrans:9850880 bytes_acked:38228689 bytes_received:87 segs_out:5745 segs_in:3571 data_segs_out:5744 data_segs_in:1 send 330Mbps lastsnd:16 lastrcv:93604 lastack:16 pacing_rate 395Mbps delivery_rate 845Mbps delivered:4570 busy:93600ms sndbuf_limited:9828ms(10.5%) unacked:1 retrans:0/1174 rcv_space:57076 rcv_ssthresh:57076 minrtt:0.067
State        Recv-Q        Send-Q                Local Address:Port                 Peer Address:Port         Process
ESTAB        0             25344                    172.19.0.4:8089                  172.19.0.11:46002
	 cubic wscale:7,7 rto:204 rtt:0.219/0.218 ato:40 mss:8448 pmtu:8500 rcvmss:536 advmss:8448 cwnd:1 ssthresh:2 bytes_sent:48483281 bytes_retrans:9926912 bytes_acked:38531025 bytes_received:87 segs_out:5792 segs_in:3601 data_segs_out:5791 data_segs_in:1 send 309Mbps lastsnd:184 lastrcv:94616 lastack:184 pacing_rate 1.11Gbps delivery_rate 583Mbps delivered:4608 busy:94612ms sndbuf_limited:9828ms(10.4%) unacked:3 retrans:1/1183 lost:1 sacked:2 rcv_space:57076 rcv_ssthresh:57076 minrtt:0.067
```

分析抓包文件，可以看到吞吐会周期性断崖式下跌然后在缓慢爬升。

![](https://i-blog.csdnimg.cn/img_convert/cb5a1e31cb99c7f18b6ed34caad4b390.png)

在丢包时，接收端收到的包会乱序，会影响其 ACK 响应的速度，导致某些包在缓冲区中多等待一会，因此接收窗口也会间歇性的下降，并在收到重传包后恢复。

![](https://i-blog.csdnimg.cn/img_convert/a569077ae9259c01405326e8e772eab4.png)

###### 4. 默认 mem 和延迟，BBR 算法，20% 丢包

服务器默认使用的是 cubic 算法，受丢包影响较大，我们将算法改为 bbr 算法在测试下传输性能。

首先启用 BBR 拥塞控制算法：

```
$ sudo modprobe tcp_bbr
$ sudo sysctl -w net.ipv4.tcp_congestion_control=bbr
```

BBR 算法推荐结合 fq 调度算法使用，因此我们将调度算法也一块改掉。

```
 sudo sysctl -w net.core.default_qdisc=fq
```

完成后再次执行下载并抓包，结果如下，整体传输时间只有 1 分多钟， 20% 的丢包率没有造成太大的影响。

```
$ curl 172.19.0.4:8089/testfile > /dev/null
  % Total    % Received % Xferd  Average Speed   Time    Time     Time  Current
                                 Dload  Upload   Total   Spent    Left  Speed
100 2048M  100 2048M    0     0  31.6M      0  0:01:04  0:01:04 --:--:-- 39.0M
```

传输过程中查看 cwnd 虽然有变为 1 的情况，但很快就会恢复，整体传输速度没有明显下降。

```
	 bbr wscale:7,7 rto:204 rtt:0.168/0.093 ato:40 mss:8448 pmtu:8500 rcvmss:536 advmss:8448 cwnd:14 ssthresh:30 bytes_sent:2353347537 bytes_retrans:468131072 bytes_acked:1884861649 bytes_received:87 segs_out:278665 segs_in:29372 data_segs_out:278664 data_segs_in:1 bbr:(bw:9.46Gbps,mrtt:0.089,pacing_gain:1,cwnd_gain:2) send 5.63Gbps lastsnd:72 lastrcv:73884 lastack:72 pacing_rate 9.37Gbps delivery_rate 1.7Gbps delivered:223216 busy:73848ms rwnd_limited:8ms(0.0%) unacked:42 retrans:14/55435 lost:14 sacked:28 rcv_space:57076 rcv_ssthresh:57076 notsent:5913600 minrtt:0.071
	 bbr wscale:7,7 rto:408 backoff:1 rtt:0.227/0.166 ato:40 mss:8448 pmtu:8500 rcvmss:536 advmss:8448 cwnd:1 ssthresh:30 bytes_sent:2436754641 bytes_retrans:484951040 bytes_acked:1951448785 bytes_received:87 segs_out:288538 segs_in:30288 data_segs_out:288537 data_segs_in:1 bbr:(bw:10.1Gbps,mrtt:0.086,pacing_gain:1.25,cwnd_gain:2) send 298Mbps lastsnd:400 lastrcv:74896 lastack:608 pacing_rate 12.5Gbps delivery_rate 4.89Gbps delivered:231091 busy:74860ms rwnd_limited:8ms(0.0%) unacked:42 retrans:1/57426 lost:21 sacked:21 rcv_space:57076 rcv_ssthresh:57076 notsent:5026560 minrtt:0.071
	 bbr wscale:7,7 rto:204 rtt:0.355/0.379 ato:40 mss:8448 pmtu:8500 rcvmss:536 advmss:8448 cwnd:14 ssthresh:30 bytes_sent:2547279825 bytes_retrans:507127040 bytes_acked:2039975377 bytes_received:87 segs_out:301622 segs_in:31383 data_segs_out:301621 data_segs_in:1 bbr:(bw:9.46Gbps,mrtt:0.086,pacing_gain:1,cwnd_gain:2) send 2.67Gbps lastsnd:80 lastrcv:75908 lastack:80 pacing_rate 9.37Gbps delivery_rate 3.61Gbps delivered:241557 busy:75872ms rwnd_limited:12ms(0.0%) unacked:21 retrans:7/60051 lost:7 sacked:7 rcv_space:57076 rcv_ssthresh:57076 notsent:6859776 minrtt:0.071
	 bbr wscale:7,7 rto:204 rtt:0.283/0.279 ato:40 mss:8448 pmtu:8500 rcvmss:536 advmss:8448 cwnd:14 ssthresh:30 bytes_sent:2606584785 bytes_retrans:518768384 bytes_acked:2087579857 bytes_received:87 segs_out:308642 segs_in:32086 data_segs_out:308641 data_segs_in:1 bbr:(bw:8.16Gbps,mrtt:0.086,pacing_gain:1,cwnd_gain:2) send 3.34Gbps lastsnd:184 lastrcv:76924 lastack:184 pacing_rate 8.08Gbps delivery_rate 5.57Gbps delivered:247199 busy:76888ms rwnd_limited:12ms(0.0%) unacked:28 retrans:7/61429 lost:7 sacked:14 rcv_space:57076 rcv_ssthresh:57076 notsent:5203968 minrtt:0.071
```

###### 5. 客户端 recvbuf 为 4Kb，默认延迟

我们将客户端的 recvbuf 设置为 4Kb。

```
$ sudo sysctl -w "net.ipv4.tcp_rmem=4096        4096      4096"
```

在默认延迟下执行下载，抓包如下：

```
$ curl 172.19.0.4:8089/testfile > testfile
  % Total    % Received % Xferd  Average Speed   Time    Time     Time  Current
                                 Dload  Upload   Total   Spent    Left  Speed
100 2048M  100 2048M    0     0  14.8M      0  0:02:18  0:02:18 --:--:-- 14.8M
```

总体耗时两分多钟，抓包可以看到有大量 Window Full 的情况，但内网 RT 非常小，因此空出来后可以很快的通知给服务端，对整体传输速率的性能不算太大。

![](https://i-blog.csdnimg.cn/img_convert/114b9c5e0fc83e5d3fcf266784de1b59.png)

查看传输过程，可以看到大约每 40ms 接收窗口会上升，
 Linux
 内核有一个宏定义来设置延迟确认的最小时间为 40ms，推测应该是 delayed ack 起了作用。

```C
# https://elixir.bootlin.com/linux/v5.15.130/source/include/net/tcp.h#L135
# define TCP_DELACK_MIN	((unsigned)(HZ/25))	/* minimal time to delay before sending an ACK */
```

###### 6. 客户端 recvbuf 为 4Kb，100ms 延迟

将延迟增加到 100ms 后，整体传输时间预计需要 29 小时，这种情况下，数据只能一点点发，而且耗时还比较长，整体传输速度变得巨慢无比。

```
$ sudo tc qdisc add dev eth0 root netem delay 100ms

$ curl 172.19.0.4:8089/testfile > testfile
  % Total    % Received % Xferd  Average Speed   Time    Time     Time  Current
                                 Dload  Upload   Total   Spent    Left  Speed
  0 2048M    0 2789k    0     0  20419      0 29:12:50  0:02:19 29:10:31 20451
```

###### 7. 服务端 sendbuf 为 4Kb，默认延迟

下载时间只需要 10 几秒，对性能没有明显影响。虽然发送 buffer 小，但因为 rtt 也很小，ACK 包能很快回来可以立即释放 wmem，因此对速度影响不大。好比即使我们只有两辆货车，但装货发货非常快，货车卸完货能立马回来继续拉，整体运货速度也是有保证的，但如果卸货贼慢或者货车路上跑的贼慢，整体发货效率也提不上去。

```
$ curl 172.19.0.4:8089/testfile > testfile
  % Total    % Received % Xferd  Average Speed   Time    Time     Time  Current
                                 Dload  Upload   Total   Spent    Left  Speed
100 2048M  100 2048M    0     0   164M      0  0:00:12  0:00:12 --:--:--  195M
```

这里可以和实验 5 做对比，在默认延迟下修改 recvbuf 和 sendbuf，可以看到修改 recvbuf 对性能的影响更加明显。都是 RT 很小，但 server 端收到 ACK 后 sendbuf 清理出空间，可以立即发送，是内存级别的延迟；但接收端在有 recvbuf 有空间后返回 ACK 到服务端，是网络通信级别的延迟，两者相差几个数量级。

![](https://i-blog.csdnimg.cn/img_convert/b34168e550772d6b577428e3e6215402.png)

![](https://i-blog.csdnimg.cn/img_convert/2e1bbad2e148405e0b02d393e7d8f818.png)

图片来自 [## TCP性能和发送接收窗口、Buffer的关系](https://plantegg.github.io/2019/09/28/%E5%B0%B1%E6%98%AF%E8%A6%81%E4%BD%A0%E6%87%82TCP--%E6%80%A7%E8%83%BD%E5%92%8C%E5%8F%91%E9%80%81%E6%8E%A5%E6%94%B6Buffer%E7%9A%84%E5%85%B3%E7%B3%BB/)

###### 8. 服务端 sendbuf 为 4Kb，100ms 延迟

将延迟增大到 100ms 后，下载时间预计需要 1 小时 37 分钟，整体效率下降了很多。

```
$ curl 172.19.0.4:8089/testfile > testfile
  % Total    % Received % Xferd  Average Speed   Time    Time     Time  Current
                                 Dload  Upload   Total   Spent    Left  Speed
  0 2048M    0 17.4M    0     0   357k      0  1:37:50  0:00:49  1:37:01  366k
```

![](https://i-blog.csdnimg.cn/img_convert/24e40dccdc416235e47207ceb3710a1b.png)

![](https://i-blog.csdnimg.cn/img_convert/3d8243ad88959b4ed5d52c301c6bab31.png)

抓包查看传输过程，可以看到整体传输过程是非常丝滑的，放大后看每 100ms 窗口才会增大，性能就是受 RT 的影响一直上不去。

### 性能问题复现

这里我们模拟任总遇到的场景，假设我们的带宽是 500Mbps，RT 为 10ms，通过调整发送 buffer 来优化发送效率。

##### BDP(Bandwidth-Delay Product) 带宽时延积

首先要理解一个概念带宽时延积:

> Bandwidth-delay product (BDP)

Product of data link’s capacity and its end-to-end delay. The result is the maximum amount of unacknowledged data that can be in flight at any point in time.

> 《High Performance Browser Networking》

![](https://i-blog.csdnimg.cn/img_convert/bab47f70d2ee147cf7bec496231c9602.png)

图片来自 [High Performance Browser Networking](https://hpbn.co/building-blocks-of-tcp/#bandwidth-delay-product)

其含义就是整个传输链路上可以传输的最大数据，TCP
 性能优化
 的一个关键点就是发送的数据要填满 BDP，从而充分利用带宽。就好比我们用货车拉货时，要尽可能将货车装满才能最大化其运力。

回到我们 500Mbps 带宽，10ms RT 的场景，我们先来计算下 BDP 是 625KB，这意味着我们能够一下子发出 625KB 时才能最大化的利用网络带宽，对应到发送端的优化，则是将发送窗口大小设置为 BDP。

```
500Mbit/s * 0.01s = 5Mbits
# 转为 byte
5 * 10^6 bits / 8 = 625,000 bytes
# 转为 KB
625,000 bytes / 1000 = 625KB
```

在其他条件都满足的情况下，传输一个 512MB 大小的文件，理想传输速度大约为 8~10s 左右。下面是调整 sendbuf 后所得到的下载 512MB 大小文件的速度：

下面是调整 sendbuf 后所得到的下载 512MB 大小文件的速度：

- sendbuf 为 100KB，下载时长 56s.

```
$ curl 172.19.0.4:8089/testfile > testfile
  % Total    % Received % Xferd  Average Speed   Time    Time     Time  Current
                                 Dload  Upload   Total   Spent    Left  Speed
100  512M  100  512M    0     0  9350k      0  0:00:56  0:00:56 --:--:-- 9363k
```

- sendbuf 为 200KB，下载时长 24s。

```
$ curl 172.19.0.4:8089/testfile > /dev/null
  % Total    % Received % Xferd  Average Speed   Time    Time     Time  Current
                                 Dload  Upload   Total   Spent    Left  Speed
100  512M  100  512M    0     0  21.0M      0  0:00:24  0:00:24 --:--:-- 21.0M
```

- sendbuf 为 700KB 或者 100KB，下载速度均为 8 ~ 9s，后续继续在增大 sendbuf 也不再有明显提到了。

```
$ curl 172.19.0.4:8089/testfile > /dev/null
  % Total    % Received % Xferd  Average Speed   Time    Time     Time  Current
                                 Dload  Upload   Total   Spent    Left  Speed
100  512M  100  512M    0     0  58.4M      0  0:00:08  0:00:08 --:--:-- 58.7M
```

### 简要总结

整体来看，要想 TCP 数据传输的快，需要满足三个条件：

- **发得快**：发送端窗口足够，能填满 BDP，数据发送快。
- **传得快**：网络环境好，带宽大、RT 小、丢包率低。
- **收的快**：接收端数据处理快，接收窗口大。

在实际工作场景中，需要结合具体场景探查性能问题出现在哪一点，然后在寻找针对性的优化方案。
