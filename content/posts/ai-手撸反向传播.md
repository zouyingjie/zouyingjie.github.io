---
title: 从零实现反向传播：Micrograd 与神经网络
date: 2026-07-18 17:09:01 +08:00
tags:
  - AI
  - 深度学习
  - 神经网络
  - 反向传播
categories:
  - AI
description: 从数值微分、链式法则到多层感知机，手写实现反向传播和神经网络训练。
---

![AI 好啊，AI 得学](https://pub-08b57ed9c8ce4fadab4077a9d577e857.r2.dev/ai-notes-hou-cover.jpg)

本文是 Andrej Karpathy [《Neural Networks: Zero to Hero》](https://www.youtube.com/playlist?list=PLAqhIrjkxbuWI23v9cThsA9GvCAUhRvKZ) 课程 building micrograd 章节的笔记，看大佬是如何带我们一步步实现反向传播和神经网络的。

## 导数计算与链式法则

神经网络可以视作一个函数 f(x)，其各个参数的权重和偏置相当于函数的参数。训练神经网络就是不断调整参数以达到预期效果，方法就是计算各个参数变化时对整个函数的变化影响，本质上是一个求导数的过程。

对于导数计算，数学上的近似计算方法为数值微分中的前向差分：

$$
d = \frac{f(x+h)-f(x)}{h}
$$

当参数 x 的变化值为 h 时，f(x) 的变化值除以参数的变化，就得出了 x 变化时对 f(x) 的影响，也就是 f(x) 对 x 的导数。实际导数是这个比值在 $h \to 0$ 时的极限：

$$
f'(x) = \lim_{h \to 0} \frac{f(x+h)-f(x)}{h}
$$

下面我们定义一系列的参数和函数，并计算其导数：

```python
# 已知常数
a = 2.0
b = -3.0
c = 10.0
f = -2.0
# 计算函数
d = a * b # -6
e = d + c # 4
L = e * f # -8
```
套用上面的公式，我们可以求出 L 对 a、b、c、d、e、f 的导数。下面每次只让正在求导的变量增加 h：

对 e 和 f 求导：

$$
\begin{aligned}
\frac{\partial L}{\partial e}
&= \frac{(e+h)f - ef}{h} \\
&= \frac{ef + hf - ef}{h} \\
&= f = -2.0
\end{aligned}
$$

$$
\begin{aligned}
\frac{\partial L}{\partial f}
&= \frac{e(f+h) - ef}{h} \\
&= \frac{ef + eh - ef}{h} \\
&= e = 4.0
\end{aligned}
$$

对 d 和 c 求导：

$$
\begin{aligned}
\frac{\partial L}{\partial d}
&= \frac{(d+h+c)f - (d+c)f}{h} \\
&= \frac{df + hf + cf - df - cf}{h} \\
&= f = -2.0
\end{aligned}
$$

$$
\begin{aligned}
\frac{\partial L}{\partial c}
&= \frac{(d+c+h)f - (d+c)f}{h} \\
&= \frac{df + cf + hf - df - cf}{h} \\
&= f = -2.0
\end{aligned}
$$

对 b 和 a 求导：

$$
\begin{aligned}
\frac{\partial L}{\partial b}
&= \frac{(a(b+h)+c)f - (ab+c)f}{h} \\
&= \frac{abf + ahf + cf - abf - cf}{h} \\
&= af = -4.0
\end{aligned}
$$

$$
\begin{aligned}
\frac{\partial L}{\partial a}
&= \frac{(((a+h)b)+c)f - (ab+c)f}{h} \\
&= \frac{abf + bhf + cf - abf - cf}{h} \\
&= bf = 6.0
\end{aligned}
$$

除了通过公式直接计算，导数运算还遵循**链式法则**，即如果我们知道 L 对 e 的导数和 e 对 d 的导数，那么可以通过导数乘法计算出 L 对 d 的导数：

$$
\frac{\partial L}{\partial d}
= \frac{\partial L}{\partial e} \cdot \frac{\partial e}{\partial d}
$$

我们使用链式法则再次对上面的计算过程求导，过程如下，可以看到最终得出的结果和我们使用公式计算的结果一致。

先计算每一步的局部导数：

| 局部计算 | 局部导数 | 结果 |
| --- | --- | --- |
| $L = e \cdot f$ | $\frac{\partial L}{\partial e} = f$ | $-2.0$ |
| $L = e \cdot f$ | $\frac{\partial L}{\partial f} = e$ | $4.0$ |
| $e = d + c$ | $\frac{\partial e}{\partial d} = 1$ | $1.0$ |
| $e = d + c$ | $\frac{\partial e}{\partial c} = 1$ | $1.0$ |
| $d = a \cdot b$ | $\frac{\partial d}{\partial a} = b$ | $-3.0$ |
| $d = a \cdot b$ | $\frac{\partial d}{\partial b} = a$ | $2.0$ |

再通过链式法则把导数从 L 一层层传回去：

| 目标导数 | 链式法则 | 结果 |
| --- | --- | --- |
| $\frac{\partial L}{\partial d}$ | $\frac{\partial L}{\partial e} \cdot \frac{\partial e}{\partial d} = -2.0 \cdot 1.0$ | $-2.0$ |
| $\frac{\partial L}{\partial c}$ | $\frac{\partial L}{\partial e} \cdot \frac{\partial e}{\partial c} = -2.0 \cdot 1.0$ | $-2.0$ |
| $\frac{\partial L}{\partial b}$ | $\frac{\partial L}{\partial d} \cdot \frac{\partial d}{\partial b} = -2.0 \cdot 2.0$ | $-4.0$ |
| $\frac{\partial L}{\partial a}$ | $\frac{\partial L}{\partial d} \cdot \frac{\partial d}{\partial a} = -2.0 \cdot (-3.0)$ | $6.0$ |

我们将上述过程以计算图的形式打印出来：

![](https://pub-08b57ed9c8ce4fadab4077a9d577e857.r2.dev/micrograd_graph.svg)

上面的每次运算都可以类比为神经网络中的局部计算，从左到右的计算就是正向传播，而反向传播就是从右到左通过链式法则来计算 L 对 e、f、d、c、b、a 的导数的过程。

### 偏导数、斜率与梯度下降

学习神经网络时经常被梯度、斜率、导数这些概念搞混，这里简要整理：

- **导数**：是微积分中的概念，代表函数在某一个点的变化率，直白点说就是 x 变化时，f(x) 怎么变，即 f(x) 对 x 的导数，比如乘法运算 f(x) = a * b，那 a  增加 0.1，f(x)会增加 0.1*b，即 f(x) 对 a 的导数就是 b。
- **斜率**：导数的几何视角表示，在一元函数里，某一点的导数就是这一点的切线斜率。
  - 导数的绝对值越大，代表函数的变化程度越大，斜率越陡峭；
  - 导数的正负代表对函数的影响方向，导数为正，变量增加时函数值也会变大，切线往上倾斜；导数为负，变量增加时函数值会变小，切线向下倾斜。

![](https://pub-08b57ed9c8ce4fadab4077a9d577e857.r2.dev/tangent_to_a_curve.svg.png)

- **偏导数**：普通导数处理的是一元函数，比如 $f(x)$；偏导数处理的是多元变量，比如我们上面的函数 $L = ((a \cdot b) + c) \cdot d$ 就是一个多元函数，$L$ 对每个单一变量的导数就是偏导数，计算某个变量的偏导数时，其他变量保持固定。比如 $\frac{\partial L}{\partial a}$ 代表 $L$ 对 $a$ 的偏导数，$\frac{\partial L}{\partial b}$ 代表 $L$ 对 $b$ 的偏导数。
- **梯度**：对于函数 L，其所有偏导数组成的向量就是梯度。比如示例函数中，L 对 a、b、c、d、e、f 这些变量的偏导数组合起来，就是 L 相对于这些变量的梯度。在神经网络训练中，我们通常关注 L 对可训练参数的梯度，比如权重 w 和偏置 b 的梯度。
- **梯度下降**：神经网络训练通常用 loss 损失函数来衡量训练的效果，有了梯度，我们就知道了每个参数对最终 loss 的影响程度。梯度表示让 loss 增加最快的方向，因此为了减小 loss，我们就要让参数沿着梯度的反方向进行更新，因此叫梯度下降法。

## 反向传播

了解了导数、链式法则的概念，接下来是反向传播的底层实现，我们首先实现一个 Value 对象，Value 对象会记录下当下的值以及为了得到该值所做的计算，最终画出上面的计算图，然后进行反向传播计算每个参数的偏导数。

下面是只支持乘法和加法运算的简要实现：

```Python
class Value:
    def __init__(self, data, _children=(), _op='', label=''):
        self.data = data
        self._prev = set(_children)
        self._op = _op
        self.grad = 0.0
        self.label = label
        self._backward = lambda: None
        
    def __repr__(self):
        return f"value(data={self.data})"

    # 两个 Value 相加，得到一个新的 Value
    def __add__(self, other):
        other = other if isinstance(other, Value) else Value(other)
        # 当前计算的输出节点
        out = Value(self.data + other.data, (self, other),'+')
        def _backward():
            self.grad += out.grad
            other.grad  += out.grad
        out._backward = _backward
        return out

    # 两个 Value 相乘，得到一个新的 Value
    def __mul__(self, other):
        other = other if isinstance(other, Value) else Value(other)
        # 当前计算的输出节点
        out = Value(self.data * other.data, (self, other), '*')
        def _backward():
            self.grad += other.data * out.grad
            other.grad += self.data * out.grad
        out._backward = _backward
        return out 
```

各个参数的含义如下：

- **data：** 当前 Value 的数据值。
- **_prev：** 本次计算的前项值，比如 d = a * b ，则 d 的 _prev 就是 a 和 b。
- **_op：** 操作符，这里就是 * 或者 +。
- **grad：** 梯度，即当前参数的偏导数，反向传播的过程就是计算出所有参数的梯度值。
- **_backward：** 反向传播执行函数，用于计算当前参数的偏导数。


比如下面的计算例子
```Python
a = Value(2.0)
b = Value(4.0)
c = a + b

d = Value(3)
e = d * c
```
这里：
- c 由 a + b 计算得到，其 _prev 就是 (a, b)，_op 是 +；
- e 由 d * c 得到，其 _prev 就是(d, c)，_op 是 *；
  
  计算图如下：
![](https://pub-08b57ed9c8ce4fadab4077a9d577e857.r2.dev/macrograd_02.jpg)

这里的重点是反向传播的实现：

- 在执行正向传播时，输出值 out 由当前参与计算的若干 Value 得出。
  
- 反向传播则是反过来，out 的梯度已经提前计算出来了，我们基于链式法则，当前函数的梯度乘上 out 的梯度得到当前的梯度。这是比较反直觉的一点，明明当前是在计算 out，但却又需要 out 的梯度来做计算。


$$
\frac{\partial L}{\partial \text{current}}
= \frac{\partial L}{\partial \text{out}}
\cdot \frac{\partial \text{out}}{\partial \text{current}}
$$
以乘法和加法为例：

- 对于加法，c = a + b，c 对 a 和 b 的导数都是 1。即 a 增加多少，c 就增加多少。
- 对于乘法，c = a * b，c 对 a 的导数 是 b；对 b 的导数是 a。

因此结合链式法则：

- 对于加法，$\frac{\partial L}{\partial \text{current}} = 1 \cdot \frac{\partial L}{\partial \text{out}} = \frac{\partial L}{\partial \text{out}}$。


- 对于乘法，$\frac{\partial L}{\partial \text{current}} = \frac{\partial L}{\partial \text{out}} \cdot \frac{\partial \text{out}}{\partial \text{current}}$。即如果 $\text{out} = a \cdot b$，则 $L$ 对 $a$ 的导数就是 $\frac{\partial L}{\partial \text{out}} \cdot b$。

所以可以得出反向传播的计算函数：

```Python
    def __add__(self, other):
        other = other if isinstance(other, Value) else Value(other)
        out = Value(self.data + other.data, (self, other),'+')
        def _backward():
            # 本质是 1 * out.grad
            self.grad += out.grad
            other.grad  += out.grad
        out._backward = _backward
        return out

    def __mul__(self, other):
        other = other if isinstance(other, Value) else Value(other)
        out = Value(self.data * other.data, (self, other), '*')
        def _backward():
            # 对于乘法，out 对 self 的导数是 other；对 other 的导数是 self
            # 在乘以 out 的偏导数，就是当前 Value 对最终 L 的导数
            self.grad += other.data * out.grad
            other.grad += self.data * out.grad
        out._backward = _backward
        return out 
```

这里有一点需要注意，当前梯度的计算方式是 += 而不是 =，这是因为当前参数可能会在多个计算中起作用，因此必须是累加的，否则会损失掉。

除了加法和乘法，常见的导数计算公式有：

| 函数 | 运算说明 | 导数 | 说明 |
| --- | --- | --- | --- |
| $f(x) = c$ | 常数项 | $f^{\prime}(x) = 0$ | 常数对变量没有变化率 |
| $f(x) = x$ | 恒等运算 | $f^{\prime}(x) = 1$ | 自变量对自身的变化率为 1 |
| $f(x) = x^n$ | 幂运算 | $f^{\prime}(x) = n x^{n-1}$ | 幂函数求导 |
| $f(x) = u(x) + v(x)$ | 加法运算 | $f^{\prime}(x) = u^{\prime}(x) + v^{\prime}(x)$ | 加法的导数分别相加 |
| $f(x) = u(x)v(x)$ | 乘法运算 | $f^{\prime}(x) = u^{\prime}(x)v(x) + u(x)v^{\prime}(x)$ | 乘法使用乘积法则 |
| $f(x) = \frac{u(x)}{v(x)}$ | 除法运算 | $f^{\prime}(x) = \frac{u^{\prime}(x)v(x) - u(x)v^{\prime}(x)}{v(x)^2}$ | 除法使用商法则，$v(x) \neq 0$ |
| $f(x) = e^x$ | 指数运算 | $f^{\prime}(x) = e^x$ | 自然指数函数导数不变 |
| $f(x) = \ln x$ | 对数运算 | $f^{\prime}(x) = \frac{1}{x}$ | 自然对数导数，$x > 0$ |
| $f(x) = \tanh x$ | tanh 运算 | $f^{\prime}(x) = 1 - \tanh^2 x$ | 双曲正切常用于激活函数 |
| $f(x) = u(v(x))$ | 复合运算 | $f^{\prime}(x) = u^{\prime}(v(x))v^{\prime}(x)$ | 复合函数使用链式法则 |

基于上述公式，我们可以实现幂运算、tanh 和指数运算的反向传播函数。它们的共同结构都是：先算出当前运算的输出 out，再在 _backward 中把 out.grad 乘上局部导数，累加回输入节点的 grad：

```Python
def __pow__(self, other):
    assert isinstance(other, (int, float))
    out = Value(self.data**other, (self,), f'**{other}')
    def _backward():
        # 幂运算的局部导数：d(x**n)/dx = n * x**(n - 1)
        self.grad += (other * self.data**(other - 1)) * out.grad
    out._backward = _backward
    return out
    
def tanh(self):
    n = self.data
    # 正向传播：计算 tanh(x) 的值
    t = (math.exp(2*n) - 1) / (math.exp(2*n) + 1)
    out = Value(t, (self,), 'tanh')
    def _backward():
        # tanh 的局部导数：1 - tanh(x)**2，也就是 1 - out.data**2
        self.grad += (1 - t**2) * out.grad
    out._backward = _backward
    return out

def exp(self):
    x = self.data
    out = Value(math.exp(x), (self,), 'exp')
    def _backward():
        # exp 的局部导数等于 exp(x)，也就是 out.data
        self.grad += out.data * out.grad
    out._backward = _backward
    return out
```

有了每个基本运算的求导计算，我们就可以进行反向传播的实现了，结合计算图来看，我们需要做的事情有：
- 获取整个计算的执行顺序，为此要进行拓扑排序
- 按照相反的顺序，基于链式法则做求导运算

完整实现如下：
```Python
# 一般是从最后一个节点 L 开始进行反向传播
def backward(self):
    topo = []
    visited = set()
    # 从最后节点开始，不断 prev 节点
    def build_topo(v):
        # 去重
        if v not in visited:
            visited.add(v)
            # 后序遍历，最终得到 [a,b,c,d,e,f,L] 正向传播的拓扑排序
            for child in v._prev:
                build_topo(child)
            topo.append(v)

    build_topo(self)
    self.grad = 1.0
    # 先执行 reverse，从 L 开始执行反向传播
    for node in reversed(topo):
        node._backward()

```

这样我们就实现了完整的 Value 神经元和反向传播，完整代码如下：

```Python
class Value:
    def __init__(self, data, _children=(), _op='', label=''):
        self.data = data
        self._prev = set(_children)
        self._op = _op
        self.grad = 0.0
        self.label = label
        self._backward = lambda: None
        
    def __repr__(self):
        return f"value(data={self.data})"

    def __add__(self, other):
        other = other if isinstance(other, Value) else Value(other)
        out = Value(self.data + other.data, (self, other),'+')
        def _backward():
            self.grad += out.grad
            other.grad  += out.grad
        out._backward = _backward
        return out

    def __mul__(self, other):
        other = other if isinstance(other, Value) else Value(other)
        out = Value(self.data * other.data, (self, other), '*')
        def _backward():
            self.grad += other.data * out.grad
            other.grad += self.data * out.grad
        out._backward = _backward
        return out 
        
    def __rmul__(self, other):
        return self * other

    def __truediv__(self, other):
        return self * other**-1

    def __neg__(self):
        return self * -1

    def __sub__(self, other):
        return self + (-other)

    def __pow__(self, other):
        assert isinstance(other, (int, float))
        out = Value(self.data**other, (self,), f'**{other}')
        def _backward():
            self.grad += (other* self.data**(other-1)) * out.grad
        out._backward = _backward
        return out
        
    def tanh(self):
        n = self.data
        t = (math.exp(2*n) - 1) / (math.exp(2*n) + 1)
        out = Value(t, (self,), 'tanh')
        def _backward():
            self.grad += (1 - t**2) * out.grad
        out._backward = _backward
        return out

    def exp(self):
        x = self.data
        out = Value(math.exp(x), (self,), 'exp')
        def _backward():
            self.grad += out.data * out.grad
        out._backward = _backward;
        return out
        
    def backward(self):
        topo = []
        visited = set()
        def build_topo(v):
            if v not in visited:
                visited.add(v)
                for child in v._prev:
                    build_topo(child)
                topo.append(v)
        build_topo(self)
        self.grad = 1.0
        for node in reversed(topo):
            node._backward()
  
```

这里我们模拟神经网络，对输入的 X1、X2 执行线性和非线性计算，然后执行反向传播，结果如下：
可以看到每个节点的梯度都计算出来了
![](https://pub-08b57ed9c8ce4fadab4077a9d577e857.r2.dev/macrograd_graph_02.svg)

```Python
# inputs: x1, x2
x1 = Value(2.0, label='x1')
x2 = Value(0.0, label='x2')

# weights 权重
w1 = Value(-3, label='w1')
w2 = Value(1.0, label='w2')

# bias 偏置
b = Value(6.8813735870195432, label='b')

x1w1 = x1*w1; 
x2w2 = x2*w2;

# 权重和
x1w1x2w2 = x1w1 + x2w2

# 加偏置项
n = x1w1x2w2 + b; n.label = 'n' 

# 执行 tanh 计算
o = n.tanh(); o.label = 'o'
# 执行反向传播
o.backward()
draw_dot(o)
```

这里使用 Pytorch 做同样的运算，可以得到和图中相同的梯度值。

```Python
x1 = torch.Tensor([2.0]).double(); x1.requires_grad = True
x2 = torch.Tensor([0.0]).double(); x2.requires_grad = True
w1 = torch.Tensor([-3.0]).double(); w1.requires_grad = True
w2 = torch.Tensor([1.0]).double(); w2.requires_grad = True
b = torch.Tensor([6.8813735870195432]).double(); b.requires_grad = True

n = x1* w1 + x2 * w2 + b
o=torch.tanh(n)
print(o.data.item())
o.backward()

print('---')
print('x2', x2.grad.item())
print('w2', w2.grad.item())
print('x1', x1.grad.item())
print('w1', w1.grad.item()) 

0.7071066904050358
---
x2 0.5000001283844369
w2 0.0
x1 -1.5000003851533106
w1 1.0000002567688737
```

## 神经网络实现

有了完整的 Value 实现，现在可以基于 Value 构建神经网络了。

首先是神经元的构建，一个神经元本质就是一个函数，它接收一系列的输入，为每个输入赋一个权重，通常还会加上一个 bias 偏置值，执行加权求和后，再执行激活函数，最后返回一个输出。
![](https://pub-08b57ed9c8ce4fadab4077a9d577e857.r2.dev/artificial_neuron_structure.svg.png)

这里重要的是神经元的输入维度和激活函数，我们使用 tanh，完整代码如下：

```Python
import random
class Neuron:
    def __init__(self, nin):
        # nin 代表输入维度，为输入随机分配权重
        self.w = [Value(random.uniform(-1,1)) for _ in range(nin)]
        # 生成偏置
        self.b = Value(random.uniform(-1,1))

    def __call__(self, x):
        # 求和
        act = sum((wi * xi for wi, xi in zip(self.w, x)), self.b)
        # 激活函数使用 tanh
        out = act.tanh()
        return out

    def parameters(self):
        return self.w + [self.b]
```

- **self.w**：权重矩阵，长度和输入维度相同，代表给每个输入的初始权重

定义好神经元，接下来就是 Layer，多个神经元组成一层神经网络。神经网络需要定义清楚输入维度和输出维度：

- 输入维度：每个神经元接收的输入值的数量，用于初始化权重矩阵
- 输出维度：本层神经网络的输出值的数量，本层的输出就是下一层的输入

```Python
# Layer 实现
class Layer:
    def __init__(self, nin, nout):
        # nin 代表神经元的输入维度，基于此构造本层的每个神经元
        # nout 代表本层的输出维度，代表需要 nout 个神经元
        self.neurons = [Neuron(nin) for _ in range(nout)]

    def __call__(self, x):
        # 每层执行时，分别执行每个神经元的运算，然后组成完整的输出
        outs = []
        for neu in self.neurons:
            outs.append(neu(x))
        return outs[0] if len(outs) == 1 else outs

    def parameters(self):
        params = []
        for n in self.neurons:
            params += n.parameters()
        return params
    
```

现在有了神经元和 Layer，我们就可以实现多层感知机 MLP 了，一个 MLP 由输入输出层和若干隐藏层组成，除了第一层外，每一层的输出维度就是下一层的输入维度，直到最后一层，返回完整结果。完整代码实现如下：

```Python
class MLP:
    def __init__(self, nin, nouts):
        # 第一层输入和后续的输出
        dims = [nin,] + nouts
        # 构造每一层神经网
        self.layers = [Layer(dnin, dnout) for dnin, dnout in zip(dims[:-1], dims[1:])]

    def __call__(self, x):
        outputs = x
        for layer in self.layers:
            outputs = layer(outputs)
        return outputs

    def parameters(self):
        params = []
        for layer in self.layers:
            params += layer.parameters()
        return params
```
以上就完整了一个最基本的神经网络，接下来我们使用这个神经网络来进行训练：

- 构造模型
```
model = MLP(3, [4,4,1])
```
这里我们构造一个输入维度为 3 维两层隐藏层的感知机

![](https://pub-08b57ed9c8ce4fadab4077a9d577e857.r2.dev/3-mlp.png)

- 准备数据集

```Python
# 训练数据集
xs = [
    [2.0, 3.0, -1.0],
    [3.0, -1.0, 0.5],
    [0.5, 1.0, 1.0],
    [1.0, 1.0, -1.0],   
]
# 目标值
ys = [1.0, -1.0, -1.0, 1.0]

# 初始计算
y = model(xs[0])
y
Value(data=0.41462415026058974)
```
我们的目标就是将 xs 作为输入时，模型的数据尽可能的接近 ys。为此我们使用梯度下降来训练模型：

```Python

# 执行 1000 次梯度下降
losses = [] # 记录每次的 loss
for i in range(1000):
    # 将每一行作为输入，获取输出[y1, y2, y3 ,y 4]
    ypred = [model(x) for x in xs]
    # 计算本次 loss：平方差和，即 输出值 - ys预期值的平方和
    loss = sum(((yout - ygt)**2 for ygt, yout in zip(ys, ypred)), Value(0))
    losses.append(loss.data)
    # 清空梯度，反向传播
    # 每次反向传播前必须清空梯度
    for p in model.parameters():
        p.grad = 0.0
    loss.backward()
    # 基于梯度，更新参数
    for p in model.parameters():
        # -0.2 代表学习率
        p.data += -0.2 * p.grad
```

下面是执行 1000 次后的 loss，可以看到几次迭代后 loss 快速下降到了 0.01，然后经过 1000 次迭代最终下降到了 0.00013。
```
Value(data=4.747363068963533)
Value(data=6.381085477793832)
Value(data=6.596598206106293)
Value(data=0.5969951894018467)
Value(data=0.08152538164269135)
Value(data=0.014788927034199428)
Value(data=0.013218620836651245)
...
Value(data=0.00012638657716733235)
```
使用训练后的模型再次进行计算，可以看到得出的结果已经非常接近 [1.0, -1.0, -1.0, 1.0] 这个目标值了。

```Python
ypred = [model(x) for x in xs]
ypred
[Value(data=0.9970541959227349),
 Value(data=-0.9976645657855302),
 Value(data=-0.9964738859181087),
 Value(data=0.9961799917458396)]
```

## 简要总结

本章节的重点是两个：
- **反向传播的实现** 本质就是根据链式法则，从神经网络的输出沿着计算图倒推各个中间节点和可训练参数对结果的影响大小。

- **梯度下降法** 基于反向传播计算出的所有参数的导数共同组成一个梯度向量，代表着让 loss 增加最快的方向，为了降低 loss，我们沿着梯度的相反的方向调整参数，通常会让 loss 下降。基本流程就是
    - 前向计算
    - 计算 loss
    - 重置梯度
    - 反向传播
    - 更新参数
    - 继续循环，直到 loss 足够小
![](https://pub-08b57ed9c8ce4fadab4077a9d577e857.r2.dev/macrograd_gradient_descent.png)
