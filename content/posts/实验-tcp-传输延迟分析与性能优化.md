---
title: "【动手实验】TCP 传输延迟分析与性能优化"
date: 2025-07-23T10:52:02+08:00
draft: true
tags:
  - TCP
  - 动手实验
  - 性能优化
categories:
  - 计算机网络
source: "https://blog.csdn.net/Ahri_J/article/details/149564241"
---
### 问题

这是 [xintao](https://x.com/laixintao?lang=en) 老师在其[计算机网络实用技术](https://www.kawabangga.com/posts/6097)专栏里提出的一个问题（墙裂推荐这个专栏）。

有 A 和 B 两个服务位于两个 IDC 中，A 服务需要访问 B 服务的
 HTTP
 接口。A 到 B 之间 ping 延迟为 200ms，B 服务的固定处理时间为 100ms。基于如下条件，计算 A 请求 B 的延迟是多少。

- TCP 需要重新建立连接
- 请求的大小是 16KiB
- 响应的大小是 20KiB

![](https://i-blog.csdnimg.cn/img_convert/a59b929f259af175878aa75fce238cb6.png)

### 原始抓包分析

笔者读文章时初步分析的结果是 500ms，理由如下：

- 建立连接耗时 200ms。这是第 1/2 次握手完成的延迟，客户端在响应第三次握手后会立即发送数据，因此第三次握手不占用延迟。
- B 服务处理请求耗时 100ms。
- 响应数据从 B 服务返回到 A 服务耗时 200ms。

因此整体延迟为 200 + 100 + 200 = 500ms。

接下来我们看下 [原blog](https://www.kawabangga.com/posts/6372) 中给出的抓包文件：

![](https://i-blog.csdnimg.cn/img_convert/7ba8658f43cd369e535dfdb114f1bd9d.png)

可以看到数据在 0.905 秒时传输完成后，服务端向
 客户端
发出了 FIN 包，整体耗时约为 900ms，我们来分析下原因。基于之前的实验，我们知道 TCP 数据传的慢可能有三个原因：

- 发得慢
- 传的慢（网络环境，拥塞控制）
- 收的慢

在这个实验中，并没有提到 A 和 B 的服务端问题，并且数据量不大，因此可以排除发和收的问题，初步可以认为是传的慢导致的，由此可以推测是拥塞控制问题。

TCP 为了避免一次性发送的数据过多，会采用 Slow Start 慢启动机制，一次性发送的数据不会超过 CWND（拥塞窗口）的限制。Linux 下默认 CWND 大小为 10 个 MSS（最大报文段长度），从抓包文件中可以看到 MSS 为 1460 字节，则 CWND 大小为 14600 字节约等于 14.6 KB，因此在初始阶段 A 和 B 最多只能一次性发送 14.25KB 的数据，超过了 A 的 16KB 和 B 的 20KB 的数据量，需要分多次发送。因此 A 和 B 都需要分两次发送数据，
 数据传输
会占用 2 个 RTT。由此可以推测出整体延迟为：

- TCP 连接建立耗时 200ms
- A 发送数据，耗时 2 个 RTT，即 2 * 200ms = 400ms
- B 处理请求，耗时 100ms
- B 响应数据，耗时 2 个 RTT，即 2 * 200ms = 400ms

理论上计算为 200 + 400 + 100 + 400 = 1100ms。但这里有一个误区，响应和数据发送是可以并行的。A 的第二次发送和 B 的第一次数据响应只占用一个 RTT，即 B 在确认 A 的第二次数据发送时，也顺带完成了数据发送。

这里我们通过传输流来分析下：

![](https://i-blog.csdnimg.cn/img_convert/6814efdbd46f941f7d7386410c6dd86f.png)

-
1. TCP 在 0.2 秒时收到服务端 ACK 后响应第三次握手（0.201s），并在 0.202s 开始发送数据，这里耗时 **200ms**。
-
1. 0.202 ~ 0.203s 间，A 发送了 10 个包，每个数据大小为 1448，数据总量为 14480 字节，接近 CWND 大小，符合慢启动特性。
-
1. 0.402s 收到服务端 ACK，这里完成第一次数据发送，耗时 **200ms。**
-
1. 收到 ACK 后，A 在 0.402s 立即继续发送剩余数据，并在 0.602s 收到服务端 ACK，完成第二次数据发送，耗时 **200ms。**
-
1. 0.602s ~ 0.702s 间，B 服务处理请求，耗时 **100ms。**
-
1. 0.705s B 服务开始响应数据，连续发送若干数据包。
-
1. 收到 ACK 后再 0.905s 再次发送若干数据，完成后发送 FIN 包，耗时 **200ms。**

因此总时长为 200 + 400 + 100 + 200 = 900ms。

#### 场景复现 & 性能优化

这里我们使用 Linux tc 来模拟网络延迟复现上述的实验场景并进行性能优化。

- 服务端设置

```
# 设置 200ms 的延迟
tc qdisc add dev eth0 root netem delay 200ms

# 设置网卡 mtu 为 1500（服务端、客户端都要设置）
sudo ip link set dev eth0 mtu 1500
```

- 服务端程序

```python
from http.server import BaseHTTPRequestHandler, HTTPServer
import time

class SimpleHandler(BaseHTTPRequestHandler):
    def do_POST(self)
```
