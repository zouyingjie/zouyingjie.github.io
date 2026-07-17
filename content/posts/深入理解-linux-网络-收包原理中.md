---
title: "【深入理解 Linux 网络】收包原理与内核实现（中）TCP 传输层处理"
date: 2025-08-21T12:31:59+08:00
tags:
  - Linux
  - TCP
  - 计算机网络
categories:
  - 计算机网络
source: "https://blog.csdn.net/Ahri_J/article/details/150580355"
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

上一篇我们分析了从网卡到达数据包到
 IP
 层的处理流程，接下来我们将深入探讨 L4 层 TCP 协议栈的处理流程，也就是来到了图中第 7 步协议栈 L2、L3、L4 三层处理的最后阶段。

![](https://pub-08b57ed9c8ce4fadab4077a9d577e857.r2.dev/csdn-e7abfdc665c24e5371fb7e0da18c7b01233ca03899b1fe90022656d1c18eb515.png)

图片来自 [Linux Networking Stack tutorial: Receiving Data](https://maxnilz.com/docs/004-network/006-linux-rx/)

### 7.3
 TCP
 协议栈处理

TCP
 协议
栈的入口函数是 [tcp_v4_rcv](https://elixir.bootlin.com/linux/v5.15.139/source/net/ipv4/tcp_ipv4.c#L1976)，这个函数比较复杂，主要完成以下几件事情：

1. 检查 TCP 头部是否合法。
2. 根据 TCP 头部信息查找对应的 socket。
3. 根据 socket 的状态，进行相应的处理

#### 基于
 socket
 状态的处理分发

```c
/*
 *	From tcp_input.c
 */

int tcp_v4_rcv(struct sk_buff *skb)
{
	// ... 代码省略

    // 获取 TCP 头指针
    th = (const struct tcphdr *)skb->data;
	iph = ip_hdr(skb);
lookup:
    // 查找 socket
	sk = __inet_lookup_skb(&tcp_hashinfo, skb, __tcp_hdrlen(th), th->source,
			       th->dest, sdif, &refcounted);
	if (!sk)
		goto no_tcp_socket;

process:
    // 处理 TIME_WAIT 状态的 socket
	if (sk->sk_state == TCP_TIME_WAIT)
		goto do_time_wait;

    // 处理 TCP_NEW_SYN_RECV 状态的 socket，表示 socket 正在建立连接
	if (sk->sk_state == TCP_NEW_SYN_RECV) {
		// ... 代码省略
	}
    ...
    // LISTEN 状态处理
	if (sk->sk_state == TCP_LISTEN) {
		ret = tcp_v4_do_rcv(sk, skb);
		goto put_and_return;
	}

    // 处理 ESTABLISHED 状态的 socket
	ret = 0;
	if (!sock_owned_by_user(sk)) {
		skb_to_free = sk->sk_rx_skb_cache;
		sk->sk_rx_skb_cache = NULL;
		ret = tcp_v4_do_rcv(sk, skb);
	} else {
		if (tcp_add_backlog(sk, skb))
			goto discard_and_relse;
		skb_to_free = NULL;
	}
	...

    // // 释放缓存的skb
	if (skb_to_free)
		__kfree_skb(skb_to_free);
    ...
}
```

可以看到针对 LISTEN、ESTABLISHED、TIME_WAIT 以及建立连接的不同状态，内核分别采取了不同的处理策略。这里我们只关注正常收包的 LISTEN 和 ESTABLISHED 状态处理：

- 对于 LISTEN 状态的 socket，内核会将数据包交给 `tcp_v4_do_rcv()` 函数进行处理。
- 对于 ESTABLISHED 的状态，有一个 `!sock_owned_by_user(sk)` 的判断，如果为真，也是执行 tcp_v4_do_rcv() 函数进行处理，否则会调用 `tcp_add_backlog()` 将数据包放入 backlog 队列。

`!sock_owned_by_user(sk)` 这个判断的意思是当前 socket 是否被用户空间所拥有，如果我们在使用 socket，比如执行 `recv()`、`send()`、`setsockopt()` 等系统调用时，内核会将 socket 标记为“被用户空间拥有”。如果 socket 被用户空间拥有，内核就不能直接对其进行操作，而是需要将数据包放入 backlog 队列，等待用户空间应用程序来处理。从而避免内核和用户态进程同时修改 socket。

![](https://pub-08b57ed9c8ce4fadab4077a9d577e857.r2.dev/csdn-7a01b518f6dfb2652ac6a7545b1b3876061c919201ac6b7b00bc4b0fb0757256.png)

#### backlog
 缓存
队列

当 socket 被占用无法立即处理时，socket 会将这些数据包缓存到 backlog 队列。虽然也叫 backlog，但注意和半连接队列的 backlog 是不同。内核将数据包放入 backlog 队列中后，等待用户空间应用程序通过 `recv()` 等系统调用来读取。队列的长度计算如下：

```
// 基础限制 = 接收缓冲区大小 + 发送缓冲区大小的一半
limit = (u32)READ_ONCE(sk->sk_rcvbuf) + (u32)(READ_ONCE(sk->sk_sndbuf) >> 1);

// 添加64KB的安全边界
limit += 64 * 1024;
```

因此适当的调大 rcv_buf 和 snd_buf 的大小，可以有效提高 backlog 队列的长度，从而提升网络性能。

#### tcp_v4_do_rcv() 接收数据

现在数据包来到 [tcp_v4_do_rcv()](https://elixir.bootlin.com/linux/v5.15.139/source/net/ipv4/tcp_ipv4.c#L1707) 函数进行处理，该函数逻辑比较简单：

- 如果是 ESTABLISHED 状态的 socket，调用 `tcp_rcv_established()` 函数进行处理。
- 如果是其他状态，调用 `tcp_rcv_state_process()` 函数进行处理。

```c
int tcp_v4_do_rcv(struct sock *sk, struct sk_buff *skb)
{
	struct sock *rsk;

	if (sk->sk_state == TCP_ESTABLISHED) { /* Fast path */
		...
		tcp_rcv_established(sk, skb);
		return 0;
	}

	...

	if (tcp_rcv_state_process(sk, skb)) {
		rsk = sk;
		goto reset;
	}
	return 0;
}
```

在 [tcp_rcv_state_process](https://elixir.bootlin.com/linux/v5.15.139/source/net/ipv4/tcp_input.c#L6417) 函数可以看到对 TCP 协议所有状态的处理。

```c
int tcp_rcv_state_process(struct sock *sk, struct sk_buff *skb)
{
	...

	switch (sk->sk_state) {
	case TCP_CLOSE:
		goto discard;

	case TCP_LISTEN:
		if (th->ack)
			return 1;

		if (th->rst)
			goto discard;

		if (th->syn) {
			...
			return 0;
		}
		goto discard;

	case TCP_SYN_SENT:
		...
		tcp_data_snd_check(sk);
		return 0;
	}


	switch (sk->sk_state) {
	case TCP_SYN_RECV:
		tcp_set_state(sk, TCP_ESTABLISHED);
		sk->sk_state_change(sk);
		...
		break;

	case TCP_FIN_WAIT1: {
        ...
		tcp_set_state(sk, TCP_FIN_WAIT2);


		if (tp->linger2 < 0) {
			tcp_done(sk);
			NET_INC_STATS(sock_net(sk), LINUX_MIB_TCPABORTONDATA);
			return 1;
		}

		tmo = tcp_fin_time(sk);
		if (tmo > TCP_TIMEWAIT_LEN) {
			inet_csk_reset_keepalive_timer(sk, tmo - TCP_TIMEWAIT_LEN);
		} else if (th->fin || sock_owned_by_user(sk)) {
			inet_csk_reset_keepalive_timer(sk, tmo);
		} else {
			tcp_time_wait(sk, TCP_FIN_WAIT2, tmo);
			goto discard;
		}
		break;
	}

	case TCP_CLOSING:
		if (tp->snd_una == tp->write_seq) {
			tcp_time_wait(sk, TCP_TIME_WAIT, 0);
			goto discard;
		}
		break;

	case TCP_LAST_ACK:
		if (tp->snd_una == tp->write_seq) {
			tcp_update_metrics(sk);
			tcp_done(sk);
			goto discard;
		}
		break;
	}
	/* step 7: process the segment text */
	switch (sk->sk_state) {
	case TCP_CLOSE_WAIT:
	case TCP_CLOSING:
	case TCP_LAST_ACK:
		...
	case TCP_FIN_WAIT1:
	case TCP_FIN_WAIT2:
		...
	case TCP_ESTABLISHED:
		tcp_data_queue(sk, skb);
		queued = 1;
		break;
	}

	/* tcp_data could move socket to TIME-WAIT */
	if (sk->sk_state != TCP_CLOSE) {
		tcp_data_snd_check(sk);
		tcp_ack_snd_check(sk);
	}

	return 0;
}
```

感兴趣的同学不妨参考着 TCP 状态图来读读这段代码，可以对相关状态的处理有更深入的理解。

![](https://pub-08b57ed9c8ce4fadab4077a9d577e857.r2.dev/csdn-6d80a8ea4303bfb7a91ab0e9268d218d2c946505c64dde68145b7571f207ef7b.png)

#### tcp_rcv_established() 数据处理

基于接收包的信息，[tcp_rcv_established()](https://elixir.bootlin.com/linux/v5.15.139/source/net/ipv4/tcp_input.c#L4942) 会有两种不同路径：

- **Fast path：** 快速路径，正常情况下的收包处理，当收到的包正好是期望的包是，会执行该路径进行快速处理。
- **Slow path：** 慢速路径，当传输过程存在问题时，比如丢包、乱序、Zero Window 等情况，会执行该路径进行更加复杂严格的处理。

对于快速路径，还会分为无数据和有数据两种情况，前者只需要响应 ACK 即可；后者则需要将数据放入接收缓冲区并通知上层应用。

##### 快速路径处理

当发送接收端和网络状态都正常时，tcp_rcv_established() 函数会进入快速路径处理。这是大多数情况下的处理流程。核心逻辑如是在有数据时会调用 `tcp_queue_rcv` 函数将数据放入接收缓冲区，写入流程也非常简单，正常情况下数据时有序到达的，因此直接将数据添加到队列末尾即可。

```c
void tcp_rcv_established(struct sock *sk, struct sk_buff *skb)
{
	// ... 代码省略

    // 快速路径判断
	if ((tcp_flag_word(th) & TCP_HP_BITS) == tp->pred_flags &&
	    TCP_SKB_CB(skb)->seq == tp->rcv_nxt &&
	    !after(TCP_SKB_CB(skb)->ack_seq, tp->snd_nxt)) {
		int tcp_header_len = tp->tcp_header_len;
        ...

        // 无数据
		if (len <= tcp_header_len) {
			/* Bulk data transfer: sender */
			if (len == tcp_header_len) {
				// 响应 ACK
				tcp_ack(sk, skb, 0);
                // 释放 skb
				__kfree_skb(skb);
                // 检查是否需要发送数据
				tcp_data_snd_check(sk);
				...
				return;
			} else { /* Header too small */
				TCP_INC_STATS(sock_net(sk), TCP_MIB_INERRS);
				goto discard;
			}
		} else {

			/* Bulk data transfer: receiver */
            // 移除TCP头部，只保留数据部分
			__skb_pull(skb, tcp_header_len);
            // 将数据写入接收缓冲区
			eaten = tcp_queue_rcv(sk, skb, &fragstolen);

            // 触发数据接收事件，主要为了调整拥塞窗口
			tcp_event_data_recv(sk, skb);

			...
no_ack:
            // 释放 skb
			if (eaten)
				kfree_skb_partial(skb, fragstolen);
            // 通知应用层数据已准备好，快速处理路径完成
			tcp_data_ready(sk);
			return;
		}
	}

slow_path:
	if (len < (th->doff << 2) || tcp_checksum_complete(skb))
		goto csum_error;

	if (!th->ack && !th->rst && !th->syn)
		goto discard;

	/*
	 *	Standard slow path.
	 */

	if (!tcp_validate_incoming(sk, skb, th, 1))
		return;

step5:
	if (tcp_ack(sk, skb, FLAG_SLOWPATH | FLAG_UPDATE_TS_RECENT) < 0)
		goto discard;

	tcp_rcv_rtt_measure_ts(sk, skb);

	/* Process urgent data. */
	tcp_urg(sk, skb, th);

	/* step 7: process the segment text */
	tcp_data_queue(sk, skb);

	tcp_data_snd_check(sk);
	tcp_ack_snd_check(sk);
	return;

csum_error:
	trace_tcp_bad_csum(skb);
	TCP_INC_STATS(sock_net(sk), TCP_MIB_CSUMERRORS);
	TCP_INC_STATS(sock_net(sk), TCP_MIB_INERRS);

discard:
	tcp_drop(sk, skb);
}
```

##### 慢速路径处理

如果收到的包不满足快速路径的条件，就会进入慢速路径处理。慢速路径处理的代码如下：

```c
slow_path:
	if (len < (th->doff << 2) || tcp_checksum_complete(skb))
		goto csum_error;

	if (!th->ack && !th->rst && !th->syn)
		goto discard;

	/*
	 *	Standard slow path.
	 */

	if (!tcp_validate_incoming(sk, skb, th, 1))
		return;

step5:
	if (tcp_ack(sk, skb, FLAG_SLOWPATH | FLAG_UPDATE_TS_RECENT) < 0)
		goto discard;

	tcp_rcv_rtt_measure_ts(sk, skb);

	/* Process urgent data. */
	tcp_urg(sk, skb, th);

	/* step 7: process the segment text */
	tcp_data_queue(sk, skb);

	tcp_data_snd_check(sk);
	tcp_ack_snd_check(sk);
	return;
```

这里的核心逻辑是在 [tcp_data_queue](https://elixir.bootlin.com/linux/v5.15.139/source/net/ipv4/tcp_input.c#L5017) 函数中处理的。

```c
static void tcp_data_queue(struct sock *sk, struct sk_buff *skb)
{
	struct tcp_sock *tp = tcp_sk(sk);
	bool fragstolen;
	int eaten;
     ...
	skb_dst_drop(skb);
	__skb_pull(skb, tcp_hdr(skb)->doff * 4);

	tp->rx_opt.dsack = 0;

	/*  Queue data for delivery to the user.
	 *  Packets in sequence go to the receive queue.
	 *  Out of sequence packets to the out_of_order_queue.
	 */
	if (TCP_SKB_CB(skb)->seq == tp->rcv_nxt) {
		if (tcp_receive_window(tp) == 0) {
			NET_INC_STATS(sock_net(sk), LINUX_MIB_TCPZEROWINDOWDROP);
			goto out_of_window;
		}

		/* Ok. In sequence. In window. */
queue_and_out:
		if (skb_queue_len(&sk->sk_receive_queue) == 0)
			sk_forced_mem_schedule(sk, skb->truesize);
		else if (tcp_try_rmem_schedule(sk, skb, skb->truesize)) {
			NET_INC_STATS(sock_net(sk), LINUX_MIB_TCPRCVQDROP);
			sk->sk_data_ready(sk);
			goto drop;
		}

		eaten = tcp_queue_rcv(sk, skb, &fragstolen);
		if (skb->len)
			tcp_event_data_recv(sk, skb);
		if (TCP_SKB_CB(skb)->tcp_flags & TCPHDR_FIN)
			tcp_fin(sk);

		if (!RB_EMPTY_ROOT(&tp->out_of_order_queue)) {
			tcp_ofo_queue(sk);

			/* RFC5681. 4.2. SHOULD send immediate ACK, when
			 * gap in queue is filled.
			 */
			if (RB_EMPTY_ROOT(&tp->out_of_order_queue))
				inet_csk(sk)->icsk_ack.pending |= ICSK_ACK_NOW;
		}

		if (tp->rx_opt.num_sacks)
			tcp_sack_remove(tp);

		tcp_fast_path_check(sk);

		if (eaten > 0)
			kfree_skb_partial(skb, fragstolen);
		if (!sock_flag(sk, SOCK_DEAD))
			tcp_data_ready(sk);
		return;
	}

	if (!after(TCP_SKB_CB(skb)->end_seq, tp->rcv_nxt)) {
		tcp_rcv_spurious_retrans(sk, skb);
		/* A retransmit, 2nd most common case.  Force an immediate ack. */
		NET_INC_STATS(sock_net(sk), LINUX_MIB_DELAYEDACKLOST);
		tcp_dsack_set(sk, TCP_SKB_CB(skb)->seq, TCP_SKB_CB(skb)->end_seq);

out_of_window:
		tcp_enter_quickack_mode(sk, TCP_MAX_QUICKACKS);
		inet_csk_schedule_ack(sk);
drop:
		tcp_drop(sk, skb);
		return;
	}

	/* Out of window. F.e. zero window probe. */
	if (!before(TCP_SKB_CB(skb)->seq, tp->rcv_nxt + tcp_receive_window(tp)))
		goto out_of_window;

	if (before(TCP_SKB_CB(skb)->seq, tp->rcv_nxt)) {
		...
		goto queue_and_out;
	}

	tcp_data_queue_ofo(sk, skb);
}
```

这里对数据包分了五种场景进行处理，我们来分别看下。

###### 场景一：正常数据流

这里的判断条件是 `TCP_SKB_CB(skb)->seq == tp->rcv_nxt`，也就是到达的数据包刚好是我们期望的数据包，没有丢包、乱序和重传。这是如果窗口还有空间，则会调用 `tcp_queue_rcv()` 将数据写入缓冲区。

除此之外，这里还会检查 `out_of_order_queue` 乱序队列中是否有提前到达的数据，可以在当前数据包达到后连起来，有的话也会一起写入到缓冲区。比如我们有 1、3、4、5 号数据包，1 和 2 收到后接着收到了 4 和 5，这两个包就会放入乱序队列，3 号包达到后数据就连起来了，此时可以从乱序队列将 4、5 号包取出放入缓冲区。

```c
// https://elixir.bootlin.com/linux/v5.15.139/source/net/ipv4/tcp_input.c#L5044
if (TCP_SKB_CB(skb)->seq == tp->rcv_nxt) {
         // 接收窗口已满
		if (tcp_receive_window(tp) == 0) {
			NET_INC_STATS(sock_net(sk), LINUX_MIB_TCPZEROWINDOWDROP);
			goto out_of_window;
		}

	    ...
        // 将数据写入缓冲区
		eaten = tcp_queue_rcv(sk, skb, &fragstolen);
		if (skb->len)
			tcp_event_data_recv(sk, skb);
		if (TCP_SKB_CB(skb)->tcp_flags & TCPHDR_FIN)
			tcp_fin(sk);

		// 处理乱序队列
		if (!RB_EMPTY_ROOT(&tp->out_of_order_queue)) {
			tcp_ofo_queue(sk);

			/* RFC5681. 4.2. SHOULD send immediate ACK, when
			 * gap in queue is filled.
			 */
			if (RB_EMPTY_ROOT(&tp->out_of_order_queue))
				inet_csk(sk)->icsk_ack.pending |= ICSK_ACK_NOW;
		}
        ..

        // 通知应用层 数据处理完毕
		if (!sock_flag(sk, SOCK_DEAD))
			tcp_data_ready(sk);
		return;
}
```

###### 场景二：数据重传

这里的判断条件是 `!after(TCP_SKB_CB(skb)->end_seq, tp->rcv_nxt)`：

- `end_seq` 表示当前报文的最大序列号。
- `rcv_nxt` 表示接收窗口。

这里判断的意思就是收到包的报文不晚于 RCV.NXT，如图所示也就是位于已经接收并确认的区域内。很明显是重传包，因此这里会再次进行 ACK，但会通过 `tcp_dsack_set()` 标记为 Duplicate ACK。

![](https://pub-08b57ed9c8ce4fadab4077a9d577e857.r2.dev/csdn-78d51a29bb8554b31260b86291d0e30576e38abb6fe740b1d69b974f801631a2.png)

```c
// https://elixir.bootlin.com/linux/v5.15.139/source/net/ipv4/tcp_input.c#L5088
	if (!after(TCP_SKB_CB(skb)->end_seq, tp->rcv_nxt)) {
		tcp_rcv_spurious_retrans(sk, skb);
		/* A retransmit, 2nd most common case.  Force an immediate ack. */
		NET_INC_STATS(sock_net(sk), LINUX_MIB_DELAYEDACKLOST);
		tcp_dsack_set(sk, TCP_SKB_CB(skb)->seq, TCP_SKB_CB(skb)->end_seq);

out_of_window:
		tcp_enter_quickack_mode(sk, TCP_MAX_QUICKACKS);
		inet_csk_schedule_ack(sk);
drop:
		tcp_drop(sk, skb);
		return;
	}
```

###### 场景三：零窗口处理

这里的判断条件是 `!before(TCP_SKB_CB(skb)->seq, tp->rcv_nxt + tcp_receive_window(tp))`，也就是收到的包的序列号位于图中的黄色区域，已经超出了接收窗口的可接受范围。

![](https://pub-08b57ed9c8ce4fadab4077a9d577e857.r2.dev/csdn-78d51a29bb8554b31260b86291d0e30576e38abb6fe740b1d69b974f801631a2.png)

```c
// https://elixir.bootlin.com/linux/v5.15.139/source/net/ipv4/tcp_input.c#L5103
out_of_window:
		tcp_enter_quickack_mode(sk, TCP_MAX_QUICKACKS);
		inet_csk_schedule_ack(sk);

/* Out of window. F.e. zero window probe. */
if (!before(TCP_SKB_CB(skb)->seq, tp->rcv_nxt + tcp_receive_window(tp)))
		goto out_of_window;
```

这种情况通常意味着发送速度超过了接收速度，此时需要通知发送方进行调整。这里会执行 Quick ACK，立即通知发送方，告知自己的窗口大小，减缓发送速度。

###### 场景四：部分重传

这里的判断条件是 `before(TCP_SKB_CB(skb)->seq, tp->rcv_nxt)`，也就是收到的包的序列号小于接收窗口的下一个期望序列号，简单来说就是收到的包一部分是旧数据，一部分是新数据。这种情况下会对数据进行裁剪，将新数据写入到缓冲区。

```c
// https://elixir.bootlin.com/linux/v5.15.139/source/net/ipv4/tcp_input.c#L5106

if (before(TCP_SKB_CB(skb)->seq, tp->rcv_nxt)) {
		/* Partial packet, seq < rcv_next < end_seq */
		tcp_dsack_set(sk, TCP_SKB_CB(skb)->seq, tp->rcv_nxt);

		/* If window is closed, drop tail of packet. But after
		 * remembering D-SACK for its head made in previous line.
		 */
		if (!tcp_receive_window(tp)) {
			NET_INC_STATS(sock_net(sk), LINUX_MIB_TCPZEROWINDOWDROP);
			goto out_of_window;
		}
		goto queue_and_out;
	}
```

###### 场景五：乱序

上述四种情况都处理结束后，如果还有包，那就是乱序包。因为其：

- seq 大于 rcv.nxt 且小于 rcv.nxt + window，说明其落在滑动窗口内
- seq 不等于 rcv.nxt 说明并不是期望的包

因此这个包就只会是乱序包。

![](https://pub-08b57ed9c8ce4fadab4077a9d577e857.r2.dev/csdn-78d51a29bb8554b31260b86291d0e30576e38abb6fe740b1d69b974f801631a2.png)

这种情况下会调用 [tcp_data_queue_ofo(sk, skb);](https://elixir.bootlin.com/linux/v5.15.139/source/net/ipv4/tcp_input.c#L4798) 将数据包写入 out_of_order_queue 乱序队列，等后续包继续到达后再场景一下被取出并写入缓冲区。

##### tcp_data_ready 处理

无论是快速路径还是慢速路径，都是调用 `tcp_queue_rcv` 将数据写入缓冲区，最后调用 [tcp_data_ready](https://elixir.bootlin.com/linux/v5.15.139/source/net/ipv4/tcp_input.c#L5011) 来通知应用层的。

```c
void tcp_data_ready(struct sock *sk)
{
	if (tcp_epollin_ready(sk, sk->sk_rcvlowat) // 缓冲区是否有数据
    || sock_flag(sk, SOCK_DONE)) // socket 接收完毕（收发 FIN）
		sk->sk_data_ready(sk); // 调用回调函数
}
```

如果缓冲区有数据就会调用 `sk_data_ready` 回调函数来处理，这里一般默认是 [sock_def_readable](https://elixir.bootlin.com/linux/v5.15.139/source/net/core/sock.c#L3066) 函数。

```c
// https://elixir.bootlin.com/linux/v5.15.139/source/net/core/sock.c#L3173
void sock_init_data_uid(struct socket *sock, struct sock *sk, kuid_t uid)
{
	...
	sk->sk_data_ready	=	sock_def_readable;
}

// https://elixir.bootlin.com/linux/v5.15.139/source/net/core/sock.c#L3066
void sock_def_readable(struct sock *sk)
{
	struct socket_wq *wq;

	rcu_read_lock();
	wq = rcu_dereference(sk->sk_wq);
	if (skwq_has_sleeper(wq))
		wake_up_interruptible_sync_poll(&wq->wait, EPOLLIN | EPOLLPRI |
						EPOLLRDNORM | EPOLLRDBAND);
	sk_wake_async(sk, SOCK_WAKE_WAITD, POLL_IN);
	rcu_read_unlock();
}
```

这个函数做的事情非常简单：

- 如果 socket 的 wq（wait queue）等待队列有等待的任务（（epoll_wait/poll/select 或阻塞 recv 等）。），则执行 `wake_up_interruptible_sync_poll` 函数唤醒这些任务。
- `sk_wake_async`：向开启了异步通知的进程发送 SIGIO（异步 IO 信号），通知有数据到达。这主要是为了兼容一些没有使用 poll/epoll 的旧的应用程序。

到这里就完成了图中的第7、第 8 步，内核协议栈将数据写入缓冲区并通知应用程序，内核的收包处理就到此为止了，后续由应用程序在用户态空间继续进行处理。
