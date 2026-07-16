---
title: "【Kubernetes 源码剖析】kube-scheduler 调度流程"
date: 2025-09-10T17:38:40+08:00
draft: true
tags:
  - Kubernetes
  - 源码剖析
categories:
  - 云原生
source: "https://blog.csdn.net/Ahri_J/article/details/151409125"
---
- [scheduleOne：调度主流程](#scheduleone%E8%B0%83%E5%BA%A6%E4%B8%BB%E6%B5%81%E7%A8%8B)
- [获取待调度 Pod](#%E8%8E%B7%E5%8F%96%E5%BE%85%E8%B0%83%E5%BA%A6-pod)
- [获取调度器](#%E8%8E%B7%E5%8F%96%E8%B0%83%E5%BA%A6%E5%99%A8)
- [可调度性检查 & 准备工作](#%E5%8F%AF%E8%B0%83%E5%BA%A6%E6%80%A7%E6%A3%80%E6%9F%A5--%E5%87%86%E5%A4%87%E5%B7%A5%E4%BD%9C)
- [schedulingCycle](#schedulingcycle)
- [bindingCycle](#bindingcycle)
- [schedulingCycle：调度循环](#schedulingcycle%E8%B0%83%E5%BA%A6%E5%BE%AA%E7%8E%AF)
- [schedulePod：节点选择](#schedulepod%E8%8A%82%E7%82%B9%E9%80%89%E6%8B%A9)
- [findNodesThatFitPod: 过滤阶段](#findnodesthatfitpod-%E8%BF%87%E6%BB%A4%E9%98%B6%E6%AE%B5)
- [Priorities 打分阶段](#priorities-%E6%89%93%E5%88%86%E9%98%B6%E6%AE%B5)
- [Select 选择阶段](#select-%E9%80%89%E6%8B%A9%E9%98%B6%E6%AE%B5)
- [Assume、Reserve、Permit](#assumereservepermit)
- [记录调度延迟](#%E8%AE%B0%E5%BD%95%E8%B0%83%E5%BA%A6%E5%BB%B6%E8%BF%9F)
- [Assume](#assume)
- [Reserve](#reserve)
- [Permit](#permit)
- [激活新的 Pod](#%E6%BF%80%E6%B4%BB%E6%96%B0%E7%9A%84-pod)
- [BindCycle：绑定循环](#bindcycle%E7%BB%91%E5%AE%9A%E5%BE%AA%E7%8E%AF)

上一篇我们分析了 kube-scheduler 的启动流程，在做完一系列启动工作后，就会启动调度循环，持续从调度队列中取出待调度的 Pod 进行调度，本篇我们来分析下调度循环的实现。

在 Scheduler 的 Run 方法中，会启动一个 goroutine，调用 `sched.ScheduleOne` 方法来执行调度逻辑，这是调度循环的入口。

```go
// Run begins watching and scheduling. It starts scheduling and blocked until the context is done.
func (sched *Scheduler) Run(ctx context.Context) {


	...
	go wait.UntilWithContext(ctx, sched.ScheduleOne, 0)
	<-ctx.Done()
	sched.SchedulingQueue.Close()
    ...
}
```

### scheduleOne：调度主流程

完整的调度逻辑是在 [schedule_one.go](https://github.com/kubernetes/kubernetes/blob/v1.32.8/pkg/scheduler/schedule_one.go) 文件中的 `ScheduleOne` 方法中实现的。整体流程如图，我们一步步来看下。

![](https://i-blog.csdnimg.cn/img_convert/a9abf0a110bd7f7fa07a81db6de43242.png)

#### 获取待调度 Pod

首先会调用 `sched.NextPod(logger)` 方法从调度队列中取出下一个待调度的 Pod。该方法是在调度器创建时指定的。

```go
// scheduler 创建时指定 NextPod 方法为 podQueue.Pop，即优先级队列的 Pop 方法
func New() {


	...
	sched.NextPod = podQueue.Pop
}

// 实际调用 activeQ 的 Pop 方法
func (p *PriorityQueue) Pop(logger klog.Logger) (*framework.QueuedPodInfo, error) {


	return p.activeQ.pop(logger)
}

// activeQ 队列的 Pop 方法

func (aq *activeQueue) pop(logger klog.Logger) (*framework.QueuedPodInfo, error) {


	aq.lock.Lock()
	defer aq.lock.Unlock()

	return aq.unlockedPop(logger)
}
```

最终就是执行 activeQ 的 `Pop` 方法，从队列头取出第一个 Pod。

#### 获取调度器

获取到待调度的 Pod 后，接下来会调用 `sched.frameworkForPod()` 方法获取调度器的 Framework 对象，Framework 是调度器的核心对象，封装了调度器的各种功能和插件。

```go
func (sched *Scheduler) frameworkForPod(pod *v1.Pod) (framework.Framework, error) {


	fwk, ok := sched.Profiles[pod.Spec.SchedulerName]
	if !ok {


		return nil, fmt.Errorf("profile not found for scheduler name %q", pod.Spec.SchedulerName)
	}
	return fwk, nil
}
```

`sched.Profiles` 是一个 map，存储了所有调度器的 Framework 对象，这里会基于 Pod 的 `spec.schedulerName` 字段来获取对应的调度器配置，默认是 `default-scheduler`，如果没有特殊设置，就会使用默认调度器。

```yaml
$ kubectl get pods nginx-deployment-65dfb68db7-4l5w4 -o yaml
apiVersion: v1
kind: Pod
metadata:
  labels:
    app: nginx
    pod-template-hash: 65dfb68db7
  name: nginx-deployment-65dfb68db7-4l5w4
  namespace: default
...
spec:
  containers:
  - image: nginx:1.29.1
   ...
  schedulerName: default-scheduler
```

#### 可调度性检查 & 准备工作

在获取到待调度的 Pod 和对应的调度器后，会进行一系列的可调度性检查，主要包括：

- 执行 `skipPodScheduling` 方法，对于已删除或者已初步调度完成的 Pod，直接跳过调度。
- 调度状态初始化：创建新的调度状态对象 `framework.NewCycleState()`，用于存储调度过程中的各种状态信息。
- 初始化待激活的 Pod 列表 `framework.NewPodsToActivate()`，用于存储在当前调度周期中需要重新入队的 Pod。

```go
	if sched.skipPodSchedule(ctx, fwk, pod) {


		// We don't put this Pod back to the queue, but we have to cleanup the in-flight pods/events.
		sched.SchedulingQueue.Done(pod.UID)
		return
	}

	// Synchronously attempt to find a fit for the pod.
	start := time.Now()
	state := framework.NewCycleState()
	state.SetRecordPluginMetrics(rand.Intn(100) < pluginMetricsSamplePercent)

	// Initialize an empty podsToActivate struct, which will be filled up by plugins or stay empty.
	podsToActivate := framework.NewPodsToActivate()
	state.Write(framework.PodsToActivateKey, podsToActivate)
```

执行完上述准备工作后，就会调用 `sched.schedulingCycle()` 方法，进入调度的核心逻辑。

#### schedulingCycle

`schedulingCycle` 方法实现了 Pod 的完整调度流程，这是调度的核心逻辑，后面我们还会详细分析该方法的实现。

```go
// 准备调度上下文
schedulingCycleCtx, cancel := context.WithCancel(ctx)
defer cancel()

// 执行调度循环，获取调度结果
scheduleResult, assumedPodInfo, status := sched.schedulingCycle(schedulingCycleCtx, state, fwk, podInfo, start, podsToActivate)
// 错误处理
if !status.IsSuccess() {


	sched.FailureHandler(schedulingCycleCtx, fwk, assumedPodInfo, status, scheduleResult.nominatingInfo, start)
	return
	}
```

#### bindingCycle

在执行完调度逻辑选择出最合适的节点后，kube-scheduler 并不会直接与 kubelet 交互通知其创建 Pod，而是会启动绑定循环，更新 Pod 的 `spec.nodeName` 字段，更新完成后，Kubelet 会监测到该字段的变化，然后拉取镜像并创建 Pod。

```go
// bind the pod to its host asynchronously (we can do this b/c of the assumption step above).
go func() {


	// 准备绑定上下文
	bindingCycleCtx, cancel := context.WithCancel(ctx)
	defer cancel()
	// 绑定过程的指标统计
	metrics.Goroutines.WithLabelValues(metrics.Binding).Inc()
	defer metrics.Goroutines.WithLabelValues(metrics.Binding).Dec()

	// 执行绑定循环
	status := sched.bindingCycle(bindingCycleCtx, state, fwk, scheduleResult, assumedPodInfo, start,podsToActivate)

	// 绑定失败的错误处理
	if !status.IsSuccess() {


		sched.handleBindingCycleError(bindingCycleCtx, state, fwk, assumedPodInfo,
```
