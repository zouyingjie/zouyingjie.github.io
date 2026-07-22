---
title: "【AI 得学啊】makemore 02：用 MLP 构建字符级语言模型"
date: 2026-07-22T20:01:00+08:00
math: true
tags:
  - AI
  - 深度学习
  - 神经网络
  - 语言模型
  - PyTorch
categories:
  - AI
series:
  - AI 得学啊
description: 用字符嵌入和多层感知机改进 bigram 模型，理解 softmax、交叉熵、mini-batch 与数据集划分。
---

<img class="ai-series-cover" src="https://pub-08b57ed9c8ce4fadab4077a9d577e857.r2.dev/ai-notes-hou-cover.jpg" alt="AI 好啊，AI 得学">

> 本文承接上一篇 [makemore 01](/posts/ai-makemore01-ngram/)。为便于单独运行，下文代码默认已执行下面的公共初始化；姓名数据集可从课程仓库的 [names.txt](https://github.com/karpathy/makemore/blob/master/names.txt) 获取。
>
> ```python
> import torch
> import torch.nn.functional as F
> import matplotlib.pyplot as plt
>
> words = open("names.txt", "r").read().splitlines()
> chars = sorted(set("".join(words)))
> stoi = {s: i + 1 for i, s in enumerate(chars)}
> stoi["."] = 0
> itos = {i: s for s, i in stoi.items()}
> ```
>
## N-gram 模型的局限性

上一节虽然我们使用神经网络代替了基于统计的 N-gram 模型实现，但其预测结果依然不够理想。

N-gram 模型虽然比较简单，但也存在着根本缺陷：**训练语料不能覆盖所有的词组合**。以 Bigram 为例，即使词汇表只有 1 万，其可能的 bigram 数量为一万的平方，即 1 亿；如果想扩大上下文为 Trigram，则词汇组合会变为 1 万亿，随着词表大小和上下文长度 N 的增加，可能的序列组合数量会呈指数级增长，这被称为**维度灾难（curse of dimensionality）**。由此会带来一系列的问题：

- **稀疏性问题**：训练数据只能覆盖全部组合中的一小部分，因此会有大量的组合统计计数为 0 或次数极少，导致其几乎不可能被预测到。
- **泛化能力弱**：每个词都是离散的符号，词组合之间没有相似性，比如 `the dog is running` 和 `the cat is running`，N-gram 会把 dog 和 cat 当成完全独立的符号，前者学到的规律没办法应用到后者。
- **长距离依赖弱**：因为维度灾难，N-gram 没办法使用更长的上下文，实际场景中 N-gram 一般最多不超过 5，像 `The book that I bought yesterday from the old shop was ___` 这样的长句子，因为上下文窗口过小，模型看不到更多有效的信息，就没办法做出很好的预测。

为了解决稀疏性和泛化能力，图灵奖得主，和杨立昆、辛顿并称为深度学习三巨头的 Bengio 等人在 2003 年发表了论文 [A Neural Probabilistic Language Model](https://jmlr.org/papers/volume3/tmp/bengio03a.pdf)，提出了神经语言模型，旨在解决传统统计语言模型中的问题。论文提出了如下方案：

- 将单词表映射为（embedding）词向量矩阵，向量初始时可以是随机的，训练过程中通过反向传播不断调整。
- 将训练样本拼接为完整的输入向量，比如每个字符使用二维向量表示、上下文包含 3 个字符时，每个样本可以拼接为一个 6 维向量。
- 引入非线性隐藏层，提取上下文的组合特征，论文里使用的是 tanh。

整体结构如图：

![](https://pub-08b57ed9c8ce4fadab4077a9d577e857.r2.dev/mlp-01.jpg)

这一节就是沿着论文的思路，实现字符集的语言模型。

## 语言模型实现

### Embedding

这里我们做两项改进：

- 将上下文长度变为 3
- 使用可以捕获相似性的向量表示样本，而不是原来离散的独热编码。

首先我们将字符向量化，一共有 27 个字符，每个字符用 2 个数字表示，完整词表（embedding table）的代码如下：

```python
import torch
import torch.nn.functional as F
import matplotlib.pyplot as plt
%matplotlib inline

# 构建 embedding table
C = torch.randn((27, 2))
print(C.shape)
print(C[:5])

# torch.Size([27, 2])
# tensor([[ 1.3265, -0.5742],
#         [-1.7264, -0.4404],
#         [ 0.2553,  0.5558],
#         [ 0.8205, -0.5425],
#         [ 0.4945, -0.9881]])
```

有了词表后，对原始字符样本需要执行嵌入查表（embedding lookup），获取样本数据的向量表示：

```python
# 构建数据集，这次使用 3 个字母作为上下文
block_size = 3 # 上下文长度：使用前 3 个字符预测下一个字符
X, Y = [], []

# 用前 5 个单词做样本测试
for w in words[:5]:
    context = [0] * block_size
    for ch in w + '.':
        ix = stoi[ch]
        X.append(context)
        Y.append(ix)
        # print('.'.join(itos[i] for i in context), '--->', itos[ix])
        context = context[1:] + [ix]

# (torch.Size([32, 3]), torch.int64, torch.Size([32]), torch.int64)
X = torch.tensor(X)
Y = torch.tensor(Y)
# embedding lookup
emb = C[X]
emb.shape
torch.Size([32, 3, 2])
```

上面用前 5 个名字做测试，输出表示我们一共有 32 个样本，每个样本有 3 个字符，每个字符由一个二维向量表示。因此每个样本相当于一个 6 维的向量，我们可以做如下转换得到：

```Python
# embedding concatenated，将每个样本转为 6 维的向量
embcat = emb.view(-1, 6)
embcat
tensor([[ 1.3265, -0.5742,  1.3265, -0.5742,  1.3265, -0.5742],
        [ 1.3265, -0.5742,  1.3265, -0.5742, -0.0406, -1.2178],
        [ 1.3265, -0.5742, -0.0406, -1.2178, -0.8393, -0.8490],
        [-0.0406, -1.2178, -0.8393, -0.8490, -0.8393, -0.8490],
        [-0.8393, -0.8490, -0.8393, -0.8490, -1.7264, -0.4404],
        [ 1.3265, -0.5742,  1.3265, -0.5742,  1.3265, -0.5742],
        [ 1.3265, -0.5742,  1.3265, -0.5742,  0.1894, -0.6970],
        [ 1.3265, -0.5742,  0.1894, -0.6970,  0.0148,  0.6193],
        [ 0.1894, -0.6970,  0.0148,  0.6193,  0.8007,  0.4400],
        [ 0.0148,  0.6193,  0.8007,  0.4400,  1.0688,  0.2932],
        [ 0.8007,  0.4400,  1.0688,  0.2932,  0.8007,  0.4400],
        [ 1.0688,  0.2932,  0.8007,  0.4400, -1.7264, -0.4404],
        [ 1.3265, -0.5742,  1.3265, -0.5742,  1.3265, -0.5742],
        [ 1.3265, -0.5742,  1.3265, -0.5742, -1.7264, -0.4404],
        [ 1.3265, -0.5742, -1.7264, -0.4404,  1.0688,  0.2932],
        [-1.7264, -0.4404,  1.0688,  0.2932, -1.7264, -0.4404],
        [ 1.3265, -0.5742,  1.3265, -0.5742,  1.3265, -0.5742],
        [ 1.3265, -0.5742,  1.3265, -0.5742,  0.8007,  0.4400],
        [ 1.3265, -0.5742,  0.8007,  0.4400, -1.3961, -0.0234],
        [ 0.8007,  0.4400, -1.3961, -0.0234, -1.7264, -0.4404],
        [-1.3961, -0.0234, -1.7264, -0.4404,  0.2553,  0.5558],
        [-1.7264, -0.4404,  0.2553,  0.5558, -0.0406, -1.2178],
        [ 0.2553,  0.5558, -0.0406, -1.2178,  0.0148,  0.6193],
        [-0.0406, -1.2178,  0.0148,  0.6193,  0.0148,  0.6193],
        [ 0.0148,  0.6193,  0.0148,  0.6193, -1.7264, -0.4404],
        [ 1.3265, -0.5742,  1.3265, -0.5742,  1.3265, -0.5742],
        [ 1.3265, -0.5742,  1.3265, -0.5742, -1.3961, -0.0234],
        [ 1.3265, -0.5742, -1.3961, -0.0234,  0.1894, -0.6970],
        [-1.3961, -0.0234,  0.1894, -0.6970,  1.4068, -0.4071],
        [ 0.1894, -0.6970,  1.4068, -0.4071, -0.3412, -0.6007],
        [ 1.4068, -0.4071, -0.3412, -0.6007,  0.8007,  0.4400],
        [-0.3412, -0.6007,  0.8007,  0.4400, -1.7264, -0.4404]])
```

### 神经网络训练

现在我们开始进行神经网络的训练，首先我们初始化隐藏层的权重，每个样本向量的维度是 6，即输入维度为 6，然后我们这里设置 100 个神经元，因此隐藏层权重矩阵的形状为 6 * 100:

```Python
W1 = torch.randn((6, 100))
b1 = torch.randn(100)
```

然后我们在隐藏层引入非线性变换，这里使用的是 tanh 函数，整个隐藏层的计算逻辑为：

```Python
# 预激活，执行矩阵运算
hpreact = embcat @ W1 + b1
# 非线性激活
h = torch.tanh(hpreact)
```
最后我们要设置输出层的权重，这里有 100 个神经元，输出结果的范围是 27 个字母，因此我们设置权重矩阵的形状为 100 * 27，经过矩阵运算后得到 logits 分数，然后执行 softmax 运算得到预测下一个字母的概率：

```Python
W2 = torch.rand((100, 27))
b2 = torch.rand(27)

logits = h @ W2 + b2
logits_stable = logits - logits.max(1, keepdim=True).values
counts = logits_stable.exp()
probs = counts / counts.sum(1, keepdim = True)

loss = -probs[torch.arange(32), Y].log().mean()
loss
```
神经网络结构如图：
![](https://pub-08b57ed9c8ce4fadab4077a9d577e857.r2.dev/mlp-03.png)

下面是完整的训练代码，我们执行 1000 次梯度下降。

```Python
g = torch.Generator().manual_seed(2137483647)

# 初始 embedding table
C = torch.rand((27, 2), generator=g, requires_grad=True)

# 隐藏层权重和偏置
W1 = torch.rand((6, 100), generator=g, requires_grad=True)
b1 = torch.rand((100), generator=g, requires_grad=True)

#输出层权重和偏置
W2 = torch.rand((100, 27), generator=g, requires_grad=True)
b2 = torch.rand((27), generator=g, requires_grad=True)

# C 也作为参数，执行梯度下降
parameters = [C, W1, b1, W2, b2]
loss = None

steps = []
lossi = []
for i in range(1000):
    # 执行查表
    emb = C[X]
    # 转换为维度为 6 的向量
    embcat = emb.view(-1, 6)

    # 隐藏层计算
    hpreact = embcat @ W1 + b1
    h = torch.tanh(hpreact)

    # 输出层运算
    logits = h @ W2 + b2

    logits_stable = logits - logits.max(1, keepdim=True).values
    counts = logits_stable.exp()
    probs = counts / counts.sum(1, keepdim = True)
    loss = -probs[torch.arange(32), Y].log().mean()

    for p in parameters:
        p.grad = None
    loss.backward()
    steps.append(i)
    lossi.append(loss.item())
    for p in parameters:
        p.data += -0.1 * p.grad

print(loss)
plt.plot(steps, lossi)
```

经过 1000 次迭代，最终得到的 loss 为 0.3583。
![](https://pub-08b57ed9c8ce4fadab4077a9d577e857.r2.dev/mlp-neural-01.jpg)



上面的 32 条样本只用于检查张量形状与前向、反向传播是否正确；在后续的 mini-batch 训练中，需要使用完整姓名数据集：

```python
X, Y = [], []
for w in words:
    context = [0] * block_size
    for ch in w + ".":
        ix = stoi[ch]
        X.append(context)
        Y.append(ix)
        context = context[1:] + [ix]

X = torch.tensor(X)
Y = torch.tensor(Y)
print(X.shape, Y.shape)
# torch.Size([228146, 3]) torch.Size([228146])
```

## 神经网络训练优化

至此我们已经完成了最基础的神经网络训练，但除了降低 loss 这一基本目标外，神经网络训练还需要考虑效率、稳定性等其他因素。接下来我们看下神经网络有哪些训练优化方法。

### softmax & 交叉熵

之前我们使用 softmax 将模型输出的 logits 转换为概率，再计算 loss。对于第 $i$ 个类别，softmax 的计算公式是：对每个 logit 取自然常数 e 的次方，然后做归一化处理，公式如下：

$$
p_i = \operatorname{softmax}(z_i) = \frac{e^{z_i}}{\sum_{j=1}^{K} e^{z_j}}
$$

因为是指数运算，因此 softmax 计算存在一个问题，当某个 $z_i$ 很大时，$e^{z_i}$ 可能发生数值溢出。解决方法是：对**同一个样本的所有 logits** 同时减去同一个常数 $c$，这相当于把所有分数一起下移，类别之间的相对差值不变，例如 $(z_i-c) - (z_j-c) = z_i-z_j$，因此各类别之间的概率比例也不变。

从公式看，减去 $c$ 后，每一项指数都会额外乘上 $e^{-c}$。分子和分母乘了相同的倍数，归一化时便会抵消：

$$
\operatorname{softmax}(z_i - c) = \frac{e^{z_i-c}}{\sum_{j=1}^{K} e^{z_j-c}}
= \frac{e^{-c}e^{z_i}}{e^{-c}\sum_{j=1}^{K} e^{z_j}}
= \frac{e^{z_i}}{\sum_{j=1}^{K} e^{z_j}}
= \operatorname{softmax}(z_i)
$$

例如，两个类别的 logits 为 $[3, 1]$，第一个类别的概率为：

$$
\frac{e^3}{e^3 + e^1} = \frac{1}{1 + e^{-2}}
$$

对所有 logits 减去最大值 $3$ 后得到 $[0, -2]$，此时概率仍然是：

$$
\frac{e^0}{e^0 + e^{-2}} = \frac{1}{1 + e^{-2}}
$$

通常取 $c = m = \max_j z_j$，使最大的 logit 变为 $0$，从而避免指数运算溢出：

$$
p_i = \frac{e^{z_i - m}}{\sum_{j=1}^{K} e^{z_j - m}}
$$

进一步地，实际训练时通常都是直接使用交叉熵来作为 loss 计算，避免先计算 softmax 再取对数带来的精度损失，计算公式如下：

$$
\mathcal{L} = -z_y + \log \sum_{j=1}^{K} e^{z_j}
= -z_y + m + \log \sum_{j=1}^{K} e^{z_j-m}, \quad m = \max_j z_j
$$

PyTorch 已经提供了现成的函数，可以进行更加高效的运算，因此后续计算 loss 我们一律使用交叉熵：

```
loss = F.cross_entropy(logits, Y_batch)
```

### mini-batch

之前我们每次进行梯度下降运算时都是用上了所有的数据，但这并不是必须的，根据每次计算更新参数使用的数据量的不同，梯度下降算法可以分为三类：

| 类型 | 每次参数更新使用的数据量 | 优点 | 缺点 | 适用场景 |
| --- | --- | --- | --- | --- |
| **批量梯度下降（BGD）** | 全部训练数据 | 梯度方向稳定，收敛过程平滑 | 单次计算开销大，数据量大时速度慢、内存占用高 | 数据集较小的场景 |
| **随机梯度下降（SGD）** | 1 个训练样本 | 更新速度快，可在线学习，有机会跳出局部极小值 | 梯度波动大，收敛不稳定，难以充分利用并行计算 | 在线学习或超大规模数据集 |
| **小批量梯度下降（MBGD）** | 一小批训练样本（mini-batch） | 兼顾计算效率与梯度稳定性，适合 GPU 并行计算 | 需要选择合适的批量大小 | 深度学习训练中的常用方式 |

为了提高训练效率，深度学习通常使用 mini-batch 来做训练，现在我们每次只取 32 条数据来做梯度下降，代码改动如下：

```Python
batch_size = 32
for i in range(30000):
    """
    批量 SGD
    """
    # emb = C[X]

    """
    mini-batch
    """
    # 随机挑选本次的训练样本索引
    ix = torch.randint(
        low=0, # 从 0
        high=X.shape[0],
        size=(batch_size,), # 每次取 32个
    )
    # 获取随机选择的样本
    X_batch = X[ix]
    Y_batch = Y[ix]

    # 执行查表和梯度下降
    emb = C[X_batch]
    ...
    # 计算 loss
    loss = F.cross_entropy(logits, Y_batch)
```

### 调整学习率

除了梯度算法，学习率也是影响梯度下降计算的关键因素，学习率过小，可能导致要迭代很多次才能达到最优，学习率过大，则容易跳过最优。之前默认使用了 0.1，但在实际训练中通常需要通过训练来确定一个合适的学习率，示例如下：这里我们在 -3 ~ 0 的区间取 1000 个均匀分布的指数 `-3, -2.997, -2.994, ..., 0`，然后将其转为学习率

```Python
lre = torch.linspace(-3, 0, 1000)
lrs = 10 ** lre          # 0.001 → 1
lrs
tensor([0.0010, 0.0010, 0.0010, 0.0010, 0.0010, 0.0010, 0.0010, 0.0010, 0.0011,
        0.0011, 0.0011, 0.0011, 0.0011, 0.0011, 0.0011, 0.0011, 0.0011, 0.0011,
        0.0011, 0.0011, 0.0011, 0.0012, 0.0012, 0.0012, 0.0012, 0.0012, 0.0012,
        0.0012, 0.0012, 0.0012, 0.0012, 0.0012, 0.0012, 0.0013, 0.0013, 0.0013,
        0.0013, 0.0013, 0.0013, 0.0013, 0.0013, 0.0013, 0.0013, 0.0013, 0.0014,
        0.0014, 0.0014, 0.0014, 0.0014, 0.0014, 0.0014, 0.0014, 0.0014, 0.0014,
        0.0015, 0.0015, 0.0015, 0.0015, 0.0015, 0.0015, 0.0015, 0.0015, 0.0015,
        0.0015, 0.0016, 0.0016, 0.0016, 0.0016, 0.0016, 0.0016, 0.0016, 0.0016,
        0.0016, 0.0017, 0.0017, 0.0017, 0.0017, 0.0017, 0.0017, 0.0017, 0.0017,
        0.0018, 0.0018, 0.0018, 0.0018, 0.0018, 0.0018, 0.0018, 0.0018, 0.0019,
        0.0019, 0.0019, 0.0019, 0.0019, 0.0019, 0.0019, 0.0019, 0.0020, 0.0020,
        0.0020, 0.0020, 0.0020, 0.0020, 0.0020, 0.0021, 0.0021, 0.0021, 0.0021,
        0.0021, 0.0021, 0.0021, 0.0022, 0.0022, 0.0022, 0.0022, 0.0022, 0.0022,
        0.0022, 0.0023, 0.0023, 0.0023, 0.0023, 0.0023, 0.0023, 0.0024, 0.0024,
       ...
```
然后执行训练，查找不同学习率下 loss 的下降情况，找到下降最快且稳定的区间：

```Python
lri = []
lossi = []

for i in range(1000):
    ix = torch.randint(0, X.shape[0], (32,))

    emb = C[X[ix]]
    h = torch.tanh(emb.view(-1, 6) @ W1 + b1)
    logits = h @ W2 + b2
    loss = F.cross_entropy(logits, Y[ix])

    for p in parameters:
        p.grad = None
    loss.backward()

    lr = lrs[i]
    for p in parameters:
        p.data += -lr * p.grad

    lri.append(lre[i].item())
    lossi.append(loss.item())
plt.plot(lri, lossi)
```
最终结果如下：

![](https://pub-08b57ed9c8ce4fadab4077a9d577e857.r2.dev/learning_rate_search.png)

从图中可以看出：
- -3 ~ -2：loss 快速下降，学习率开始有效。
- -2 ~ -1：loss 较低且波动相对稳定，对应 lr≈0.01~0.1。
- -1 以后：波动明显变大，说明更新步长开始过猛。
- -0.8 附近出现尖峰，对应 lr≈0.16，已经有训练不稳定迹象。

因此合适的学习率大致应该在 0.01 ~ 0.1 之间，这里我们就沿用原来的 0.1 即可。

除了确定初始学习率外，在训练过程中，学习率通常也不是一成不变的，在训练前期，LOSS 较大，通常可以采用较大的学习率，加速训练；到训练后期时，此时参数已经比较接近最优值了，这时候需要调小学习率不断逼近最优，否则可能会导致跳过最优解，这里需要做合适的**学习率衰减（Learning Rate Decay）**。常用的衰减策略有：

- 指数衰减
- 步长衰减
- 余弦衰减

这里我们使用步长衰减，训练超过两万次后将学习率缩小 10 倍，代码如下：

```
lr = 0.1 if i < 20000 else 0.01
```
### 训练集/验证集/测试集

神经网络的最终目标是基于已有数据总结规律，然后预测未知的世界。如果一个神经网络在训练时表现良好，但在实际应用中表现不佳，这种现象称为过拟合（Overfitting）。为此在训练神经网络时，我们必须使用没有用过的数据做测试，在实践中我们通常将数据集分为训练集（train）和验证集（dev/validation）还有测试集：

- **训练集（training）**：用来执行反向传播、梯度下降，不断优化参数。
- **验证集（dev）**：用来调整超参数。测试不同的模型结构、参数等，比如隐藏层大小、embedding 维度、学习率、训练轮数、正则化等。
- **测试集（test）**：执行最终的验证，如果模型最终在三个数据集都表现良好，说明达标。

通过验证在不同数据集上的表现，可以评估模型的泛化能力：

- 训练集误差大，测试集误差大：模型欠拟合（Underfitting），说明训练不够，需要继续迭代优化
- 训练集误差小，测试集误差大：模型过拟合（Overfitting），说明模型泛化能力不足，需要对模型结构、训练方式等做进一步的调整优化。
- 训练集误差小，测试集误差小：模型泛化能力达标，符合预期。

下面是拆分代码，我们将 80% 的数据用作训练集，然后验证集和测试集分别占 10%。
```Python

# 构造函数
def build_dataset(words):
  X, Y = [], []
  for w in words:
    context = [0] * block_size
    for ch in w + '.':
      ix = stoi[ch]
      X.append(context)
      Y.append(ix)
      #print(''.join(itos[i] for i in context), '--->', itos[ix])
      context = context[1:] + [ix] # crop and append

  X = torch.tensor(X)
  Y = torch.tensor(Y)
  return X, Y

# 拆分数据集

import random
random.seed(42)
# 随机打乱数据集
random.shuffle(words)
# 按 8:1:1 的比例拆分
n1 = int(0.8*len(words))
n2 = int(0.9*len(words))

# 80% 数据作为训练集
Xtr, Ytr = build_dataset(words[:n1])

# 10% 作为验证集
Xdev, Ydev = build_dataset(words[n1:n2])

# 10% 作为测试集
Xte, Yte = build_dataset(words[n2:])
```

然后我们用训练集训练数据，用验证集来验证结果

```Python
batch_size = 32
for i in range(30000):
    # 随机挑选本次的训练样本索引
    ix = torch.randint(
        low=0, # 从 0
        high=Xtr.shape[0],
        size=(batch_size,), # 每次取 32个
    )
    # 获取随机选择的样本
    X_batch = Xtr[ix]
    Y_batch = Ytr[ix]

    # 执行查表和梯度下降
    emb = C[X_batch]
    embcat = emb.view(-1, 6)

    hpreact = embcat @ W1 + b1
    h = torch.tanh(hpreact)
    logits = h @ W2 + b2
    loss = F.cross_entropy(logits, Y_batch)

    for p in parameters:
        p.grad = None
    loss.backward()

    for p in parameters:
        p.data += -0.1 * p.grad
print(loss.item())

# 训练集
emb = C[Xtr]
embcat = emb.view(-1, 6)
preact = embcat @ W1 + b1
h = torch.tanh(preact)
logits = h @ W2 + b2
loss = F.cross_entropy(logits, Ytr)
print("training loss:", loss)

# 验证集
emb = C[Xdev]
embcat = emb.view(-1, 6)
preact = embcat @ W1 + b1
h = torch.tanh(preact)
logits = h @ W2 + b2
loss = F.cross_entropy(logits, Ydev)
print("dev loss:", loss)

training loss: tensor(2.3670, grad_fn=<NllLossBackward0>)
dev loss: tensor(2.3616, grad_fn=<NllLossBackward0>)
```

可以看到训练集和验证集上的 loss 比较接近，暂未出现明显的过拟合迹象；不过 loss 仍然较高，模型还有优化空间。

### 优化超参数

欠拟合说明训练不足，这可能是多种原因导致的，比如训练次数不足、隐藏层不足、嵌入维度不足等，这里我们做几项优化：

- 隐藏层加大到 300 个神经元
- 字符表用 10 维表示

最终完成神经网络实现如下：

```Python
# 初始化参数
g = torch.Generator().manual_seed(2137483647)

# 初始化词表，27 个样本，每个用 10 维表示
C = torch.rand((27, 10), generator=g)

# 隐藏层：输入维度为 30 维，300 个神经元
W1 = torch.rand((30, 300), generator=g)
b1 = torch.rand((300), generator=g)
W2 = torch.rand((300, 27), generator=g)
b2 = torch.rand((27), generator=g)
parameters = [C, W1, b1, W2, b2]
for p in parameters:
    p.requires_grad = True

stepi = []
lossi = []
for i in range(50000):
    # minibatch
    ix = torch.randint(0, Xtr.shape[0], (32,))
    # 前向传播
    emb= C[Xtr[ix]]
    embcat = emb.view(-1, 30)

    hpreact = embcat @ W1 + b1
    h = torch.tanh(hpreact)
    logits = h @ W2 + b2
    loss = F.cross_entropy(logits, Ytr[ix])

    for p in parameters:
        p.grad = None
    loss.backward()

    # 学习率步长衰减
    lr = 0.1 if i < 20000 else 0.01
    for p in parameters:
        p.data += -lr * p.grad

    stepi.append(i)
    lossi.append(loss.log10().item())
print(loss.item())
```

我们分别用训练集、验证集、测试集来测试，看模型在三个数据集的表现是否一致，结果如下，三组 loss 较为接近，说明模型暂未出现明显的过拟合迹象。相较前一组训练结果，验证集 loss 已从约 2.36 降至约 2.26，但仍有继续优化的空间。

```Python
emb = C[Xtr]
embcat = emb.view(-1, 30)
preact = embcat @ W1 + b1
h = torch.tanh(preact)
logits = h @ W2 + b2
loss = F.cross_entropy(logits, Ytr)
print("training loss:", loss)

emb = C[Xdev]
embcat = emb.view(-1, 30)
preact = embcat @ W1 + b1
h = torch.tanh(preact)
logits = h @ W2 + b2
loss = F.cross_entropy(logits, Ydev)
print("dev loss:", loss)

emb = C[Xte]
embcat = emb.view(-1, 30)
preact = embcat @ W1 + b1
h = torch.tanh(preact)
logits = h @ W2 + b2
loss = F.cross_entropy(logits, Yte)
print("test loss:", loss)

training loss: tensor(2.2358, grad_fn=<NllLossBackward0>)
dev loss: tensor(2.2605, grad_fn=<NllLossBackward0>)
test loss: tensor(2.2594, grad_fn=<NllLossBackward0>)
```

最后我们用改进后的模型做采样预测，从结果可以看到比起上一版，本次的预测结果更接近真实的人名了。
```Python
# sample from the model
g = torch.Generator().manual_seed(2147483647 + 10)

for _ in range(20):

    out = []
    context = [0] * block_size  # initialize with all ...

    while True:
        emb = C[torch.tensor([context])]  # (1, block_size, d)
        h = torch.tanh(emb.view(1, -1) @ W1 + b1)
        logits = h @ W2 + b2
        probs = F.softmax(logits, dim=1)

        ix = torch.multinomial(probs, num_samples=1, generator=g).item()
        if ix == 0:
            break

        context = context[1:] + [ix]
        out.append(ix)


    print(''.join(itos[i] for i in out))

carlah
amori
kiha
mori
talyn
kaadane
mahnel
amerahciareli
nellara
chaiivia
leig
hham
prin
quinn
sulie
alian
quin
elogiearyxi
jaxe
piruliwey
```
