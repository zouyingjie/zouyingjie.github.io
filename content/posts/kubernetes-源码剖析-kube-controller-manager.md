---
title: "【Kubernetes 源码剖析】kube-controller-manager 工作原理与实现"
date: 2025-08-20T17:41:20+08:00
draft: true
tags:
  - Kubernetes
  - 源码剖析
  - Controller
categories:
  - 云原生
source: "https://blog.csdn.net/Ahri_J/article/details/150559209"
---
### K8s 的控制循环

Kubernetes 运行 Pod 的核心逻辑就是基于
 Informer
 机制的控制循环（Control Loop）。每当 etcd 中的数据有更新，会触发相应的事件通知给各个 Controller，Controller 会根据这些事件来决定是否需要对集群状态进行调整，逻辑如下：

![请添加图片描述](https://i-blog.csdnimg.cn/direct/d009175bb1164c98a8954b9953581dd8.png)

```
for {
  实际状态 := 获取集群中对象 X 的实际状态（Actual State）
  期望状态 := 获取集群中对象 X 的期望状态（Desired State）
  if 实际状态 == 期望状态{
    什么都不做
  } else {
    执行编排动作，将实际状态调整为期望状态
  }
}
```

各类资源都有相应的控制器 Controller 来实现这个控制循环，比如管理节点资源的 NodeController，管理 Deployment 的 DeploymentController。kube-controller-manager 的主要职责就是启动和管理这些 Controller，所管理的 Controller 列表位于 [controller names](https://github.com/kubernetes/kubernetes/blob/v1.32.8/cmd/kube-controller-manager/names/controller_names.go)。

### kube-controller-manager 启动流程

kube-controller-manager 的启动方法是位于 controller-manager.go 文件的 [Run](https://github.com/kubernetes/kubernetes/blob/v1.32.8/cmd/kube-controller-manager/app/controllermanager.go#L180) 方法，核心代码如下：

```go
func Run(ctx context.Context, c *config.CompletedConfig) error {
	// ... 代码省略

	// 1. 一系列初始化动作，比如初始化事件广播器，与 kube-apiserver 交互的客户端对象等
	c.EventBroadcaster.StartStructuredLogging(0)
	c.EventBroadcaster.StartRecordingToSink(&v1core.EventSinkImpl{Interface: c.Client.CoreV1().Events("")})
	defer c.EventBroadcaster.Shutdown()
	...
	// 创建交互客户端
	clientBuilder, rootClientBuilder := createClientBuilders(c)

	saTokenControllerDescriptor := newServiceAccountTokenControllerDescriptor(rootClientBuilder)

	// 2. 定义核心启动方法
	run := func(ctx context.Context, controllerDescriptors map[string]*ControllerDescriptor) {
		controllerContext, err := CreateControllerContext(ctx, c, rootClientBuilder, clientBuilder)
		if err != nil {
			logger.Error(err, "Error building controller context")
			klog.FlushAndExit(klog.ExitFlushTimeout, 1)
		}

		if err := StartControllers(ctx, controllerContext, controllerDescriptors, unsecuredMux, healthzHandler); err != nil {

			logger.Error(err, "Error starting controllers")
			klog.FlushAndExit(klog.ExitFlushTimeout, 1)
		}

		controllerContext.InformerFactory.Start(stopCh)
		controllerContext.ObjectOrMetadataInformerFactory.Start(stopCh)
		close(controllerContext.InformersStarted)

		<-ctx.Done()
	}

	// 3. 是否需要选主，不需要的话直接运行 run 方法
	if !c.ComponentConfig.Generic.LeaderElection.LeaderElect {
		controllerDescriptors := NewControllerDescriptors()
		controllerDescriptors[names.ServiceAccountTokenController] = saTokenControllerDescriptor
		// 执行 run 方法
		run(ctx, controllerDescriptors)
		return nil
	}
	// 4. 选主后执行 run 方法
	go leaderElectAndRun()
	//... 代码省略
```

除了初始化和选主操作外，Controller 的启动流程都在内部的 `run` 方法中执行，我们来看下这个方法的具体实现。

### Controller 创建启动流程

##### 初始化 Controller 描述符

在运行 run 方法前，代码里先执行了 `NewControllerDescriptors()` 方法创建 ControllerDescriptors，即控制器描述符。

```Go
controllerDescriptors := NewControllerDescriptors()
controllerDescriptors = filteredControllerDescriptors(controllerDescriptors, leaderMigrator.FilterFunc, leadermigration.ControllerMigrated)

// DO NOT start saTokenController under migration lock
delete(controllerDescriptors, names.ServiceAccountTokenController)
run(ctx, controllerDescriptors)
```

每种 Controller 都有一个 ControllerDescriptor 描述符，描述符中包含了 Controller 的名称、初始化函数等信息。下面是我们常见的 [Deployment Controller](https://github.com/kubernetes/kubernetes/blob/v1.32.7/cmd/kube-controller-manager/app/controllermanager.go#L421) 的描述符信息。

```go
// https://github.com/kubernetes/kubernetes/blob/v1.32.7/cmd/kube-controller-manager/app/controllermanager.go#L421
type ControllerDescriptor struct {
	name                      string  // 控制器名称，不能为空
	initFunc                  InitFunc // 启动函数，不能为空
	requiredFeatureGates      []featuregate.Feature // 启动所需的特性
	aliases                   []string // 别名
	isDisabledByDefault       bool // 默认禁用
	isCloudProviderController bool // 是否为云提供商控制器
	requiresSpecialHandling   bool // 是否需要特殊处理
}

// https://github.com/kubernetes/kubernetes/blob/master/cmd/kube-controller-manager/app/apps.go#L98
func newDeploymentControllerDescriptor() *ControllerDescriptor {
	return &ControllerDescriptor{
		name:     names.DeploymentController,
		aliases:  []string{"deployment"},
		initFunc: startDeploymentController,
	}
}
```

[NewControllerDescriptors()](https://github.com/kubernetes/kubernetes/blob/v1.32.7/cmd/kube-controller-manager/app/controllermanager.go#L495) 方法内部会定义一个 [register()](https://github.com/kubernetes/kubernetes/blob/v1.32.7/cmd/kube-controller-manager/app/controllermanager.go#L500) 注册函数，然后执行一系列的注册，最终会生成一个 Controller 名称到描述 `map[string]*ControllerDescriptor` 的映射表。

```go
func NewControllerDescriptors() map[string]*ControllerDescriptor {
	controllers := map[string]*ControllerDescriptor{}
	aliases := sets.NewString()

	// All the controllers must fulfil common constraints, or else we will explode.
	register := func(controllerDesc *ControllerDescriptor) {
		if controllerDesc == nil {
			panic("received nil controller for a registration")
		}
		name := controllerDesc.Name()
		if len(name) == 0 {
			panic("received controller without a name for a registration")
		}
		if _, found := controllers[name]; found {
			panic(fmt.Sprintf("controller name %q was registered twice", name))
		}
		if controllerDesc.GetInitFunc() == nil {
			panic(fmt.Sprintf("controller %q does not have an init function", name))
		}

		for _, alias := range controllerDesc.GetAliases() {
			if aliases.Has(alias) {
				panic(fmt.Sprintf("controller %q has a duplicate alias %q", name, alias))
			}
			aliases.Insert(alias)
		}

		controllers[name] = controllerDesc
	}

	// First add "special" controllers that aren't initialized normally. These controllers cannot be initialized
	// in the main controller loop initialization, so we add them here only for the metadata and duplication detection.
	// app.ControllerDescriptor#RequiresSpecialHandling should return true for such controllers
	// The only known special case is the ServiceAccountTokenController which *must* be started
	// first to ensure that the SA tokens for future controllers will exist. Think very carefully before adding new
	// special controllers.
	register(newServiceAccountTokenControllerDescriptor(nil))

	register(newEndpointsControllerDescriptor())
	register(newEndpointSliceControllerDescriptor())
	register(newEndpointSliceMirroringControllerDescriptor())
	register(newReplicationControllerDescriptor())
	register(newPodGarbageCollectorControllerDescriptor())
	register(newResourceQuotaControllerDescriptor())
	register(newNamespaceControllerDescriptor())
	register(newServiceAccountControllerDescriptor())
	register(newGarbageCollectorControllerDescriptor())
	register(newDaemonSetControllerDescriptor())
	register(newJobControllerDescriptor())
	register(newDeploymentControllerDescriptor())
	// ... 代码省略
	return controllers
}
```

##### 创建 ControllerContext

创建完描述后，就会进入 run 方法启动所有 Controller 了，这里第一步就是调用 `CreateControllerContext` 方法创建[ControllerContext（控制器上下文）](https://github.com/kubernetes/kubernetes/blob/v1.32.7/cmd/kube-controller-manager/app/controllermanager.go#L366)。这是一个结构体，包含了控制器运行所需的所有上下文信息，包括 Kubernetes 客户端、Informer 工厂等，ControllerContext 会被传递给各个控制器，以便它们能够访问共享的资源和服务。

```go
type ControllerContext struct {

	// 提供与 kube-apiserver 通信的客户端
	ClientBuilder clientbuilder.ControllerClientBuilder

	// 提供对各种 Kubernetes 资源的 Informer 访问
	// Informer 用于监听 Kubernetes 资源的变化并提供事件通知，控制器可以通过它们获取资源的最新状态。
	InformerFactory informers.SharedInformerFactory

	// 提供 对象/元数据 Informer 访问，主要是监听类型化的（具有确定类型）或动态的（无需在编译时知道类型，但需要提供资源的 metadata 信息）资源的元数据变化
	ObjectOrMetadataInformerFactory informerfactory.InformerFactory

	// 提供控制器的初始化选项和配置参数
	ComponentConfig kubectrlmgrconfig.KubeControllerManagerConfiguration

	RESTMapper *restmapper.DeferredDiscoveryRESTMapper

	InformersStarted chan struct{}

	// 重同步周期函数，返回一个时间间隔，
	// 避免多个控制器同步执行，防止同时向 API 服务器发送大量 list 请求
	ResyncPeriod func() time.Duration


	//提供一个设置控制器管理器特定指标的代理，用于监控和观测控制器的运行状态
	ControllerManagerMetrics *controllersmetrics.ControllerManagerMetrics

	// 圾收集器的依赖图构建器，用来跟踪集群中资源之间的依赖关系
	// 当资源不在被依赖时，确保可以得到清理
	GraphBuilder *garbagecollector.GraphBuilder
}
```

##### 创建控制器：run()->StartControllers()

控制器运行所需的上下文准备好后，就会调用 `StartControllers` 方法启动所有 Controller。

```go
func StartControllers(ctx context.Context, controllerCtx ControllerContext, controllerDescriptors map[string]*ControllerDescriptor,
	unsecuredMux *mux.PathRecorderMux, healthzHandler *controllerhealthz.MutableHealthzHandler) error {
	var controllerChecks []healthz.HealthChecker

	if serviceAccountTokenControllerDescriptor, ok := controllerDescriptors[names.ServiceAccountTokenController]; ok {
		check, err := StartController(ctx, controllerCtx, serviceAccountTokenControllerDescriptor, unsecuredMux)
		if err != nil {
			return err
		}
		if check != nil {
			// HealthChecker should be present when controller has started
			controllerChecks = append(controllerChecks, check)
		}
	}
 emitted for it - this is a bit debatable and could be revised.
	for _, controllerDesc := range controllerDescriptors {
		if controllerDesc.RequiresSpecialHandling() {
			continue
		}

		check, err := StartController(ctx, controllerCtx, controllerDesc, unsecuredMux)
		if err != nil {
			return err
		}
		if check != nil {
			// HealthChecker should be present when controller has started
			controllerChecks = append(controllerChecks, check)
		}
	}

	healthzHandler.AddHealthChecker(controllerChecks...)

	return nil
}
```

其核心流程是遍历创建好的控制器描述符集合，然后调用 `StartController` 方法创建并启动具体的 Controller。

```Go
func StartController(ctx context.Context, controllerCtx ControllerContext, controllerDescriptor *ControllerDescriptor,
	unsecuredMux *mux.PathRecorderMux) (healthz.HealthChecker, error) {
	logger := klog.FromContext(ctx)
	controllerName := controllerDescriptor.Name()

	for _, featureGate := range controllerDescriptor.GetRequiredFeatureGates() {
		if !utilfeature.DefaultFeatureGate.Enabled(featureGate) {
			logger.Info("Controller is disabled by a feature gate", "controller", controllerName, "requiredFeatureGates", controllerDescriptor.GetRequiredFeatureGates())
			return nil, nil
		}
	}

	if controllerDescriptor.IsCloudProviderController() {
		logger.Info("Skipping a cloud provider controller", "controller", controllerName)
		return nil, nil
	}

	if !controllerCtx.IsControllerEnabled(controllerDescriptor) {
		logger.Info("Warning: controller is disabled", "controller", controllerName)
		return nil, nil
	}

	time.Sleep(wait.Jitter(controllerCtx.ComponentConfig.Generic.ControllerStartInterval.Duration, ControllerStartJitter))

	logger.V(1).Info("Starting controller", "controller", controllerName)

	initFunc := controllerDescriptor.GetInitFunc()
	ctrl, started, err := initFunc(klog.NewContext(ctx, klog.LoggerWithName(logger, controllerName)), controllerCtx, controllerName)
	if err != nil {
		logger.Error(err, "Error starting controller", "controller", controllerName)
		return nil, err
	}
	if !started {
		logger.Info("Warning: skipping controller", "controller", controllerName)
		return nil, nil
	}

	check := controllerhealthz.NamedPingChecker(controllerName)
	if ctrl != nil {
		// check if the controller supports and requests a debugHandler
		// and it needs the unsecuredMux to mount the handler onto.
		if debuggable, ok := ctrl.(controller.Debuggable); ok && unsecuredMux != nil {
			if debugHandler := debuggable.DebuggingHandler(); debugHandler != nil {
				basePath := "/debug/controllers/" + controllerName
				unsecuredMux.UnlistedHandle(basePath, http.StripPrefix(basePath, debugHandler))
				unsecuredMux.UnlistedHandlePrefix(basePath+"/", http.StripPrefix(basePath, debugHandler))
			}
		}
		if healthCheckable, ok := ctrl.(controller.HealthCheckable); ok {
			if realCheck := healthCheckable.HealthChecker(); realCheck != nil {
				check = controllerhealthz.NamedHealthChecker(controllerName, realCheck)
			}
		}
	}

	logger.Info("Started controller", "controller", controllerName)
	return check, nil
}
```

该函数的流程为：

1. **检查 FeatureGate 是否开启**：检查 Controller 是否需要通过 FeatureGate 开启，如果未开启，则跳过该 Controller。
2. **检查是否为云提供商 Controller**：如果是云提供商的 Controller，则跳过该 Controller。
3. **检查 Controller 是否启用**：如果 Controller 未启用，则跳过该 Controller。
4. **短暂等待**：调用 `time.sleep()` 短暂等待，防止 Controller 启动过快对 kube-apiserver 造成压力。
5. **启动 Controller**：调用 Controller 的 initFunc 启动 Controller。
6. **注册健康检查**：如果 Controller 实现了健康检查接口，则注册健康检查。

##### 启动 Informer

在执行完 `StartControllers` 启动完所有控制器后，run 方法的最后一步是启动 Informer 工厂，这一步会启动所有的 Informer 监听，当资源发生变化时，相关的 Controller 会收到通知并进行相应的处理。

```
controllerContext.InformerFactory.Start(stopCh)
controllerContext.ObjectOrMetadataInformerFactory.Start(stopCh)
```

### 总结

可以看到 kube-controller-manager 的整体逻辑还是比较简单的，主要就是做了一系列初始化工作后，去创建并启动 Controller 并开启 Informer 监听，这样 各个 Controller 就可以通过 Informer 机制监听资源变化并执行相应的控制逻辑了。
