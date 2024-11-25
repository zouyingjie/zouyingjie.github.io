---
title: 【资料推荐】Linux 网络扫盲帖
date: 2024-11-25T11:30:42+08:00
tags:
  - Linux
  - Network
categories:
  - Linux

---

之前为了学习 Kubernetes 网络，需要对 Linux 网络有一个比较全面的了解。这里推荐一些学习过程中觉得不错的资料，可以帮助有需要的同学快速入门。

1. [# Introduction to Linux interfaces for virtual networking](https://developers.redhat.com/blog/2018/10/22/introduction-to-linux-interfaces-for-virtual-networking#ifb)

介绍了 Linux 中常用的网络概念，比如 bridge 网桥、veth 对、VLAN & VXLAN、MACVLAN 等，可以帮助自己对这些概念做一个快速的了解。

2. [# An introduction to Linux virtual interfaces: Tunnels](https://developers.redhat.com/blog/2019/05/17/an-introduction-to-linux-virtual-interfaces-tunnels#summary)

算是上一篇文章的姊妹篇，主要介绍了 Linux 网络隧道相关的知识点。简单来说，隧道本质上都是在 IP 包里带上另外一个包，这个包可能是另一个 IP 包，也可能是 UDP 或者其他包，传输时通过外层的 IP 做路由，到达目的地后再解析出内部的包在做一次路由。

3. [VXLAN & Linux](https://vincent.bernat.ch/en/blog/2017-vxlan-linux)

一篇介绍 VXLAN 的文章，可以帮助自己对 VXLAN 有更好的理解。

4. [How Container Networking Works: a Docker Bridge Network From Scratch](https://labs.iximiuz.com/tutorials/container-networking-from-scratch)

前三篇算是对 Linux 网络的一个扫盲，有了这些基础知识再看现在的容器和 Kubernetes 网络，就会发现都是上述基础知识的运用。这些硬核基础知识始终应该是我们学习的重点。

这一篇是非常详细的介绍容器网络，尤其是其提供了在线的 Playground 帮助自己边读边练，手把手创建网桥设备、veth 以及配置 iptables。文章读完，自己也跟着手把手将容器网络实现了。

5. [容器网络与生态](https://icyfenix.cn/immutable-infrastructure/network/cni.html)

周志明老师《凤凰架构》一书中的章节，对容器网络的技术做了整体性的梳理，可以看到上面文章中提到的技术是如何应用在容器网络中的。
