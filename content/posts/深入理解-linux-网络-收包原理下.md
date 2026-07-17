---
title: "【深入理解 Linux 网络】收包原理与内核实现（下）应用层读取与 epoll 实现"
date: 2025-08-23T21:10:14+08:00
draft: true
tags:
  - Linux
  - epoll
  - 计算机网络
categories:
  - 计算机网络
source: "https://blog.csdn.net/Ahri_J/article/details/150651964"
---
**本系列文章**

- [【深入理解 Linux 网络】关键术语](/posts/深入理解-linux-网络-关键术语/)
- [【深入理解 Linux 网络】内核初始化流程](/posts/深入理解-linux-网络-内核初始化流程/)
- [【深入理解 Linux 网络】收包原理与内核实现（上）从网卡到协议层](/posts/深入理解-linux-网络-收包原理上/)
- [【深入理解 Linux 网络】收包原理与内核实现（中）TCP 传输层处理](/posts/深入理解-linux-网络-收包原理中/)
- 【深入理解 Linux 网络】收包原理与内核实现（下）应用层读取与 epoll 实现（待完善）
- [【深入理解 Linux 网络】数据发送处理流程与内核实现](/posts/深入理解-linux-网络-数据发包原理/)
- 【深入理解 Linux 网络】配置调优与性能优化（待完善）

---

【挖坑待填】。。。。

上一篇我们分析了数据包经 TCP 传输层处理后写入 socket 缓冲队列的过程。无论是 udp 还是 tcp 都是通过 sk_data_ready 方法通知应用处理数据的，本篇我们将从缓冲队列到应用读取这最后一公里的处理过程分析完毕。

Linux 使用 epoll 多路复用机制处理网络读写，所谓复用指的是对进程的复用，一个进程可以支持众多 socket 通信，本篇我们重点关注 epoll 的实现。

本篇着重于 Linux 本身的实现，对于编程语言，像 Java 的 Netty

传统的阻塞 & 非阻塞 IO## 多路复用 & epoll

为了解决，所谓，就是一个进程可以处理多个 socket ，复用指的是对进程的附庸，Linux 上的多路复用方案有 select、poll、epoll，其中以 epoll 性能最优。

```c
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <sys/socket.h>
#include <sys/epoll.h>
#include <netinet/in.h>
#include <fcntl.h>

#define PORT 8080
#define MAX_EVENTS 10
#define BUF_SIZE 1024

// 设置非阻塞模式
void set_nonblocking(int fd) {
    int flags = fcntl(fd, F_GETFL, 0);
    fcntl(fd, F_SETFL, flags | O_NONBLOCK);
}

int main() {
    int listen_fd, conn_fd, epoll_fd, n;
    struct sockaddr_in addr;
    struct epoll_event ev, events[MAX_EVENTS];
    char buf[BUF_SIZE];

    // 1. 创建监听 socket
    listen_fd = socket(AF_INET, SOCK_STREAM, 0);
    int opt = 1;
    setsockopt(listen_fd, SOL_SOCKET, SO_REUSEADDR, &opt, sizeof(opt));
    bind(listen_fd, (struct sockaddr*)&addr, sizeof(addr));
    listen(listen_fd, 5);

    printf("服务器启动，监听端口 %d\n", PORT);

    // 2. 创建 epoll 实例
    epoll_fd = epoll_create1(0);

    // 3. 将监听 socket 加入 epoll
    ev.events = EPOLLIN; // 监听的事件
    ev.data.fd = listen_fd; // 文件描述符
    epoll_ctl(epoll_fd, EPOLL_CTL_ADD, listen_fd, &ev);

    // 4. 事件循环
    while (1) {
		// 阻塞等待事件的发生
        n = epoll_wait(epoll_fd, events, MAX_EVENTS, -1);

        for (int i = 0; i < n; i++) {
            if (events[i].data.fd == listen_fd) {
                // 新连接
                conn_fd = accept(listen_fd, NULL, NULL);
                set_nonblocking(conn_fd);

                ev.events = EPOLLIN | EPOLLET; // 边缘触发
                ev.data.fd = conn_fd;
                epoll_ctl(epoll_fd, EPOLL_CTL_ADD, conn_fd, &ev);

                printf("新连接: fd=%d\n", conn_fd);
            } else {
                // 数据可读
                int fd = events[i].data.fd;
                int len = read(fd, buf, BUF_SIZE - 1);

                if (len <= 0) {
                    // 连接关闭或错误
                    printf("关闭连接: fd=%d\n", fd);
                    epoll_ctl(epoll_fd, EPOLL_CTL_DEL, fd, NULL);
                    close(fd);
                } else {
                    // 回显数据
                    buf[len] = '\0';
                    printf("收到数据: %s", buf);
                    write(fd, buf, len);
                }
            }
        }
    }

    close(listen_fd);
    close(epoll_fd);
    return 0;
}
```

#### epoll 的思想

传统的阻塞和非阻塞 IO 都需要进程本身来监听数据读写等事件。epoll 的思想是将监听事件相关的操作交给操作系统，当有事件到达时，由操作系统根据 socket 和事件来回调程序的处理函数。

epoll 核心函数有 3 个，对应着使用时的三种操作：

- **epoll_create**：创建 epoll 对象，一般每个进程在启动网络监听时都会调用该函数。
- **epoll_ctl**：向 epoll 对象添加要管理的 socket 对象，通常包含 socket 信息、监听的事件和事件回调处理函数。一般程序在建立新的连接时底层会调用该函数。
- **epoll_wait**：等待事件。

接下来我们根据
 源码
，研究下上述三个方法的实现原理。

### epoll 实现原理

#### create: epoll 对象的创建

```c
SYSCALL_DEFINE1(epoll_create1, int, flags)
{
	return do_epoll_create(flags);
}

SYSCALL_DEFINE1(epoll_create, int, size)
{
	if (size <= 0)
		return -EINVAL;

	return do_epoll_create(0);
}```

最终都是调用 [do_epoll_create](https://elixir.bootlin.com/linux/v5.15.139/source/fs/eventpoll.c#L1986) 函数，该函数实现比较简单，其核心就是执行 `ep_alloc(&ep);` 创建 [eventpoll](https://elixir.bootlin.com/linux/v5.15.139/source/fs/eventpoll.c#L177) 对象。

```c
/*
 * Open an eventpoll file descriptor.
 */
static int do_epoll_create(int flags)
{
	int error, fd;
	struct eventpoll *ep = NULL;
	struct file *file;

	/* Check the EPOLL_* constant for consistency.  */
	BUILD_BUG_ON(EPOLL_CLOEXEC != O_CLOEXEC);

	if (flags & ~EPOLL_CLOEXEC)
		return -EINVAL;
	/*
	 * Create the internal data structure ("struct eventpoll").
	 */
	error = ep_alloc(&ep);
	if (error < 0)
		return error;
	/*
	 * Creates all the items needed to setup an eventpoll file. That is,
	 * a file structure and a free file descriptor.
	 */
	fd = get_unused_fd_flags(O_RDWR | (flags & O_CLOEXEC));
	if (fd < 0) {
		error = fd;
		goto out_free_ep;
	}
	file = anon_inode_getfile("[eventpoll]", &eventpoll_fops, ep,
				 O_RDWR | (flags & O_CLOEXEC));
	if (IS_ERR(file)) {
		error = PTR_ERR(file);
		goto out_free_fd;
	}
	ep->file = file;
	fd_install(fd, file);
	return fd;

out_free_fd:
	put_unused_fd(fd);
out_free_ep:
	ep_free(ep);
	return error;
}
```

##### epoll 对象结构

现在我们来看下 epoll 的具体实现，其完整定义如下：

```c
// https://elixir.bootlin.com/linux/v5.15.139/source/fs/eventpoll.c#L177
/*
 * This structure is stored inside the "private_data" member of the file
 * structure and represents the main data structure for the eventpoll
 * interface.
 */
struct eventpoll {
	/*
	 * This mutex is used to ensure that files are not removed
	 * while epoll is using them. This is held during the event
	 * collection loop, the file cleanup path, the epoll file exit
	 * code and the ctl operations.
	 */
	struct mutex mtx;

	/* Wait queue used by sys_epoll_wait() */
	wait_queue_head_t wq;

	/* Wait queue used by file->poll() */
	wait_queue_head_t poll_wait;

	/* List of ready file descriptors */
	struct list_head rdllist;

	/* Lock which protects rdllist and ovflist */
	rwlock_t lock;

	/* RB tree root used to store monitored fd structs */
	struct rb_root_cached rbr;

	/*
	 * This is a single linked list that chains all the "struct epitem" that
	 * happened while transferring ready events to userspace w/out
	 * holding ->lock.
	 */
	struct epitem *ovflist;

	/* wakeup_source used when ep_scan_ready_list is running */
	struct wakeup_source *ws;

	/* The user that created the eventpoll descriptor */
	struct user_struct *user;

	struct file *file;

	/* used to optimize loop detection check */
	u64 gen;
	struct hlist_head refs;

#ifdef CONFIG_NET_RX_BUSY_POLL
	/* used to track busy poll napi_id */
	unsigned int napi_id;
#endif

#ifdef CONFIG_DEBUG_LOCK_ALLOC
	/* tracks wakeup nests for lockdep validation */
	u8 nests;
#endif
};
```

我们这里关注几个核心字段：

- `wq`：等待队列。记录调用 `epoll_wait`后被阻塞等待的进程。当数据到达缓冲区后最终会通过 wq 找到对应的进程。
- `rdllist`：就绪队列。当有事件时，对应的连接会被放到该队列，进程只需要通过该队列判断是否有事件需要处理即可。
- `rbr`：红黑树根节点。用来管理用户添加的所有 socket 信息，通过红黑树实现高效的查找、插入和删除。
 在 `ep_alloc` 中会分配内存并初始化上述数据结构，然后等待 socket 的注册。

#### socket 添加流程

创建好 epoll 对象后，程序就可以调用 epoll_ctl(即 epoll control) 来操作 socket 了。epoll_ctl 是 epoll 的控制接口，支持三种操作：

- `EPOLL_CTL_ADD`：添加 socket 的文件描述符
- `EPOLL_CTL_MOD`：修改监听事件
- `EPOLL_CTL_DEL`：删除 socket 的文件描述符

我们这里重点看下添加流程是如何实现的。内核会执行到 [do_epoll_ctl()](https://elixir.bootlin.com/linux/v5.15.139/source/fs/eventpoll.c#L2054) 函数，主要流程如下：

```c
int do_epoll_ctl(int epfd, int op, int fd, struct epoll_event *epds,
		 bool nonblock)
{

	struct fd f, tf;
	struct eventpoll *ep;
	struct epitem *epi;
	struct eventpoll *tep = NULL;

	error = -EBADF;
	// 获取到
	f = fdget(epfd);

	/* Get the "struct file *" for the target file */
	tf = fdget(fd);

	epi = ep_find(ep, tf.file, fd);

	switch (op) {
	case EPOLL_CTL_ADD:
		if (!epi) {
			epds->events |= EPOLLERR | EPOLLHUP;
			// 执行添加
			error = ep_insert(ep, epds, tf.file, fd, full_check);
		} else
			error = -EEXIST;
		break;	```

对于添加操作，核心逻辑是在 [ep_insert](https://elixir.bootlin.com/linux/v5.15.139/source/fs/eventpoll.c#L1439) 方法实现的。代码比较长我们分步来看下。

#### 初始化 epitem

对于每一个注册进来的 socket，epoll 会为其分配 [epitem](https://elixir.bootlin.com/linux/v5.15.139/source/fs/eventpoll.c#L136) 存储相关信息，其结构体定义如下：

```c
struct epitem {
	union {
		/* RB tree node links this structure to the eventpoll RB tree */
		// 红黑树节点
		struct rb_node rbn;
		/* Used to free the struct epitem */
		// rcu(read-copy-update)头
		struct rcu_head rcu;
	};

	/* List header used to link this structure to the eventpoll ready list */
	struct list_head rdllink;

	/*
	 * Works together "struct eventpoll"->ovflist in keeping the
	 * single linked chain of items.
	 */
	struct epitem *next;

	/* The file descriptor information this item refers to */

	struct epoll_filefd ffd;

	/* List containing poll wait queues */
	struct eppoll_entry *pwqlist;

	/* The "container" of this item */
	// 所属的 epoll 对象
	struct eventpoll *ep;

	/* List header used to link this item to the "struct file" items list */
	struct hlist_node fllink;

	/* wakeup_source used when EPOLLWAKEUP is set */
	struct wakeup_source __rcu *ws;

	/* The structure that describe the interested events and the source fd */
	struct epoll_event event;
};```

### wait
```
