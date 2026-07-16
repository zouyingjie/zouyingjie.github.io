---
title: 【动手实验】TCP半连接队列、全连接队列实战分析
date: 2023-09-02 09:17:14
tags:
  - 计算机网络
  - 动手实验
categories:
  - 计算机网络
  - 动手实验
description: 你 SYN Queue 满了么？
---

本文是对 [从一次线上问题说起，详解 TCP 半连接队列、全连接队列](https://www.51cto.com/article/687595.html) 这篇文章的实验复现和总结，借此加深对 TCP 半连接队列、全连接队列的理解。

## 实验环境

两台腾讯云服务器 node2（172.19.0.12） 和 node3（172.19.0.15）配置为 2C4G，Ubuntu 系统，内核版本 5.15.0-130-generic 。

## 全连接半连接队列简介

在 TCP 三次握手过程中，Linux 会维护两个队列分别是：

- SYN Queue 半连接队列
- Accept Queue 全连接队列

创建连接时，两个队列作用如下：

- 客户端向服务端发送 SYN 包，客户端进入 SYN_SENT 状态
- 服务端收到 SYN 包后，进入 SYN_RECV 状态，内核将连接信息放入 SYN Queue 队列，然后向客户端发送 SYN+ACK 包
- 客户端收到 SYN+ACK 包后，发送 ACK 包，客户端进入 ESTABLISHED 状态
- 服务端收到 ACK 包后，将连接从 SYN Queue 队列中取出移到 Accept Queue 队列，Server 端进入 ESTABLISHED。
- 服务端应用程序调用 accept 函数处理数据，连接从 Accept Queue 队列移除。

![](https://pub-08b57ed9c8ce4fadab4077a9d577e857.r2.dev/tcp-synqueue-01.jpg)
图片来自：[从一次线上问题说起，详解 TCP 半连接队列、全连接队列
](https://www.51cto.com/article/687595.html)


![](https://pub-08b57ed9c8ce4fadab4077a9d577e857.r2.dev/syn-queue-02.jpeg)

图片来自[Cloudflare Blog: SYN Packet Handling in the Wild](https://blog.cloudflare.com/syn-packet-handling-in-the-wild/?utm_source=chatgpt.com/)

两个队列的长度都是有限的，当队列满了之后，新建连接时内核会将 SYN 包丢弃或者直接返回 RST 包。


## 全连接队列实战

### 全连接队列长度控制

TCP 全连接队列的长度计算公式为：

> min(somaxconn, backlog)

- **somaxconn** Linux 内核参数 ``net.core.somaxconn`` 的值，默认为 4096。可以通过修改该参数来控制全连接队列的长度。
- **backlog** 是系统调用 listen 函数 ``int listen(int sockfd, int backlog)`` 的 backlog 参数， Golang 中默认使用系统 somaxconn 的值。

下面是 Linux 5.15.130 内核源码中计算全连接队列长度的代码：

源码地址：https://elixir.bootlin.com/linux/v5.15.130/source/net/socket.c#L1716
![](https://pub-08b57ed9c8ce4fadab4077a9d577e857.r2.dev/linux-source-code-01.png)


我们修改 somaxconn 的值，然后运行实验代码查看全连接队列的长度变化。

- 服务端实验代码

```golang
package main

import (
  "log"
  "net"
  "time"
)

func main() {
  l, err := net.Listen("tcp", ":8888")
  if err != nil {
    log.Printf("failed to listen due to %v", err)
  }
  defer l.Close()
  log.Println("listen :8888 success")

  for {
    time.Sleep(time.Second * 100)
  }
}
```

首先我们修改 somaxconn 为 128：

```bash
sudo sysctl -w net.core.somaxconn=128
```

启动服务后查看全连接队列的长度：

```bash
$ go run server.go
2025/02/13 09:53:01 listen :8888 success


$ ss -lnt
State             Recv-Q            Send-Q                         Local Address:Port                         Peer Address:Port            Process
LISTEN            0                 128                                        *:8888                                    *:*
...
```

这里简单解释下 ss 命令输出的含义：

- 对于 Listen 状态的 socket，Recv-Q 表示当前全连接队列的长度，也就是已经完成三次握手，等待应用层调用 accept 的 TCP 连接数；Send-Q 表示全连接队列的最大长度。
  
- 对于非 Listen 状态的 socket，Recv-Q 表示已经收到但尚未被应用读取的**字节数**；Send-Q 表示已发送但尚未收到确认的字节数。

再次修改 somaxconn 为 1024 重启服务后，查看全连接队列的长度已经变成了 1024。

```bash
$ sudo sysctl -w net.core.somaxconn=1024
$ go run server.go
2025/02/13 09:53:01 listen :8888 success


$ ss -lnt
State             Recv-Q            Send-Q                         Local Address:Port                         Peer Address:Port            Process
LISTEN            0                 1024                                       *:8888                                    *:*
...
```

### 全连接队列溢出

下面我们让服务端只 Listen 端口但不执行 accept() 处理数据，模拟全连接队列溢出的情况。

- 服务端代码

```golang
// server 端监听 8888 tcp 端口 
package main 
 
import ( 
  "log" 
  "net" 
  "time" 
) 
 
func main() { 
  l, err := net.Listen("tcp", ":8888") 
  if err != nil { 
    log.Printf("failed to listen due to %v", err) 
  } 
  defer l.Close() 
  log.Println("listen :8888 success") 
 
  for { 
    time.Sleep(time.Second * 100) 
  } 
}
```

- 客户端代码
  
和原实验相比加了 ``time.Sleep(500 * time.Millisecond)`` 一行代码，让连接一个个建立，可以更精准的复现全连接队列已满的情况。
```golang
package main 
 
import ( 
  "context" 
  "log" 
  "net" 
  "os" 
  "os/signal" 
  "sync" 
  "syscall" 
  "time" 
) 
 
var wg sync.WaitGroup 
 
func establishConn(ctx context.Context, i int) { 
  defer wg.Done() 
  conn, err := net.DialTimeout("tcp", ":8888", time.Second*5) 
  if err != nil { 
    log.Printf("%d, dial error: %v", i, err) 
    return 
  } 
  log.Printf("%d, dial success", i) 
  _, err = conn.Write([]byte("hello world")) 
  if err != nil { 
    log.Printf("%d, send error: %v", i, err) 
    return 
  } 
  select { 
  case <-ctx.Done(): 
    log.Printf("%d, dail close", i) 
  } 
} 
 
func main() { 
  ctx, cancel := context.WithCancel(context.Background()) 
  // 并发请求 10 次服务端，连接建立成功后发送数据
  for i := 0; i < 10; i++ { 
    wg.Add(1) 
    time.Sleep(500 * time.Millisecond)
    go establishConn(ctx, i) 
  } 
 
  go func() { 
    sc := make(chan os.Signal, 1) 
    signal.Notify(sc, syscall.SIGINT) 
    select { 
    case <-sc: 
      cancel() 
    } 
  }() 
 
  wg.Wait() 
  log.Printf("client exit") 
}
```

我们先将全连接队列的最大长度设置为 5：

```bash
$ sudo sysctl -w net.core.somaxconn=5

$ cat /proc/sys/net/core/somaxconn
5
```

运行服务端和客户端后，查看全连接队列情况：

- 服务端 socket 情况
```bash
$ ss -ant | grep -E "Recv|8888"
State      Recv-Q Send-Q        Local Address:Port            Peer Address:Port Process
LISTEN     6      5                         *:8888                       *:*
ESTAB      11     0      [::ffff:172.19.0.12]:8888    [::ffff:172.19.0.15]:40148
ESTAB      11     0      [::ffff:172.19.0.12]:8888    [::ffff:172.19.0.15]:40162
ESTAB      11     0      [::ffff:172.19.0.12]:8888    [::ffff:172.19.0.15]:40128
ESTAB      11     0      [::ffff:172.19.0.12]:8888    [::ffff:172.19.0.15]:40132
ESTAB      11     0      [::ffff:172.19.0.12]:8888    [::ffff:172.19.0.15]:40110
ESTAB      11     0      [::ffff:172.19.0.12]:8888    [::ffff:172.19.0.15]:40112
```

- 客户端 socket 情况

```bash
$ ss -ant | grep -E "Recv|8888"
State      Recv-Q Send-Q Local Address:Port    Peer Address:Port Process
ESTAB      0      0        172.19.0.15:40132    172.19.0.12:8888
ESTAB      0      0        172.19.0.15:40162    172.19.0.12:8888
ESTAB      0      0        172.19.0.15:40148    172.19.0.12:8888
SYN-SENT   0      1        172.19.0.15:51906    172.19.0.12:8888
ESTAB      0      0        172.19.0.15:40112    172.19.0.12:8888
ESTAB      0      0        172.19.0.15:40128    172.19.0.12:8888
SYN-SENT   0      1        172.19.0.15:51912    172.19.0.12:8888
SYN-SENT   0      1        172.19.0.15:40176    172.19.0.12:8888
ESTAB      0      0        172.19.0.15:40110    172.19.0.12:8888
SYN-SENT   0      1        172.19.0.15:51926    172.19.0.12:8888
```

- 客户端日志输出

```bash
$ go run client.go
2025/02/19 11:14:22 0, dial success
2025/02/19 11:14:22 1, dial success
2025/02/19 11:14:23 2, dial success
2025/02/19 11:14:23 3, dial success
2025/02/19 11:14:24 4, dial success
2025/02/19 11:14:24 5, dial success
2025/02/19 11:14:30 6, dial error: dial tcp 172.19.0.12:8888: i/o timeout
2025/02/19 11:14:30 7, dial error: dial tcp 172.19.0.12:8888: i/o timeout
2025/02/19 11:14:31 8, dial error: dial tcp 172.19.0.12:8888: i/o timeout
2025/02/19 11:14:31 9, dial error: dial tcp 172.19.0.12:8888: i/o timeout
```

我们来分析下上述结果：

##### 1. 全连接队列是否已满

服务端 Listen 状态的 socket 显示 Send-Q 为 5，表示该 socket 的全连接队列最大值为 5；Recv-Q 为 6，表示当前 Accept queue 中数量为 6，我们看有 6 条 ESTAB 状态的连接，符合观察结果。Linux 内核的判断依据是 > 而不是 >=，所以实际的连接数为比队列的最大值多 1 个。5.15.0-130-generic 内核代码如下：

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

之所以这样做，是为了保证在 backlog 设置为 0 时，依然可以有一个连接进入全连接队列，具体可以查看以下 commit 信息：

```c
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

##### 2. 内核 drop 包处理逻辑

客户端有 6 个 ESTAB 状态的 socket，另外还有 4 个 SYN-SENT 状态的 socket，对应着 4 条 timeout 报错信息。我们只改了全连接队列大小为 5，半连接队列大小依然为默认的 ``net.ipv4.tcp_max_syn_backlog=256``，所以第 6 个请连接建立后 Accept Queue 满了但 SYN Queue 还没有满。按理说从第 7 个请求开始服务端可以接收 SYN 但不能在处理客户端的 ACK 进入 Accept Queue，服务端会有 4 条 SYN-RECV 状态的连接，而实际情况是服务端不存在 SYN_RECV 状态的连接，这是因为当 Accept Queue 被占满时，即使 SYN Queue 没有满，Linux 内核也会将新来的 SYN 请求丢弃掉。 5.15.0-130-generic 内核处理这部分逻辑的代码如下：：

```c
// 源码地址：https://elixir.bootlin.com/linux/v5.15.130/source/net/ipv4/tcp_input.c#L6848

int tcp_conn_request(struct request_sock_ops *rsk_ops,
		     const struct tcp_request_sock_ops *af_ops,
		     struct sock *sk, struct sk_buff *skb)
{
 // ... 代码省略

	syncookies = READ_ONCE(net->ipv4.sysctl_tcp_syncookies);

	/* TW buckets are converted to open requests without
	 * limitations, they conserve resources and peer is
	 * evidently real one.
	 */
   // 强制启用 SYN cookie 或者半连接队列已满
   // !isn 表示是一个新的请求连接建立的 SYN
	if ((syncookies == 2 || inet_csk_reqsk_queue_is_full(sk)) && !isn) {
    // 这里表示是否启用 SYN cookie 机制；如果不开启，则直接 drop，如果开启，则继续执行。
		want_cookie = tcp_syn_flood_action(sk, rsk_ops->slab_name);
		if (!want_cookie)
			goto drop;
	}
  // 如果 accept queue 满了则 drop
	if (sk_acceptq_is_full(sk)) {
		NET_INC_STATS(sock_net(sk), LINUX_MIB_LISTENOVERFLOWS);
		goto drop;
	}


static bool tcp_syn_flood_action(const struct sock *sk, const char *proto)
{
	struct request_sock_queue *queue = &inet_csk(sk)->icsk_accept_queue;
	const char *msg = "Dropping request";
	struct net *net = sock_net(sk);
	bool want_cookie = false;
	u8 syncookies;

	syncookies = READ_ONCE(net->ipv4.sysctl_tcp_syncookies);

// 开启 SYN Cookie 机制
#ifdef CONFIG_SYN_COOKIES
	if (syncookies) {
		msg = "Sending cookies";
		want_cookie = true;
		__NET_INC_STATS(sock_net(sk), LINUX_MIB_TCPREQQFULLDOCOOKIES);
	} else
#endif
    // 没有启用 syncookies，统计丢弃包的数量
		__NET_INC_STATS(sock_net(sk), LINUX_MIB_TCPREQQFULLDROP);
  
  // 如果启用了 SYN cookie 机制，发送警告
	if (!queue->synflood_warned && syncookies != 2 &&
	    xchg(&queue->synflood_warned, 1) == 0)
		net_info_ratelimited("%s: Possible SYN flooding on port %d. %s.  Check SNMP counters.\n",
				     proto, sk->sk_num, msg);

	return want_cookie;
}

// 判断半连接队列是否满，用的是半连接队列的长度是否大于等于全连接队列的最大长度
static inline int inet_csk_reqsk_queue_is_full(const struct sock *sk)
{
	return inet_csk_reqsk_queue_len(sk) >= sk->sk_max_ack_backlog;
}
```
从代码中可以推测出 ``net.ipv4.tcp_syncookies`` 参数值的含义和 Linux 的处理机制：

- 2：强制开启 SYN Cookie 机制，发送警告
- 1：当半连接队列满时，开启 SYN Cookie 机制，发送警告
- 0：不开启 SYN Cookie 机制，并统计丢弃包的数量

这里判断半连接队列是否满的依据是 ``inet_csk_reqsk_queue_len(sk) >= sk->sk_max_ack_backlog``，也就是说当半连接队列长度不小于全连接队列的最大长度时，如果不开启 SYN Cookie 机制，就会将 SYN 包丢弃。

回到我们的实验环境，``net.ipv4.tcp_syncookies`` 设置为 1 并且半连接队列没满，因此不会开启 SYN Cookie 机制，继续往后执行时会因为 Accept Queue 满了将包丢弃。可以通过 ``netstat -s`` 命令查看丢弃包的数量。

```bash
$ date;netstat -s | grep -i "SYNs to LISTEN"
Wed Feb 19 12:05:51 PM CST 2025
    1289 SYNs to LISTEN sockets dropped


$ date;netstat -s | grep -i "SYNs to LISTEN"
Wed Feb 19 12:06:05 PM CST 2025
    1301 SYNs to LISTEN sockets dropped
```

可以看到有 12 个 SYN 包被 DROP 了，查看抓包情况可以看到，我们有 4 个请求连接超时，每个请求传了 3 次 SYN（一次发起 + 两次重传）。

![](https://pub-08b57ed9c8ce4fadab4077a9d577e857.r2.dev/tcp-syn-queue-01.png)


查看客户端 socket 状态能够看到重传计时器在工作，这里重传了两次和默认的 ``net.ipv4.tcp_syn_retries = 6`` 有出入，是因为代码 ``conn, err := net.DialTimeout("tcp", "172.19.0.12:8888", time.Second*5)``设置了 5s 超时，操作系统的默认重传间隔大约为 1s、2s、4s、8s、16s、32s，第 3 次重传会发生在 7s 以后，客户端已经主动断开连接了。

```bash
$ sudo netstat -anpo | grep -E "Recv-Q|8888"
Proto Recv-Q Send-Q Local Address           Foreign Address         State       PID/Program name     Timer
tcp        0      0 172.19.0.15:57384       172.19.0.12:8888        ESTABLISHED 3123924/client       keepalive (7.57/0/0)
tcp        0      0 172.19.0.15:57388       172.19.0.12:8888        ESTABLISHED 3123924/client       keepalive (8.07/0/0)
tcp        0      0 172.19.0.15:60276       172.19.0.12:8888        ESTABLISHED 3123924/client       keepalive (9.58/0/0)
tcp        0      1 172.19.0.15:60304       172.19.0.12:8888        SYN_SENT    3123924/client       on (0.08/1/0)
tcp        0      1 172.19.0.15:60286       172.19.0.12:8888        SYN_SENT    3123924/client       on (2.60/2/0)
tcp        0      0 172.19.0.15:60270       172.19.0.12:8888        ESTABLISHED 3123924/client       keepalive (9.08/0/0)
tcp        0      0 172.19.0.15:60280       172.19.0.12:8888        ESTABLISHED 3123924/client       keepalive (10.08/0/0)
tcp        0      1 172.19.0.15:60292       172.19.0.12:8888        SYN_SENT    3123924/client       on (3.11/2/0)
tcp        0      0 172.19.0.15:57398       172.19.0.12:8888        ESTABLISHED 3123924/client       keepalive (8.57/0/0)
tcp        0      1 172.19.0.15:60294       172.19.0.12:8888        SYN_SENT    3123924/client       on (3.62/2/0)
```

##### 3. overflow 参数控制

当全连接队列满时，Linux 默认会 drop 掉包，这个受 ``net.ipv4.tcp_abort_on_overflow`` 参数控制，默认为 0 表示直接 drop，为 1 则表示中断连接，服务端会返回 RST 包。可以通过如下方式修改

```bash
$ sudo sysctl -w net.ipv4.tcp_abort_on_overflow=1

或者

echo 1 > /proc/sys/net/ipv4/tcp_abort_on_overflow
```

我们修改参数后再次执行客户端请求，会出现 ``connection reset by peer`` 错误，抓包能看到 RST 包。(在实验时，如果客户端不加时间间隔，会出现返回 RST 包的情况，如果加了则不会出现这种情况，应该是和两者的生效机制有关，SYN Cookie 和全连接队列满 drop 发生在 tcp_conn_request 函数，而 abort_on_overflow 发生在 tcp_check_req 函数， 先挖个坑，等后续梳理整个网络传输流程时在做进一步分析)。

```bash
$ go run client.go
2025/03/01 13:36:55 2, dial success
2025/03/01 13:36:55 5, dial success
2025/03/01 13:36:55 4, dial success
2025/03/01 13:36:55 1, dial success
2025/03/01 13:36:55 3, dial success
2025/03/01 13:36:55 0, dial success
2025/03/01 13:36:55 7, dial error: dial tcp 172.19.0.12:8888: connect: connection reset by peer
2025/03/01 13:36:55 6, dial error: dial tcp 172.19.0.12:8888: connect: connection reset by peer
```

![](https://pub-08b57ed9c8ce4fadab4077a9d577e857.r2.dev/linux-sys-queue-04.png)

##### 4. ss 命令展示含义

服务端有 6 条 ESTAB 状态的 socket，RECV_Q 的值为 11，与客户端发送的数据 ``[]byte("hello world")`` 数据长度一致，因为我们的没有执行 accept 接收数据，所以 RECV_Q 会展示这部分数据的大小；
   
客户端 6 条 ESTAB 状态的 socket，其 RECV_Q 和 SEND_Q 均为 0；而 4 条 SYN-SENT 状态的 SEND-Q 为 1，这是因为 6 条已建立连接的 socket 包可以被正常 ACK，而 4 条建立连接失败的 socket，其 SYN 包没有收到 ACK 包，因为 SEND-Q 显示为 1。由此我们可以再次总结下 ss 的展示含义：

**对于 LISTEN 状态的 socket**

- Recv-Q：表示当前全连接队列的大小，即已完成三次握手等待应用程序 accept() 的 TCP 连接数。
- Send-Q：全连接队列的最大长度，即全连接队列所能容纳的 socket 数量。

**对于非 LISTEN 状态的 socket**

- Recv-Q：表示已被接收但尚未执行 accept 被应用程序读取的数据字节数，通常在服务端能观察到。
- Send-Q：表示已经发送但尚未收到 ACK 确认的字节数。
  
内核代码如下：

```c
// https://elixir.bootlin.com/linux/v5.15.130/source/net/ipv4/tcp_diag.c#L18
static void tcp_diag_get_info(struct sock *sk, struct inet_diag_msg *r,
			      void *_info)
{
	struct tcp_info *info = _info;

	if (inet_sk_state_load(sk) == TCP_LISTEN) { // LISTEN 状态的连接

    // 当前已完成三次握手但未被 accept 的连接数
		r->idiag_rqueue = READ_ONCE(sk->sk_ack_backlog); 
    // 最大队列长度
		r->idiag_wqueue = READ_ONCE(sk->sk_max_ack_backlog);
	} else if (sk->sk_type == SOCK_STREAM) { // 非 LISTEN 状态的普通连接
		const struct tcp_sock *tp = tcp_sk(sk);

    // TCP 读队列，即接收缓冲区中未被应用层读取的数据量，单位是字节
		r->idiag_rqueue = max_t(int, READ_ONCE(tp->rcv_nxt) -
					     READ_ONCE(tp->copied_seq), 0);
    // TCP 写队列，即已经发送但尚未被对方 ACK 确认的数据量，单位是字节
		r->idiag_wqueue = READ_ONCE(tp->write_seq) - tp->snd_una;
	}
	if (info)
		tcp_get_info(sk, info);
}
```

##### 5. SYN+ACK 重传

原实验有三种情况：

- 三次握手成功，数据正常发送
- 客户端认为连接建立成功，但服务端一直处于 SYN-RECV 状态，不断重传 SYN + ACK
- 客户端发送 SYN 未得到响应一直在重传

我们复现了第 1 中和第 3 种，之所以没有第二种情况是因为每次请求加了 500ms 的间隔，这样下一个请求发起 SYN 时，上一个请求已经完成三次握手，服务端的 socket 已经进入全连接队列了。如果我们去掉时间间隔，请求可能会一下子发出去全部进入半连接队列，等到服务端在接收到客户端的 ACK 包时，全连接队列已经满了，从而导致服务端的 socket 无法进入全连接队列，从而 DROP 掉 ACK 包出现第二种情况。这里我们去掉时间间隔尝试复现，此时可以看到服务端有 SYN-RECV 状态的连接，


```
$ ss -ant | grep -E "Recv|8888"
State      Recv-Q Send-Q        Local Address:Port            Peer Address:Port Process
LISTEN     6      5                         *:8888                       *:*
ESTAB      11     0      [::ffff:172.19.0.12]:8888    [::ffff:172.19.0.15]:33430
ESTAB      11     0      [::ffff:172.19.0.12]:8888    [::ffff:172.19.0.15]:33458
ESTAB      11     0      [::ffff:172.19.0.12]:8888    [::ffff:172.19.0.15]:33482
SYN-RECV   0      0      [::ffff:172.19.0.12]:8888    [::ffff:172.19.0.15]:33512
ESTAB      11     0      [::ffff:172.19.0.12]:8888    [::ffff:172.19.0.15]:33442
ESTAB      11     0      [::ffff:172.19.0.12]:8888    [::ffff:172.19.0.15]:33428
ESTAB      11     0      [::ffff:172.19.0.12]:8888    [::ffff:172.19.0.15]:33472
SYN-RECV   0      0      [::ffff:172.19.0.12]:8888    [::ffff:172.19.0.15]:33496
```
查看抓包结果可以看到 SYN-ACK 包重传。
![](https://pub-08b57ed9c8ce4fadab4077a9d577e857.r2.dev/tcp-syn-queue-03.png)

全连接队列的实验就到这里，下面我们来看半连接队列的实验。

## 半连接队列实战

半连接队列的最大长度计算有些麻烦，网络上资料也很繁杂，本着 **talk is cheap, show me the code** 的原则，这里还是直接看 Linux 的源码来分析，还是 tcp_conn_request 函数。

```c
// 源码地址：https://elixir.bootlin.com/linux/v5.15.130/source/net/ipv4/tcp_input.c#L6848

int tcp_conn_request(struct request_sock_ops *rsk_ops,
		     const struct tcp_request_sock_ops *af_ops,
		     struct sock *sk, struct sk_buff *skb)
{
   // ... 代码省略
	u8 syncookies;

  // 第一部分，基于 syncookies 和半连接队列是否超过全连接队列长度、半连接队列是否已满来判断是否 drop
	syncookies = READ_ONCE(net->ipv4.sysctl_tcp_syncookies);

	if ((syncookies == 2 || inet_csk_reqsk_queue_is_full(sk)) && !isn) {
		want_cookie = tcp_syn_flood_action(sk, rsk_ops->slab_name);
		if (!want_cookie)
			goto drop;
	}

	// 第二部分，判断全连接队列是否已满
	if (sk_acceptq_is_full(sk)) {
		NET_INC_STATS(sock_net(sk), LINUX_MIB_LISTENOVERFLOWS);
		goto drop;
	}

	req = inet_reqsk_alloc(rsk_ops, sk, !want_cookie);
	if (!req)
		goto drop;

// ... 代码省略

	if (!want_cookie && !isn) {
    // 获取系统参数 ``net.ipv4.tcp_max_syn_backlog`` 的值
		int max_syn_backlog = READ_ONCE(net->ipv4.sysctl_max_syn_backlog);

		/* Kill the following clause, if you dislike this way. */
    // 第三部分：判断半连接队列是否超过长度限制
		if (!syncookies &&
		    (max_syn_backlog - inet_csk_reqsk_queue_len(sk) <
		     (max_syn_backlog >> 2)) &&
		    !tcp_peer_is_proven(req, dst)) {
			/* Without syncookies last quarter of
			 * backlog is filled with destinations,
			 * proven to be alive.
			 * It means that we continue to communicate
			 * to destinations, already remembered
			 * to the moment of synflood.
			 */
			pr_drop_req(req, ntohs(tcp_hdr(skb)->source),
				    rsk_ops->family);
			goto drop_and_release;
		}

		isn = af_ops->init_seq(skb);
	}

	tcp_ecn_create_request(req, skb, sk, dst);

	if (want_cookie) {
		isn = cookie_init_sequence(af_ops, sk, skb, &req->mss);
		if (!tmp_opt.tstamp_ok)
			inet_rsk(req)->ecn_ok = 0;
	}

	return 0;

}
```

核心计算逻辑是 `` (max_syn_backlog - inet_csk_reqsk_queue_len(sk) < (max_syn_backlog >> 2))``，即 max_syn_backlog 的值减去当前半连接队列的长度的值小于 max_syn_backlog 的 1/4 时，就会将 SYN 包丢弃。简单来说就是半连接队列长度不能超过 max_syn_backlog 的 3/4。因为比较条件是 > 而不是 >=，所以在不开启 syncookies 的情况下，实际的半连接队列长度应该是 max_syn_backlog 的 3/4 + 1。大致计算如下：

- max_syn_backlog 为 128，则半连接队列长度最大为 97
- max_syn_backlog 为 256，则半连接队列长度最大为 193
- max_syn_backlog 为 512，则半连接队列长度最大为 385
- max_syn_backlog 为 1024，则半连接队列长度最大为 769

结合上面全连接实验中的代码分析，我们可以总结下 Linux 5.15.30 内核下 SYN 包的 Drop 机制：

![](https://pub-08b57ed9c8ce4fadab4077a9d577e857.r2.dev/linux-syn-queue.drawio.png)

我们修改参数验证下上述三种情况。

### 实验一：关闭 syncookies，半连接长度超过全连接最大长度

客户端我们使用 iptables 将服务端的包拦截，模拟 SYN Flood 攻击，这样服务端不会收到 ACK 包，也就不会进入全连接队列。系统参数 syn_cookies=0，max_syn_backlog=128，somaxconn=64，理论上会有 64 个 SYN-RECV 状态连接，其余的包被丢弃。

```bash
# 拦截服务端 8888 端口的包
$ sudo iptables -A INPUT -p tcp --sport 8888 -j DROP

# 发送 SYN 包
$ sudo hping3 -S 172.19.0.12 -p 8888 --flood
```
查看服务端情况

```bash
$ ss -ant | grep -E "Recv|8888"
State     Recv-Q Send-Q        Local Address:Port            Peer Address:Port Process
LISTEN    0      64                        *:8888                       *:*

# ubuntu @ node2 in ~ [11:58:11]
$ sudo netstat -nat | grep :8888 | grep SYN_RECV  | wc -l
64
```

结果符合预期。这里可以用 go 客户端做更精确的验证，我们使用 Go 程序发送 100 个请求，然后查看服务端连接数和 DROP 数

```bash
$ date;netstat -s | grep -i "SYNs to LISTEN"
Fri Feb 21 12:01:58 PM CST 2025
    3030591019 SYNs to LISTEN sockets dropped

$ sudo netstat -nat | grep :8888 | grep SYN_RECV  | wc -l
64

$ date;netstat -s | grep -i "SYNs to LISTEN"
Fri Feb 21 12:02:14 PM CST 2025
    3030591127 SYNs to LISTEN sockets dropped

```

可以看到服务端只有 64 个 SYN-RECV 状态连接，程序执行有有 3030591127-3030591019=108 个 SYN 包被丢弃。上面我们分析过，因为客户端设置了超时时间为 5s，所以 SYN 只会重传 2 次，也就是每个被 DROP 的连接都会发送 3 次 SYN。100 - 64 = 36，36 * 3 = 108，符合我们预期。

### 实验二：关闭 syncookies，全连接队列已满

修改服务端系统参数 syn_cookies=0，max_syn_backlog=128，somaxconn=64，这样全连接队列最大长度为 64，当有 65 个连接建立时，全连接队列就会满，此时再有 SYN 包建立连接时就会被丢弃。

首先我们清理掉客户端机器的 iptables 规则，是的三次握手能够正常进程。

```bash
$ sudo iptables -F
```

设置系统参数

```bash
$ sudo sysctl -w net.ipv4.tcp_syncookies=0
$ sudo sysctl -w net.ipv4.tcp_max_syn_backlog=128
$ sudo sysctl -w net.core.somaxconn=64
```
我们再次用 Go 客户端发送 100 个请求，然后查看服务端状态，可以看到有 65 个 ESTAB 状态连接，没有 SYN-RECV 状态连接，因为全连接队列已满，所有 SYN 包都会被丢弃。

```bash
$ ss -ant | grep -E "Recv|8888"
State     Recv-Q Send-Q        Local Address:Port            Peer Address:Port Process
LISTEN    65     64                        *:8888


$ sudo netstat -nat | grep :8888 | grep ESTAB  | wc -l
65


# ubuntu @ node2 in ~ [12:18:27] C:130
$ sudo netstat -nat | grep :8888 | grep SYN_RECV  | wc -l
0
```

按照以上逻辑，会有 35 个连接被拒绝，一共有 35 * 3 = 105 个 SYN 包被丢弃。我们查看统计信息可以验证，3030591766 - 3030591661 = 105，符合预期。

```bash
$ date;netstat -s | grep -i "SYNs to LISTEN"
Fri Feb 21 12:18:19 PM CST 2025
    3030591661 SYNs to LISTEN sockets dropped

# ubuntu @ node2 in ~ [12:18:19]
$ date;netstat -s | grep -i "SYNs to LISTEN"
Fri Feb 21 12:18:34 PM CST 2025
    3030591766 SYNs to LISTEN sockets dropped
```

### 实验三：关闭 syncookies，半连接队列长度超过 max_syn_backlog 的 3/4

现在我们将全连接队列长度调大 ``net.core.somaxconn`` 设置为 4096，使用 iptables 拦截服务端 8888 端口的包，这样全连接队列始终不会填满，然后 max_syn_backlog 分别设置为：

  
- 128，预期有 97 个 SYN-RECV 状态连接
- 256，预期有 193 个 SYN-RECV 状态连接
- 512，预期有 385 个 SYN-RECV 状态连接
- 1024，预期有 769 个 SYN-RECV 状态连接

分别设置并发送请求后，服务端显示结果如下，基本符合预期。

```bash
# 客户端设置 iptables 拦截服务端
sudo iptables -A INPUT -p tcp --sport 8888 -j DROP

# 服务端查看 SYN-RECV 状态连接数
$ sudo sysctl -w net.ipv4.tcp_max_syn_backlog=128
$ ss -ant | grep -E "Recv|:8888" | grep SYN-RECV | wc -l
97

$ sudo sysctl -w net.ipv4.tcp_max_syn_backlog=256
$ ss -ant | grep -E "Recv|:8888" | grep SYN-RECV | wc -l
193

$ sudo sysctl -w net.ipv4.tcp_max_syn_backlog=512
$ ss -ant | grep -E "Recv|:8888" | grep SYN-RECV | wc -l
385

$ sudo sysctl -w net.ipv4.tcp_max_syn_backlog=1024
$ ss -ant | grep -E "Recv|:8888" | grep SYN-RECV | wc -l
769
```

执行过程数值会有变化，但最大半连接队列长度符合预期。



### 实验四：开启 syncookies，半连接队列长度取决于 max(somaxconn, backlog)

当开启 syncookies 时，半连接队列不在保留 1/4 的限制，而是取决于 max(somaxconn, backlog)。这里源码判断是 >=，因此最大长度应该会等于 max(somaxconn, backlog)

```c
// 源码地址：https://elixir.bootlin.com/linux/v5.15.130/source/include/net/inet_connection_sock.h#L280
static inline int inet_csk_reqsk_queue_is_full(const struct sock *sk)
{
	return inet_csk_reqsk_queue_len(sk) >= sk->sk_max_ack_backlog;
}
```

我们分别设置 ``net.core.somaxconn`` 为 512，1024，4096并设置 ``net.ipv4.tcp_syncookies=1`` 开启 syncookies，每次设置完重启服务端，然后在发起请求，理论上会有 512，1024，4096 个 SYN-RECV 状态连接。 



修改服务端 somaxconn 并重启后，使用 watch 命令查看 SYN-RECV 状态连接数，结果如下，符合预期。

```bash
$ watch -n 1 "netstat -nat | grep :8888 | grep SYN_RECV | wc -l"
Every 1.0s: netstat -nat | grep :8888 | grep SYN_RECV | wc -l              node2: Sat Mar  1 15:07:22 2025

512

$ watch -n 1 "netstat -nat | grep :8888 | grep SYN_RECV | wc -l"
Every 1.0s: netstat -nat | grep :8888 | grep SYN_RECV | wc -l              node2: Sat Mar  1 15:08:15 2025

1024

$ watch -n 1 "netstat -nat | grep :8888 | grep SYN_RECV | wc -l"
Every 1.0s: netstat -nat | grep :8888 | grep SYN_RECV | wc -l              node2: Sat Mar  1 15:09:11 2025

4096

```
## 简要总结

- 半连接队列受限于全连接队列长度，而全连接队列会受应用的影响，尽量不要将 somaxconn 设置的过小，否则会影响服务器的性能。
- 尽量开启 syncookies，可以有效防止 SYN Flood 攻击，同时可以避免半连接队列被大量占用。
- ss、netstat 的熟练使用对探查网络状态非常重要，要熟练掌握。
- 代码之下无秘密，一定要结合源码去理解 Linux 的网络工作机制，不要只是死记硬背协议。
- 动手！动手！动手！实践出真知。
