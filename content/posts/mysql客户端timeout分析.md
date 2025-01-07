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
$ cat /proc/version
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
  
### 客户端环境

- 下载依赖 [mysql-connector-java-5.1.45.jar](https://repo1.maven.org/maven2/mysql/mysql-connector-java/5.1.45/)
- 实验代码

```java
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;
import java.sql.PreparedStatement;

public class Test {
    public static void main(String args[]) throws NumberFormatException, InterruptedException, ClassNotFoundException {
        Class.forName("com.mysql.jdbc.Driver");
        String url = args[0];
        String user = args[1];
        String pass = args[2];
        String sql = args[3];
        String interval = args[4];
        try {
            Connection conn = DriverManager.getConnection(url, user, pass);
            while (true) {
                PreparedStatement stmt = conn.prepareStatement(sql);
                stmt.setString(1, interval);
                ResultSet rs = stmt.executeQuery();
                while (rs.next()) {
                    System.out.println("fine");
                }
                rs.close();
                stmt.close();
                PreparedStatement stmt2 = conn.prepareStatement(sql);
                stmt2.setString(1, interval);
                rs = stmt2.executeQuery();
                while (rs.next()) {
                    System.out.println("fine");
                }
                rs.close();
                stmt2.close();
                Thread.sleep(Long.valueOf(interval));
                break;
            }
            conn.close();
        } catch (SQLException e) {
            e.printStackTrace();
        }
    }
}

```

## 实验一：查询到数据

执行命令得到如下日志：

```java
[root@t01 lab01]# java -cp .:./mysql-connector-java-5.1.45.jar Test "jdbc:mysql://172.17.150.182:3306/test?useSSL=false&useServerPrepStmts=true&cachePrepStmts=true&connectTimeout=500&socketTimeout=1700" test 123 "select sleep(10), id from t_user where id= ?" 1
com.mysql.jdbc.exceptions.jdbc4.CommunicationsException: Communications link failure

The last packet successfully received from the server was 1,702 milliseconds ago.  The last packet sent successfully to the server was 1,702 milliseconds ago.
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

- 抓包命令
```
 sudo tshark -i lo   -f "port 3306"   -T fields -e frame.number -e frame.time_delta -e tcp.srcport -e tcp.dstport -e _ws.col.Info -e mysql.query -w /tmp/test01.pcapng
```

- 抓包结果

![alt text](https://pub-08b57ed9c8ce4fadab4077a9d577e857.r2.dev/mysql-sockettimeout.png)

我们来分析下图中的包信息。首先是 TCP 的三次握手，三次握手成功后，MySQL Server 向客户端发送 Greeting 信息，除了基本的版本、状态信息，还有 salt 字段，用于后续的密码校验。

![在这里插入图片描述](https://pub-08b57ed9c8ce4fadab4077a9d577e857.r2.dev/mysql-socket-timeout02.png)

客户端响应 ACK 后会发送 Login 请求，可以看到数据库、用户名、密码信息。密码基于 md5、sha1 算法以及 greeting 请求的盐进行了加密。

![在这里插入图片描述](https://i-blog.csdnimg.cn/blog_migrate/67a43678964ac12e14ff214fc239b297.png#pic_center)


校验成功后就会执行后续的查询；失败的话就会报 1045 错误。下图是一个失败的抓包示例：

![在这里插入图片描述](https://i-blog.csdnimg.cn/blog_migrate/75ee5e3e14c9ba67b0912d631e8caaa4.png#pic_center)


1. 登录校验成功，会开始执行查询，在 Prepare Statement 前会执行一系列的准备语句。

![在这里插入图片描述](https://i-blog.csdnimg.cn/blog_migrate/4ef70bfc54fb588d9e9c8a329d6d5580.png#pic_center)


4. 接着就是执行 Prepare Statement 了，会向 MySQL  发 prepareStatement 请求

![在这里插入图片描述](https://i-blog.csdnimg.cn/blog_migrate/a074889dc93292dafc4b2d057314334b.png#pic_center)

然后是执行阶段，可以看到传的 ID = 1 的参数

![在这里插入图片描述](https://i-blog.csdnimg.cn/blog_migrate/f84bf95286d0be6af7f5141d1b10a550.png#pic_center)

看代码是分别执行了两次 `conn.prepareStatement(sql);` 和 `stmt2.executeQuery();` ，但抓包只看了一次 prepareStatement 请求，应该是客户端缓存了。翻了下代码应该是下面这段：

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
![在这里插入图片描述](https://i-blog.csdnimg.cn/blog_migrate/f8275373261c1a83038ba6c2f066771b.png#pic_center)


5. 查询超时

客户端设置了 1.7s 的 socket timeout，可以看到在 0.59 秒 MySQL 确认了 execute 语句，然后在 2.29 秒客户端向服务端发送终止连接的请求。

![在这里插入图片描述](https://i-blog.csdnimg.cn/blog_migrate/4dd3900e3e973f4304ee52730da110ff.png#pic_center)

## 实验二：查询不到数据

### 客户端日志

```
$ java -cp .:./mysql-connector-java-5.1.45.jar Test "jdbc:mysql://123.57.2.39:3306/test?useSSL=false&useServerPrepStmts=true&cachePrepStmts=true&connectTimeout=500&socketTimeout=1700" test 123 "select sleep(10), id from t_user where id = ?" 10
```

### 服务端日志
```shell
$ sudo tshark -i eth0 -f "port 3306"   -T fields -e frame.number -e frame.time_delta -e tcp.srcport -e tcp.dstport -e _ws.col.Info -e mysql.query -w /tmp/test02.pcapng

Running as user "root" and group "root". This could be dangerous.
Capturing on 'eth0'
 ** (tshark:218654) 12:24:27.002498 [Main MESSAGE] -- Capture started.
 ** (tshark:218654) 12:24:27.002581 [Main MESSAGE] -- File: "/tmp/test02.pcapng"
1	0.000000000	4612	3306	4612 → 3306 [SYN] Seq=0 Win=65535 Len=0 MSS=1380 WS=64 TSval=1205035536 TSecr=0 SACK_PERM=1
2	0.000058342	3306	4612	3306 → 4612 [SYN, ACK] Seq=0 Ack=1 Win=65160 Len=0 MSS=1460 SACK_PERM=1 TSval=938094158 TSecr=1205035536 WS=128
3	0.039938068	4612	3306	4612 → 3306 [ACK] Seq=1 Ack=1 Win=131328 Len=0 TSval=1205035575 TSecr=938094158
4	0.000330231	3306	4612	Server Greeting  proto=10 version=8.3.0
5	0.110430727	4612	3306	4612 → 3306 [ACK] Seq=1 Ack=78 Win=131200 Len=0 TSval=1205035637 TSecr=938094198
6	0.007077249	4612	3306	Login Request user=test db=test
7	0.000025041	3306	4612	3306 → 4612 [ACK] Seq=78 Ack=243 Win=65152 Len=0 TSval=938094316 TSecr=1205035674
8	0.000140115	3306	4612	Auth Switch Request
9	0.039862066	4612	3306	4612 → 3306 [ACK] Seq=243 Ack=126 Win=131200 Len=0 TSval=1205035732 TSecr=938094316
10	0.008360335	4612	3306	Auth Switch Response
11	0.000192880	3306	4612	Response  OK
12	0.054352994	4612	3306	4612 → 3306 [ACK] Seq=267 Ack=137 Win=131136 Len=0 TSval=1205035783 TSecr=938094365
13	0.008302588	4612	3306	Request Query	/* mysql-connector-java-5.1.45 ( Revision: 9131eefa398531c7dc98776e8a3fe839e544c5b2 ) */SELECT  @@session.auto_increment_increment AS auto_increment_increment, @@character_set_client AS character_set_client, @@character_set_connection AS character_set_connection, @@character_set_results AS character_set_results, @@character_set_server AS character_set_server, @@collation_server AS collation_server, @@init_connect AS init_connect, @@interactive_timeout AS interactive_timeout, @@license AS license, @@lower_case_table_names AS lower_case_table_names, @@max_allowed_packet AS max_allowed_packet, @@net_buffer_length AS net_buffer_length, @@net_write_timeout AS net_write_timeout, @@have_query_cache AS have_query_cache, @@sql_mode AS sql_mode, @@system_time_zone AS system_time_zone, @@time_zone AS time_zone, @@transaction_isolation AS transaction_isolation, @@wait_timeout AS wait_timeout
14	0.000349999	3306	4612	Response TABULAR Response  OK
15	0.037027110	4612	3306	4612 → 3306 [ACK] Seq=1164 Ack=1208 Win=130112 Len=0 TSval=1205035843 TSecr=938094428
16	0.034611889	4612	3306	Request Query	SHOW WARNINGS
17	0.000158468	3306	4612	Response TABULAR Response  OK
18	0.049715364	4612	3306	4612 → 3306 [ACK] Seq=1182 Ack=1411 Win=130816 Len=0 TSval=1205035916 TSecr=938094499
19	0.006872693	4612	3306	Request Query	SET NAMES utf8mb4
20	0.000147500	3306	4612	Response  OK
21	0.044582956	4612	3306	4612 → 3306 [ACK] Seq=1204 Ack=1422 Win=131008 Len=0 TSval=1205035971 TSecr=938094556
22	0.007435888	4612	3306	Request Query	SET character_set_results = NULL
23	0.000169693	3306	4612	Response  OK
24	0.040867725	4612	3306	4612 → 3306 [ACK] Seq=1241 Ack=1433 Win=131008 Len=0 TSval=1205036024 TSecr=938094608
25	0.006848669	4612	3306	Request Query	SET autocommit=1
26	0.000146285	3306	4612	Response  OK
27	0.053149480	4612	3306	4612 → 3306 [ACK] Seq=1262 Ack=1444 Win=131008 Len=0 TSval=1205036072 TSecr=938094656
28	0.028069029	4612	3306	Request Prepare Statement	select sleep(10), id from t_user where id = ?
29	0.000247868	3306	4612	Response
30	0.041648584	4612	3306	4612 → 3306 [ACK] Seq=1312 Ack=1568 Win=130944 Len=0 TSval=1205036153 TSecr=938094738
31	0.006910927	4612	3306	Request Execute Statement
32	0.000296156	3306	4612	Response TABULAR Response  OK
33	0.039407443	4612	3306	4612 → 3306 [ACK] Seq=1333 Ack=1665 Win=130944 Len=0 TSval=1205036202 TSecr=938094786
34	0.000800578	4612	3306	Request Execute Statement
35	0.000286834	3306	4612	Response TABULAR Response  OK
36	0.052320713	4612	3306	4612 → 3306 [ACK] Seq=1352 Ack=1762 Win=130944 Len=0 TSval=1205036244 TSecr=938094827
37	0.006926131	4612	3306	[TCP Previous segment not captured] 4612 → 3306 [FIN, ACK] Seq=1357 Ack=1762 Win=131072 Len=0 TSval=1205036257 TSecr=938094827
38	0.000055496	3306	4612	[TCP Dup ACK 35#1] 3306 → 4612 [ACK] Seq=1762 Ack=1352 Win=64256 Len=0 TSval=938094886 TSecr=1205036244 SLE=1357 SRE=1358
39	0.006790060	4612	3306	[TCP Out-Of-Order] 4612 → 3306 [PSH, ACK] Seq=1352 Ack=1762 Win=131072 Len=5 TSval=1205036257 TSecr=938094827
40	0.000034601	3306	4612	3306 → 4612 [ACK] Seq=1762 Ack=1358 Win=64256 Len=0 TSval=938094893 TSecr=1205036257
41	0.000098597	3306	4612	3306 → 4612 [FIN, ACK] Seq=1762 Ack=1358 Win=64256 Len=0 TSval=938094893 TSecr=1205036257
42	0.035847690	4612	3306	4612 → 3306 [ACK] Seq=1358 Ack=1763 Win=131072 Len=0 TSval=1205036308 TSecr=938094893
43	0.006935677	4612	3306	[TCP Spurious Retransmission] 4612 → 3306 [FIN, PSH, ACK] Seq=1352 Ack=1762 Win=131072 Len=5 TSval=1205036301 TSecr=938094886
44	0.000032567	3306	4612	3306 → 4612 [RST] Seq=1762 Win=0 Len=0

```

测试了好几次，并没有看到另一位老铁看到的 MySQL 的 Command Quit 包。

![在这里插入图片描述](https://i-blog.csdnimg.cn/blog_migrate/4b7848803f0b69cb93b9ec7c9e120300.png#pic_center)


## 简要总结

- 中间件连接问题，本质上都是 TCP/IP 的通信问题，抓包之下一切无所遁形。

- 做技术当然要对很多具体的知识点做掌握，但更重要的是底层内功的修炼，可以提高自己在不熟悉的问题场景下蹚出一条路的能力。