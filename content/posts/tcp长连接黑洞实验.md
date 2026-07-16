---
title: 【动手实验】TCP 长连接黑洞的分析与解决
date: 2023-09-02 09:17:14
draft: true
tags:
  - 计算机网络
  - 动手实验
categories:
  - 计算机网络
  - 动手实验
description: 
---

### 1. TCP 长连接黑洞复现


#### 1. 实验环境

阿里云 99 大洋白嫖机。机器信息如下：

```bash
# 系统信息
Alibaba Cloud Linux 3.2104 LTS 64位

$ uname -a
$ uname -a
Linux t02 5.10.134-18.al8.x86_64 #1 SMP Fri Dec 13 16:56:53 CST 2024 x86_64 x86_64 x86_64 GNU/Linux
```
默认的一些系统参数如下：

```bash
$ sysctl -a |grep -E "retries"
net.ipv4.tcp_orphan_retries = 0
net.ipv4.tcp_retries1 = 3
net.ipv4.tcp_retries2 = 15 # 系统默认为 8，我们改成了 15 来复现实验
net.ipv4.tcp_syn_retries = 4
net.ipv4.tcp_synack_retries = 2
net.ipv4.vs.sync_retries = 0
net.ipv6.idgen_retries = 3
```


#### 2. LVS + MySQL 高可用切换



这里使用 LVS 代理两个 MySQL，我们模拟其中一个 MySQL 实例挂掉切换到另一个实例的场景。

1. docker 启动两个 MySQL 实例

```bash
docker run -d --name mysql2 -p 3307:3306 -e MYSQL_ROOT_PASSWORD=123 mysql:latest
docker run -d --name mysql1 -p 3306:3306 -e MYSQL_ROOT_PASSWORD=123 mysql:latest
```

我们分别在两个 MySQL 创建数据库并准备好压测相关的数据。

```sh
# 3306 节点
create DATABASE test CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
create DATABASE a3306 CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
sysbench --debug=on --mysql-user='root' --mysql-password='123' --mysql-db='test' --mysql-host='127.0.0.1' --mysql-port='3306' --tables='16'  --table-size='10000' --range-size='5' --db-ps-mode='disable' --skip-trx='on' --mysql-ignore-errors='all' --time='11080' --report-interval='1' --histogram='on' --threads=1 oltp_read_write prepare

# 3307 节点
create DATABASE test CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
create DATABASE a3307 CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
sysbench --debug=on --mysql-user='root' --mysql-password='123' --mysql-db='test' --mysql-host='127.0.0.1' --mysql-port='3307' --tables='16'  --table-size='10000' --range-size='5' --db-ps-mode='disable' --skip-trx='on' --mysql-ignore-errors='all' --time='11080' --report-interval='1' --histogram='on' --threads=1 oltp_read_write prepare
```


2. LVS 新建虚拟服务，代理 MySQL

下面是用到的一些脚本

```bash
// add.sh
// 创建虚拟服务器代理两个 MySQL 实例
ipvsadm -A -t 127.0.0.1:3001 -s rr
ipvsadm -a -t  127.0.0.1:3001 -r 127.0.0.1:3307 -m
ipvsadm -a -t  127.0.0.1:3001 -r 127.0.0.1:3306 -m
```


```bash
// 两个切换脚本，模拟一个 mysql 实例挂掉切换到另一个实例的情况
// del3306.sh: 3306 实例挂掉，切换到 3307
ipvsadm -d -t  127.0.0.1:3001 -r 127.0.0.1:3306 ; ipvsadm -a -t  127.0.0.1:3001 -r 127.0.0.1:3307 -m

// del3307.sh: 3307 实例挂掉，切换到 3306
ipvsadm -d -t  127.0.0.1:3001 -r 127.0.0.1:3307 ; ipvsadm -a -t  127.0.0.1:3001 -r 127.0.0.1:3306 -m
```

基于以上脚本我们可以模拟高可用切换的情况。

![](https://pub-08b57ed9c8ce4fadab4077a9d577e857.r2.dev/lab-lvs-01.png)


首先我们先将 3306 的删掉，让 LVS 只代理 3307，初始的 LVS 状态如下：

```bash
# root @ t02
$ ipvsadm -L --timeout
Timeout (tcp tcpfin udp): 900 120 300

# root @ t02
$ ipvsadm -L -n
IP Virtual Server version 1.2.1 (size=4096)
Prot LocalAddress:Port Scheduler Flags
  -> RemoteAddress:Port           Forward Weight ActiveConn InActConn
TCP  127.0.0.1:3001 rr
  -> 127.0.0.1:3307               Masq    1      0          0

# root @ t02
$ ipvsadm -Lnc | head -10
IPVS connection entries
pro expire state       source             virtual            destination
```

接下来执行 sysbench 开始压测，并在 30s 时执行 del3307.sh 模拟切换。

```bash
$sysbench --debug=on --mysql-user='root' --mysql-password='123' --mysql-db='test' --mysql-host='127.0.0.1' --mysql-port='3001' --tables='16'  --table-size='10000' --range-size='5' --db-ps-mode='disable' --skip-trx='on' --mysql-ignore-errors='all' --time='11080' --report-interval='1' --histogram='on' --threads=1 oltp_read_write run
sysbench 1.0.20 (using system LuaJIT 2.1.0-beta3)

Running the test with following options:
Number of threads: 1
Report intermediate results every 1 second(s)
Debug mode enabled.

Initializing random number generator from current time


Initializing worker threads...

DEBUG: Worker thread (#0) started
DEBUG: Reporting thread started
DEBUG: Worker thread (#0) initialized
Threads started!

[ 1s ] thds: 1 tps: 47.89 qps: 876.91 (r/w/o: 684.37/192.54/0.00) lat (ms,95%): 23.10 err/s: 0.00 reconn/s: 0.00
[ 2s ] thds: 1 tps: 49.03 qps: 883.54 (r/w/o: 686.42/197.12/0.00) lat (ms,95%): 22.69 err/s: 0.00 reconn/s: 0.00
[ 3s ] thds: 1 tps: 49.00 qps: 882.02 (r/w/o: 686.01/196.00/0.00) lat (ms,95%): 22.28 err/s: 0.00 reconn/s: 0.00
...
[ 29s ] thds: 1 tps: 49.00 qps: 884.01 (r/w/o: 686.01/198.00/0.00) lat (ms,95%): 23.10 err/s: 0.00 reconn/s: 0.00
[ 30s ] thds: 1 tps: 49.00 qps: 882.98 (r/w/o: 685.99/197.00/0.00) lat (ms,95%): 23.10 err/s: 0.00 reconn/s: 0.00
[ 31s ] thds: 1 tps: 50.00 qps: 899.02 (r/w/o: 700.01/199.00/0.00) lat (ms,95%): 21.89 err/s: 0.00 reconn/s: 0.00
[ 32s ] thds: 1 tps: 49.00 qps: 881.01 (r/w/o: 686.00/195.00/0.00) lat (ms,95%): 22.69 err/s: 0.00 reconn/s: 0.00
[ 33s ] thds: 1 tps: 1.00 qps: 18.00 (r/w/o: 14.00/4.00/0.00) lat (ms,95%): 19.65 err/s: 0.00 reconn/s: 0.00
[ 34s ] thds: 1 tps: 0.00 qps: 0.00 (r/w/o: 0.00/0.00/0.00) lat (ms,95%): 0.00 err/s: 0.00 reconn/s: 0.00
[ 35s ] thds: 1 tps: 0.00 qps: 0.00 (r/w/o: 0.00/0.00/0.00) lat (ms,95%): 0.00 err/s: 0.00 reconn/s: 0.00
[ 36s ] thds: 1 tps: 0.00 qps: 0.00 (r/w/o: 0.00/0.00/0.00) lat (ms,95%): 0.00 err/s: 0.00 reconn/s: 0.00
[ 37s ] thds: 1 tps: 0.00 qps: 0.00 (r/w/o: 0.00/0.00/0.00) lat (ms,95%): 0.00 err/s: 0.00 reconn/s: 0.00

```

可以看到在 34s 压测的 QPS 已经到了 0。我们再次查看 LVS 的状态：

```bash
IP Virtual Server version 1.2.1 (size=4096)
Prot LocalAddress:Port Scheduler Flags
  -> RemoteAddress:Port           Forward Weight ActiveConn InActConn
TCP  127.0.0.1:3001 rr
  -> 127.0.0.1:3306               Masq    1      1          0

# root @ t02 in ~ [12:12:34]
$ ipvsadm -Lnc | head -10
IPVS connection entries
pro expire state       source             virtual            destination
TCP 14:15  ESTABLISHED 127.0.0.1:54618    127.0.0.1:3001     127.0.0.1:3307

$ netstat -anto |grep -E "Recv|54618|3001"
Proto Recv-Q Send-Q Local Address           Foreign Address         State       Timer
tcp        0     52 127.0.0.1:3307          127.0.0.1:54618         ESTABLISHED on (45.85/9/0)
tcp        0    162 127.0.0.1:54618         127.0.0.1:3001          ESTABLISHED probe (47.39/0/8)

$ mysql -uroot -p123 -h 127.0.0.1 -P 3001
mysql: [Warning] Using a password on the command line interface can be insecure.
Welcome to the MySQL monitor.  Commands end with ; or \g.
Your MySQL connection id is 622
Server version: 8.0.27 MySQL Community Server - GPL

Copyright (c) 2000, 2025, Oracle and/or its affiliates.

Oracle is a registered trademark of Oracle Corporation and/or its
affiliates. Other names may be trademarks of their respective
owners.

Type 'help;' or '\h' for help. Type '\c' to clear the current input statement.

mysql> show databases;
+--------------------+
| Database           |
+--------------------+
| a3306              |

```

可以看到 LVS 的代理已经切换到了 3306 端口的 MySQL，我们使用 mysql 命令连接 3001 端口查看数据库，可以看到连到的也是 3306。但查看 LVS 的连接信息，其依然是在访问 3307，这导致 sysbench 一直执行失败，QPS 为 0，我们看 LVS 的连接信息，其 expire 也一直在减少，说明已经没有数据在传输了。


```
Proto Recv-Q Send-Q Local Address           Foreign Address         State       Timer
tcp        0     52 127.0.0.1:3307          127.0.0.1:54618         ESTABLISHED on (20.79/15/0)
tcp        0    162 127.0.0.1:54618         127.0.0.1:3001          ESTABLISHED probe (5.24/0/8)
```
#### 3. LVS + Nginx 高可用切换

#### 4. K8s



### 2. 长连接黑洞原因分析

### 3. sysbench 重连失败

### 4. TCP 重传参数总结

结合之前做过的 TCP 半连接队列、TCP 连接建立抓包实验，整个 TCP 重传相关的参数就都已经涉猎到了，Linux 有 ``tcp_syn_retries``、``tcp_synack_retries``、``tcp_orphan_retries``、``tcp_retries1``、``tcp_retries2`` 5 个参数。这里我们结合抓包这 5 个参数的作用做下总结。

```bash
$ sysctl -a |grep -E "retries"
net.ipv4.tcp_orphan_retries = 0
net.ipv4.tcp_retries1 = 3
net.ipv4.tcp_retries2 = 15
net.ipv4.tcp_syn_retries = 4
net.ipv4.tcp_synack_retries = 2
net.ipv4.vs.sync_retries = 0
net.ipv6.idgen_retries = 3
```
