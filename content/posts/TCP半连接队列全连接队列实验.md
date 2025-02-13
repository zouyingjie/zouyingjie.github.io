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

## 全连接队列实战

### 全连接队列长度控制

TCP 半连接队列的长度计算公式为：

> min(somaxconn, backlog)

- **somaxconn** 是系统内核参数 ``net.core.somaxconn`` ，默认值为 4096
- **backlog** 是 TCP 的 listen 函数 ``int listen(int sockfd, int backlog)`` 的 backlog 参数。在 Golang 中使用的就是 net.core.somaxconn 的值。

下面我们修改 somaxconn 的值，启动服务后使用 ``ss -lnt`` 命令查看全连接队列的长度。下面是实验代码：

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

- 对于 Listen 状态的 socket，Recv-Q 表示当前全连接队列的长度，也就是已经完成三次握手，等待应用层调用 accept 的 TCP 连接；Send-Q 表示全连接队列的最大长度。
- 对于非 Listen 状态的 socket，Recv-Q 表示已经收到但尚未被应用读取的**字节数**；Send-Q 表示已发送但尚未收到确认的字节数。

再次修改 somaxconn 为 1024 重启服务后，查看全连接队列的长度：

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

下面我们让服务端只 Listen 端口但不执行 accept() 处理连接，看看全连接队列溢出时会发生什么。

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

为了验证全队列溢出，我们先将全连接队列的最大长度设置为 5：

```bash
$ sudo sysctl -w net.core.somaxconn=5

$ cat /proc/sys/net/core/somaxconn
5
```
运行服务端和客户端后，实验结果付下：


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

## 半连接队列实战
