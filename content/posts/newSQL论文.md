---
title: 【读点论文】What’s Really New with NewSQL?
date: 2025-01-10T21:07:27+08:00
tags:
- 读点论文
- 数据库
categories:
- 数据库
- 读点论文
description: 了解下NewSQL 发展历程
---

本篇论文是 2016 年 CMU 发表介绍 NewSQL 发展的一篇综述论文，论文主要对新兴的 NewSQL 数据库的起源、分类以及主要技术原理做了介绍，其中对数据库发展历史、NewSQL 实现原理的介绍非常值得一读。

## 数据库发展简史

论文首先简要梳理了数据库的发展历程。

**1. 1960 年代 ~ 1970 年代：数据库的诞生**

早在 1960 年代，IBM 为了支持阿波罗计划，开发了 IMS 来存储数据，引入了**代码与数据分离**的思想，让开发者可以专注于操作数据，无需关心这些操作的底层实现细节。

在之后的 1970 年代，作为关系型数据库的先驱，IBM 的 System R 和加州大学的 INGRES 数据库诞生，后者被其他大学广泛使用，并在之后被商业化。与此同时，Oracle 发布了其第一版的 DBMS。

**2. 1980-1990 年代：创新与开源**

1980 年代，IBM 发布了 DB2 数据库，与此同时还有 Sybase、Informix 等商业产品进入市场，推动着关系型数据库的普及。

在 1980 年代末、1990 年代初，有一股面向对象数据库设计的浪潮，旨在克服关系型数据库和面向对象编程语言之间的不匹配。虽然此类数据库没有成为主流，但在此过程中的许多技术创新为后来 XML 数据存储、对象存储以及 NoSQL 文档数据库的设计奠定了基础。

到了 1990 年代，开源数据库项目兴起，当前流行的 MySQL 和 PostgreSQL 数据库均在此期间诞生。

**3. 2000 年代：互联网推动数据库革新**

互联网迅猛发展，互联网应用对高并发和高可用的需求，让传统数据库成为瓶颈。虽然可以通过垂直扩展来解决，但这种方法存在局限性，并且从低配机器向高配机器迁移数据的成本也非常高。

为了克服这些限制，Google、eBay 等公司开始采用 middleware 中间件的方式，将多台机器上的单点数据库组合起来，通过 middleware 做代理，实现跨机器的操作，但这种方式对复杂的查询和事务支持有限，有时候开发者有时候需要自己来维护数据处理逻辑。像 eBay 的 middleware 组件就要求开发者自己实现相关的事务和复杂查询。

总的来看，现阶段的关系型数据库面临三个问题：

1. 关系型数据库的核心是 ACID，其关注重点在事务一致性和数据的正确性，而这是以可用性和性能为代价的。与互联网应用需要面对的高并发、高可用、高性能的需求不匹配。
2. 与互联网应用一起而来的还有海量的数据，使用像 MySQL 这样的数据库存储海量数据是非常不明智的选择。
3. 关系型数据库的数据建模和互联网应用所需的数据模型往往并不匹配，有时候需要更灵活、适配的建模方案。

以上问题最终催生了 NoSQL 数据库的诞生。

**4. NoSQL 的崛起**

NoSQL 数据库最大的特点就是放弃了对 ACID 强一致性的支持，转而追求最终一致性。数据模型也更加的灵活，比如可以是键值对、文档模型或者图数据库等

Google的 BigTable、Amazon 的 Dynamo，以及后来的 Cassandra、MongoDB、ElasticSearch 等开源产品都可以归类为 NoSQL 数据库。

**5. NoSQL 的局限与 NewSQL 的诞生**

NoSQL 数据库虽然解决了传统关系型数据库的很多问题，但同时也带来了新的问题。许多企业应用（如金融系统）要求必须做到强一致性，同时又需要 NoSQL 所带来的高性能、高可用、可扩展性。为此，结合了传统数据库的强一致性和 NoSQL 的高性能、高可用、可扩展特性的数据库应运而生，此类数据库被称为 NewSQL 数据库。

## NewSQL 的定义与分类

### NewSQL 的定义
论文中对 NewSQL 的定义如下：

> They are a class of modern relational DBMSs that seek to provide the same scalable performance of NoSQL for OLTP read-write workloads while still maintaining ACID guarantees for transactions.
> 它们是一类现代关系型 DBMS，旨在为 OLTP 读写工作负载提供与NoSQL相同的可扩展性能，同时仍然为事务保持ACID保证。

简单来书就是，NewSQL 既有传统关系型数据库的 ACID 保证，又兼具了 NoSQL 可扩展性。

还有一种更狭义的定义：

> 1. a lock-free concurrency control scheme and 
> 2. a shared-nothing distributed architecture [57]


NewSQL 大致可以分为三类：

- **New Architecture**：采用新的架构设计，从零开发的新数据库
- **Transparent Sharding Middleware**：基于中间件实现，对开发者透明
- **Cloud Database**：云厂商提供的 NewSQL 数据库

## New SQL 实现原理

这部分是论文的重点，对 NewSQL 相关的实现原理做了介绍。

