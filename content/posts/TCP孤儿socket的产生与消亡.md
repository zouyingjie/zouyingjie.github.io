---
title: 【动手实验】TCP orphan socket 的产生与消亡
date: 2023-09-02 09:17:14
tags:
  - TCP
  - 动手实验
categories:
  - TCP
  - 动手实验
description: 我是一只无人知道的 orphan socket。。。
---

在之前的 [TCP 连接的建立与关闭抓包分析]() 实验中有提到 orphan socket，当时对该类 socket 的产生和粗粒还有很多疑问没有解决，后续学习发现了两篇非常不错案例分析文章：

- [结合案例深入解析orphan socket产生与消亡（一）](https://developer.aliyun.com/article/91966)
- [结合案例深入解析orphan socket产生与消亡（二）](https://developer.aliyun.com/article/92925)

本篇是基于上述两篇文章的实践分析，借此深入了解 orphan socket 的产生和消除过程。

