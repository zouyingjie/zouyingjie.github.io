---
title: "【Kubernetes 源码剖析】Deployment 的实现原理"
date: 2025-08-27T15:38:47+08:00
tags:
  - Kubernetes
  - 源码剖析
  - Deployment
categories:
  - 云原生
source: "https://blog.csdn.net/Ahri_J/article/details/150928147"
---
本篇我们来探讨下 Deployment Controller 的执行过程，了解下 Deployment 具体的实现原理。

### Deployment 概述

Kubernetes 的 Deployment 用来管理无状态应用的部署和扩缩容，除了少数分布式存储外，我们日常开发的所有服务都是无状态的，状态数据都被存储在
 关系型数据库
、缓存等外部存储中，因此大部分情况下都是使用 Deployment 作为 Controller 来部署服务。

下面是一个简单的 Deployment 配置示例，我们声明了一个 nginx 的 Deployment，期望运行 3 个副本，最终 Kubernetes 会帮我们创建出三个运行 Nginx 的 Pod。

```
apiVersion: apps/v1
kind: Deployment
metadata:
  name: nginx-deployment
  labels:
    app: nginx
spec:
  replicas: 3
  selector:
    matchLabels:
      app: nginx
  template:
    metadata:
      labels:
        app: nginx
    spec:
      containers:
        - name: nginx
          image: nginx:latest
          ports:
            - containerPort: 80
```

Deployment 本身其实并不直接管理 Pod，而是通过 ReplicaSet 来间接管理 Pod 的生命周期。可以看到我们通过 yaml 文件创建后，会有 1 个 Deployment、 1 个 ReplicaSet 和 3 个 Pod 对象被创建。

```bash
$ kubectl apply -f nginx-deployment.yml
deployment.apps/nginx-deployment created

$ kubectl get deployments.apps
NAME               READY   UP-TO-DATE   AVAILABLE   AGE
nginx-deployment   3/3     3            3           17s

$ kubectl get replicasets.apps
NAME                        DESIRED   CURRENT   READY   AGE
nginx-deployment-96b9d695   3         3         3       23s

$ kubectl get pods
NAME                              READY   STATUS    RESTARTS   AGE
nginx-deployment-96b9d695-47trr   1/1     Running   0          26s
nginx-deployment-96b9d695-9sl7z   1/1     Running   0          26s
nginx-deployment-96b9d695-gbxdt   1/1     Running   0          26s
```

任何 Pod、ReplicaSet 以及 Deployment 的变更都会被 Deployment Controller 监听到，并做出相应的处理，下面我们来看下 Deployment Controller 的具体。

### Deployment Controller 实现原理

#### Informer
 监听

上面我们提到 Pod、ReplicaSet 以及 Deployment 的变更都会被 Deployment Controller 监听到。比如：

- Pod 被删除时，Deployment Controller 会根据当前的 ReplicaSet 状态来决定是否需要创建新的 Pod 以满足期望的副本数。
- ReplicaSet 被删除或修改时，Deployment Controller 会根据当前的 Deployment 状态来决定是否需要创建新的 ReplicaSet。
- Deployment 变更时，Deployment Controller 会根据新的 Deployment 配置来创建新的 ReplicaSet 和 Pod。

之所以能这样监听，是 Deployment Controller 在创建函数[NewDeploymentController](https://github.com/kubernetes/kubernetes/blob/v1.32.8/pkg/controller/deployment/deployment_controller.go#L101) 中向相关 Informer 注册了事件处理函数，代码如下：

```go
// https://github.com/kubernetes/kubernetes/blob/v1.32.8/pkg/controller/deployment/deployment_controller.go#L101

func NewDeploymentController(ctx context.Context, dInformer appsinformers.DeploymentInformer, rsInformer appsinformers.ReplicaSetInformer, podInformer coreinformers.PodInformer, client clientset.Interface) (*DeploymentController, error) {
	...

	dInformer.Informer().AddEventHandler(cache.ResourceEventHandlerFuncs{
		AddFunc: func(obj interface{}) {
			dc.addDeployment(logger, obj)
		},
		UpdateFunc: func(oldObj, newObj interface{}) {
			dc.updateDeployment(logger, oldObj, newObj)
		},
		// This will enter the sync loop and no-op, because the deployment has been deleted from the store.
		DeleteFunc: func(obj interface{}) {
			dc.deleteDeployment(logger, obj)
		},
	})
	rsInformer.Informer().AddEventHandler(cache.ResourceEventHandlerFuncs{
		AddFunc: func(obj interface{}) {
			dc.addReplicaSet(logger, obj)
		},
		UpdateFunc: func(oldObj, newObj interface{}) {
			dc.updateReplicaSet(logger, oldObj, newObj)
		},
		DeleteFunc: func(obj interface{}) {
			dc.deleteReplicaSet(logger, obj)
		},
	})
	podInformer.Informer().AddEventHandler(cache.ResourceEventHandlerFuncs{
		DeleteFunc: func(obj interface{}) {
			dc.deletePod(logger, obj)
		},
	})

    // 指定同步处理函数
	dc.syncHandler = dc.syncDeployment

	return dc, nil
}
```

DeploymentController 接收 DeploymentInformer、ReplicaSetInformer 和 PodInformer 三种
 类
型的 Informer，并注册相应的监听函数。对于 Deployment 和 ReplicaSet，Deployment Controller 都监听了新增、更新和删除事件，而对于 Pod 则只监听了删除事件

![](https://pub-08b57ed9c8ce4fadab4077a9d577e857.r2.dev/csdn-d7ef035f58c3bd2cece4b4280b202471d2daf1fd511d08bf5caaa383671e4efc.png)

#### Deployment Controller 启动

在 kube-controller-manager 启动时，会调用 NewDeploymentController 函数来创建 DeploymentController 实例，然后会执行 DeploymentController 的 [Run](https://github.com/kubernetes/kubernetes/blob/v1.32.8/pkg/controller/deployment/deployment_controller.go#L162) 方法，开始启动 Controller 的工作流程。

```go
// https://github.com/kubernetes/kubernetes/blob/v1.32.8/pkg/controller/deployment/deployment_controller.go#L162
// Run begins watching and syncing.
func (dc *DeploymentController) Run(ctx context.Context, workers int) {
	defer utilruntime.HandleCrash()

	// Start events processing pipeline.
	dc.eventBroadcaster.StartStructuredLogging(3)
	dc.eventBroadcaster.StartRecordingToSink(&v1core.EventSinkImpl{Interface: dc.client.CoreV1().Events("")})
	defer dc.eventBroadcaster.Shutdown()

	defer dc.queue.ShutDown()

	logger := klog.FromContext(ctx)
	logger.Info("Starting controller", "controller", "deployment")
	defer logger.Info("Shutting down controller", "controller", "deployment")

	if !cache.WaitForNamedCacheSync("deployment", ctx.Done(), dc.dListerSynced, dc.rsListerSynced, dc.podListerSynced) {
		return
	}

	for i := 0; i < workers; i++ {
		go wait.UntilWithContext(ctx, dc.worker, time.Second)
	}

	<-ctx.Done()
}
```

这里的核心逻辑就是启动多个 Goroutine 运行 DeploymentController 的 [worker](https://github.com/kubernetes/kubernetes/blob/v1.32.8/pkg/controller/deployment/deployment_controller.go#L482) 方法，该方法会从队列中读取最新的 Deployment 事件并进行同步处理。

这里的 worker goroutine 数量受 kube-controller-manager 的 `--concurrent-deployment-syncs` 参数控制，默认是 5，表示可以同时操作 5 个 Deployment 的同步处理。可以根据需要来修改参数，worker 越多，Deployment 的变更响应速度就会更快，同时也会占用更多的 CPU 和网络资源。

worker 后续主要是调用了 DeploymentController 的 syncHandler，也就是在 `NewDeploymentController` 是指定的 `dc.syncHandler = dc.syncDeployment` 方法。

```go
// worker runs a worker thread that just dequeues items, processes them, and marks them done.
// It enforces that the syncHandler is never invoked concurrently with the same key.
func (dc *DeploymentController) worker(ctx context.Context) {
	for dc.processNextWorkItem(ctx) {
	}
}

func (dc *DeploymentController) processNextWorkItem(ctx context.Context) bool {
	key, quit := dc.queue.Get()
	if quit {
		return false
	}
	defer dc.queue.Done(key)

	err := dc.syncHandler(ctx, key)
	dc.handleErr(ctx, err, key)

	return true
}
```

#### 同步处理

[syncDeployment](https://github.com/kubernetes/kubernetes/blob/v1.32.8/pkg/controller/deployment/deployment_controller.go#L590) 是处理 Deployment 相关的资源对象所有变更的唯一入口。

以下是该方法的核心代码：

```go
// syncDeployment will sync the deployment with the given key.
// This function is not meant to be invoked concurrently with the same key.
func (dc *DeploymentController) syncDeployment(ctx context.Context, key string) error {

    // 1. 根据传入的 key 获取 Deployment 资源
	namespace, name, err := cache.SplitMetaNamespaceKey(key)
	deployment, err := dc.dLister.Deployments(namespace).Get(name)

	d := deployment.DeepCopy()

    // 2. 检查 Deployment 的 Selector 是否为空（即选择所有 Pod）
    // 为空代表选择所有 Pod，属于危险操作，只更新状态，不做后续处理。
	everything := metav1.LabelSelector{}
	if reflect.DeepEqual(d.Spec.Selector, &everything) {
		dc.eventRecorder.Eventf(d, v1.EventTypeWarning, "SelectingAll", "This deployment is selecting all pods. A non-empty selector is required.")
		if d.Status.ObservedGeneration < d.Generation {
			d.Status.ObservedGeneration = d.Generation
			dc.client.AppsV1().Deployments(d.Namespace).UpdateStatus(ctx, d, metav1.UpdateOptions{})
		}
		return nil
	}

    // 3. 根据 Deployment 获取对应的 ReplicaSet 列表
	rsList, err := dc.getReplicaSetsForDeployment(ctx, d)

    // 4. 根据 Deployment 和 ReplicaSet 获取对应的 Pod 列表
	podMap, err := dc.getPodMapForDeployment(d, rsList)

    // 5. 如果正在删除中，只同步状态
	if d.DeletionTimestamp != nil {
		return dc.syncStatusOnly(ctx, d, rsList)
	}

    // 6. 检查 Deployment 的暂停状态，如果暂停中，则执行同步
	if err = dc.checkPausedConditions(ctx, d); err != nil {
		return err
	}
	if d.Spec.Paused {
		return dc.sync(ctx, d, rsList)
	}

	// 7. 如果需要回滚且目标 Revision 还在，则执行回滚
	if getRollbackTo(d) != nil {
		return dc.rollback(ctx, d, rsList)
	}

    // 8. 检查是否为扩缩容事件，如果是则执行同步操作
	scalingEvent, err := dc.isScalingEvent(ctx, d, rsList)
	if scalingEvent {
		return dc.sync(ctx, d, rsList)
	}

    // 9. 根据部署策略，做相应的拟合处理
	switch d.Spec.Strategy.Type {
	case apps.RecreateDeploymentStrategyType:
		return dc.rolloutRecreate(ctx, d, rsList, podMap)
	case apps.RollingUpdateDeploymentStrategyType:
		return dc.rolloutRolling(ctx, d, rsList)
	}
	return fmt.Errorf("unexpected deployment strategy type: %s", d.Spec.Strategy.Type)
}
```

主要流程如下：

1. 首先根据 key 获取到对应的 Deployment 资源对象。
2. 根据 Deployment 获取到 ReplicaSet 对象。
3. 根据 Deployment 和 ReplicaSet 获取到 Pod 对象。
4. 如果处于暂停状态或者需要进行扩缩容，则调用 `dc.sync(ctx, d, rsList)` 方法进行同步处理。
5. 如果需要回滚到某个版本，则调用 `dc.rollback(ctx, d, rsList)` 方法进行回滚处理。
6. 如果部署策略是 Recreate，则调用 `dc.rolloutRecreate(ctx, d, rsList, podMap)` 方法进行重新创建处理。
7. 如果部署策略是 RollingUpdate，则调用 `dc.rolloutRolling(ctx, d, rsList)` 方法进行滚动更新处理。

可以看到处理的关键就是 `sync`、`rollback`、`rolloutRecreate` 和 `rolloutRolling` 这几个方法，它们分别对应了不同的处理逻辑，我们来分别看下。

#### sync 同步

当 Deployment 处于暂停状态或者触发的事件是扩缩容，也就是 ReplicaSet 设置的副本数量和实际 Pod 数量不一致时，就会调用 [dc.sync(ctx, d, rsList)](https://github.com/kubernetes/kubernetes/blob/v1.32.8/pkg/controller/deployment/sync.go#L49) 方法进行同步处理。我们省略掉无关的代码，核心逻辑如下：

```go
// sync is responsible for reconciling deployments on scaling events or when they
// are paused.
func (dc *DeploymentController) sync(ctx context.Context, d *apps.Deployment, rsList []*apps.ReplicaSet) error {

	newRS, oldRSs, err := dc.getAllReplicaSetsAndSyncRevision(ctx, d, rsList, false)
	dc.scale(ctx, d, newRS, oldRSs);

	// Clean up the deployment when it's paused and no rollback is in flight.
	if d.Spec.Paused && getRollbackTo(d) == nil {
		if err := dc.cleanupDeployment(ctx, oldRSs, d); err != nil {
			return err
		}
	}

	allRSs := append(oldRSs, newRS)
	return dc.syncDeploymentStatus(ctx, allRSs, newRS, d)
}
```

这里首先会调用 `getAllReplicaSetsAndSyncRevision` 方法获取 Deployment 对应的 ReplicaSet 对象和历史 ReplicaSet 对象列表。然后执行 [dc.scale](https://github.com/kubernetes/kubernetes/blob/v1.32.8/pkg/controller/deployment/sync.go#L299)) 进行扩容，我们来看下 scale 方法的实现。

```go
func (dc *DeploymentController) scale(ctx context.Context, deployment *apps.Deployment, newRS *apps.ReplicaSet, oldRSs []*apps.ReplicaSet) error {

	if activeOrLatest := deploymentutil.FindActiveOrLatest(newRS, oldRSs); activeOrLatest != nil {
		if *(activeOrLatest.Spec.Replicas) == *(deployment.Spec.Replicas) {
			return nil
		}
		_, _, err := dc.scaleReplicaSetAndRecordEvent(ctx, activeOrLatest, *(deployment.Spec.Replicas), deployment)
		return err
	}


	if deploymentutil.IsSaturated(deployment, newRS) {
		for _, old := range controller.FilterActiveReplicaSets(oldRSs) {
			if _, _, err := dc.scaleReplicaSetAndRecordEvent(ctx, old, 0, deployment); err != nil {
				return err
			}
		}
		return nil
	}

	// There are old replica sets with pods and the new replica set is not saturated.
	// We need to proportionally scale all replica sets (new and old) in case of a
	// rolling deployment.
	if deploymentutil.IsRollingUpdate(deployment) {
		...
	}
	return nil
}
```

scale 方法主要有三种情况：

- `FindActiveOrLatest`：获取活跃度或者最新的 ReplicaSet 对象，进行扩缩容。这一般是首次创建并部署的情况，只有一个 ReplicaSet，没有多版本共存的情况。
- `IsSaturated`：最新版本的 ReplicaSet 已达到饱和，也就是达到了期望的副本数。需要将旧版本的 ReplicaSet 缩容为 0。
- `IsRollingUpdate`：当前的 Deployment 正在滚动更新，需要执行一系列处理，精确计算不同副本的比例分配。

我们来分别看下具体实现。

##### 首次部署

这里会获取活跃度或者最新的 ReplicaSet 对象，然后判断该 ReplicaSet 的副本数是否和 Deployment 期望的副本数一致，如果一致则不做处理，否则调用 [dc.scaleReplicaSetAndRecordEvent](https://github.com/kubernetes/kubernetes/blob/master/pkg/controller/deployment/sync.go#L403) 进行扩容操作，这里最终是通过 [scaleReplicaSetAndRecordEvent](https://github.com/kubernetes/kubernetes/blob/v1.32.8/pkg/controller/deployment/sync.go#L395) 和 [scaleReplicaSet](https://github.com/kubernetes/kubernetes/blob/v1.32.8/pkg/controller/deployment/sync.go#L404) 函数实现的，后续所有需要调整副本的操作都是在 scaleReplicaSet 实现的。 代码如下：

```go
func (dc *DeploymentController) scaleReplicaSetAndRecordEvent(ctx context.Context, rs *apps.ReplicaSet, newScale int32, deployment *apps.Deployment) (bool, *apps.ReplicaSet, error) {
	// No need to scale
	if *(rs.Spec.Replicas) == newScale {
		return false, rs, nil
	}
	scaled, newRS, err := dc.scaleReplicaSet(ctx, rs, newScale, deployment)
	return scaled, newRS, err
}

func (dc *DeploymentController) scaleReplicaSet(ctx context.Context, rs *apps.ReplicaSet, newScale int32, deployment *apps.Deployment) (bool, *apps.ReplicaSet, error) {

	...
	if sizeNeedsUpdate || annotationsNeedUpdate {
		// 更新副本数量
		*(rsCopy.Spec.Replicas) = newScale
		// 更新 RS 注解
		deploymentutil.SetReplicasAnnotations(rsCopy, *(deployment.Spec.Replicas), *(deployment.Spec.Replicas)+deploymentutil.MaxSurge(*deployment))
		// 执行更新
		rs, err = dc.client.AppsV1().ReplicaSets(rsCopy.Namespace).Update(ctx, rsCopy, metav1.UpdateOptions{})
		if err == nil && sizeNeedsUpdate {
			var scalingOperation string
			if oldScale < newScale {
				scalingOperation = "up"
			} else {
				scalingOperation = "down"
			}
			scaled = true
			// 记录事件
			dc.eventRecorder.Eventf(deployment, v1.EventTypeNormal, "ScalingReplicaSet", "Scaled %s replica set %s from %d to %d", scalingOperation, rs.Name, oldScale, newScale)
		}
	}
	return scaled, rs, err
}
```

可以看到其核心逻辑就是修改副本值，然后记录事件，我们在 Deployment 中看到的事件信息就是这里记录的，我们通过 `kubectl scale` 命令对 Deployment 进行扩容可以看到对应的输出。

```bash
$ kubectl scale deployment nginx-deployment --replicas 5

$ kubectl describe deployments.apps nginx-deployment
Name:                   nginx-deployment
Namespace:              default
...
OldReplicaSets:  <none>
NewReplicaSet:   nginx-deployment-96b9d695 (5/5 replicas created)
Events:
  Type    Reason             Age   From                   Message
  ----    ------             ----  ----                   -------
  Normal  ScalingReplicaSet  1s    deployment-controller  Scaled up replica set nginx-deployment-96b9d695 from 3 to 5
```

##### 副本饱和

当实际的可用副本数达到期望值时，表示 ReplicaSet 已经饱和。

```go
func IsSaturated(deployment *apps.Deployment, rs *apps.ReplicaSet) bool {
	if rs == nil {
		return false
	}
	desiredString := rs.Annotations[DesiredReplicasAnnotation]
	desired, err := strconv.Atoi(desiredString)
	if err != nil {
		return false
	}
	return *(rs.Spec.Replicas) == *(deployment.Spec.Replicas) &&
		int32(desired) == *(deployment.Spec.Replicas) &&
		rs.Status.AvailableReplicas == *(deployment.Spec.Replicas)
}
```

此时无需在进行扩缩容操作。但对于旧的 ReplicaSet 则需要将其副本数缩容为 0，因此也会调用 `scaleReplicaSetAndRecordEvent` 方法将所有旧版本的 ReplicaSet 缩容为 0。

```go
for _, old := range controller.FilterActiveReplicaSets(oldRSs) {
	// 副本数为 0
	if _, _, err := dc.scaleReplicaSetAndRecordEvent(ctx, old, 0, deployment); err != nil {
		return err
	}
}
```

##### 滚动升级

如果一个 Deployment 即存在旧的 RS 副本集，且新的 RS 尚未饱和，说明其处于滚动升级状态，Deployment Controller 需要根据滚动升级的策略来精确计算每个 ReplicaSet 的副本数。

首先我们需要了解滚动更新相关的两个参数：maxUnavailable 和 maxSurge：

- **maxUnavailable** 表示在更新过程中能够进入不可用状态的 Pod 的最大值，可以是比例或者绝对值。默认值为 25%，比如我们预期的副本数是 4，那么在更新过程中最多允许有 1 个 Pod 处于不可用状态。
- **maxSurge** 表示能够额外创建的 Pod 个数，可以是比例或者绝对值。默认值为 25%，比如我们预期的副本数是 4，那么在更新过程中最多允许有 1 个 Pod，也就是最多有 5 个 Pod 同时存在。

```yaml
$ kubectl get deployments.apps nginx-deployment -o yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  labels:
    app: nginx
  name: nginx-deployment
  namespace: default

spec:
  replicas: 5
  selector:
    matchLabels:
      app: nginx
  strategy:
    rollingUpdate:
      maxSurge: 25%
      maxUnavailable: 25%
    type: RollingUpdate
	...
```

我们来看下具体的代码实现：

```go
if deploymentutil.IsRollingUpdate(deployment) {

		// 1. 获取所有活跃的 ReplicaSet
		allRSs := controller.FilterActiveReplicaSets(append(oldRSs, newRS))

		// 2. 获取所有 ReplicaSet 的 Pod 副本总数
		allRSsReplicas := deploymentutil.GetReplicaCountForReplicaSets(allRSs)

		// 3. 根据 Deployment 的期望副本数和 maxSurge 计算允许的最大副本数
		allowedSize := int32(0)
		if *(deployment.Spec.Replicas) > 0 {
			allowedSize = *(deployment.Spec.Replicas) + deploymentutil.MaxSurge(*deployment)
		}

		// 4. 计算需要添加或删除的副本数
		deploymentReplicasToAdd := allowedSize - allRSsReplicas


		// 根据扩缩容对副本集进行排序，决定优先级
		// 扩容时优先新版本，缩容时优先旧版本
		switch {
		// 5. 需要新增副本，按副本数从大到小排序，如果副本数相同，则新的 RS 排前面
		case deploymentReplicasToAdd > 0:
			sort.Sort(controller.ReplicaSetsBySizeNewer(allRSs))
		// 6. 需要减少副本，按副本数从大到小排序，如果副本数相同，则旧的 RS 排前面
		case deploymentReplicasToAdd < 0:
			sort.Sort(controller.ReplicaSetsBySizeOlder(allRSs))
		}

		deploymentReplicasAdded := int32(0)
		nameToSize := make(map[string]int32)
		logger := klog.FromContext(ctx)

		// 7. 遍历所有活跃的副本集，计算每个副本集的比例
		for i := range allRSs {
			rs := allRSs[i]
			if deploymentReplicasToAdd != 0 {
				// 计算 RS 的副本变化比例
				proportion := deploymentutil.GetReplicaSetProportion(logger, rs, *deployment, deploymentReplicasToAdd, deploymentReplicasAdded)
				// 计算 RS 的新副本数
				nameToSize[rs.Name] = *(rs.Spec.Replicas) + proportion
				// 记录实际添加的副本数
				deploymentReplicasAdded += proportion
			} else {
				nameToSize[rs.Name] = *(rs.Spec.Replicas)
			}
		}

		// 8. 遍历所有活跃的副本集，更新副本数
		for i := range allRSs {
			rs := allRSs[i]

			//计算因舍入而剩余的副本数，将其加到第一个副本集
			if i == 0 && deploymentReplicasToAdd != 0 {
				leftover := deploymentReplicasToAdd - deploymentReplicasAdded
				nameToSize[rs.Name] = nameToSize[rs.Name] + leftover
				if nameToSize[rs.Name] < 0 {
					nameToSize[rs.Name] = 0
				}
			}

			// 9. 更新 RS 的副本数
			if _, _, err := dc.scaleReplicaSet(ctx, rs, nameToSize[rs.Name], deployment); err != nil {
				// Return as soon as we fail, the deployment is requeued
				return err
			}
		}
	}
```

这里的核心就是基于预期副本数、实际副本总数计算出要变化的副本数量，然后调用 `GetReplicaSetProportion` 计算出变化数后，得到 RS 的新的预期副本数，最后会执行到 `scaleReplicaSet`方法，设置其副本数，并将预期副本数（replicas）和最大副本数（replicas + maxSurge）加到注解上。

```bash
$ kubectl describe rs nginx-deployment-96b9d695
Name:           nginx-deployment-96b9d695
Namespace:      default
Selector:       app=nginx,pod-template-hash=96b9d695
Labels:         app=nginx
                pod-template-hash=96b9d695
Annotations:    deployment.kubernetes.io/desired-replicas: 5
                deployment.kubernetes.io/max-replicas: 7
                deployment.kubernetes.io/revision: 1
```

#### rollback 回滚

Deployment 有一个 revision 的版本概念，是一个单调递增的数字，每次更新都会变化。revision 会被自动加到 Deployment 的 `deployment.kubernetes.io/revision` 注解，代表其当前版本。

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  annotations:
    deployment.kubernetes.io/revision: "3"
```

另外可以通过 `kubectl rollout history` 命令查看历史版本信息，可以看到 revision 和 变更原因。

```
$ kubectl rollout history deployment nginx-deployment
deployment.apps/nginx-deployment
REVISION  CHANGE-CAUSE
1         <none>
2         <none>
3         kubectl set image deployments nginx-deployment nginx=nginx:1.28.0 --record=true
```

基于此 Deployment支持对版本进行回滚，可以回滚到上一个版本或者通过制定 revision 回滚到指定版本，命令如下：

```
// 回退到上一版本
$ kubectl rollout undo deployment nginx-deployment

// 回退到指定版本
$ kubectl rollout undo deployment nginx-deployment --to-revision 2
```

Deployment 的规格字段中有一个 `.spec.revisionHistoryLimit` 字段，用于指定保留的历史版本数量，默认值为 10，其实就是对历史 ReplicaSet 对象做保留。当我们更新升级 Deployment 时，Deployment Controller 会对历史 ReplicaSet 做清理，凡是超出 `revisionHistoryLimit` 的历史版本都会被删除。

```go
// https://github.com/kubernetes/kubernetes/blob/091f87c10bc3532041b77a783a5f832de5506dc8/pkg/controller/deployment/sync.go#L443

func (dc *DeploymentController) cleanupDeployment(ctx context.Context, oldRSs []*apps.ReplicaSet, deployment *apps.Deployment) error {
	...

	// 比较可清理的副本集数量与保留的历史版本数量，如果在范围内则不需要清理
	diff := int32(len(cleanableRSes)) - *deployment.Spec.RevisionHistoryLimit
	if diff <= 0 {
		return nil
	}
	...
	return nil
}
```

当我们执行回滚命令时，Deployment Controller 会调用 [rollback](https://github.com/kubernetes/kubernetes/blob/master/pkg/controller/deployment/rollback.go#L33) 方法进行处理。

```go
// rollback the deployment to the specified revision. In any case cleanup the rollback spec.
func (dc *DeploymentController) rollback(ctx context.Context, d *apps.Deployment, rsList []*apps.ReplicaSet) error {

	newRS, allOldRSs, err := dc.getAllReplicaSetsAndSyncRevision(ctx, d, rsList, true)
	allRSs := append(allOldRSs, newRS)

	rollbackTo := getRollbackTo(d)
	// If rollback revision is 0, rollback to the last revision
	if rollbackTo.Revision == 0 {
		if rollbackTo.Revision = deploymentutil.LastRevision(logger, allRSs); rollbackTo.Revision == 0 {
			// If we still can't find the last revision, gives up rollback
			dc.emitRollbackWarningEvent(d, deploymentutil.RollbackRevisionNotFound, "Unable to find last revision.")
			// Gives up rollback
			return dc.updateDeploymentAndClearRollbackTo(ctx, d)
		}
	}
	for _, rs := range allRSs {
		v, err := deploymentutil.Revision(rs)

		if v == rollbackTo.Revision {
			performedRollback, err := dc.rollbackToTemplate(ctx, d, rs)
			return err
		}
	}

	dc.emitRollbackWarningEvent(d, deploymentutil.RollbackRevisionNotFound, "Unable to find the revision to rollback to.")
	// Gives up rollback
	return dc.updateDeploymentAndClearRollbackTo(ctx, d)
}
```

处理流程如下：

1. 首先获取 Deployment 的所有 ReplicaSet 列表
2. 查找要回滚的版本
3. 如果找到，则对比版本找到对应 ReplicaSet
4. 调用 `rollbackToTemplate` 执行回滚

这里具体的回滚操作就是将对应版本的 ReplicaSet 的 Pod 模板设置为 Deployment 的 Pod 模板，然后在触发后续的滚动更新流程，达到预期状态。

```go
func (dc *DeploymentController) rollbackToTemplate(ctx context.Context, d *apps.Deployment, rs *apps.ReplicaSet) (bool, error) {
	...
	deploymentutil.SetFromReplicaSetTemplate(d, rs.Spec.Template)
	...
}

func SetFromReplicaSetTemplate(deployment *apps.Deployment, template v1.PodTemplateSpec) *apps.Deployment {
	deployment.Spec.Template.ObjectMeta = template.ObjectMeta
	deployment.Spec.Template.Spec = template.Spec
	deployment.Spec.Template.ObjectMeta.Labels = labelsutil.CloneAndRemoveLabel(
		deployment.Spec.Template.ObjectMeta.Labels,
		apps.DefaultDeploymentUniqueLabelKey)
	return deployment
}
```

#### rolloutRecreate 重新创建

当 Deployment 的更新策略类型是 Recreate 时，DeploymentController 会调用 [rolloutRecreate](https://github.com/kubernetes/kubernetes/blob/master/pkg/controller/deployment/recreate.go#L29) 方法进行处理，代码如下：

```go
// rolloutRecreate implements the logic for recreating a replica set.
func (dc *DeploymentController) rolloutRecreate(ctx context.Context, d *apps.Deployment, rsList []*apps.ReplicaSet, podMap map[types.UID][]*v1.Pod) error {

	// 1. 获取所有的 ReplicaSet 和历史 ReplicaSet 列表以及活跃的 ReplicaSet 列表
	newRS, oldRSs, err := dc.getAllReplicaSetsAndSyncRevision(ctx, d, rsList, false)
	allRSs := append(oldRSs, newRS)
	activeOldRSs := controller.FilterActiveReplicaSets(oldRSs)

	// scale down old replica sets.
	// 2. 将所有历史 RS 副本数缩减到 0
	scaledDown, err := dc.scaleDownOldReplicaSetsForRecreate(ctx, activeOldRSs, d)


	if scaledDown {
		// Update DeploymentStatus.
		return dc.syncRolloutStatus(ctx, allRSs, newRS, d)
	}

	// 检查是否还有 Pod 在运行
	if oldPodsRunning(newRS, oldRSs, podMap) {
		return dc.syncRolloutStatus(ctx, allRSs, newRS, d)
	}

	// 创建新的 RS
	if newRS == nil {
		newRS, oldRSs, err = dc.getAllReplicaSetsAndSyncRevision(ctx, d, rsList, true)
		if err != nil {
			return err
		}
		allRSs = append(oldRSs, newRS)
	}

	// 执行扩容
	if _, err := dc.scaleUpNewReplicaSetForRecreate(ctx, newRS, d); err != nil {
		return err
	}

	if util.DeploymentComplete(d, &d.Status) {
		if err := dc.cleanupDeployment(ctx, oldRSs, d); err != nil {
			return err
		}
	}

	// Sync deployment status.
	return dc.syncRolloutStatus(ctx, allRSs, newRS, d)
}
```

整体的逻辑比较简单：

1. 找到所有历史 ReplicaSet
2. 将所有历史 ReplicaSet 的副本数缩减到 0
3. 创建新的 ReplicaSet
4. 执行扩容
5. 执行清理和状态同步

可以看到流程非常符合 `recreate` 的含义，先将全部 Pod 下线在去执行扩容，这会导致有一段时间没有可用的 Pod，因此实际生产中会导致服务不可用，通常不建议生产中使用该方式。

#### rolloutRolling 滚动更新

当 Deployment 的更新策略类型是 RollingUpdate 时，DeploymentController 会调用 [rolloutRolling](https://github.com/kubernetes/kubernetes/blob/master/pkg/controller/deployment/rolling.go#L31) 执行具体的滚动升级。

```go
// rolloutRolling implements the logic for rolling a new replica set.
func (dc *DeploymentController) rolloutRolling(ctx context.Context, d *apps.Deployment, rsList []*apps.ReplicaSet) error {
	newRS, oldRSs, err := dc.getAllReplicaSetsAndSyncRevision(ctx, d, rsList, true)
	allRSs := append(oldRSs, newRS)

	// Scale up, if we can.
	scaledUp, err := dc.reconcileNewReplicaSet(ctx, allRSs, newRS, d)
	if scaledUp {
		return dc.syncRolloutStatus(ctx, allRSs, newRS, d)
	}

	// Scale down, if we can.
	scaledDown, err := dc.reconcileOldReplicaSets(ctx, allRSs, controller.FilterActiveReplicaSets(oldRSs), newRS, d)
	if scaledDown {
		return dc.syncRolloutStatus(ctx, allRSs, newRS, d)
	}

	if deploymentutil.DeploymentComplete(d, &d.Status) {
		if err := dc.cleanupDeployment(ctx, oldRSs, d); err != nil {
			return err
		}
	}

	// Sync deployment status
	return dc.syncRolloutStatus(ctx, allRSs, newRS, d)
}
```

整体逻辑如下：

1. 获取 Deployment 所有的 ReplicaSet
2. 执行 `reconcileNewReplicaSet`，在满足 `maxSurge` 限制的情况下拟合新版本的 ReplicaSet。
3. 执行 `reconcileOldReplicaSets`，在满足 `maxUnavailable` 限制的情况下缩减旧版本的 ReplicaSet。
4. 删除无用的 ReplicaSet、超过 `spec.revisionHistoryLimit` 限制的 ReplicaSet 并同步 Deployment 状态。
