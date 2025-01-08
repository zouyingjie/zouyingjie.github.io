---
title: 【动手实验】MySQL 客户端 SocketTimeout 问题抓包分析
date: 2023-09-02 09:17:14
tags:
  - 计算机网络
  - 动手实验
categories:
  - 计算机网络
  - 动手实验
description: 动手实验
---

## 实验准备

### 服务端环境准备

- 服务器信息

阿里云 99 大洋白嫖机

```bash
[root@t01 ~]# cat /proc/version
Linux version 5.10.134-18.al8.x86_64 (mockbuild@h87c01383.na61) (gcc (GCC) 10.2.1 20200825 (Alibaba 10.2.1-3.8 2.32), GNU ld version 2.35-12.3.al8) #1 SMP Fri Dec 13 16:56:53 CST 2024
```

- 安装 JDK， docker， tshark

```shell
​yum install -y java-1.8.0-openjdk.x86_64 java-1.8.0-openjdk-devel.x86_64  podman-docker.noarch wireshark

```

- 启动 MySQL
```shell
[root@t01 ~]#  docker run -it -d --net=host -e MYSQL_ROOT_PASSWORD=123 --name=mysql mysql:8.0.28
Emulate Docker CLI using podman. Create /etc/containers/nodocker to quiet msg.
233c8ca518d0e8feef367995aee656fffb65b6a2f16a589d2e765f06dad96828

[root@t01 ~]# docker  ps
Emulate Docker CLI using podman. Create /etc/containers/nodocker to quiet msg.
CONTAINER ID  IMAGE                           COMMAND     CREATED         STATUS         PORTS       NAMES
233c8ca518d0  docker.io/library/mysql:8.0.28  mysqld      11 seconds ago  Up 12 seconds              mysql

[root@t01 ~]# docker exec -it mysql sh
Emulate Docker CLI using podman. Create /etc/containers/nodocker to quiet msg.
# mysql -uroot -p
Enter password:
Welcome to the MySQL monitor.  Commands end with ; or \g.
Your MySQL connection id is 8
Server version: 8.0.28 MySQL Community Server - GPL

Copyright (c) 2000, 2022, Oracle and/or its affiliates.

Oracle is a registered trademark of Oracle Corporation and/or its
affiliates. Other names may be trademarks of their respective
owners.

Type 'help;' or '\h' for help. Type '\c' to clear the current input statement.

mysql> \s
--------------
mysql  Ver 8.0.28 for Linux on x86_64 (MySQL Community Server - GPL)

Connection id:		8
Current database:
Current user:		root@localhost
SSL:			Not in use
Current pager:		stdout
Using outfile:		''
Using delimiter:	;
Server version:		8.0.28 MySQL Community Server - GPL
Protocol version:	10
Connection:		Localhost via UNIX socket
Server characterset:	utf8mb4
Db     characterset:	utf8mb4
Client characterset:	latin1
Conn.  characterset:	latin1
UNIX socket:		/var/run/mysqld/mysqld.sock
Binary data as:		Hexadecimal
Uptime:			23 sec

Threads: 2  Questions: 5  Slow queries: 0  Opens: 117  Flush tables: 3  Open tables: 36  Queries per second avg: 0.217
--------------
```

- 初始化 MySQL 密码、数据库

```sql
CREATE DATABASE test CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

ALTER USER 'root'@'%' IDENTIFIED WITH mysql_native_password BY '123';

CREATE USER 'test'@'%'  IDENTIFIED BY '123';  
GRANT ALL PRIVILEGES ON test.* TO test@'%';  
FLUSH PRIVILEGES;

# 创建表
create table t_user  
(  
    id        bigint(20) unsigned not null auto_increment primary key comment 'primary key',  
    name      varchar(64)         not null default '' comment 'user name',  
    age       tinyint unsigned    not null default 0 comment '年龄',  
    gender    tinyint unsigned    not null default 0 comment '性别, 0 男，1 女',  
    create_at datetime(3)         not null default current_timestamp(3) comment 'record create date',  
    update_at datetime(3)         not null default current_timestamp(3) on update current_timestamp(3) comment 'record update date'  
) engine = innodb  
  default charset = utf8mb4  
  collate = utf8mb4_unicode_ci comment '用户表';

# 插入数据
insert into t_user (id, name, age) values (1, "tom", 18);
```

- 执行查询

```sql
mysql>  select sleep(10), id, name from t_user where id = 100;
Empty set (0.00 sec)

mysql>  select sleep(10), id, name from t_user where id = 1;
+-----------+----+------+
| sleep(10) | id | name |
+-----------+----+------+
|         0 |  1 | tom  |
+-----------+----+------+
1 row in set (10.00 sec)
```

- 能查到数据时，sleep 生效
- 数据不存在时，sleep 不生效
  
**服务端抓包命令**

这里用 tshark 进行抓包，命令如下：
```shell
 sudo tshark -i lo   -f "port 3306"   -T fields -e frame.number -e frame.time_delta -e tcp.srcport -e tcp.dstport -e _ws.col.Info -e mysql.query -w /tmp/test01.pcapng
```
该命令的含义是：
- -i lo 指定抓取的网卡为 lo，即本地回环网卡
- -f "port 3306" 指定抓取的端口为 3306，即 MySQL 端口
- -T fields 指定输出格式为字段
- -e frame.number -e frame.time_delta -e tcp.srcport -e tcp.dstport -e _ws.col.Info -e mysql.query 指定输出字段
- -w /tmp/test01.pcapng 指定输出文件为 /tmp/test01.pcapng


### 客户端环境

- 下载依赖 [mysql-connector-java-5.1.45.jar](https://repo1.maven.org/maven2/mysql/mysql-connector-java/5.1.45/)
- 客户端代码：[Test.java](https://github.com/zouyingjie/labs/blob/main/mysql-socket-timeout/Test.java)



准备好环境后，执行客户端代码访问 MySQL，抓包分析网络通信过程。
## 实验一：正常查询数据

客户端执行如下命令

```shell
java -cp .:./mysql-connector-java-5.1.45.jar Test "jdbc:mysql://172.17.150.182:3306/test?useSSL=false&useServerPrepStmts=true&cachePrepStmts=true&connectTimeout=500&socketTimeout=1700" test 123 "select  id from t_user where id= ?" 1
```
上述 JDBC 连接中各个参数的含义：
- ``useSSL=false``：禁用 SSL 加密
- ``useServerPrepStmts=true``：启用服务器端预处理语句
- ``cachePrepStmts=true``：启用预处理语句缓存
- ``connectTimeout=500``：连接超时时间，单位为毫秒
- ``socketTimeout=1700``：socket 超时时间，单位为毫秒，也就是客户端等待 MySQL 返回结果的最大时间，这里我们设置为 1.7s

下面分析抓包结果。首先是 TCP 的三次握手，三次握手成功后，MySQL Server 向客户端发送 Greeting 信息，除了基本的版本、状态信息，还有 salt 字段，用于后续的密码校验。

![](https://pub-08b57ed9c8ce4fadab4077a9d577e857.r2.dev/mysql-sockettimeout-01.png)

客户端响应 ACK 后会发送 Login 请求，可以看到数据库、用户名、密码信息。密码基于 md5、sha1 算法以及 greeting 请求的盐进行了加密。

![](https://pub-08b57ed9c8ce4fadab4077a9d577e857.r2.dev/mysql-sockettimeout-02.png)

如果校验失败会报 1045 错误，提示 ``Access denied for user xxx``。下图是一个登录失败的抓包示例：

![在这里插入图片描述](https://pub-08b57ed9c8ce4fadab4077a9d577e857.r2.dev/mysql-sockettimeout-05.png)

登录成功后，会开始执行查询，在 Prepare Statement 前会执行一系列的准备语句。比如图中的一个请求执行的是 ``set autocommit = 1``语句。

![](https://pub-08b57ed9c8ce4fadab4077a9d577e857.r2.dev/mysql-sockettimeout-03.png)

上述一系列语句执行完成后，就会执行 Prepare Statement，会向 MySQL 发 prepareStatement 请求，然后在发送参数执行 Execute Statement 请求。

![](https://pub-08b57ed9c8ce4fadab4077a9d577e857.r2.dev/mysql-sockettimeout-04.png)

在代码中我们执行了两次查询，分别调用 ``conn.prepareStatement(sql);`` 和 ``stmt2.executeQuery();`` ，但抓包显示通信过程只有一次 prepareStatement 请求和两次 Execute Statement 请求。这说明预处理语句缓存已生效，查看 JDBC 代码应该是下面这段代码的作用：
```java
if (this.cachePrepStmts.getValue()) {  
    ParseInfo pStmtInfo = this.cachedPreparedStatementParams.get(nativeSql);  
  
    if (pStmtInfo == null) {  
        pStmt = ClientPreparedStatement.getInstance(getMultiHostSafeProxy(), nativeSql, this.database);  
  
        this.cachedPreparedStatementParams.put(nativeSql, pStmt.getParseInfo());  
    } else {  
        pStmt = ClientPreparedStatement.getInstance(getMultiHostSafeProxy(), nativeSql, this.database, pStmtInfo);  
    }  
}
```
第二次查询结束后 TCP 连接三次挥手断开。

## 实验二：查询时 sleep(10)

这次我们将查询命令改为 ``select sleep(10), id from t_user where id = ?`` 且 ID 传 1，按照开始的测试 sleep 会生效，因此查询应该会超时。因此执行是报如下错误：

```shell
java -cp .:./mysql-connector-java-5.1.45.jar Test "jdbc:mysql://172.17.150.182:3306/test?useSSL=false&useServerPrepStmts=true&cachePrepStmts=true&connectTimeout=500&socketTimeout=1700" test 123 "select sleep(10) id from t_user where id= ?" 1

com.mysql.jdbc.exceptions.jdbc4.CommunicationsException: Communications link failure

The last packet successfully received from the server was 1,704 milliseconds ago.  The last packet sent successfully to the server was 1,704 milliseconds ago.
	at sun.reflect.NativeConstructorAccessorImpl.newInstance0(Native Method)
	at sun.reflect.NativeConstructorAccessorImpl.newInstance(NativeConstructorAccessorImpl.java:62)
	at sun.reflect.DelegatingConstructorAccessorImpl.newInstance(DelegatingConstructorAccessorImpl.java:45)
	at java.lang.reflect.Constructor.newInstance(Constructor.java:423)
	at com.mysql.jdbc.Util.handleNewInstance(Util.java:425)
	at com.mysql.jdbc.SQLError.createCommunicationsException(SQLError.java:990)
	at com.mysql.jdbc.MysqlIO.reuseAndReadPacket(MysqlIO.java:3559)
	at com.mysql.jdbc.MysqlIO.reuseAndReadPacket(MysqlIO.java:3459)
	at com.mysql.jdbc.MysqlIO.checkErrorPacket(MysqlIO.java:3900)
	at com.mysql.jdbc.MysqlIO.sendCommand(MysqlIO.java:2527)
	at com.mysql.jdbc.ServerPreparedStatement.serverExecute(ServerPreparedStatement.java:1283)
	at com.mysql.jdbc.ServerPreparedStatement.executeInternal(ServerPreparedStatement.java:783)
	at com.mysql.jdbc.PreparedStatement.executeQuery(PreparedStatement.java:1966)
	at Test.main(Test.java:21)
Caused by: java.net.SocketTimeoutException: Read timed out
	at java.net.SocketInputStream.socketRead0(Native Method)
	at java.net.SocketInputStream.socketRead(SocketInputStream.java:116)
	at java.net.SocketInputStream.read(SocketInputStream.java:171)
	at java.net.SocketInputStream.read(SocketInputStream.java:141)
	at com.mysql.jdbc.util.ReadAheadInputStream.fill(ReadAheadInputStream.java:101)
	at com.mysql.jdbc.util.ReadAheadInputStream.readFromUnderlyingStreamIfNecessary(ReadAheadInputStream.java:144)
	at com.mysql.jdbc.util.ReadAheadInputStream.read(ReadAheadInputStream.java:174)
	at com.mysql.jdbc.MysqlIO.readFully(MysqlIO.java:3008)
	at com.mysql.jdbc.MysqlIO.reuseAndReadPacket(MysqlIO.java:3469)
	... 7 more
```

分析抓包信息，前期的握手、登录 prepareStatement 和 executeStatement 都和正常查询时一致。但是因为设置了 sleep(10)，MySQL 会等 10s 才会返回结果。而我们客户端设置的超时时间是 1.7s，从 Wireshark 中可以看到，客户端在 0.117s 发送了 executeStatement 请求，数据没有返回后，在 1.84s 客户端向服务端发送了 FIN 请求，并在 MySQL 返回 ACK 发送了 RST 包断开连接。

![](https://pub-08b57ed9c8ce4fadab4077a9d577e857.r2.dev/mysql-sockettimeout-06.png)

### 实验三：sleep(10) 但查询不到数据
这里将传递的 ID 改为 10，数据库中是没有这条数据的，因此 sleep(10) 不会生效，查询会正常执行，

```shell
java -cp .:./mysql-connector-java-5.1.45.jar Test "jdbc:mysql://172.17.150.182:3306/test?useSSL=false&useServerPrepStmts=true&cachePrepStmts=true&connectTimeout=500&socketTimeout=1700" test 123 "select sleep(10), id from t_user where id= ?" 10
```
抓包结果和实验一基本一致，唯一区别就是执行 executeStatement 请求后，因为查不到数据，MySQL 返回的数据大小不一致。
![](https://pub-08b57ed9c8ce4fadab4077a9d577e857.r2.dev/mysql-sockettimeout-07.png)


## 简要总结

- 中间件连接问题，本质上都是 TCP/IP 的通信问题，抓包之下一切无所遁形。

- 做技术当然要对很多具体的知识点做掌握，但更重要的是底层内功的修炼，可以提高自己在不熟悉的问题场景下蹚出一条路的能力。