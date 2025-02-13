---
title: 【资料推荐】一些学习iptables的优质材料
date: 2023-09-02 09:17:14
tags:
- 资料推荐
- 计算机网络
categories:
- 计算机网络
- 资料推荐
description: 推荐一些学习 iptables 的优质材料，包括入门介绍、深入原理、NAT 等。

---

iptables 是 Linux 下的一个非常重要的网络包过滤工具，可以用来配置防火墙、NAT 等。学习 iptables 有助于理解网络包的传输过程、网络安全等。Kubernetes 在 1.31 版本中引入 nfttables 前，也使用 iptables 作为 kube-proxy 的实现。

iptables 的原理和使用方法网上有很多资料，这里推荐一些个人觉得不错的材料。

1. [Illustrated introduction to Linux iptables](https://iximiuz.com/en/posts/laymans-iptables-101/)

一篇非常好的介绍 iptables 的入门文章，给出了大量的图例帮助理解。比如 iptables 是基于 netfilter 的 hook 点工作的。文章给出的图示非常直观的将 5 个 hook 的生效位置展现了出来。

![](https://iximiuz.com/laymans-iptables-101/iptables-stages-white.png)


2. [A Deep Dive into Iptables and Netfilter Architecture](https://www.digitalocean.com/community/tutorials/a-deep-dive-into-iptables-and-netfilter-architecture)

这篇文章讲的更细致一些，对表的功能、优先级、规则做了比较全面的介绍，非常浅显易懂。读英文觉得困难的话也可以看这篇译文 [(译)深入理解 iptables 和 netfilter 架构](https://arthurchiao.art/blog/deep-dive-into-iptables-and-netfilter-arch-zh/)。

读完上述两篇文章，对 iptables 就能有个基本的理解了。

简单来说，iptables 就是使用 netfilter 提供的 hook 点来注册 IP 包的处理规则， iptables 基于功能（过滤、地址转换、修改包、追踪、安全）将这些规则组织成了不同的表。

每个表有若干个规则链，iptables 默认有 5 种链，对应 netfilter 的 5 个 hook 点。在某个表的某个链上添加规则，本质上就是在链对应的 hook 点注册规则。如果多个表在同一个链上注册规则，则基于表的优先级生效。

结合包的传输顺序、表的作用点和优先级，就形成了文章中的二维表格：

![alt text](https://pub-08b57ed9c8ce4fadab4077a9d577e857.r2.dev/iptables-001.png)

Tables 列有由上到下代表的 table 的执行顺序，由此我们可以得出处理网络包时，iptables 规则执行顺序：

- 发送到本机的包：`PREROUTING(raw, mangle, dnat)` -> `INPUT(mangle, filter, security, snat)`
- 本机路由到其他机器的包：`PREROUTING(raw, mangle, dnat)` -> `FORWARD(mangle, filter, security)` -> `POSTROUTING(mangle, snat)`
- 本地发送到其他机器的包：`OUTPUT(raw, mangle, dnat, filter, security)` -> `POSTROUTING（mangle, snat）`

理解了上述内容，在看下面这张经典的配图就不至于头大了。

![alt text](https://pub-08b57ed9c8ce4fadab4077a9d577e857.r2.dev/iptables-002.png)


3. [Network Address Translation](https://www.karlrupp.net/en/computer/nat_tutorial)

这篇文章对 iptables 中的 NAT 做了更细致的讲解。也可以看这篇译文 [(译)# NAT - 网络地址转换](https://arthurchiao.art/blog/nat-zh/)。


4. [iptables 快速入门系列文章](https://www.zsythink.net/archives/tag/iptables/)

国内一位技术人员写的一系列关于 iptables 的文章，有十几篇，从基础到进阶都有涉及，通俗易懂的介绍了 iptables 的概念、命令、用法，非常值得一读。

