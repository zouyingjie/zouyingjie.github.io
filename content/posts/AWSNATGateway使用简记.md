---
title: "AWS NAT Gateway 使用简记"
description: AWS NAT 网关介绍以及使用方式简介
date: 2024-10-30T14:34:37+08:00
tags: 
- AWS
categories:
- AWS
---

最近项目遇到个需求，需要将后端的服务器出口统一成一个 IP，服务器在 AWS 上，这个可以用 AWS 的 NAT Gateway 实现，调研实施的过程中发现如果对 AWS 相关概念不熟悉的话会绕点路的，这里简单整理下，希望对需要的小伙伴有帮助。

## 一. 相关概念简介

### 1. NAT Gateway

[NAT Gateway（网络地址转换网关）](https://docs.aws.amazon.com/zh_cn/vpc/latest/userguide/vpc-nat-gateway.html) 主要用来对一组私有子网内的服务器进行代理，被代理的所有服务器的对外请求都将通过 NAT 网关发出，这样目标服务所看到的请求 IP 也都是 NAT 网关的 IP。这么做有两个好处：

- 应用服务器只能在内网访问，提高了安全性
- 如果要访问的服务存在 IP 白名单的话，只需要将 NAT 网关的 IP 加进去即可，不需要挨个添加服务器地址。（自己之前和一家公司对接数据接口，对方就有 IP 白名单，当时没有统一网关导致添加了 20 几个 IP，一旦服务器 IP 变了还得重加，都是泪。。。）

下图是 AWS 官网中给出一个包含 NAT 网关的 VPC 架构图：

![](https://pub-08b57ed9c8ce4fadab4077a9d577e857.r2.dev/f12bafc7ea70604f0f453de38612a21c.png)

简单讲解一下，在 10.0.0.0 VPC 下有两个子网：公共子网 ``10.0.0.0/24`` 和 私有子网 ``10.0.1.0/24``。NAT 网关位于公共子网中，因此可以访问公网。私有子网的三台机器连接到了 NAT 网关，对公网的访问全部通过 NAT 网关实现。

***公共子网与私有子网***

AWS 的 VPC 网络配置关系是：***实例与子网关联，子网关联路由表，路由表设置网关***。所谓公共子网就是其对应的路由表中配置了规则将请求路由到了 ``Internet Gateway``，这样公共子网内的服务器实例、NAT 网关就可以对外访问。而私有子网就是其关联的路由表中没有配置到 ``Internet Gatway`` 的路由规则，因此无法对外访问。

清楚了公共子网、私有子网的概念，就可以进行 NAT 网关的相关设置了。私有子网中的服务器通过 NAT 网关对外访问需要做下面几步操作：

- VPC 下创建公共子网和私有子网
- 在私有子网中开通服务器实例
- 在公共子网中开通 NAT 网关和登陆到私有服务器的跳板机
- 修改私有子网的路由表规则，配置路由地址到 NAT 网关
- 执行测试。

下面是具体的操作，

## 二. NAT 网关设置

### 1. 设置私有子网

上面提到，AWS 中网络配置的关系：`实例与子网关联，子网关联路由表，路由表设置网关`。我在 AWS 香港地区有三个子网如下

![](https://pub-08b57ed9c8ce4fadab4077a9d577e857.r2.dev/aws-nat-blog-01.png)

所有子网的默认路由表配置一般都是指向了 ``Internet Gateway``，如图所示：

![](https://pub-08b57ed9c8ce4fadab4077a9d577e857.r2.dev/aws-nat-blog-02.png)

图中 ``0.0.0.0/0`` 的规则就表示将所有的请求路由到默认的 ``Internet Gateway``，从而可以与公网通信。为了将使得子网变为私有，我们需要自己新建路由表，并将指向 ``Internet Gateway`` 的路由规则给去掉，这样子网就无法直接访问公网了。如图所示：

- 创建路由表

![](https://pub-08b57ed9c8ce4fadab4077a9d577e857.r2.dev/aws-nat-blog-03.png)

![](https://pub-08b57ed9c8ce4fadab4077a9d577e857.r2.dev/aws-nat-blog-04.png)


- 修改子网关联

可以看到新建好的路由表并没有关联子网，点击 ``编辑子网关联`` 将 ``subnet-1f2a2767`` 子网关联上，这样这个子网下的服务器就无法和公网通信了。

![](https://pub-08b57ed9c8ce4fadab4077a9d577e857.r2.dev/aws-nat-blog-05.png)

![](https://pub-08b57ed9c8ce4fadab4077a9d577e857.r2.dev/aws-nat-blog-06.png)

### 2. 创建私有服务器与跳板机

我选择第上面关联到自定义路由表的自我一个子网 ``subnet-1f2a2767`` 作为私有子网，第二个 f500f 作为公有子网。在私有子网下开了两台服务器，在公有子网下设置了一台服务器作为跳板机，步骤如下，注意在 「配置示例」模块选择对应的子网，并将在私有子网中的服务器禁用公网 IP。

- 选择服务器

![01](https://pub-08b57ed9c8ce4fadab4077a9d577e857.r2.dev/aws-nat-blog-07.png)

![02](https://pub-08b57ed9c8ce4fadab4077a9d577e857.r2.dev/aws-nat-blog-08.png)

- 选择子网，启动实例。

![03](https://pub-08b57ed9c8ce4fadab4077a9d577e857.r2.dev/aws-nat-blog-09.png)

此时子网中的两台服务器是无法与公网通信的。跳板机的创建也是上面的步骤，只是要选择公共子网并设置公网 IP，这里不再赘述。

### 3. 创建 NAT 网关

在 AWS 的 VPC 控制面板，选择 「NAT 网关」，点击创建，需要选择子网，这里一定要选择公共子网，保证 NAT 网关是可以与公网通信。

- 创建 NAT 网关，选择公共子网并分配 IP

![](https://pub-08b57ed9c8ce4fadab4077a9d577e857.r2.dev/aws-nat-blog-10.png)

![](https://pub-08b57ed9c8ce4fadab4077a9d577e857.r2.dev/aws-nat-blog-11.png)


可以看到创建的 NAT 网关 IP 为 ``18.162.217.123``，待 NAT 网关的状态变为可用之后就可以修改路由表，将子网中的请求路由到 NAT 网关了。

### 4. 修改私有子网的路由表

创建完成 NAT 网关之后，修改我们自己创建的私有子网的路由表，将子网中所有的请求路由到 NAT 网关了。如图：

- 选择之前新建的路由表，选择「编辑路由」
![](https://pub-08b57ed9c8ce4fadab4077a9d577e857.r2.dev/aws-nat-blog-12.png)

- 第一栏目标设置为 ``0.0.0.0/0`` 表示除第一条外所有的请求都路由向设置的网关，第二栏目标选择 NAT 网关，就会出现可选的 NAT 网关列表
![](https://pub-08b57ed9c8ce4fadab4077a9d577e857.r2.dev/aws-nat-blog-13.png)

- 选择上面新建的 NAT 网关

![](https://pub-08b57ed9c8ce4fadab4077a9d577e857.r2.dev/aws-nat-blog-14.png)

### 5. 测试网络

默认情况下，私有网络内的服务器是无法访问公网的，可以先用 ping 或者 curl 命令试下。配置完成之后就可以测试我们的私网服务器是否可以与外界通信了，我在腾讯云开了一台新的服务器并运行了 Nginx，访问情况如下：


![](https://pub-08b57ed9c8ce4fadab4077a9d577e857.r2.dev/aws-nat-blog-15.png)

可以看到私网内的服务器可以访问其他网络内的服务器了，然后看下腾讯云上的 Nginx 日志，如下：

![](https://pub-08b57ed9c8ce4fadab4077a9d577e857.r2.dev/aws-nat-blog-16.png)

日志中请求的源 IP 为 ``18.162.217.123``，是我们设置的 NAT 网关的 IP 地址，由此通过 NAT 网关实现私有子网内服务器对外统一访问的设置就完成了。

