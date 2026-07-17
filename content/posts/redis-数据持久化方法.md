---
title: "Redis 的数据持久化方法"
date: 2018-06-02T15:03:11+08:00
tags:
  - Redis
  - 数据库
categories:
  - 数据库
source: "https://blog.csdn.net/Ahri_J/article/details/80548127"
---
工作中经常会遇到 Redis 数据库相关的使用操作，因为其将数据存储在内存中的缘故，其数据的读写效率要远远高于数据库等方式的读写。但也因为数据存储在内存中，如果机器意外关机，就会导致数据的丢失。为了避免数据丢失造成的损失，因此就需要对 Redis 中的数据进行持久化的备份处理。本篇是对最近学习 Redis 数据持久化的一个笔记，简要介绍了 Redis 提供的 RDB (快照方式) 与 AOF (只追加文件) 两种持久化方式的使用。

#### 一. RDB 持久化

RDB 持久化方式有点
 类
似 MySQL 的 mysqldump 命令，就是将库中的数据导出后作为备份。Redis 提供了 SAVE、 BGSAVE 以及自动化 SAVE 三种方式。下面分别演示一下。

首先修改下配置文件，来指定一下当前 Redis 进程生成的 RDB 文件的目录和文件名称

```
# 指定文件目录
dir /Users/mymac/study/Redis/data
# 指定文件名
dbfilename dump-6379.rdb
```

##### 1. SAVE

直接执行命令 SAVE 命令即可

```
127.0.0.1:6379> set hello redis
OK
127.0.0.1:6379> SAVE
OK
127.0.0.1:6379>
```

查看其日志可以看到其备份的日志打印

```
20 67675:M 02 Jun 11:19:49.072 # Server started, Redis version 3.2.8
21 67675:M 02 Jun 11:19:49.073 * The server is now ready to accept connections on port 6379
22 67675:M 02 Jun 11:20:21.974 * DB saved on disk
```

查看上面配置的 目录就可以看到对应的 rdb 文件了，整个过程非常简单，但是 SAVE 命令有几个注意点:

- 和 mysqldump 会阻塞数据库一样，SAVE 命令也会阻塞 Redis 主进程服务，导致服务暂时不可用
- 生成的 RDB 文件会覆盖掉旧文件

##### 2. BGSAVE

BGSAVE，多了 BG， 顾名思义就是后台 SAVE 的意思，和上面 SAVE 命令直接阻塞主进程不同，BGSAVE 会 Fork 一个子进程，然后通过子进程进行备份，这样就不会影响到主进程对外提供服务了。操作如下

```
127.0.0.1:6379> BGSAVE
Background saving started
127.0.0.1:6379>
```

日志打印

```
23 67675:M 02 Jun 11:25:08.063 * Background saving started by pid 68038
24 68038:C 02 Jun 11:25:08.064 * DB saved on disk
25 67675:M 02 Jun 11:25:08.081 * Background saving terminated with success
```

可以看到其是新启动了一个进程进行 Background saving, 对应的 rdb 文件也会覆盖之前的文件。

不过需要注意的是，虽然 BGSAVE 的备份过程不会阻塞主进程，但是其 Fork 子进程的操作是由主进程进行的，所以当 Fork 子进程花费时间过多的时候也会导致服务不可用。

##### 3. 自动间隔备份

除了上面两种手动存储之外， Redis 还提供了相关配置允许我们根据时间和 key 的改变次数类进行自动备份。

下面是配置方式

```
save 900 1 # 在 900 秒(15分钟)内有一个 key 发生改变则进行 rdb 备份
save 300 10 # 在 300 秒内有至少 10 个 key 发生变化则进行备份
save 60 10000 # 在 60 秒内如果有 10000 个 key 发生变化则进行备份
```

可以通过注释掉上面的配置来关闭自动间隔备份。

##### 4. 使用建议

- 建议关掉自动 rdb 备份
- 对于 rdb 文件管理进行集中管理
- 可以考虑在主从系统中，在从节点进行 RDB 备份，但是要注意控制粒度

以上就是三种 RDB 方式的简要介绍，除了上面三种方式之外，还有全量复制、shutdown 时等触发 RDB 的操作，使用时需要加以注意。

#### 二. AOF (Append only file)持久化方式

虽然 RDB 可以实现数据的备份，但也存在如下问题:

- 耗时耗性能，其将所有数据进行 dump, 性能是 O(n)，消耗内存和 IO 性能
- 易丢失数据，在最后一次 save 和宕机时间之间的数据无法备份

鉴于 RDB 的问题，Redis 还提供了 AOF 方式进行数据备份。

要使用 AOF 功能的话需要在配置文件中进行配置

```
593 appendonly yes # 开启 AOF 功能，默认是 no
594 appendfilename "appendonly.aof" # 指定 aof 文件名
595 no-appendfsync-on-rewrite no #  重写时是否做 aof 操作，关闭可以节省 IO 资源消耗, 但也会造成数据丢失的可能，需要权衡
596 appendfsync always # 刷新方式
```

AOF (只追加文件)类似于 MySQL 的 binlog，其会将 Redis 的每一条写命令添加到 aof 文件中，本质上是先写入一个缓冲区，然后在刷新到磁盘中，可以通过 ***appendfsync*** 进行配置其刷新方式有三种:

- always: 每条命令会立即刷新到 aof 文件中，这样可以保证数据不丢失，但是会导致较大的 IO 开销
- everysec: 每秒刷新，可以减轻 IO 压力，但会存在丢失一秒数据的
- no: 由操作系统决定何时刷新

上面三种方式，大部分都是用第二种，达到数据安全性和性能的平衡，不推荐使用第三种，虽然不需要我们进行管理，但是也不可控。对于数据安全性较高的部分数据可以考虑使用第一种 always 方式。

##### 1. AOF 文件重写

AOF 的方式会将每一条写命令存到 aof 文件中，随着写命令的增多，其文件会越来越大，占用存储资源，并且恢复数据的时候也会越来越慢。为了减少资源的消耗，Redis 提供了 AOF 重写，本质就是将过期的写命令移除掉，只保留最新的一条。如下面三条命令，对 a 这个 key 我写入了三次，AOF 备份会将三条命令都写入到文件中备份，但此时其实只有第三条命令是有效的，那么 AOF 文件重写就会将 前两条命令移除掉，只保留第三条。这样可以达到减少磁盘占用和加速数据恢复的目的。

```
127.0.0.1:6379> set a 1
OK
127.0.0.1:6379> set a 2
OK
127.0.0.1:6379> set a 3
OK
```

##### 2. AOF 文件重写的两种方式

***BGREWRITEAOF 命令***

执行该命令，Redis 会将内存中的数据进行一次回溯，然后将对应的写入命令保存到 aof 文件中。

```
127.0.0.1:6379> BGREWRITEAOF
Background append only file rewriting started
```

查看 Redis 日志其打印如下, 可以看到重写也是先 fork 一个新的进程然后进行:

```
62 69318:M 02 Jun 12:17:09.042 * Background append only file rewriting started by pid 71343
63 69318:M 02 Jun 12:17:09.067 * AOF rewrite child asks to stop sending diffs.
64 71343:C 02 Jun 12:17:09.067 * Parent agreed to stop sending diffs. Finalizing AOF...
65 71343:C 02 Jun 12:17:09.068 * Concatenating 0.00 MB of AOF diff received from parent.
66 71343:C 02 Jun 12:17:09.068 * SYNC append only file rewrite performed
67 69318:M 02 Jun 12:17:09.101 * Background AOF rewrite terminated with success
68 69318:M 02 Jun 12:17:09.101 * Residual parent diff successfully flushed to the rewritten AOF (0.00 MB)
69 69318:M 02 Jun 12:17:09.102 * Background AOF rewrite finished successfully
```

***重写自动配置***

Redis 提供了两个重写相关的配置

```
664 auto-aof-rewrite-min-size 64mb # AOF 文件重写所需的尺寸，当 aof 文件达到该值时进行一次重写
665 auto-aof-rewrite-percentage 100 # AOF 文件的增长率， 即 AOF 变大多少时再次重写，100 表示下次到达 128 M 时进行重写
```

Redis 中提供了 aof_curren_size 和 aof_base_size 分别表示当前 AOF 文件大小和上次重写时的 AOF 文件大小，其自动重写就是满足下面两个条件:

```
aof_curren_size > auto-aof-rewrite-min-size
aof_curren_size - aof_base_size / aof_base_size > auto-aof-rewrite-percentage
```

##### 3. AOF 文件重写过程

Redis 在 AOF 重写时是通过 fork 一个子进程实现的，这样可以在 aof 重写时不影响服务。但此时如果有新的写入命令的话，那样就会导致 Redis 实际数据和 AOF 文件不一致。针对该问题 Redis 提供了 aof_rewrite_buffer 缓冲区。结合缓冲区，其整个重写过程如下:

- Redis 接到 AOF 重写命令，fork 子进程
- 子进程执行 AOF 重写
- Redis 收到写命令时，子进程继续将写命令写入原来的 aof_buffer 并刷新到旧的 aof 文件中
- 子进程将写命令写入到 aof_rewrite_buffer 中
- 子进程完成 aof 重写后，将 aof_rewrite_buffer 中的写命令写入新的 aof 文件
- 新的 aof 文件代替旧的 aof 文件，完成重写

##### 4. 使用建议

- 建议开启，当然如果只是作缓存使用数据丢失影响不大时可以关闭
- AOF 重写集中管理
- 刷新机制建议使用 everysec
- 足够的内存！足够的内存！足够的内存！ (要是硬件资源无限，哪来那么多分布式系统微服务的破事= =！)

#### 三. AOF 与 RDB 对比

上面介绍了 AOF 与 RDB 的使用，最后做一下简要的对比

<table><thead><tr><th>特性</th><th>RDB</th><th>AOF</th></tr></thead><tbody><tr><td>加载优先级</td><td>后加载</td><td>先加载</td></tr><tr><td>体积</td><td>小</td><td>大</td></tr><tr><td>恢复速度</td><td>慢</td><td>快</td></tr><tr><td>数据安全</td><td>低</td><td>取决于刷新策略，较高</td></tr><tr><td>操作性能</td><td>重，全量备份比较消耗资源</td><td>操作较轻</td></tr></tbody></table>

上面就是 Redis 持久化的简单使用，基本会用了，后面需要的话在考虑对其机制、文件格式和内容做深入的学习。
