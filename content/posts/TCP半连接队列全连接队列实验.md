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

## 全连接半连接队列
在 TCP 三次握手过程中，Linux 会维护两个队列分别是：

- SYN Queue 半连接队列
- Accept Queue 全连接队列

三次握手过程中，两个队列作用如下：

- 客户端向服务端发送 SYN 包，客户端进入 SYN_SENT 状态
- 服务端收到 SYN 包后，进入 SYN_RECV 状态，内核将连接信息放入 SYN Queue 队列，然后向客户端发送 SYN+ACK 包
- 客户端收到 SYN-ACK 包后，发送 ACK 包，客户端进入 ESTABLISHED 状态
- 服务端收到 ACK 包后，将连接从 SYN Queue 队列中取出移到 Accept Queue 队列，Server 端进入 ESTABLISHED。
- 服务端应用程序调用 accept 函数处理数据，连接从 accept 队列移除。

![](https://pub-08b57ed9c8ce4fadab4077a9d577e857.r2.dev/tcp-synqueue-01.jpg)
图片来自：[从一次线上问题说起，详解 TCP 半连接队列、全连接队列
](https://www.51cto.com/article/687595.html)



## 全连接队列实战

### 全连接队列长度控制

TCP 半连接队列的长度计算公式为：

> min(somaxconn, backlog)

- **somaxconn** 是 Linux 内核参数 ``net.core.somaxconn`` ，默认值为 4096。
- **backlog** 是 listen 函数 ``int listen(int sockfd, int backlog)`` 的 backlog 参数。在 Golang 中使用的就是该陈述的值。

下面我们修改 somaxconn 的值，然后运行实验代码查看全连接队列的情况。

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

1. 服务端 Listen 状态的 socket 显示 Send-Q 为 5，表示该 socket 的全连接队列最大值为 5；Recv-Q 为 6，表示当前 accept queue 数量为 6，我们看有 6 条 ESTAB 状态的连接，符合观察结果。Linux 内核的判断依据是 > 而不是 >=，所以实际的连接数为比队列的最大值多 1 个。5.15.0-130-generic 内核代码如下：

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

2. 客户端有 6 个 ESTAB 状态的 socket，另外还有 4 个 SYN-SENT 状态的 socket，客户端报错 timeout。我们只改了全连接队列大小为 5，半连接队列大小依然为默认的 ``net.ipv4.tcp_max_syn_backlog=256``，所以第 6 个请连接建立后 Accept Queue 就满了，但 SYN Queue 还没有满，按理说从第 7 个请求开始服务端可以接收 SYN 但不能在处理客户端的 ACK 进入 Accept Queue，服务端会有 4 条 SYN-RECV 状态的连接。但实际情况是服务端不存在，因为当 Accept Queue 被占满时，即使 SYN Queue 没有满，Linux 内核也会将新来的 SYN 请求丢弃掉。源码如下：

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
```
从代码中可以推测出 ``net.ipv4.tcp_syncookies`` 参数值的含义和 Linux 的处理机制：

- 2：强制开启 SYN Cookie 机制，发送警告
- 1：当半连接队列满时，开启 SYN Cookie 机制，发送警告
- 0：不开启 SYN Cookie 机制，并统计丢弃包的数量

回到我们的实验环境，``net.ipv4.tcp_syncookies`` 设置为 1 并且半连接队列没满，因此不会开启 SYN Cookie 机器，继续往后执行时会因为 Accept Queue 满了将包丢弃。可以通过 ``netstat -s`` 命令查看丢弃包的数量。

```bash
$ date;netstat -s | grep -i "SYNs to LISTEN"
Wed Feb 19 12:05:51 PM CST 2025
    1289 SYNs to LISTEN sockets dropped


$ date;netstat -s | grep -i "SYNs to LISTEN"
Wed Feb 19 12:06:05 PM CST 2025
    1301 SYNs to LISTEN sockets dropped
```

可以看到有 12 个 SYN 包被 DROP 了，查看抓包情况可以看到，我们 4 个请求连接超时，每个请求传了 3 次 SYN（一次发起 + 两次重传）。

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

3. 服务端 6 条 ESTAB 状态的 socket，RECV_Q 的值为 11，与客户端发送的数据 ``[]byte("hello world")`` 数据长度一致，因为我们的没有执行 accept 接收数据，所以 RECV_Q 会展示这部分数据的大小；
4. 客户端 6 条 ESTAB 状态的 socket，其 RECV_Q 和 SEND_Q 均为 0；而 4 条 SYN-SENT 状态的 SEND-Q 为 1，是因为 SYN 包没有收到 ACK 包。由此我们可以再次总结下 ss 的展示含义：

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

## 半连接队列实战
