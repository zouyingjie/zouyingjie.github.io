---
title: "【深入理解 Linux 网络】内核初始化流程"
date: 2025-08-12T11:25:57+08:00
draft: true
tags:
  - Linux
  - 计算机网络
categories:
  - 计算机网络
source: "https://blog.csdn.net/Ahri_J/article/details/150266097"
---
**本系列文章**

- [【深入理解 Linux 网络】关键术语](https://blog.csdn.net/Ahri_J/article/details/149772425)
- [【深入理解 Linux 网络】内核初始化流程](https://blog.csdn.net/Ahri_J/article/details/150266097)
- [【深入理解 Linux 网络】收包原理与内核实现（上） 从网卡到协议层](https://blog.csdn.net/Ahri_J/article/details/150575842)
- [【深入理解 Linux 网络】收包原理与内核实现（中）TCP 传输层处理](https://blog.csdn.net/Ahri_J/article/details/150580355)
- [【深入理解 Linux 网络】收包原理与内核实现（下）应用层读取与 epoll 实现](https://blog.csdn.net/Ahri_J/article/details/150651964)
- [【深入理解 Linux 网络】数据发送处理流程与内核实现](https://blog.csdn.net/Ahri_J/article/details/150928387)
- [【深入理解 Linux 网络】配置调优与性能优化](https://blog.csdn.net/Ahri_J/article/details/150928557)

---

Linux 在启动时会进行一系列的初始化工作，以准备好网络数据包的接收和发送。本篇文章我们先来看下 Linux 具体做了哪些初始化工作，后面在具体分析网络包的接收和发送流程。

### ksoftirqd 软中断线程初始化

Linux 使用 ksoftirqd 线程来处理软中断，在系统启动时会为每个 CPU 创建一个对应 ksoftirqd 线程。使用 ps 或 systemd 命令可以查看已经启动的 ksoftirqd 线程及其绑定的 CPU。

```
~$ ps aux | grep ksoftirqd
root          16  0.0  0.0      0     0 ?        S    Jul26   0:01 [ksoftirqd/0]
root          24  0.0  0.0      0     0 ?        S    Jul26   0:01 [ksoftirqd/1]

~$ systemd-cgls -k | grep softirq
├─    16 [ksoftirqd/0]
├─    24 [ksoftirqd/1]
```

Linux 创建 ksoftirqd 线程的过程如下：

1. `softirq.c` 下的 `spawn_ksoftirqd` 函数调用 `smpboot.c` 的注册函数，为每个 CPU 创建 softirq_threads。

核心代码位于[kernel/softirq.c](https://elixir.bootlin.com/linux/v5.15.139/source/kernel/softirq.c)。

```c
// https://elixir.bootlin.com/linux/v5.15.139/source/kernel/softirq.c#L959
// 软中断线程的结构体定义
static struct smp_hotplug_thread softirq_threads = {
	.store			= &ksoftirqd,
	.thread_should_run	= ksoftirqd_should_run,
	// 这里是 ksoftirqd 线程的处理函数
	.thread_fn		= run_ksoftirqd,
	.thread_comm		= "ksoftirqd/%u",
};
```

创建软中断线程的函数调用栈如下：

```shell
|- softirq.c: spawn_ksoftirqd
	|- smpboot.c: smpboot_register_percpu_thread
		|- smpboot.c __smpboot_create_thread
```

这里我们重点关注 `__smpboot_create_thread` 函数，其主要负责为每个 CPU 创建一个 ksoftirqd 线程。

```c
// https://elixir.bootlin.com/linux/v5.15.139/source/kernel/smp

static int
__smpboot_create_thread(struct smp_hotplug_thread *ht, unsigned int cpu)
{
	struct task_struct *tsk = *per_cpu_ptr(ht->store, cpu);
	struct smpboot_thread_data *td;

	if (tsk)
		return 0;
	// 分配线程数据结构
	td = kzalloc_node(sizeof(*td), GFP_KERNEL, cpu_to_node(cpu));
	if (!td)
		return -ENOMEM;
	td->cpu = cpu;
	td->ht = ht;
    // 创建线程
	tsk = kthread_create_on_cpu(smpboot_thread_fn, td, cpu,
				    ht->thread_comm);
	...
	return 0;
}
```

1. 开启循环，等待处理软中断.

在 `__smpboot_create_thread` 函数创建 ksoftirqd 线程时有一个 `smpboot_thread_fn` 函数作为参数。在创建好 ksoftirqd 线程后会执行该函数，开启循环判断是否有软中断触发。如果有软中断就会调用 [softirq_threads](https://elixir.bootlin.com/linux/v5.15.139/source/kernel/softirq.c#L959) 的 `thread_fn` 函数，也就是 `run_ksoftirqd()` 函数处理软中断。

```c
/**
 * smpboot_thread_fn - percpu hotplug thread loop function
 * @data:	thread data pointer
 *
 * Checks for thread stop and park conditions. Calls the necessary
 * setup, cleanup, park and unpark functions for the registered
 * thread.
 *
 * Returns 1 when the thread should exit, 0 otherwise.
 */
static int smpboot_thread_fn(void *data)
{
	struct smpboot_thread_data *td = data;
	struct smp_hotplug_thread *ht = td->ht;

	while (1) {// 开启循环
		set_current_state(TASK_INTERRUPTIBLE);
		preempt_disable();
		...

		if (!ht->thread_should_run(td->cpu)) { // 无 Pending 软中断
			preempt_enable_no_resched();
			schedule();
		} else {
			__set_current_state(TASK_RUNNING); // 有 Pending 软中断，执行 run_ksoftirqd
			preempt_enable();
			ht->thread_fn(td->cpu);
		}
	}
}
```

1. 当有软中断触发时，会调用 [run_ksoftirqd](https://elixir.bootlin.com/linux/v5.15.139/source/kernel/softirq.c#L913) 函数：

```c
static void run_ksoftirqd(unsigned int cpu)
{
	ksoftirqd_run_begin();
	if (local_softirq_pending()) {
		/*
		 * We can safely run softirq on inline stack, as we are not deep
		 * in the task stack here.
		 */
		__do_softirq();
		ksoftirqd_run_end();
		cond_resched();
		return;
	}
	ksoftirqd_run_end();
}

// https://elixir.bootlin.com/linux/v5.15.139/source/kernel/softirq.c#L405
static inline void ksoftirqd_run_begin(void)
{
	local_irq_disable();
}

static inline void ksoftirqd_run_end(void)
{
	local_irq_enable();
}
```

其执行逻辑为：

1. 关闭所在 CPU 的硬中断。
2. 如果有待处理的软中断，则执行 __do_softirq() 函数处理。
3. 恢复所在 CPU 的硬中断。

这里最终会调用到 `__do_softirq()` 函数来执行具体的处理操作，我们在后续分析 Linux 收包流程时在详细研究。

Linux 支持如下类型的软中断：

```
$ cat /proc/softirqs
                    CPU0       CPU1
          HI:          1          0
       TIMER:   71111915  120166497
      NET_TX:          7         11
      NET_RX:   19292553   19371990
       BLOCK:    1805974   16211728
    IRQ_POLL:          0          0
     TASKLET:     153626     151427
       SCHED:  119862293  170637587
     HRTIMER:     482614     371796
         RCU:   65165801   66029526
```

其中网络有相关的软中断有两个：

- `NET_TX` 代表网络数据包的发送
- `NET_RX` 代表网络数据包的接收

为了能够处理这两类软中断，还需要为其注册处理函数，这一步在初始化网络设备子系统时完成。

### 初始化内核网络设备子系统

系统在启动时会执行网络设备子系统的初始化，由 subsys_initcall 调用 [net/core/dev.c](https://elixir.bootlin.com/linux/v5.15.139/source/net/core/dev.c#L11716)的 [net_dev_init（）](https://elixir.bootlin.com/linux/v5.15.139/source/net/core/dev.c#L11640)函数，其主要流程如下。

#### 注册 /proc/net/{dev/softnet_data/ptype}

首先会注册 /proc/net/ 下的伪文件信息，代码如下。

```c
static int __init net_dev_init(void)
{
	if (dev_proc_init())
		goto out;
		...
}
```

这样在系统启动后我们可以通过 `/proc/dev`看到相关的网络统计信息。主要有三种类型：

- `dev`：网卡接口统计信息，包括收发的数据包、字节数、丢包数等。

```
$ cat /proc/net/dev | column -t
Inter-|           Receive      |         Transmit
face              |bytes       packets   errs      drop  fifo  frame  compressed  multicast|bytes  packets     errs      drop  fifo  colls  carrier  compressed
lo:               2935050070   2601791   0         0     0     0      0           0                2935050070  2601791   0     0     0      0        0           0
eth0:             30656772745  25692220  0         0     0     0      0           0                7836773623  21772082  0     0     0      0        0           0
docker0:          0            0         0         0     0     0      0           0                0           0         0     0     0      0        0           0
br-f2a5dfa5547a:  1320746372   328165    0         0     0     0      0           0                1308994780  218407    0     0     0      0        0           0
vethd08c5d8:      1325340430   328159    0         0     0     0      0           0                1309054050  219256    0     0     0      0        0           0
```

- `softnet_stat`：每个 CPU 的软中断接收状态。每行代表一个 CPU。

```
$ cat /proc/net/softnet_stat | column -t
00c15138  00000000  00000000  00000000  00000000  00000000  00000000  00000000  00000000  00000000  00000000  00000000  00000000
00e9c405  00000000  00000002  00000000  00000000  00000000  00000000  00000000  00000000  00000000  00000000  00000000  00000001
```

- `ptype`：协议类型对应的处理函数。

```
$ cat /proc/net/ptype | column -t
Type  Device    Function
ALL   eth0      tpacket_rcv
ALL   eth0      tpacket_rcv
0800  ip_rcv
0004  llc_rcv   [llc]
0806  arp_rcv
86dd  ipv6_rcv
```

关于以上注册类型更详细的解释可以参考 [Monitoring and Tuning the Linux Networking Stack: Receiving Data](https://blog.packagecloud.io/monitoring-tuning-linux-networking-stack-receiving-data/)

#### 创建 softnet_data 数据结构

这里会为每个 CPU 创建 [softnet_data](https://elixir.bootlin.com/linux/v5.15.139/source/include/linux/netdevice.h#L3351) 数据结构。这是每个 CPU 都有的处理网络数据包的上下文结构，包括缓存 skb 的队列、要处理的设备列表等。

```c
static int __init net_dev_init(void)
{   // 注册 /proc/net/ 信息
	if (dev_proc_init())
		goto out;
	...
     // 针对每个 CPU，初始化各种数据结构
	for_each_possible_cpu(i) {
	    struct work_struct *flush = per_cpu_ptr(&flush_works, i);
	    // 1. 为每个 CPU 创建 softnet_data 数据结构
		struct softnet_data *sd = &per_cpu(softnet_data, i);

        // 初始化接收队列
		INIT_WORK(flush, flush_backlog);

		skb_queue_head_init(&sd->input_pkt_queue);
		skb_queue_head_init(&sd->process_queue);
#ifdef CONFIG_XFRM_OFFLOAD
		skb_queue_head_init(&sd->xfrm_backlog);
#endif
		INIT_LIST_HEAD(&sd->poll_list);
		sd->output_queue_tailp = &sd->output_queue;
#ifdef CONFIG_RPS
		INIT_CSD(&sd->csd, rps_trigger_softirq, sd);
		sd->cpu = i;
#endif
        // 初始化 GRO 哈希表
		init_gro_hash(&sd->backlog);
		sd->backlog.poll = process_backlog;
		sd->backlog.weight = weight_p;
	    ...
	}
...
out:
	return rc;
}
```

`softnet_data` 内有一个 poll_list 变量，用来保存
 网卡驱动
 注册的 poll 函数，网卡驱动在初始化时会将其 poll 函数添加到 poll_list 中。

```c
https://elixir.bootlin.com/linux/v5.15.139/source/include/linux/netdevice.h#L3351
/*
 * Incoming packets are placed on per-CPU queues
 */
struct softnet_data {
	struct list_head	poll_list;
	struct sk_buff_head	process_queue;
	...
}
```

#### 注册软中断函数

网络收发的软中断分别为 NET_RX 和 NET_TX：

- NET_RX 软中断注册处理函数为 net_rx_action
- NET_TX 注册的软中断处理函数为 net_tx_action

可以看到其注册方式就是中断类型作为 key，处理函数作为 value，保存到 [softirq_vec](https://elixir.bootlin.com/linux/v5.15.139/source/kernel/softirq.c#L59) 变量中。

```c
static int __init net_dev_init(void)
{

    // 为软中断注册处理函数
	open_softirq(NET_TX_SOFTIRQ, net_tx_action);
	open_softirq(NET_RX_SOFTIRQ, net_rx_action);

	rc = cpuhp_setup_state_nocalls(CPUHP_NET_DEV_DEAD, "net/dev:dead",
				       NULL, dev_cpu_dead);
	WARN_ON(rc < 0);
	rc = 0;
out:
	return rc;
}

// https://elixir.bootlin.com/linux/v5.15.139/source/kernel/softirq.c#L703
void open_softirq(int nr, void (*action)(struct softirq_action *))
{
	softirq_vec[nr].action = action;
}

// https://elixir.bootlin.com/linux/v5.15.139/source/kernel/softirq.c#L59
static struct softirq_action softirq_vec[NR_SOFTIRQS] __cacheline_aligned_in_smp;

DEFINE_PER_CPU(struct task_struct *, ksoftirqd);

const char * const softirq_to_name[NR_SOFTIRQS] = {
	"HI", "TIMER", "NET_TX", "NET_RX", "BLOCK", "IRQ_POLL",
	"TASKLET", "SCHED", "HRTIMER", "RCU"
};
```

上面我们提到软中断创建完成会执行 `_do_softirq` 函数来处理软中断，其 `h>action(h)` 就是调用这里注册的处理函数来处理软中断的。

### 注册协议栈

网络设备子系统初始化完成后，Linux 会注册 TCP/IP 网络协议栈。Linux通过 `fs_initcall` 调用 [inet_init](https://elixir.bootlin.com/linux/v5.15.139/source/net/ipv4/af_inet.c#L1934) 函数来注册协议栈。主要代码如下：

```c
// https://elixir.bootlin.com/linux/v5.15.139/source/net/ipv4/af_inet.c#L1934
static int __init inet_init(void)
{

	/*
	 *	Add all the base protocols.
	 *
	 * 注册 ICMP、UDP、TCP、IGMP 等协议的处理函数
	 */

	if (inet_add_protocol(&icmp_protocol, IPPROTO_ICMP) < 0)
		pr_crit("%s: Cannot add ICMP protocol\n", __func__);
	if (inet_add_protocol(&udp_protocol, IPPROTO_UDP) < 0)
		pr_crit("%s: Cannot add UDP protocol\n", __func__);
	if (inet_add_protocol(&tcp_protocol, IPPROTO_TCP) < 0)
		pr_crit("%s: Cannot add TCP protocol\n", __func__);
#ifdef CONFIG_IP_MULTICAST
	if (inet_add_protocol(&igmp_protocol, IPPROTO_IGMP) < 0)
		pr_crit("%s: Cannot add IGMP protocol\n", __func__);
#endif

    ...

    // 多种协议的初始化
	arp_init();
	ip_init();
	tcp_init();
	udp_init();
	udplite4_register();
	raw_init();
	ping_init();
	ipv4_proc_init();
	ipfrag_init();

    // 注册 IP 协议的处理函数
	dev_add_pack(&ip_packet_type);

	ip_tunnel_core_init();

	rc = 0;
out:
	return rc;
...
}

// 注册协议栈
fs_initcall(inet_init);
```

核心代码是下面几行，注册了 IP 协议以及 ICMP、UDP、TCP、IGMP 等协议的处理函数。

```c
inet_add_protocol(&icmp_protocol, IPPROTO_ICMP);
inet_add_protocol(&udp_protocol, IPPROTO_UDP);
inet_add_protocol(&tcp_protocol, IPPROTO_TCP);
inet_add_protocol(&igmp_protocol, IPPROTO_IGMP);
dev_add_pack(&ip_packet_type);
```

各种协议的定义信息如下：

```c
// https://elixir.bootlin.com/linux/v5.15.139/source/net/ipv4/af_inet.c#L1727
#ifdef CONFIG_IP_MULTICAST
static const struct net_protocol igmp_protocol = {
	.handler =	igmp_rcv,
};
#endif

static const struct net_protocol tcp_protocol = {
	.handler	=	tcp_v4_rcv,
	.err_handler	=	tcp_v4_err,
	.no_policy	=	1,
	.icmp_strict_tag_validation = 1,
};

static const struct net_protocol udp_protocol = {
	.handler =	udp_rcv,
	.err_handler =	udp_err,
	.no_policy =	1,
};

static const struct net_protocol icmp_protocol = {
	.handler =	icmp_rcv,
	.err_handler =	icmp_err,
	.no_policy =	1,
};

// https://elixir.bootlin.com/linux/v5.15.139/source/net/ipv4/af_inet.c#L1928
static struct packet_type ip_packet_type __read_mostly = {
	.type = cpu_to_be16(ETH_P_IP),
	.func = ip_rcv,
	.list_func = ip_list_rcv,
};
```

可以看到每种协议都注册了相应的处理函数:

- TCP 协议注册了 `tcp_v4_rcv` 作为处理函数。
- UDP 协议注册了 `udp_rcv` 作为处理函数。
- IP 协议注册了 `ip_rcv` 作为处理函数。

最终，ICMP、UDP、TCP、IGMP 协议通过 `inet_add_protocol` 函数被注册到 `inet_protocols` 数组中，而 IP 协议通过 `dev_add_pack` 函数被注册到 `ptype_base` 哈希表中。

- `inet_add_protocol` 注册函数

```c
// https://elixir.bootlin.com/linux/v5.15.139/source/net/ipv4/protocol.c#L32
int inet_add_protocol(const struct net_protocol *prot, unsigned char protocol)
{
	return !cmpxchg((const struct net_protocol **)&inet_protos[protocol],
			NULL, prot) ? 0 : -1;
```

- `dev_add_pack` 注册函数

```c
void dev_add_pack(struct packet_type *pt)
{
	struct list_head *head = ptype_head(pt);

	spin_lock(&ptype_lock);
	list_add_rcu(&pt->list, head);
	spin_unlock(&ptype_lock);
}

static inline struct list_head *ptype_head(const struct packet_type *pt)
{
	if (pt->type == htons(ETH_P_ALL))
		return pt->dev ? &pt->dev->ptype_all : &ptype_all;
	else
		return pt->dev ? &pt->dev->ptype_specific :
				 &ptype_base[ntohs(pt->type) & PTYPE_HASH_MASK];
}
```

Linux 在执行收包处理时，最终会根据上述注册信息找到 ip_rcv、 tcp_rcv 或 udp_rcv 等函数来处理，我们将在后续文章中分析其流程。

### 初始化网卡驱动

网卡需要驱动程序来与操作系统进行交互。驱动程序负责管理网卡的硬件资源，并提供一个抽象接口供上层协议栈使用。

我们可以通过 `proc` 信息或者 `ethtool` 命令查看本机网卡使用的驱动程序。可以看到我的腾讯云服务器用的是 [virtio_net](https://elixir.bootlin.com/linux/v5.15.139/source/drivers/net/virtio_net.c#L3471) 驱动，这是为虚拟化环境设计的驱动程序。

```bash
$ ip link show
1: lo: <LOOPBACK,UP,LOWER_UP> mtu 65536 qdisc noqueue state UNKNOWN mode DEFAULT group default qlen 1000
    link/loopback 00:00:00:00:00:00 brd 00:00:00:00:00:00
2: eth0: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 8500 qdisc mq state UP mode DEFAULT group default qlen 1000
    link/ether 52:54:00:1e:5e:c3 brd ff:ff:ff:ff:ff:ff
    altname enp0s5
    altname ens5
3: docker0: <NO-CARRIER,BROADCAST,MULTICAST,UP> mtu 1500 qdisc noqueue state DOWN mode DEFAULT group default
    link/ether ce:42:63:b6:d8:9c brd ff:ff:ff:ff:ff:ff
4: br-f2a5dfa5547a: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 qdisc noqueue state UP mode DEFAULT group default
    link/ether be:96:58:67:a1:91 brd ff:ff:ff:ff:ff:ff
9: vethd08c5d8@if2: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 qdisc noqueue master br-f2a5dfa5547a state UP mode DEFAULT group default
    link/ether 2a:62:64:aa:47:00 brd ff:ff:ff:ff:ff:ff link-netnsid 0

# 查看 /sys 信息
$ ls -l /sys/class/net/eth0/device/driver
lrwxrwxrwx 1 root root 0 Jul 25 11:11 /sys/class/net/eth0/device/driver -> ../../../../bus/virtio/drivers/virtio_net

# 使用 ethtool 命令查看
$ ethtool -i eth0
driver: virtio_net
version: 1.0.0
firmware-version:
expansion-rom-version:
bus-info: 0000:00:05.0
supports-statistics: yes
supports-test: no
supports-eeprom-access: no
supports-register-dump: no
supports-priv-flags: no
```

这是另一个数据中心机器的网卡驱动为 i40e，这是 Intel 推出的针对高性能网卡的驱动，带宽可以达到 40 Gbps。

```
$ ls -l /sys/class/net/eno1/device/driver
lrwxrwxrwx 1 root root 0 Jul 29  2024 /sys/class/net/eno1/device/driver -> ../../../../../../bus/pci/drivers/i40e
```

本系列文章我们以 i40e 驱动为例，分析其初始化过程和后续的收发包处理。

#### 注册 PCI 设备列表

PCI 设备通过 [PCI 配置空间](https://en.wikipedia.org/wiki/PCI_configuration_space#Standardized_registers) 中的一系列寄存器来标识自己。

当驱动程序编译时，使用名为 `MODULE_DEVICE_TABLE` 的宏会导出一个全局的 PCI 设备 ID 列表，用来标识该驱动支持的设备型号，内核会根据这些设备型号匹配对应的驱动程序。

```c
// https://elixir.bootlin.com/linux/v5.15.139/source/include/linux/module.h#L241
// 宏定义
#ifdef MODULE
/* Creates an alias so file2alias.c can find device table. */
#define MODULE_DEVICE_TABLE(type, name)					\
extern typeof(name) __mod_##type##__##name##_device_table		\
  __attribute__ ((unused, alias(__stringify(name))))
#else  /* !MODULE */
#define MODULE_DEVICE_TABLE(type, name)
#endif
```

i40e 支持的设备列表和 PCI 设备 ID 分别定义在 [i40e_devids.h](https://elixir.bootlin.com/linux/v5.15.139/source/drivers/net/ethernet/intel/i40e/i40e_devids.h#L14) 和 [i40e_main.c](https://elixir.bootlin.com/linux/v5.15.139/source/drivers/net/ethernet/intel/i40e/i40e_main.c#L61) 中。

```c
// https://elixir.bootlin.com/linux/v5.15.139/source/drivers/net/ethernet/intel/i40e/i40e_devids.h#L14
/* SPDX-License-Identifier: GPL-2.0 */
/* Copyright(c) 2013 - 2018 Intel Corporation. */

#ifndef _I40E_DEVIDS_H_
#define _I40E_DEVIDS_H_

/* Device IDs */
#define I40E_DEV_ID_X710_N3000		0x0CF8
#define I40E_DEV_ID_XXV710_N3000	0x0D58
#define I40E_DEV_ID_SFP_XL710		0x1572
#define I40E_DEV_ID_QEMU		0x1574
#define I40E_DEV_ID_KX_B		0x1580
#define I40E_DEV_ID_KX_C		0x1581
#define I40E_DEV_ID_QSFP_A		0x1583
#define I40E_DEV_ID_QSFP_B		0x1584
#define I40E_DEV_ID_QSFP_C		0x1585
#define I40E_DEV_ID_10G_BASE_T		0x1586
#define I40E_DEV_ID_20G_KR2		0x1587
#define I40E_DEV_ID_20G_KR2_A		0x1588
#define I40E_DEV_ID_10G_BASE_T4		0x1589
#define I40E_DEV_ID_25G_B		0x158A
#define I40E_DEV_ID_25G_SFP28		0x158B
#define I40E_DEV_ID_10G_BASE_T_BC	0x15FF
#define I40E_DEV_ID_10G_B		0x104F
#define I40E_DEV_ID_10G_SFP		0x104E
#define I40E_DEV_ID_5G_BASE_T_BC	0x101F
#define I40E_IS_X710TL_DEVICE(d) \
	(((d) == I40E_DEV_ID_5G_BASE_T_BC) || \
	 ((d) == I40E_DEV_ID_10G_BASE_T_BC))
#define I40E_DEV_ID_KX_X722		0x37CE
#define I40E_DEV_ID_QSFP_X722		0x37CF
#define I40E_DEV_ID_SFP_X722		0x37D0
#define I40E_DEV_ID_1G_BASE_T_X722	0x37D1
#define I40E_DEV_ID_10G_BASE_T_X722	0x37D2
#define I40E_DEV_ID_SFP_I_X722		0x37D3

#endif /* _I40E_DEVIDS_H_ */

// https://elixir.bootlin.com/linux/v5.15.139/source/drivers/net/ethernet/intel/i40e/i40e_main.c#L61
// 驱动支持的 PCI 设备 ID 列表
/* i40e_pci_tbl - PCI Device ID Table
 *
 * Last entry must be all 0s
 *
 * { Vendor ID, Device ID, SubVendor ID, SubDevice ID,
 *   Class, Class Mask, private data (not used) }
 */
static const struct pci_device_id i40e_pci_tbl[] = {
	{PCI_VDEVICE(INTEL, I40E_DEV_ID_SFP_XL710), 0},
	{PCI_VDEVICE(INTEL, I40E_DEV_ID_QEMU), 0},
	{PCI_VDEVICE(INTEL, I40E_DEV_ID_KX_B), 0},
	{PCI_VDEVICE(INTEL, I40E_DEV_ID_KX_C), 0},
	{PCI_VDEVICE(INTEL, I40E_DEV_ID_QSFP_A), 0},
	{PCI_VDEVICE(INTEL, I40E_DEV_ID_QSFP_B), 0},
	{PCI_VDEVICE(INTEL, I40E_DEV_ID_QSFP_C), 0},
	{PCI_VDEVICE(INTEL, I40E_DEV_ID_10G_BASE_T), 0},
	{PCI_VDEVICE(INTEL, I40E_DEV_ID_10G_BASE_T4), 0},
	{PCI_VDEVICE(INTEL, I40E_DEV_ID_10G_BASE_T_BC), 0},
	{PCI_VDEVICE(INTEL, I40E_DEV_ID_10G_SFP), 0},
	{PCI_VDEVICE(INTEL, I40E_DEV_ID_10G_B), 0},
	{PCI_VDEVICE(INTEL, I40E_DEV_ID_KX_X722), 0},
	{PCI_VDEVICE(INTEL, I40E_DEV_ID_QSFP_X722), 0},
	{PCI_VDEVICE(INTEL, I40E_DEV_ID_SFP_X722), 0},
	{PCI_VDEVICE(INTEL, I40E_DEV_ID_1G_BASE_T_X722), 0},
	{PCI_VDEVICE(INTEL, I40E_DEV_ID_10G_BASE_T_X722), 0},
	{PCI_VDEVICE(INTEL, I40E_DEV_ID_SFP_I_X722), 0},
	{PCI_VDEVICE(INTEL, I40E_DEV_ID_20G_KR2), 0},
	{PCI_VDEVICE(INTEL, I40E_DEV_ID_20G_KR2_A), 0},
	{PCI_VDEVICE(INTEL, I40E_DEV_ID_X710_N3000), 0},
	{PCI_VDEVICE(INTEL, I40E_DEV_ID_XXV710_N3000), 0},
	{PCI_VDEVICE(INTEL, I40E_DEV_ID_25G_B), 0},
	{PCI_VDEVICE(INTEL, I40E_DEV_ID_25G_SFP28), 0},
	/* required last entry */
	{0, }
};
MODULE_DEVICE_TABLE(pci, igb_pci_tbl);
```

#### 注册驱动：module_init–> pci_register_driver

所有类型的驱动都需要通过 `module_init` 宏来向内核注册其初始化函数，当内核加载驱动时会调用该函数进行初始化。i40e 的初始化函数是 [i40e_init_module](https://elixir.bootlin.com/linux/v5.15.139/source/drivers/net/ethernet/intel/i40e/i40e_main.c#L16660) ，代码如下：

```c
// https://elixir.bootlin.com/linux/v5.15.139/source/drivers/net/ethernet/intel/i40e/i40e_main.c#L16660

/**
 * i40e_init_module - Driver registration routine
 *
 * i40e_init_module is the first routine called when the driver is
 * loaded. All it does is register with the PCI subsystem.
 **/
static int __init i40e_init_module(void)
{
	int err;

	pr_info("%s: %s\n", i40e_driver_name, i40e_driver_string);
	pr_info("%s: %s\n", i40e_driver_name, i40e_copyright);

	/* There is no need to throttle the number of active tasks because
	 * each device limits its own task using a state bit for scheduling
	 * the service task, and the device tasks do not interfere with each
	 * other, so we don't set a max task limit. We must set WQ_MEM_RECLAIM
	 * since we need to be able to guarantee forward progress even under
	 * memory pressure.
	 */
	i40e_wq = alloc_workqueue("%s", WQ_MEM_RECLAIM, 0, i40e_driver_name);
	if (!i40e_wq) {
		pr_err("%s: Failed to create workqueue\n", i40e_driver_name);
		return -ENOMEM;
	}

	i40e_dbg_init();
	err = pci_register_driver(&i40e_driver);
	if (err) {
		destroy_workqueue(i40e_wq);
		i40e_dbg_exit();
		return err;
	}

	return 0;
}
module_init(i40e_init_module);
```

具体的注册流程是在 pci_register_driver 函数执行，我们来看下驱动信息的格式：

```c
// https://elixir.bootlin.com/linux/v5.15.139/source/drivers/net/ethernet/intel/i40e/i40e_main.c#L16641

static struct pci_driver i40e_driver = {
	.name     = i40e_driver_name,
	.id_table = i40e_pci_tbl,
	.probe    = i40e_probe,
	.remove   = i40e_remove,
	.driver   = {
		.pm = &i40e_pm_ops,
	},
	.shutdown = i40e_shutdown,
	.err_handler = &i40e_err_handler,
	.sriov_configure = i40e_pci_sriov_configure,
};

// https://elixir.bootlin.com/linux/v5.15.139/source/drivers/net/ethernet/intel/i40e/i40e_main.c#L24
// 驱动基本信息
const char i40e_driver_name[] = "i40e";
static const char i40e_driver_string[] =
			"Intel(R) Ethernet Connection XL710 Network Driver";

static const char i40e_copyright[] = "Copyright (c) 2013 - 2019 Intel Corporation.";
```

这里简要解释下几个字段的含义：

- **name**：标识驱动的字符串名称，在 `/sys/bus/pci/drivers/` 目录下会创建一个以该名称命名的目录，里面包含了驱动的相关信息。`$ ls /sys/bus/pci/drivers/
8250_mid i40e lpc_ich serial`
- **id_table**：驱动支持的设备 ID 列表。只有匹配到这些设备时才会初始化驱动。
- **probe**：驱动的初始化函数，当匹配到设备时会调用该函数进行初始化。
- **remove**：驱动的卸载函数，当设备被移除时会调用该函数进行清理。

#### 加载驱动：i40e_probe

网卡驱动注册后，内核在启动时会根据其注册的设备 ID 列表去搜索匹配相关网卡硬件，如果匹配则调用驱动的 probe 函数执行网卡驱动的初始化任务，对于 i40e 驱动其初始化函数为 [i40e_probe](https://elixir.bootlin.com/linux/v5.15.139/source/drivers/net/ethernet/intel/i40e/i40e_main.c#L15577)。

i40e_probe 函数比较冗长，这里我们只关注几个最关键的步骤：

- PCI 设备初始化
- 获取 MAC 地址
- 初始化 VSI
- 网络设备初始化
- net_device_ops 注册
- ethtool 注册
- NAPI 初始化
- 网卡启动

我们来详细看下上述几个步骤的实现：

##### PCI 设备初始化

这一步会将唤醒 PCI 设备，启用内存资源，然后 `dma_set_mask_and_coherent` 方法是为设备设置 DMA 掩码，参数是 `DMA_BIT_MASK(64)`，因此网卡可以访问 64 位内存地址。

之后会为网卡申请内存区域，并开启错误报告、DMA 功能等特性。代码如下：

```c
// https://elixir.bootlin.com/linux/v5.15.139/source/drivers/net/ethernet/intel/i40e/i40e_main.c#L15577

static int i40e_probe(struct pci_dev *pdev, const struct pci_device_id *ent)
{
    ...
	// // 启用PCI设备的内存访问功能
	err = pci_enable_device_mem(pdev);
	if (err)
		return err;

	/* set up for high or low dma */
	// 设置DMA掩码 - 优先尝试64位DMA，如果不支持则降级为 32 位
	err = dma_set_mask_and_coherent(&pdev->dev, DMA_BIT_MASK(64));
	if (err) {
		err = dma_set_mask_and_coherent(&pdev->dev, DMA_BIT_MASK(32));
		if (err) {
			dev_err(&pdev->dev,
				"DMA configuration failed: 0x%x\n", err);
			goto err_dma;
		}
	}

	/* set up pci connections */
	// 请求内存区域
	err = pci_request_mem_regions(pdev, i40e_driver_name);
	if (err) {
		dev_info(&pdev->dev,
			 "pci_request_selected_regions failed %d\n", err);
		goto err_pci_reg;
	}
    // 启用错误报告
	pci_enable_pcie_error_reporting(pdev);
	// 启用 DMA 传输
	pci_set_master(pdev);
```

##### 获取 MAC 地址

经过 PCI 设备初始化以及一些其他初始化步骤后，驱动会尝试获取网卡的 MAC 地址。

```c
https://elixir.bootlin.com/linux/v5.15.139/source/drivers/net/ethernet/intel/i40e/i40e_main.c#L15830
static int i40e_probe(struct pci_dev *pdev, const struct pci_device_id *ent)
{
	...
	// 从平台获取 MAC 地址
	i40e_get_platform_mac_addr(pdev, pf);
    // 检查是否有效
	if (!is_valid_ether_addr(hw->mac.addr)) {
		dev_info(&pdev->dev, "invalid MAC address %pM\n", hw->mac.addr);
		err = -EIO;
		goto err_mac_addr;
	}
	// 打印 MAC 地址
	dev_info(&pdev->dev, "MAC address: %pM\n", hw->mac.addr);
	// 将当前 MAC 地址复制到永久地址字段
	ether_addr_copy(hw->mac.perm_addr, hw->mac.addr);
	// 获取端口特定的 MAC 地址（
	i40e_get_port_mac_addr(hw, hw->mac.port_addr);
	if (is_valid_ether_addr(hw->mac.port_addr))
		pf->hw_features |= I40E_HW_PORT_ID_VALID;
	...
}
```

##### 以太网初始化

PCI 设备初始化完成后，会进行以太网的初始化，主要是创建内核抽象的网络设备，并执行一系列的注册操作。

Linux 内核定义了 [net_device](https://elixir.bootlin.com/linux/v5.15.139/source/include/linux/netdevice.h#L1974)
 结构体
来表示网络设备，驱动程序初始化时会创建该结构体实例，并为其标识硬件特性、注册 net_dev_ops、ethtool_ops 等操作函数，也会为其注册 NAPI。

net_device 的创建是在 [i40e_config_netdev(](https://elixir.bootlin.com/linux/v5.15.139/source/drivers/net/ethernet/intel/i40e/i40e_main.c#L13668) 函数实现的，整体调用栈如下：

```
i40e_probe()
└── i40e_setup_pf_switch()
    └── i40e_vsi_setup()
	        └── i40e_set_num_rings_in_vsi // 设置 VSI 的队列数量
	        └── i40e_vsi_mem_alloc() // 初始化 VSI
			     └── i40e_vsi_setup_irqhandler() 初始化 IRQ 处理函数
            └── i40e_config_netdev()
                    └── netdev->netdev_ops = &i40e_netdev_ops;  // 注册 net_device_ops
					└── i40e_set_ethtool_ops(netdev); // 注册 ethtool_ops
			└── i40e_vsi_setup_vectors(vsi);
				└── i40e_vsi_alloc_q_vectors()
				└── netif_napi_add()  // 注册 NAPI poll 方法
			└── i40e_alloc_rings(vsi);
			└── i40e_vsi_map_rings_to_vectors(vsi); // 分配中断向量和队列，并绑定
```

###### 初始化VSI

VSI（Virtual Station Interface）是虚拟化环境中用于网络数据包处理的虚拟接口。每个 VSI 对应一个虚拟网络设备，负责处理与该设备相关的网络流量。一张网卡可以支持多个 VSI，每个 VSI 有独立的队列、中断向量、MAC地址等资源。

这一阶段 i40e 会创建 VSI 并为其分配内存，初始化向量、队列、中断处理函数等。

**设置队列数量**

这里调用 [i40e_set_num_rings_in_vsi](https://elixir.bootlin.com/linux/v5.15.139/source/drivers/net/ethernet/intel/i40e/i40e_main.c#L11313) 函数，根据 VIS 类型、MSIX 特性支持等条件确定缓冲队列，即 RingBuffer 的数量，在网卡启动时会根据这里的数量创建队列。

**初始化硬中断处理函数**

[i40e_vsi_mem_alloc](https://elixir.bootlin.com/linux/v5.15.139/source/drivers/net/ethernet/intel/i40e/i40e_main.c#L11427)会进行一系列的初始化操作，其中会调用 [i40e_vsi_setup_irqhandler](https://elixir.bootlin.com/linux/v5.15.139/source/drivers/net/ethernet/intel/i40e/i40e_main.c#L11493) 来初始化硬中断处理函数，逻辑如下：

```c
// https://elixir.bootlin.com/linux/v5.15.139/source/drivers/net/ethernet/intel/i40e/i40e_main.c#L11493
static int i40e_vsi_mem_alloc(struct i40e_pf *pf, enum i40e_vsi_type type)
{
    ...

	/* Setup default MSIX irq handler for VSI */
	i40e_vsi_setup_irqhandler(vsi, i40e_msix_clean_rings);
    ...
}

// https://elixir.bootlin.com/linux/v5.15.139/source/drivers/net/ethernet/intel/i40e/i40e.h#L1040

static inline void i40e_vsi_setup_irqhandler(struct i40e_vsi *vsi,
				irqreturn_t (*irq_handler)(int, void *))
{
	vsi->irq_handler = irq_handler;
}
```

可以看到，i40e 驱动使用的 IRQ 处理函数为 [i40e_msix_clean_rings()](https://elixir.bootlin.com/linux/v5.15.139/source/drivers/net/ethernet/intel/i40e/i40e_main.c#L4039)，在网卡启动时，会将这里初始化的 IRQ 处理函数注册到中断向量中。

###### 创建 net_device

这一步会创建抽象的 net_device 结构体，代表网络设备。

```c
// https://elixir.bootlin.com/linux/v5.15.139/source/drivers/net/ethernet/intel/i40e/i40e_main.c#L13681
/**
 * i40e_config_netdev - Setup the netdev flags
 * @vsi: the VSI being configured
 *
 * Returns 0 on success, negative value on failure
 **/
static int i40e_config_netdev(struct i40e_vsi *vsi)
{
	struct i40e_pf *pf = vsi->back;
	struct i40e_hw *hw = &pf->hw;
	struct i40e_netdev_priv *np;
	// net_device 指针
	struct net_device *netdev;
	u8 broadcast[ETH_ALEN];
	u8 mac_addr[ETH_ALEN];
	int etherdev_size;
	netdev_features_t hw_enc_features;
	netdev_features_t hw_features;

	etherdev_size = sizeof(struct i40e_netdev_priv);
	// 分配 net_device 结构体
	netdev = alloc_etherdev_mq(etherdev_size, vsi->alloc_queue_pairs);
	if (!netdev)
		return -ENOMEM;

    // 关联 net_device 和 VSI
	vsi->netdev = netdev;
	...
```

###### 定义硬件相关特性

netdev 创建完成后，会为其定义一系列硬件相关特性，这些特性会在网络数据包处理时被用到。下面是一些常见特性的设置，包括：

- 配置 TCP/UDP 校验和、TSO、GSO 等硬件卸载功能。
- 启用 VXLAN、GRE 等隧道协议的硬件处理
- 配置硬件 VLAN 标签处理能力

```c
// https://elixir.bootlin.com/linux/v5.15.139/source/drivers/net/ethernet/intel/i40e/i40e_main.c#L13681

netdev = alloc_etherdev_mq(etherdev_size, vsi->alloc_queue_pairs);
	if (!netdev)
		return -ENOMEM;

	vsi->netdev = netdev;
	np = netdev_priv(netdev);
	np->vsi = vsi;

    // 定义硬件加密卸载功能特性
	// 这些特性可以被硬件直接处理，减少 CPU 负载
	hw_enc_features = NETIF_F_SG			|  // 支持分散-聚集 DMA
			  NETIF_F_IP_CSUM		|  // IPv4 校验和卸载
			  NETIF_F_IPV6_CSUM		|  // IPv6 校验和卸载
			  NETIF_F_HIGHDMA		|  // 支持高内存 DMA (>4GB)
			  NETIF_F_SOFT_FEATURES		|  // 软件功能特性集合
			  NETIF_F_TSO			|  // TCP 分段卸载 (IPv4)
			  NETIF_F_TSO_ECN		|  // TSO 支持 ECN 标记
			  NETIF_F_TSO6			|  // TCP 分段卸载 (IPv6)
			  NETIF_F_GSO_GRE		|  // GRE 通用分段卸载
			  NETIF_F_GSO_GRE_CSUM		|  // GRE 校验和分段卸载
			  NETIF_F_GSO_PARTIAL		|  // 部分 GSO 支持
			  NETIF_F_GSO_IPXIP4		|  // IP-in-IP (IPv4) GSO
			  NETIF_F_GSO_IPXIP6		|  // IP-in-IP (IPv6) GSO
			  NETIF_F_GSO_UDP_TUNNEL	|  // UDP 隧道 GSO
			  NETIF_F_GSO_UDP_TUNNEL_CSUM	|  // UDP 隧道校验和 GSO
			  NETIF_F_GSO_UDP_L4		|  // UDP L4 GSO
			  NETIF_F_SCTP_CRC		|  // SCTP CRC 校验和卸载
			  NETIF_F_RXHASH		|  // 接收哈希（RSS）支持
			  NETIF_F_RXCSUM		|  // 接收校验和验证
			  0;                             // 结束标记

	if (!(pf->hw_features & I40E_HW_OUTER_UDP_CSUM_CAPABLE))
		netdev->gso_partial_features |= NETIF_F_GSO_UDP_TUNNEL_CSUM;

    // 设置 UDP 隧道网卡信息，用于 VXLAN、GENEVE 等隧道协议
	netdev->udp_tunnel_nic_info = &pf->udp_tunnel_nic;

    // 总是将 GRE 校验和作为部分 GSO 功能
	netdev->gso_partial_features |= NETIF_F_GSO_GRE_CSUM;

    // 将定义的加密功能添加到硬件加密功能列表中
	netdev->hw_enc_features |= hw_enc_features;

	/* record features VLANs can make use of */
	// 设置 VLAN 可以使用的功能特性
	netdev->vlan_features |= hw_enc_features | NETIF_F_TSO_MANGLEID;

	/* enable macvlan offloads */
	// 启用 MACVLAN 卸载功能，允许硬件处理 MACVLAN 转发
	netdev->hw_features |= NETIF_F_HW_L2FW_DOFFLOAD;

   // 定义基本的硬件功能特性
	hw_features = hw_enc_features		| // 加密特性
		      NETIF_F_HW_VLAN_CTAG_TX	|  // VLAN 发送标记
		      NETIF_F_HW_VLAN_CTAG_RX;    // VLAN 接收标记

	if (!(pf->flags & I40E_FLAG_MFP_ENABLED))
		hw_features |= NETIF_F_NTUPLE | NETIF_F_HW_TC;

   // 将定义的硬件功能添加到网络设备的硬件功能列表
	netdev->hw_features |= hw_features;

	netdev->features |= hw_features | NETIF_F_HW_VLAN_CTAG_FILTER;
	netdev->hw_enc_features |= NETIF_F_TSO_MANGLEID;
```

###### 注册 net_device_ops

`net_device_ops` 是 Linux 定义的一个函数指针结构体，里面规定了针对网络设备的所有操作函数，相当于给网络设备驱动程序提供了标准化的操作接口，所有网络驱动都必须实现这一套接口。完整代码参考 [struct net_device_ops](https://elixir.bootlin.com/linux/v5.15.139/source/include/linux/netdevice.h#L1374)，下面只列出了一些常用功能对应的处理函数：

```c
// https://elixir.bootlin.com/linux/v5.15.139/source/include/linux/netdevice.h#L1374
/*
 * This structure defines the management hooks for network devices.
 * The following hooks can be defined; unless noted otherwise, they are
 * optional and can be filled with a null pointer.
 */
struct net_device_ops {

	// 启动网卡
	int	(*ndo_open)(struct net_device *dev);
	// 停止网卡
	int	(*ndo_stop)(struct net_device *dev);
	// 发送数据包
	netdev_tx_t	(*ndo_start_xmit)(struct sk_buff *skb, struct net_device *dev);
    // 获取网络统计信息
	void(*ndo_get_stats64)(struct net_device *dev, struct rtnl_link_stats64 *storage);
	// 修改 MTU 大小
	int	(*ndo_change_mtu)(struct net_device *dev, int new_mtu);
	// 设置 MAC 地址
	int	(*ndo_set_mac_address)(struct net_device *dev, void *addr);
	...
};
```

`i40e` 网络驱动实现了上述接口，完整代码如下，可以看到网卡启动函数为 `i40e_open`，这个我们在网卡启动时还会看到。

```c
// https://elixir.bootlin.com/linux/v5.15.139/source/drivers/net/ethernet/intel/i40e/i40e_main.c#L13623
static const struct net_device_ops i40e_netdev_ops = {
	.ndo_open		= i40e_open,
	.ndo_stop		= i40e_close,
	.ndo_start_xmit		= i40e_lan_xmit_frame,
	.ndo_get_stats64	= i40e_get_netdev_stats_struct,
	.ndo_set_rx_mode	= i40e_set_rx_mode,
	.ndo_validate_addr	= eth_validate_addr,
	.ndo_set_mac_address	= i40e_set_mac,
	.ndo_change_mtu		= i40e_change_mtu,
	.ndo_eth_ioctl		= i40e_ioctl,
	.ndo_tx_timeout		= i40e_tx_timeout,
	.ndo_vlan_rx_add_vid	= i40e_vlan_rx_add_vid,
	.ndo_vlan_rx_kill_vid	= i40e_vlan_rx_kill_vid,
#ifdef CONFIG_NET_POLL_CONTROLLER
	.ndo_poll_controller	= i40e_netpoll,
#endif
	.ndo_setup_tc		= __i40e_setup_tc,
	.ndo_select_queue	= i40e_lan_select_queue,
	.ndo_set_features	= i40e_set_features,
	.ndo_set_vf_mac		= i40e_ndo_set_vf_mac,
	.ndo_set_vf_vlan	= i40e_ndo_set_vf_port_vlan,
	.ndo_get_vf_stats	= i40e_get_vf_stats,
	.ndo_set_vf_rate	= i40e_ndo_set_vf_bw,
	.ndo_get_vf_config	= i40e_ndo_get_vf_config,
	.ndo_set_vf_link_state	= i40e_ndo_set_vf_link_state,
	.ndo_set_vf_spoofchk	= i40e_ndo_set_vf_spoofchk,
	.ndo_set_vf_trust	= i40e_ndo_set_vf_trust,
	.ndo_get_phys_port_id	= i40e_get_phys_port_id,
	.ndo_fdb_add		= i40e_ndo_fdb_add,
	.ndo_features_check	= i40e_features_check,
	.ndo_bridge_getlink	= i40e_ndo_bridge_getlink,
	.ndo_bridge_setlink	= i40e_ndo_bridge_setlink,
	.ndo_bpf		= i40e_xdp,
	.ndo_xdp_xmit		= i40e_xdp_xmit,
	.ndo_xsk_wakeup	        = i40e_xsk_wakeup,
	.ndo_dfwd_add_station	= i40e_fwd_add,
	.ndo_dfwd_del_station	= i40e_fwd_del,
};
```

在 [i40e_config_netdev()](https://elixir.bootlin.com/linux/v5.15.139/source/drivers/net/ethernet/intel/i40e/i40e_main.c#L13668) 函数中会完成的 net_dev_ops 的注册，相关代码如下：

```c
static int i40e_config_netdev(struct i40e_vsi *vsi)
{
	...
    // 注册 net_device_Ops
	netdev->netdev_ops = &i40e_netdev_ops;
	netdev->watchdog_timeo = 5 * HZ;
	// 注册 net_dev_ethtool_ops
	i40e_set_ethtool_ops(netdev);

	/* MTU range: 68 - 9706 */
	netdev->min_mtu = ETH_MIN_MTU;
	netdev->max_mtu = I40E_MAX_RXBUFFER - I40E_PACKET_HDR_PAD;

	return 0;
}
```

###### 注册 ethtool 操作函数

在 [i40e_config_netdev()](https://elixir.bootlin.com/linux/v5.15.139/source/drivers/net/ethernet/intel/i40e/i40e_main.c#L13668) 函数，还有一行代码 `i40e_set_ethtool_ops(netdev);`，这是用来 ethtool 的操作函数的。

ethtool 是用来查看和修改网卡配置的命令行工具，和 net_device_ops 一样，内核也定义了一系列的函数，网卡驱动实现这些函数后就可以通过 ethtool 来查看修改网卡的配置。

Linux 的接口定义和 i40e 的实现如下：

```c
// Linux 定义
// https://elixir.bootlin.com/linux/v5.15.139/source/include/linux/ethtool.h#L418
struct ethtool_ops {
	u32     cap_link_lanes_supported:1;
	u32	supported_coalesce_params;
	void	(*get_drvinfo)(struct net_device *, struct ethtool_drvinfo *);
	int	(*get_regs_len)(struct net_device *);
	void	(*get_regs)(struct net_device *, struct ethtool_regs *, void *);
	void	(*get_wol)(struct net_device *, struct ethtool_wolinfo *);
	int	(*set_wol)(struct net_device *, struct ethtool_wolinfo *);
	u32	(*get_msglevel)(struct net_device *);
	void	(*set_msglevel)(struct net_device *, u32);
	int	(*nway_reset)(struct net_device *);
	u32	(*get_link)(struct net_device *);
	int	(*get_link_ext_state)(struct net_device *,
				      struct ethtool_link_ext_state_info *);
	int	(*get_eeprom_len)(struct net_device *);
	int	(*get_eeprom)(struct net_device *,
			      struct ethtool_eeprom *, u8 *);
	int	(*set_eeprom)(struct net_device *,
			      struct ethtool_eeprom *, u8 *);
	...
};

// i40e 实现
// https://elixir.bootlin.com/linux/v5.15.139/source/drivers/net/ethernet/intel/i40e/i40e_ethtool.c#L5658
static const struct ethtool_ops i40e_ethtool_ops = {
	.supported_coalesce_params = ETHTOOL_COALESCE_USECS |
				     ETHTOOL_COALESCE_MAX_FRAMES_IRQ |
				     ETHTOOL_COALESCE_USE_ADAPTIVE |
				     ETHTOOL_COALESCE_RX_USECS_HIGH |
				     ETHTOOL_COALESCE_TX_USECS_HIGH,
	.get_drvinfo		= i40e_get_drvinfo,
	.get_regs_len		= i40e_get_regs_len,
	.get_regs		= i40e_get_regs,
	.nway_reset		= i40e_nway_reset,
	.get_link		= ethtool_op_get_link,
	.get_wol		= i40e_get_wol,
	.set_wol		= i40e_set_wol,
	.set_eeprom		= i40e_set_eeprom,
	.get_eeprom_len		= i40e_get_eeprom_len,
	.get_eeprom		= i40e_get_eeprom,
	.get_ringparam		= i40e_get_ringparam,
	.set_ringparam		= i40e_set_ringparam,
	.get_pauseparam		= i40e_get_pauseparam,
	.set_pauseparam		= i40e_set_pauseparam,
	.get_msglevel		= i40e_get_msglevel,
	.set_msglevel		= i40e_set_msglevel,
	.get_rxnfc		= i40e_get_rxnfc,
	.set_rxnfc		= i40e_set_rxnfc,
	.self_test		= i40e_diag_test,
	.get_strings		= i40e_get_strings,
	.get_eee		= i40e_get_eee,
	.set_eee		= i40e_set_eee,
	.set_phys_id		= i40e_set_phys_id,
	.get_sset_count		= i40e_get_sset_count,
	.get_ethtool_stats	= i40e_get_ethtool_stats,
	.get_coalesce		= i40e_get_coalesce,
	.set_coalesce		= i40e_set_coalesce,
	.get_rxfh_key_size	= i40e_get_rxfh_key_size,
	.get_rxfh_indir_size	= i40e_get_rxfh_indir_size,
	.get_rxfh		= i40e_get_rxfh,
	.set_rxfh		= i40e_set_rxfh,
	.get_channels		= i40e_get_channels,
	.set_channels		= i40e_set_channels,
	.get_module_info	= i40e_get_module_info,
	.get_module_eeprom	= i40e_get_module_eeprom,
	.get_ts_info		= i40e_get_ts_info,
	.get_priv_flags		= i40e_get_priv_flags,
	.set_priv_flags		= i40e_set_priv_flags,
	.get_per_queue_coalesce	= i40e_get_per_queue_coalesce,
	.set_per_queue_coalesce	= i40e_set_per_queue_coalesce,
	.get_link_ksettings	= i40e_get_link_ksettings,
	.set_link_ksettings	= i40e_set_link_ksettings,
	.get_fecparam = i40e_get_fec_param,
	.set_fecparam = i40e_set_fec_param,
	.flash_device = i40e_ddp_flash,
};
```

最终在 `i40e_set_ethtool_ops` 函数中完成注册：

```c
void i40e_set_ethtool_ops(struct net_device *netdev)
{
	struct i40e_netdev_priv *np = netdev_priv(netdev);
	struct i40e_pf		*pf = np->vsi->back;

	if (!test_bit(__I40E_RECOVERY_MODE, pf->state))
		netdev->ethtool_ops = &i40e_ethtool_ops;
	else
		netdev->ethtool_ops = &i40e_ethtool_recovery_mode_ops;
}
```

这样我们执行命令时就会调用相应的函数，比如执行 `ethtool -S eth0` 就会调用 i40e 驱动的 `i40e_get_ethtool_stats` 函数来获取相关统计信息。

```shell
$ ethtool -S eth0
NIC statistics:
     rx_queue_0_packets: 13542096
     rx_queue_0_bytes: 3997050818
     rx_queue_0_drops: 0
     rx_queue_0_xdp_packets: 0
     rx_queue_0_xdp_tx: 0
     rx_queue_0_xdp_redirects: 0
     rx_queue_0_xdp_drops: 0
     rx_queue_0_kicks: 5
     rx_queue_1_packets: 16117078
     rx_queue_1_bytes: 28092443956
     rx_queue_1_drops: 0
     rx_queue_1_xdp_packets: 0
     rx_queue_1_xdp_tx: 0
     rx_queue_1_xdp_redirects: 0
     rx_queue_1_xdp_drops: 0
     rx_queue_1_kicks: 19
     tx_queue_0_packets: 12617077
     tx_queue_0_bytes: 4545453868
     tx_queue_0_xdp_tx: 0
     tx_queue_0_xdp_tx_drops: 0
     tx_queue_0_kicks: 11321447
     tx_queue_1_packets: 12421775
     tx_queue_1_bytes: 3816676688
     tx_queue_1_xdp_tx: 0
     tx_queue_1_xdp_tx_drops: 0
     tx_queue_1_kicks: 11235062
```

###### 初始化向量，注册 NAPI poll 方法

正常情况下，当数据包到来时，网卡通过硬中断的方式通知 CPU 处理数据是没有问题的。但随着网络带宽、吞吐量的不断升高，传统的中断方式逐渐不再适应。假设 MTU 是 1460byte，在千兆以太网下，可能每秒有近 10 万次的中断，这会导致 CPU 一直忙于处理硬中断从而没办法做别的事情。

为了解决该问题，从 Linux 内核 2.6 开始引入了 NAPI 机制，其核心思想是 **通过轮询而不是中断的方式去读取数据包**，其工作过程大致如下，详细过程我们会在后续章节中介绍。

- 网卡驱动初始化时会注册 poll 函数
- 数据到来时会判断是否有 poll 函数运行
- 如果有，则通过 poll 函数进行数据包的处理，从而避免触发硬中断
- 如果没有，则触发硬中断，CPU 进入中断流程处理，并在后续的处理中唤醒 poll 函数

在 i40e_probe 中，i40e 会注册自己的 poll NAPI 函数，调用栈如下：

```
i40e_probe()
└── i40e_setup_pf_switch()
    └── i40e_vsi_setup()

			└── i40e_vsi_setup_vectors(vsi);
				└── i40e_vsi_alloc_q_vectors()
				└── netif_napi_add()  // 注册 NAPI poll 方法
			└── i40e_alloc_rings(vsi);
			└── i40e_vsi_map_rings_to_vectors(vsi); // 分配中断向量和队列，并绑定
```

在设置向量时，最终是通过 [netif_napi_add](https://elixir.bootlin.com/linux/v5.15.139/source/net/core/dev.c#L6909) 函数完成注册，每个向量都会有自己的 NAPI poll 方法。

```c
https://elixir.bootlin.com/linux/v5.15.139/source/drivers/net/ethernet/intel/i40e/i40e_main.c#L11945
static int i40e_vsi_alloc_q_vector(struct i40e_vsi *vsi, int v_idx)
{
    ...
	if (vsi->netdev)
		netif_napi_add(vsi->netdev, &q_vector->napi,
			       i40e_napi_poll, NAPI_POLL_WEIGHT);

	/* tie q_vector and vsi together */
	vsi->q_vectors[v_idx] = q_vector;

	return 0;
}
```

这里有两个参数：

- [i40e_napi_poll()函数](https://elixir.bootlin.com/linux/v5.15.139/source/drivers/net/ethernet/intel/i40e/i40e_txrx.c#L2675)：i40e 网卡驱动的 NAPI poll 函数
- [NAPI_POLL_WEIGHT](https://elixir.bootlin.com/linux/v5.15.139/source/include/linux/netdevice.h#L2488)：NAPI poll 的权重，默认为 64，表示在一次 poll 中最多处理 64 个数据包，这个是可以根据实际情况进行调整的。

```c
/* Default NAPI poll() weight
 * Device drivers are strongly advised to not use bigger value
 */
#define NAPI_POLL_WEIGHT 64
```

###### 向量绑定队列

在完成向量初始化后，驱动会调用 [i40e_alloc_rings](https://elixir.bootlin.com/linux/v5.15.139/source/drivers/net/ethernet/intel/i40e/i40e_main.c#L11622) 初始化队列的结构体，并绑定到向量和 VSI，这里只是创建结构体，具体内存的分配要等到网卡启动时执行。创建完结构体后，会调用 [i40e_vsi_map_rings_to_vectors](https://elixir.bootlin.com/linux/v5.15.139/source/drivers/net/ethernet/intel/i40e/i40e_main.c#L4526) 方法绑定队列和向量的映射，后续还会再网卡启动时，通过对向量设置 CPU 亲和性，最终完成队列-向量-CPU 的关联关系。

```c
static void i40e_vsi_map_rings_to_vectors(struct i40e_vsi *vsi)
{
	int qp_remaining = vsi->num_queue_pairs;
	int q_vectors = vsi->num_q_vectors;
	int num_ringpairs;
	int v_start = 0;
	int qp_idx = 0;

	/* If we don't have enough vectors for a 1-to-1 mapping, we'll have to
	 * group them so there are multiple queues per vector.
	 * It is also important to go through all the vectors available to be
	 * sure that if we don't use all the vectors, that the remaining vectors
	 * are cleared. This is especially important when decreasing the
	 * number of queues in use.
	 */
	for (; v_start < q_vectors; v_start++) {
		struct i40e_q_vector *q_vector = vsi->q_vectors[v_start];

		num_ringpairs = DIV_ROUND_UP(qp_remaining, q_vectors - v_start);

		q_vector->num_ringpairs = num_ringpairs;
		q_vector->reg_idx = q_vector->v_idx + vsi->base_vector - 1;

		q_vector->rx.count = 0;
		q_vector->tx.count = 0;
		q_vector->rx.ring = NULL;
		q_vector->tx.ring = NULL;

		while (num_ringpairs--) {
			i40e_map_vector_to_qp(vsi, v_start, qp_idx);
			qp_idx++;
			qp_remaining--;
		}
	}
}
```

### 5.启动网卡

当网络驱动加载完成后，就可以启动网卡进行正常的网络包收发了。根据 Linux 的定义，网卡启动会调用 `ndo_open` 函数，对应到 i40e 驱动就是 [i40e_open()](https://elixir.bootlin.com/linux/v5.15.139/source/drivers/net/ethernet/intel/i40e/i40e_main.c#L8954) 函数。

`i40e_open` 会调用 [i40e_vsi_open](https://elixir.bootlin.com/linux/v5.15.139/source/drivers/net/ethernet/intel/i40e/i40e_main.c#L9018) 函数，最主要的操作都在该函数下完成。

```c
int i40e_vsi_open(struct i40e_vsi *vsi)
{
	struct i40e_pf *pf = vsi->back;
	char int_name[I40E_INT_NAME_STR_LEN];
	int err;

	/* allocate descriptors */
	// 创建 TX 队列
	err = i40e_vsi_setup_tx_resources(vsi);
	if (err)
		goto err_setup_tx;
	// 创建 RX 队列
	err = i40e_vsi_setup_rx_resources(vsi);
	if (err)
		goto err_setup_rx;

	err = i40e_vsi_configure(vsi);
	if (err)
		goto err_setup_rx;

	if (vsi->netdev) {
		snprintf(int_name, sizeof(int_name) - 1, "%s-%s",
			 dev_driver_string(&pf->pdev->dev), vsi->netdev->name);
		// 注册硬中断处理函数
		err = i40e_vsi_request_irq(vsi, int_name);
		if (err)
			goto err_setup_rx;

		/* Notify the stack of the actual queue counts. */
		err = i40e_netif_set_realnum_tx_rx_queues(vsi);
		if (err)
			goto err_set_queues;

	} else if (vsi->type == I40E_VSI_FDIR) {
		snprintf(int_name, sizeof(int_name) - 1, "%s-%s:fdir",
			 dev_driver_string(&pf->pdev->dev),
			 dev_name(&pf->pdev->dev));
		err = i40e_vsi_request_irq(vsi, int_name);
		if (err)
			goto err_setup_rx;

	} else {
		err = -EINVAL;
		goto err_setup_rx;
	}
    // 完成后续步骤，启动网卡
	err = i40e_up_complete(vsi);
	if (err)
		goto err_up_complete;

	return 0;

err_up_complete:
	i40e_down(vsi);
err_set_queues:
	i40e_vsi_free_irq(vsi);
err_setup_rx:
	i40e_vsi_free_rx_resources(vsi);
err_setup_tx:
	i40e_vsi_free_tx_resources(vsi);
	if (vsi == pf->vsi[pf->lan_vsi])
		i40e_do_reset(pf, I40E_PF_RESET_FLAG, true);

	return err;
}
```

这里主要完成几件事情：

- 创建 RX、TX RingBuffer 队列
- 注册硬中断处理函数
- 启用硬中断，等待数据到来

#### 分配 RX、TX 队列

在 i40e_vsi_open 中，i40e 会调用 i40e_vsi_setup_tx_resources 和 i40e_vsi_setup_rx_resources 函数来分配 TX 和 RX 队列的资源，也就是我们常说的 RingBuffer。代码如下，可以看到其通过循环创建若干个 RingBuffer：

```c
// https://elixir.bootlin.com/linux/v5.15.139/source/drivers/net/ethernet/intel/i40e/i40e_main.c#L3331
/**
 * i40e_vsi_setup_rx_resources - Allocate VSI queues Rx resources
 **/
static int i40e_vsi_setup_rx_resources(struct i40e_vsi *vsi)
{
	int i, err = 0;

	for (i = 0; i < vsi->num_queue_pairs && !err; i++)
		err = i40e_setup_rx_descriptors(vsi->rx_rings[i]);
	return err;
}

// https://elixir.bootlin.com/linux/v5.15.139/source/drivers/net/ethernet/intel/i40e/i40e_main.c#L3282
/**
 * i40e_vsi_setup_tx_resources - Allocate VSI Tx queue resources
 **/
static int i40e_vsi_setup_tx_resources(struct i40e_vsi *vsi)
{
	int i, err = 0;

    // 普通独队列创建
	for (i = 0; i < vsi->num_queue_pairs && !err; i++)
		err = i40e_setup_tx_descriptors(vsi->tx_rings[i]);

	if (!i40e_enabled_xdp_vsi(vsi))
		return err;
    // XDP（eXpress Data Path) 专用队列
	for (i = 0; i < vsi->num_queue_pairs && !err; i++)
		err = i40e_setup_tx_descriptors(vsi->xdp_rings[i]);

	return err;
}
```

我们来看下具体的创建流程。

##### RX 队列创建流程

```c
https://elixir.bootlin.com/linux/v5.15.139/source/drivers/net/ethernet/intel/i40e/i40e_txrx.c#L1559
int i40e_setup_rx_descriptors(struct i40e_ring *rx_ring)
{
	struct device *dev = rx_ring->dev;
	int err;

	u64_stats_init(&rx_ring->syncp);

	/* Round up to nearest 4K */
	rx_ring->size = rx_ring->count * sizeof(union i40e_rx_desc);
	rx_ring->size = ALIGN(rx_ring->size, 4096);
	rx_ring->desc = dma_alloc_coherent(dev, rx_ring->size,
					   &rx_ring->dma, GFP_KERNEL);

	if (!rx_ring->desc) {
		dev_info(dev, "Unable to allocate memory for the Rx descriptor ring, size=%d\n",
			 rx_ring->size);
		return -ENOMEM;
	}

	rx_ring->next_to_alloc = 0;
	rx_ring->next_to_clean = 0;
	rx_ring->next_to_use = 0;

	/* XDP RX-queue info only needed for RX rings exposed to XDP */
	if (rx_ring->vsi->type == I40E_VSI_MAIN) {
		err = xdp_rxq_info_reg(&rx_ring->xdp_rxq, rx_ring->netdev,
				       rx_ring->queue_index, rx_ring->q_vector->napi.napi_id);
		if (err < 0)
			return err;
	}

	rx_ring->xdp_prog = rx_ring->vsi->xdp_prog;

	rx_ring->rx_bi =
		kcalloc(rx_ring->count, sizeof(*rx_ring->rx_bi), GFP_KERNEL);
	if (!rx_ring->rx_bi)
		return -ENOMEM;

	return 0;
}
```

##### TX 队列创建流程

```c
https://elixir.bootlin.com/linux/v5.15.139/source/drivers/net/ethernet/intel/i40e/i40e_txrx.c#L1419
int i40e_setup_tx_descriptors(struct i40e_ring *tx_ring)
{
	struct device *dev = tx_ring->dev;
	int bi_size;

	if (!dev)
		return -ENOMEM;

	/* warn if we are about to overwrite the pointer */
	WARN_ON(tx_ring->tx_bi);
	bi_size = sizeof(struct i40e_tx_buffer) * tx_ring->count;
	tx_ring->tx_bi = kzalloc(bi_size, GFP_KERNEL);
	if (!tx_ring->tx_bi)
		goto err;

	u64_stats_init(&tx_ring->syncp);

	/* round up to nearest 4K */
	tx_ring->size = tx_ring->count * sizeof(struct i40e_tx_desc);
	/* add u32 for head writeback, align after this takes care of
	 * guaranteeing this is at least one cache line in size
	 */
	tx_ring->size += sizeof(u32);
	tx_ring->size = ALIGN(tx_ring->size, 4096);
	tx_ring->desc = dma_alloc_coherent(dev, tx_ring->size,
					   &tx_ring->dma, GFP_KERNEL);
	if (!tx_ring->desc) {
		dev_info(dev, "Unable to allocate memory for the Tx descriptor ring, size=%d\n",
			 tx_ring->size);
		goto err;
	}

	tx_ring->next_to_use = 0;
	tx_ring->next_to_clean = 0;
	tx_ring->tx_stats.prev_pkt_ctr = -1;
	return 0;

err:
	kfree(tx_ring->tx_bi);
	tx_ring->tx_bi = NULL;
	return -ENOMEM;
}
```

#### 注册硬中断处理函数

RingBuffer 队列创建完后，会注册硬中断处理函数，整体调用栈如下：

```
i40e_open()
└── i40e_vsi_open()
    └── i40e_vsi_request_irq()
            └── i40e_vsi_request_irq_msix()
                    └── request_irq()
```

主要注册逻辑是在 [i40e_vsi_request_irq_msix](https://elixir.bootlin.com/linux/v5.15.139/source/drivers/net/ethernet/intel/i40e/i40e_main.c#L4085) 实现的，我们来看下。

```c
static int i40e_vsi_request_irq_msix(struct i40e_vsi *vsi, char *basename)
{
	int q_vectors = vsi->num_q_vectors;
	struct i40e_pf *pf = vsi->back;
	int base = vsi->base_vector;
	int rx_int_idx = 0;
	int tx_int_idx = 0;
	int vector, err;
	int irq_num;
	int cpu;

	for (vector = 0; vector < q_vectors; vector++) {
		struct i40e_q_vector *q_vector = vsi->q_vectors[vector];

		irq_num = pf->msix_entries[base + vector].vector;

		if (q_vector->tx.ring && q_vector->rx.ring) {
			snprintf(q_vector->name, sizeof(q_vector->name) - 1,
				 "%s-%s-%d", basename, "TxRx", rx_int_idx++);
			tx_int_idx++;
		} else if (q_vector->rx.ring) {
			snprintf(q_vector->name, sizeof(q_vector->name) - 1,
				 "%s-%s-%d", basename, "rx", rx_int_idx++);
		} else if (q_vector->tx.ring) {
			snprintf(q_vector->name, sizeof(q_vector->name) - 1,
				 "%s-%s-%d", basename, "tx", tx_int_idx++);
		} else {
			/* skip this unused q_vector */
			continue;
		}
		// 注册中断处理函数
		err = request_irq(irq_num,
				  vsi->irq_handler,
				  0,
				  q_vector->name,
				  q_vector);
		if (err) {
			dev_info(&pf->pdev->dev,
				 "MSIX request_irq failed, error: %d\n", err);
			goto free_queue_irqs;
		}

		/* register for affinity change notifications */
		q_vector->affinity_notify.notify = i40e_irq_affinity_notify;
		q_vector->affinity_notify.release = i40e_irq_affinity_release;
		irq_set_affinity_notifier(irq_num, &q_vector->affinity_notify);
		/* Spread affinity hints out across online CPUs.
		 *
		 * get_cpu_mask returns a static constant mask with
		 * a permanent lifetime so it's ok to pass to
		 * irq_set_affinity_hint without making a copy.
		 */
		cpu = cpumask_local_spread(q_vector->v_idx, -1);
		irq_set_affinity_hint(irq_num, get_cpu_mask(cpu));
	}

	vsi->irqs_ready = true;
	return 0;

	...
}
```

这里会为每个向量注册硬中断处理函数，并且会设置 CPU 亲和性，这样结合之前的队列与向量关系绑定，就形成了队列-向量-CPU 的关联关系，在数据包处理时，根据选择的队列就可以确定处理该数据包的 CPU。

#### 启用硬中断

最后，[i40e_up_complete()](https://elixir.bootlin.com/linux/v5.15.139/source/drivers/net/ethernet/intel/i40e/i40e_main.c#L7342) 函数注册完 IRQ 驱动函数后网卡驱动会完成一系列的启动工作，做好收发网络包的准备。主要步骤如下：

```c
static int i40e_up_complete(struct i40e_vsi *vsi)
{
	...

	/* start rings */
	// 1. 启动VSI的所有TX和RX队列（环形缓冲区）
	err = i40e_vsi_start_rings(vsi);
	if (err)
		return err;

	clear_bit(__I40E_VSI_DOWN, vsi->state);
	// 2. 为VSI的所有队列向量启用NAPI（New API）轮询机制
	i40e_napi_enable_all(vsi);
	// 3. 启用VSI的所有硬件中断
	i40e_vsi_enable_irq(vsi);

	if ((pf->hw.phy.link_info.link_info & I40E_AQ_LINK_UP) &&
	    (vsi->netdev)) {
		i40e_print_link_message(vsi, true);
		// 启用发送队列
		netif_tx_start_all_queues(vsi->netdev);
		// 设置网卡状态为 UP
		netif_carrier_on(vsi->netdev);
	}

	/* replay FDIR SB filters */
	if (vsi->type == I40E_VSI_FDIR) {
		/* reset fd counters */
		pf->fd_add_err = 0;
		pf->fd_atr_cnt = 0;
		i40e_fdir_filter_restore(vsi);
	}

	/* On the next run of the service_task, notify any clients of the new
	 * opened netdev
	 */
	// 通知其他子系统（如RDMA、存储等）网络接口已经就绪
	set_bit(__I40E_CLIENT_SERVICE_REQUESTED, pf->state);
	i40e_service_event_schedule(pf);

	return 0;
}
```

至此，网络相关的系统初始化工作基本完成，网卡和驱动程序已经准备好接收和发送网络数据包。下一篇我们将分析 Linux 网络收包的具体流程。
