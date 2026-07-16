---
title: 【动手实验】TCP 数据的发送与接收抓包分析
date: 2023-09-02 09:17:14
draft: true
tags:
  - 计算机网络
  - 动手实验
categories:
  - 计算机网络
  - 动手实验
description: tcp那些事
---

## 重传

**实验环境**

这里使用两台腾讯云服务器：vm-1（172.19.0.3）和vm-2（172.19.0.6）。

### 超时重传

首先 vm-1 作为服务端启动 nc，然后开启抓包，并使用 netstat 查看连接状态：

```bash
$ nc -k -l 172.19.0.3 9527

# 新开一个终端开启抓包
$ sudo tcpdump -s0 -X -nn "tcp port 9527" -w tcp.pcap --print

# 新开一个终端查看连接状态
$ while true; do sudo netstat -anpo | grep 9527 | grep -v LISTEN; sleep 1; done
```

然后我们在 vm-2 上使用 nc 连接 vm-1，三次握手成功后使用 iptables 拦截所有 vm-1 发来的包。

```bash
$ nc 172.19.0.3 9527

# 新开一个终端使用 iptables 拦截所有 vm-1 发来的包
$ sudo iptables -A INPUT -p tcp --sport 9527 -j DROP
```

准备好后我们从 vm-1 输入 abc 按下回车， vm-2 的 iptables 会将包丢弃，因此会触发 vm-1 进行重传，我们来看下 vm-1 的网络连接状态以及抓包结果：

- 网络连接状态
  
```bash
tcp        0      0 172.19.0.3:9527         172.19.0.6:41278        ESTABLISHED 490833/nc            off (0.00/0/0)
tcp        0      4 172.19.0.3:9527         172.19.0.6:41278        ESTABLISHED 490833/nc            on (0.30/1/0)
tcp        0      4 172.19.0.3:9527         172.19.0.6:41278        ESTABLISHED 490833/nc            on (0.08/2/0)
tcp        0      4 172.19.0.3:9527         172.19.0.6:41278        ESTABLISHED 490833/nc            on (0.72/3/0)
tcp        0      4 172.19.0.3:9527         172.19.0.6:41278        ESTABLISHED 490833/nc            on (2.96/4/0)
...
tcp        0      4 172.19.0.3:9527         172.19.0.6:41278        ESTABLISHED 490833/nc            on (6.35/5/0)
...
tcp        0      4 172.19.0.3:9527         172.19.0.6:41278        ESTABLISHED 490833/nc            on (12.31/6/0)
...
tcp        0      4 172.19.0.3:9527         172.19.0.6:41278        ESTABLISHED 490833/nc            on (25.12/7/0)
...
tcp        0      4 172.19.0.3:9527         172.19.0.6:41278        ESTABLISHED 490833/nc            on (50.24/8/0)
...
tcp        0      4 172.19.0.3:9527         172.19.0.6:41278        ESTABLISHED 490833/nc            on (101.48/9/0)
...
tcp        0      4 172.19.0.3:9527         172.19.0.6:41278        ESTABLISHED 490833/nc            on (119.18/10/0)
...
tcp        0      4 172.19.0.3:9527         172.19.0.6:41278        ESTABLISHED 490833/nc            on (119.30/11/0)
...
tcp        0      4 172.19.0.3:9527         172.19.0.6:41278        ESTABLISHED 490833/nc            on (119.41/12/0)
...
tcp        0      4 172.19.0.3:9527         172.19.0.6:41278        ESTABLISHED 490833/nc            on (119.54/13/0)
...
tcp        0      4 172.19.0.3:9527         172.19.0.6:41278        ESTABLISHED 490833/nc            on (119.66/14/0)
...
tcp        0      4 172.19.0.3:9527         172.19.0.6:41278        ESTABLISHED 490833/nc            on (119.80/15/0)
...
```


- 抓包结果
  
![](https://pub-08b57ed9c8ce4fadab4077a9d577e857.r2.dev/tcp-rto-01.png)


我们来分析下抓包结果。

#### 1. RTO 计算算法

三次握手后第 4 个包发送数据，其 length 为 4，我们输入了 abc 并按下回车，刚好四个字节，因为客户端收不到包，因此后续触发了重传。

TCP 重传是基于时间来判断的，这里有两个概念：
- RTO（Retransmission TimeOut）：重传超时时间
- RTT（Round Trip Time）：往返时间

TCP 会根据 RTT 来动态的计算 RTO，如果超时 RTO 会采用指数退避原则进行指数级增长，但最大不超过 120s。我们先来回顾下 RTO 的计算算法：

##### 经典算法

RFC 793 中定义的 RTO 计算算法如下：

1. 记录初始的几次 RTT 值
2. 计算平滑 RTT 值（SRTT，Smoothed RTT），计算公式为如下：

```sh
# alpha 为平滑因子，取值在 0.8 到 0.9 之间，Linux 内核中默认是 0.875
SRTT = ( ALPHA * SRTT ) + ((1-ALPHA) * RTT)
```
可以看到，如果 alpha 值越大，标识系统越信任之前的计算结果，否则就会更信任新的 RTT 值。

3. 计算 RTO 值，计算公式为如下：

```sh
RTO = min[Ubound,max[Lbound,(BETA*SRTT)]]
```
- Ubound 为 RTO 上限，Linux 内核中默认是 120s
- Lbound 为 RTO 下限，Linux 内核中默认是 200ms
- Beta 为延迟方差因子，取值在 1.3 到 2.0 之间。

##### Karn 算法

上述算法的问题在于将所有包的 RTT 一视同仁，是对于重传的包，如果取第一次发送+ACK 包的 RTT 值，会导致 RTT 明显偏大；如果取重传的包，此时如果之前的 ACK 响应回来了，又会导致取值偏小。

![](https://pub-08b57ed9c8ce4fadab4077a9d577e857.r2.dev/Karn-Partridge-Algorithm.jpg)


为此 1987 年 Phil Karn/Craig Partridge  在论文 [Improving Round-Trip Time Estimates in Reliable Transport Protocols ](https://dl.acm.org/doi/pdf/10.1145/55483.55484) 中提出了 Karn 算法，其最大的特点是将重传的包忽略掉，不用来做 RTT 的计算，同时一旦重传，RTO 会立即翻倍。

[rfc6298](https://datatracker.ietf.org/doc/html/rfc6298)  中规定，RTT 的采用必须采用 Karn 算法。

##### Jacobson/Karels 算法

RFC2988 中改进了重传算法，并在 [rfc6298](https://datatracker.ietf.org/doc/html/rfc6298) 中进行了更新，其规定的 RTO 计算算法如下:

```
对于初始 RTO，当第一个包的 RTT 获取到后：
SRTT = RTT
RTTVAR = RTT / 2
RTO = SRTT + max(K*RTTVAR, G) where K = 4 and G = 200ms

对于后续的 RTO 值计算，获取到新的 RTT 后：
RTTVAR = (1-Beta)*RTTVAR + Beta*|SRTT - RTT|
SRTT = (1-Alpha)*SRTT + Alpha*RTT

最后 RTO 的计算公式为：

RTO = SRTT + max(K*RTTVAR, G)
```

在 Linux 中，Alpha 取值为 0.125，Beta 取值为 0.25，K 取值为 4，G 取值为 200ms，其次还做了一些工程上的优化，这里先不深究，具体源码参考[tcp_rtt_estimator](https://elixir.bootlin.com/linux/v6.0/source/net/ipv4/tcp_input.c#L828) 和 [tcp_set_rto](https://elixir.bootlin.com/linux/v6.0/source/net/ipv4/tcp_input.c#L933)。


#### RTO 与 Delayed ACK

我们可以通过 ``ss -tip`` 命令查看某个连接的 rto，可以看到我们的连接初始 RTO 为 200ms，每次超时重传后都会翻倍，一直增长到 120s 后固定不变。

```bash
# 初始 RTO 为 200ms

ESTAB 0      0               172.19.0.3:9527                172.19.0.6:41278 users:(("nc",pid=490833,fd=4))
	 cubic wscale:7,7 rto:200 rtt:0.153/0.076 mss:8448 pmtu:8500 rcvmss:536 advmss:8448 cwnd:10 segs_in:2 send 4.42Gbps lastsnd:11221 lastrcv:11221 lastack:11221 pacing_rate 8.83Gbps delivered:1 app_limited rcv_space:57076 rcv_ssthresh:57076 minrtt:0.153 snd_wnd:59264

ESTAB 0      4               172.19.0.3:9527                172.19.0.6:41278 users:(("nc",pid=490833,fd=4))
	 cubic wscale:7,7 rto:12800 backoff:6 rtt:0.153/0.076 mss:8448 pmtu:8500 rcvmss:536 advmss:8448 cwnd:1 ssthresh:7 bytes_sent:32 bytes_retrans:28 segs_out:8 segs_in:2 data_segs_out:8 send 442Mbps lastsnd:1115 lastrcv:28668 lastack:28668 pacing_rate 8.83Gbps delivered:1 app_limited busy:14438ms unacked:1 retrans:1/7 lost:1 rcv_space:57076 rcv_ssthresh:57076 minrtt:0.153 snd_wnd:59264


ESTAB 0      4               172.19.0.3:9527                172.19.0.6:41278 users:(("nc",pid=490833,fd=4))
	 cubic wscale:7,7 rto:51200 backoff:8 rtt:0.153/0.076 mss:8448 pmtu:8500 rcvmss:536 advmss:8448 cwnd:1 ssthresh:7 bytes_sent:40 bytes_retrans:36 segs_out:10 segs_in:2 data_segs_out:10 send 442Mbps lastsnd:45728 lastrcv:112705 lastack:112705 pacing_rate 8.83Gbps delivered:1 app_limited busy:98475ms unacked:1 retrans:1/9 lost:1 rcv_space:57076 rcv_ssthresh:57076 minrtt:0.153 snd_wnd:59264


ESTAB 0      4               172.19.0.3:9527                172.19.0.6:41278 users:(("nc",pid=490833,fd=4))
	 cubic wscale:7,7 rto:102400 backoff:9 rtt:0.153/0.076 mss:8448 pmtu:8500 rcvmss:536 advmss:8448 cwnd:1 ssthresh:7 bytes_sent:44 bytes_retrans:40 segs_out:11 segs_in:2 data_segs_out:11 send 442Mbps lastsnd:2475 lastrcv:124748 lastack:124748 pacing_rate 8.83Gbps delivered:1 app_limited busy:110518ms unacked:1 retrans:1/10 lost:1 rcv_space:57076 rcv_ssthresh:57076 minrtt:0.153 snd_wnd:59264


$ sudo ss -tip | grep -A 1 9527
ESTAB 0      4               172.19.0.3:9527                172.19.0.6:41278 users:(("nc",pid=490833,fd=4))
	 cubic wscale:7,7 rto:120000 backoff:10 rtt:0.153/0.076 mss:8448 pmtu:8500 rcvmss:536 advmss:8448 cwnd:1 ssthresh:7 bytes_sent:48 bytes_retrans:44 segs_out:12 segs_in:2 data_segs_out:12 send 442Mbps lastsnd:4544 lastrcv:233313 lastack:233313 pacing_rate 8.83Gbps delivered:1 app_limited busy:219083ms unacked:1 retrans:1/11 lost:1 rcv_space:57076 rcv_ssthresh:57076 minrtt:0.153 snd_wnd:59264


$ sudo ss -tip | grep -A 1 9527
ESTAB 0      4               172.19.0.3:9527                172.19.0.6:41278 users:(("nc",pid=490833,fd=4))
	 cubic wscale:7,7 rto:120000 backoff:15 rtt:0.153/0.076 mss:8448 pmtu:8500 rcvmss:536 advmss:8448 cwnd:1 ssthresh:7 bytes_sent:68 bytes_retrans:64 segs_out:17 segs_in:2 data_segs_out:17 send 442Mbps lastsnd:2520 lastrcv:845689 lastack:845689 pacing_rate 8.83Gbps delivered:1 app_limited busy:831459ms unacked:1 retrans:1/16 lost:1 rcv_space:57076 rcv_ssthresh:57076 minrtt:0.153 snd_wnd:59264
```


从 ss 的信息中可以看到虽然 RTT 的大小始终是 ``rtt:0.153/0.076 ``，代表 rtt 时间为 0.153ms，平均偏差为 0.076ms，但 RTO 时间最小也是 200ms，后续一直增加到120000 ms，看起来和 RTT 并没有关系。

这样是因为 Linux 内核规定了 RTO 的最小值和最大值分别为 200ms 和 120s，具体源码如下：

```c
// 源码地址：https://elixir.bootlin.com/linux/v6.0/source/include/net/tcp.h#L141
#define TCP_RTO_MAX     ((unsigned)(120*HZ)) 
#define TCP_RTO_MIN     ((unsigned)(HZ/5))
```
HZ 表示 CPU 一秒种发出多少次时间中断–IRQ-0，通常使用 HZ 做时间片的单位，可以理解为 1HZ 就是 1s。
```bash
$ cat /boot/config-`uname -r` | grep '^CONFIG_HZ='
CONFIG_HZ=1000

# ubuntu @ vm-1 in ~ [15:44:15]
$ cat /proc/interrupts | grep timer && sleep 1 && cat /proc/interrupts | grep timer
LOC:  134957597  148734818   Local timer interrupts
LOC:  134957987  148735153   Local timer interrupts
```

这样做主要是为了给 Delayed ACK 留出时间。简单来说就是让 TCP 在收到数据包后稍微等一会，看有没有其他需要发送的数据，如果有就让 ACK 搭个便车一起发送回去，这样可以减少网络上小包的数量，提高网络传输效率。RTO 的计算逻辑几经改进，最终一顿操作猛如虎，不如 Delayed ACK 直接一把梭给你定死个下限。
   
#### 重传超时时长

netstat 查看状态也可以看到重传计时器在不断变化，从 200ms 开始不断翻倍，最终在传完 10 次后固定为 120s，最终显示已经重传了 15 次 `` on (119.80/15/0)``。这里主要受 ``tcp_retries2`` 参数的控制，默认为 15。注意这里不是精确控制一定会重传 15 次，而是 tcp_retries2 结合 TCP_RTO_MIN（200ms）计算出一个超时时间来，tcp 连接不断重传，最终不能超过这个超时时间。源码如下，


```c

// 源码地址：https://elixir.bootlin.com/linux/v6.0/source/net/ipv4/tcp_timer.c#L231
static int tcp_write_timeout(struct sock *sk)
{
	// ... 代码省略
	bool expired = false, do_reset;
	int retry_until = READ_ONCE(net->ipv4.sysctl_tcp_retries2);

	if (!expired)
		expired = retransmits_timed_out(sk, retry_until,
						icsk->icsk_user_timeout);
	if (expired) {
		/* Has it gone just too far? */
		tcp_write_err(sk);
		return 1;
	} 
}
// 源码地址：https://elixir.bootlin.com/linux/v6.0/source/net/ipv4/tcp_timer.c#L209
static bool retransmits_timed_out(struct sock *sk,
				  unsigned int boundary,
				  unsigned int timeout)
{
	// ... 代码省略
	unsigned int start_ts;
	unsigned int rto_base = TCP_RTO_MIN;
	timeout = tcp_model_timeout(sk, boundary, rto_base);
	return (s32)(tcp_time_stamp(tcp_sk(sk)) - start_ts - timeout) >= 0;
}


// 源码地址：https://elixir.bootlin.com/linux/v6.0/source/net/ipv4/tcp_timer.c#L182
static unsigned int tcp_model_timeout(struct sock *sk,
				      unsigned int boundary,
				      unsigned int rto_base)
{
	unsigned int linear_backoff_thresh, timeout;
	linear_backoff_thresh = ilog2(TCP_RTO_MAX / rto_base);
	if (boundary <= linear_backoff_thresh)
		timeout = ((2 << boundary) - 1) * rto_base;
	else
		timeout = ((2 << linear_backoff_thresh) - 1) * rto_base +
			(boundary - linear_backoff_thresh) * TCP_RTO_MAX;
	return jiffies_to_msecs(timeout);
}
```

可以看到内核取 ``tcp_retries2`` 参数值作为 boundary，核心计算逻辑位于 ``tcp_model_timeout`` 函数中，首先会计算出小于 120s 时的指数退避次数为 9。因此重传次数在小于等于 9 次时，下一次的重传时间都是指数增加的，如果超过 9 次比如已经发生了 10 次重传，那下一次的重传时间就是 120s 了。从 netstat 的输出中我们可以验证这一点：

```sh
tcp        0      4 172.19.0.3:9527         172.19.0.6:41278        ESTABLISHED 490833/nc            on (101.48/9/0)
...
tcp        0      4 172.19.0.3:9527         172.19.0.6:41278        ESTABLISHED 490833/nc            on (119.18/10/0)
```

总超时的计算逻辑为：

- tcp_retries2 <= 9 时， ``timeout = ((2 << boundary) - 1) * rto_base``
- tcp_retries2 > 9 时， ``timeout = ((2 << linear_backoff_thresh) - 1) * rto_base + (boundary - linear_backoff_thresh) * TCP_RTO_MAX;``

基于上述逻辑，在 rto 为 200ms时，我们可以计算出 tcp_retries2 设置和总重传超时时间的关系：

| tcp_retries2 | 重传超时时间   | 总超时时间 |
| ------------ | ------------ |-----------|
| 0            | 200ms        |200ms      |
| 1            | 400ms        |600ms      |
| 2            | 800ms 		  |1.4s       |
| 3            | 1.6s         |3s         |
| 4            | 3.2s         |6.2s       |
| 5            | 6.4s         |12.6s      |	
| 6            | 12.8s        |25.4s      |
| 7            | 25.6s        |51s        |
| 8            | 51.2s        |102.2s     |
| 9            | 102.4s       |204.6s     |
| 10           | 120s 		  |324.6s     |
| 11           | 120s         |444.6s     |
| 12           | 120s         |564.6s     |
| 13           | 120s         |684.6s     |
| 14           | 120s         |804.6s     |
| 15           | 120s         |924.6s     |


tcp_retries2 默认是 15，因此默认情况下，TCP 发送数据失败后大约会在 924.6s，大约 15 分钟左右才会放弃连接。如果实际 RTO 很大，也不会真的重传 15 次导致等待时间过长，而是在超过 924.6s 后放弃连接。下面我们使用 ``tc qdisc`` 将 vm-2 的延迟改为 2s 来模拟网络延迟在来看下重传的次数：

```bash
# ubuntu @ vm-2 in ~ [10:05:28]
$ sudo tc qdisc add dev eth0 root netem delay 2000ms
```

修改完成后重新建立连接并发送数据，通过 ss、netstat 查看，可以看到初始 RTO 已经成了 6s，抓包显示实际的重传次数为 11 次，超时时长为 ``973.2567 -  45.5127 = 927.744s``，大约 15 分钟多一些，基本符合预期。

```bash
# 初始 RTO 为 6s
$ sudo ss -tip | grep -A 1 9527
ESTAB 0      0               172.19.0.3:9527                172.19.0.6:36856 users:(("nc",pid=1880252,fd=4))
	 cubic wscale:7,7 rto:6000 rtt:2000/1000 mss:8448 pmtu:8500 rcvmss:536 advmss:8448 cwnd:10 segs_in:3 send 338kbps lastsnd:25355 lastrcv:25355 lastack:24330 pacing_rate 676kbps delivered:1 app_limited retrans:0/1 rcv_space:57076 rcv_ssthresh:57076 minrtt:2000 snd_wnd:59264

# 超时时间翻倍到 120s 后，RTO 也变为 120000ms
$ sudo ss -tip | grep -A 1 9527
ESTAB 0      4               172.19.0.3:9527                172.19.0.6:39054 users:(("nc",pid=1910324,fd=4))
	 cubic wscale:7,7 rto:120000 backoff:5 rtt:2000/1000 mss:8448 pmtu:8500 rcvmss:536 advmss:8448 cwnd:1 ssthresh:7 bytes_sent:28 bytes_retrans:24 segs_out:7 segs_in:3 data_segs_out:7 send 33.8kbps lastsnd:74641 lastrcv:308618 lastack:307585 pacing_rate 676kbps delivered:1 app_limited busy:269672ms unacked:1 retrans:1/7 lost:1 rcv_space:57076 rcv_ssthresh:57076 minrtt:2000 snd_wnd:59264

# 从 6 s 开始翻倍，6、12、24、48、96，在传完 5 次后超时时间固定为 120s。最终重传完 11 次后，总时间超过了 900 多s，系统终止连接
$ while true; do sudo netstat -anpo | grep 9527 | grep -v LISTEN; sleep 1; done
tcp        0      0 172.19.0.3:9527         172.19.0.6:39054        ESTABLISHED 1910324/nc           off (0.00/0/0)
tcp        0      4 172.19.0.3:9527         172.19.0.6:39054        ESTABLISHED 1910324/nc           on (3.98/0/0)
tcp        0      4 172.19.0.3:9527         172.19.0.6:39054        ESTABLISHED 1910324/nc           on (2.96/0/0)
tcp        0      4 172.19.0.3:9527         172.19.0.6:39054        ESTABLISHED 1910324/nc           on (1.94/0/0)
tcp        0      4 172.19.0.3:9527         172.19.0.6:39054        ESTABLISHED 1910324/nc           on (0.92/0/0)
tcp        0      4 172.19.0.3:9527         172.19.0.6:39054        ESTABLISHED 1910324/nc           on (0.00/0/0)
....
tcp        0      4 172.19.0.3:9527         172.19.0.6:39054        ESTABLISHED 1910324/nc           on (5.24/0/0)
tcp        0      4 172.19.0.3:9527         172.19.0.6:39054        ESTABLISHED 1910324/nc           on (4.22/0/0)
tcp        0      4 172.19.0.3:9527         172.19.0.6:39054        ESTABLISHED 1910324/nc           on (3.20/0/0)
tcp        0      4 172.19.0.3:9527         172.19.0.6:39054        ESTABLISHED 1910324/nc           on (2.17/0/0)
tcp        0      4 172.19.0.3:9527         172.19.0.6:39054        ESTABLISHED 1910324/nc           on (1.15/0/0)
tcp        0      4 172.19.0.3:9527         172.19.0.6:39054        ESTABLISHED 1910324/nc           on (0.13/0/0)
tcp        0      4 172.19.0.3:9527         172.19.0.6:39054        ESTABLISHED 1910324/nc           on (11.25/1/0)
...
tcp        0      4 172.19.0.3:9527         172.19.0.6:39054        ESTABLISHED 1910324/nc           on (23.27/2/0)
...
tcp        0      4 172.19.0.3:9527         172.19.0.6:39054        ESTABLISHED 1910324/nc           on (47.80/3/0)
...
tcp        0      4 172.19.0.3:9527         172.19.0.6:39054        ESTABLISHED 1910324/nc           on (95.36/4/0)
...
tcp        0      4 172.19.0.3:9527         172.19.0.6:39054        ESTABLISHED 1910324/nc           on (119.48/5/0)
...
tcp        0      4 172.19.0.3:9527         172.19.0.6:39054        ESTABLISHED 1910324/nc           on (119.48/11/0)
...
tcp        0      4 172.19.0.3:9527         172.19.0.6:39054        ESTABLISHED 1910324/nc           on (2.70/11/0)
tcp        0      4 172.19.0.3:9527         172.19.0.6:39054        ESTABLISHED 1910324/nc           on (1.68/11/0)
...
tcp        0      4 172.19.0.3:9527         172.19.0.6:39054        ESTABLISHED 1910324/nc           on (0.00/11/0)
tcp        0      4 172.19.0.3:9527         172.19.0.6:39054        ESTABLISHED 1910324/nc           on (0.00/11/0)
```

抓包结果如下：

![](https://pub-08b57ed9c8ce4fadab4077a9d577e857.r2.dev/tcp-data-transform-002.png)


### 快速重传

可以看到依赖于 RTO 的重传会因为 TCP_RTO_MIN 的影响，导致重传超时时间很长，效率很低。为此 [RFC 5681](https://datatracker.ietf.org/doc/html/rfc5681) 中提出了快速重传（Fast Retransmit），该算法不以时间作为重传依据，而是按照收到的重复 ACK 来判断是否需要重传。

RFC 规定，当接收方收到的包乱序时，要立即响应一个 duplicate ACK，比如有 1、2、3、4、5 共5个包，在收到 1 后接收方 ACK 为 2，表示希望接下来收到 2 号包，但此时如果收到了 3、4、5 号包，此时接收方需要立即响应 duplicate ACK 给发送方。

RFC 规定发送方在收到 3 个 Duplicate ACK 后，会立即重传，这样判断的依据是，有两种情况会导致接收方收到的包乱序：**乱序**或**丢包**。如果是乱序，接收方通常会稍后收到预期的包，比如在收到 3 后才收到 2 号包，此时发送方一般只会收到 1 ~ 2  次 Duplicate ACK。但如果是丢包，就会导致接收方多次响应 Duplicate ACK，此时发送方就可以认为是丢包，从而引发进行快速重传。

下面我们使用 [scapy](https://scapy.readthedocs.io/en/latest/) 来模拟快速重传的过程。代码如下：

- 服务端程序
  
```python
import socket
import time 

def start_server(host, port, backlog):
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind((host, port))
    server.listen(backlog)
    client, _ = server.accept()
    client.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1) # 禁用 Nagle 算法

    client.sendall(b"a" * 1460)
    time.sleep(0.01) # 避免协议栈合并包的方式，不严谨但是凑合能工作
    client.sendall(b"b" * 1460)
    time.sleep(0.01)
    client.sendall(b"c" * 1460)
    time.sleep(0.01)
    client.sendall(b"d" * 1460)
    time.sleep(0.01)
    client.sendall(b"e" * 1460)
    time.sleep(0.01)
    client.sendall(b"f" * 1460)
    time.sleep(0.01)
    client.sendall(b"g" * 1460)

    time.sleep(10000)


if __name__ == '__main__':
    start_server('172.19.0.3', 9527, 8)
```

- 客户端程序

```python
import threading
import time
from scapy.all import *
from scapy.layers.inet import *


class ACKDataThread(threading.Thread):
    def __init__(self):
        super().__init__()
        self.first_data_ack_seq = 0

    def run(self):
        def packet_callback(packet):
            ip = IP(dst="172.19.0.3")

            resp_tcp = packet[TCP]

            # 收到第二次握手包
            if 'SA' in str(resp_tcp.flags):
                recv_seq = resp_tcp.seq
                recv_ack = resp_tcp.ack
                print(f"received SYN, seq={recv_seq}, ACK={recv_ack}")
                send_ack = recv_seq + 1
                tcp = TCP(sport=9528, dport=9527, flags='A', seq=2, ack=send_ack)
                print(f"send ACK={send_ack}")
                # 第三次握手
                send(ip/tcp)
                return
            # 收到数据包
            elif resp_tcp.payload:
                print("-" * 50)
                print(f"Received TCP packet")
                print(f"Flags: {resp_tcp.flags}")
                print(f"Sequence: {resp_tcp.seq}")
                print(f"ACK: {resp_tcp.ack}")
                print(f"Payload: {resp_tcp.load}")
                # send_ack = resp_tcp.seq + len(resp_tcp.load)
                if self.first_data_ack_seq == 0:
                    self.first_data_ack_seq = resp_tcp.seq + len(resp_tcp.load)
                send_ack = self.first_data_ack_seq
                tcp = TCP(sport=9528, dport=9527, flags='A', seq=2, ack=send_ack)
                print(f"send ACK={send_ack}")
				# 发送 4 次重复的 ACK
                send(ip/tcp)
                send(ip/tcp)
                send(ip/tcp)
                send(ip/tcp)

        interface = "eth0"  # 根据实际络接口名称更改
        sniff(iface=interface, prn=packet_callback, filter="tcp and port 9527", store=0)


def main():
    thread = ACKDataThread()
    thread.start()

    time.sleep(1)

    ip = IP(dst="172.19.0.3")
    tcp = TCP(sport=9528, dport=9527, flags='S', seq=1, options=[('MSS', 1460)])

    # 第一次握手
    print("send SYN, seq=0")
    send(ip/tcp)

    thread.join()


if __name__ == "__main__":
    main()
```

启动程序

```
# vm-1
# 启动服务端
$ python3 server.py
# 开启抓包
$ sudo tcpdump -S -s0 -nn "tcp port 9527" -w tcp-fast-retra.pcap --print


# vm-2
# 丢弃 RST 包
$ sudo iptables -A OUTPUT -p tcp --tcp-flags RST RST --dport 9527 -j DROP

# 启动客户端
$ python3 client.py
```

我们将抓包结果放到 Wireshark 中做分析，其标识了 Duplicate ACK 的包和快速重传的包，可以看到在服务端 0.018s 发送了数据包，然后在 0.072s 进行了快速重传，中间只差了 54ms，比 RTO 要小很多。然后在 0.285s 又进行了一次快速重传，这个和之前的快速重传包差了大约 200ms，已经是超时重传在进行了，后续在 0.709s、1.589s 进行的重传，时间间隔基本符合指数退避的规律。

![](https://pub-08b57ed9c8ce4fadab4077a9d577e857.r2.dev/tcp-fast-retra01.png)

 Wireshark -> 统计 -> TCP 流图形 -> 序列号（tcptrace）窗口中可以看到重传的标识，其中的蓝色竖线表示有包发生了重传。

![](https://pub-08b57ed9c8ce4fadab4077a9d577e857.r2.dev/tcp-fast-retra02.png)

虽然 RFC 规定收到 3 个 Duplicate ACK 后才需要快速重传，但 Linux 提供了参数 ``net.ipv4.tcp_reordering``来控制，默认为 3，如果我们修改为 1 可以看到在收到一个 Duplicate ACK 后就会立即重传。当然，生产环境中不建议修改这些参数。

```bash
$ sudo sysctl -w net.ipv4.tcp_reordering=1
net.ipv4.tcp_reordering = 1
```

![](https://pub-08b57ed9c8ce4fadab4077a9d577e857.r2.dev/tcp-fast-retra03.png)

### SACK（Selective ACK）

SACK 是 TCP 提供的一种可选择重传机制，允许发送方在收到乱序包时，只重传丢失的包，而不是重传整个窗口的数据。

SACK 的实现需要双方协商，在握手时需要发送方在选项中携带 SACK 选项，接收方在收到后会启用 SACK 机制。



## 滑动窗口

## 拥塞控制

### 开启 BBR 算法

可以通过 ``net.ipv4.tcp_available_congestion_control`` 参数查看当前已经启用的拥塞控制算法：

```bash
$ sysctl net.ipv4.tcp_available_congestion_control
net.ipv4.tcp_available_congestion_control = reno cubic
```

Linux 内核从 4.9 开始就支持 BBR 算法了，我们的内核版本是 ``5.15.0-130-generic``，因此是支持的只需要启用下即可。


```bash
# 检查内核配置文件是否支持BBR，如果是 y 说明已经内置，可以直接启用；如果是 m 说明是基于模块存在，需要加载模块；如果没有需要更新内核。
$ sudo cat /boot/config-$(uname -r) | grep CONFIG_TCP_CONG_BBR
CONFIG_TCP_CONG_BBR=m

# BBR 需要配合 fq 调度器使用，看是否已支持，输出是 m 说明支持。
# ubuntu @ vm-02 in ~ [10:02:06]
$ sudo cat /boot/config-$(uname -r) | grep CONFIG_NET_SCH_FQ
CONFIG_NET_SCH_FQ_CODEL=m
CONFIG_NET_SCH_FQ=m
CONFIG_NET_SCH_FQ_PIE=m

# 加载 bbr 模块
$ sudo modprobe tcp_bbr

# 查看可用算法
$ sysctl net.ipv4.tcp_available_congestion_control
net.ipv4.tcp_available_congestion_control = reno cubic bbr
```

bbr 算法可用后，修改 tcp_congestion_control 和 qdisc 配置即可启用 BBR：

```bash
$ sysctl -w net.ipv4.tcp_congestion_control=bbr net.core.default_qdisc=fq
net.core.default_qdisc=fq
net.ipv4.tcp_congestion_control=bbr
```

