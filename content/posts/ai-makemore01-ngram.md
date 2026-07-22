---
title: "【AI 得学啊】makemore 01：从统计学习到神经网络"
date: 2026-07-22T20:00:00+08:00
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
description: 从统计 bigram 模型到神经网络，手写字符级姓名生成模型并理解负对数似然与梯度下降。
---

<img class="ai-series-cover" src="https://pub-08b57ed9c8ce4fadab4077a9d577e857.r2.dev/ai-notes-hou-cover.jpg" alt="AI 好啊，AI 得学">

本文是 Andrej Karpathy [《Neural Networks: Zero to Hero》](https://www.youtube.com/playlist?list=PLAqhIrjkxbuWI23v9cThsA9GvCAUhRvKZ) 课程 makemore01 章节的笔记，介绍根据姓名数据集，用统计学习和神经网络的方式实现姓名预测的模型。

## N-gram

自然语言处理（NLP, Natural Language Processing）是人工智能的一个重要分支，其目的是让计算机理解、生成和处理人类语言。典型任务包括分词、文本分类、情感分析、机器翻译、信息抽取、问答系统、摘要生成、对话系统等。语言模型（Language Model, LM，语言模型）是 NLP 的核心课题之一，它学习”一个词或 token 在上下文中出现的概率“，然后根据给定的前面的文本，模型预测后面最可能出现什么。例如：

> 今天北京的天气很 __

语言模型会根据训练经验判断后面更可能是：

> 好 / 冷 / 热 / 晴朗

在深度学习和大语言模型之前，传统语言模型通常是基于统计方法，其核心思想是**根据文本出现的频率统计得到其出现的概率，然后基于概率做预测**。以一个句子为例，一个句子出现的概率，是句子中每个单词出现的**条件概率**之积。注意这里是条件概率，指的是前一个单词为 X、Y 时，下一个单词 Z 出现的概率。对于一个由 w1,w2...wn 共 N 个单词组成的句子，其出现的概率为：


$$
P(S) = P(w_1 \mid .) \cdot P(w_2 \mid w_1, .) \cdot \ldots \cdot P(w_n \mid w_{n-1}, w_{n-2}, \ldots, w_1)
$$


上面的公式被称为概率的链式法则：

![](https://pub-08b57ed9c8ce4fadab4077a9d577e857.r2.dev/biggram01.png)

链式法则本身没问题，但预测下一个字符需要统计完整的历史信息，比如我希望根据《红楼梦》的内容做预测，预测最后一个字的概率就是全书所有汉字的概率之积，这在实际实践中几乎不可能实现。

俄国数学家 Andrey Markov（安德烈·马尔可夫）在 1906 年左右研究诗歌和字母序列时提出了后来被称为 **马尔可夫链（Markov Chain）** 的理论：

> 系统未来的状态，只依赖当前状态，与更久远的历史无关。

研究者借鉴了这一思想，预测下一个单词时不在回溯其全部的历史，而是近似的认为只与它前面有限 N - 1 个单词有关，对应的模型就是 N-gram 模型（N 元模型）。N 表示一个 N-gram 中包含的单词数，当 N = 2 时称为 Bigram 模型，即只关心前面的一个单词；N=3 时称为 Trigram 模型。

### 数据准备

课程要做的是一个基于名字数据集训练能起名字的神经网络，第一版就是采用 Bigram 模型来实现的，这里的 bigram 代表字母对。首先需要根据数据集构造 bigram（字母对），除了 26 个英文字母外，为了识别每个单词的开始和结束，这里还会以 `.` 来表示起止符。构建代码如下：

```Python
import torch.nn.functional as F
import torch

# 读取所有姓名数据，大约三万多个样本
words = open('names.txt', 'r').read().splitlines()

# 遍历每个单词构造每个字母的两两组合 bigram，开始结尾用 . 表示
b = {}
for w in words:
    chs = ['.'] + list(w) + ['.']
    for ch1, ch2 in zip(chs, chs[1:]):
        bigram = (ch1, ch2)
        # 对 bigram 计数
        b[bigram] = b.get(bigram, 0) + 1

# 根据计数对构造好的 bigram 排序
sorted(b.items(), key = lambda kv: -kv[1])
```

这样我们就拿到了训练数据集的所有字符对计数：
```ipynb
 (('n', '.'), 6763),
 (('a', '.'), 6640),
 (('a', 'n'), 5438),
 (('.', 'a'), 4410),
 (('e', '.'), 3983),
 ...
```

另外为了后面的训练，我们需要建立字符索引：

```Python
chars = sorted(list(set(''.join(words))))
stoi = {s:i+1 for i, s in enumerate(chars)}
# 字符到数字的映射
stoi['.'] = 0 # 将起止符作为索引 0
# 数字到字符的映射
itos = {i:s for s,i in stoi.items()}
```
这样我们就建立了字符到数字的映射。

```python
{'a': 1, 'b': 2, 'c': 3, 'd': 4, 'e': 5, 'f': 6, 'g': 7, 'h': 8, 'i': 9, 'j': 10, 'k': 11, 'l': 12, 'm': 13, 'n': 14, 'o': 15, 'p': 16, 'q': 17, 'r': 18, 's': 19, 't': 20, 'u': 21, 'v': 22, 'w': 23, 'x': 24, 'y': 25, 'z': 26, '.': 0}
{1: 'a',
 2: 'b',
 3: 'c',
 4: 'd',
 5: 'e',
 6: 'f',
 7: 'g',
 8: 'h',
 9: 'i',
 10: 'j',
 11: 'k',
 12: 'l',
 13: 'm',
 14: 'n',
 15: 'o',
 16: 'p',
 17: 'q',
 18: 'r',
 19: 's',
 20: 't',
 21: 'u',
 22: 'v',
 23: 'w',
 24: 'x',
 25: 'y',
 26: 'z',
 0: '.'}
```

上面代码使用的是字典来统计 bigram 的计数，现在我们用 27 * 27 的字符矩阵来表示 bigram 出现的次数，行代表首字符，列代表第二个字符。
```python
# 构建 bigram统计
# 使用的是 27 * 27 的字符矩阵，行代表第一个字母，列代表第二个字母
# 每个位置 N[row, col] 就代表对应 bigram 出现的次数
N = torch.zeros((27, 27), dtype=torch.int32)
for w in words:
    chs = ['.'] + list(w) + ['.']
    for ch1, ch2 in zip(chs, chs[1:]):
        ix1 = stoi[ch1]
        ix2 = stoi[ch2]
        N[ix1, ix2] += 1
```

打印后最终可以得到所有 bigram 的统计计数，比如索引为 1 的行就代表以 a 字母开头，`a.`、`aa`、`ab`、`ac`一直到 `az`，每个以 a 开头的字母对出现的次数。

![](https://pub-08b57ed9c8ce4fadab4077a9d577e857.r2.dev/bigram_counts.png)

### bigram 统计模型

有了完整的统计计数后就可以计算概率分布然后做预测了。首先做一次加一平滑，这样可以避免某个 bigram 因为没有出现过导致其统计概率为 0，进而导致永远没办法预测到。

```python
# N+1 表示将矩阵中的每个元素的数加一
P = (N+1).float()
```

然后对矩阵做归一化处理，

```Python
# 对每一行求和，得到总次数
row_sums = P.sum(1, keepdims = True)

# 计算每个 bigram 的概率：单个 bigram 次数 / 总次数
P = P / row_sums
```
这样我们完成了从统计计数向概率分布的转换，每一行就表示当前字符为行索引代表的字符时，列索引代表字符出现的概率，每一行的概率和为 1。

```python
P[1].sum()
tensor(1.0000)
```

然后就可以基于基本的概率分布模型做名字预测了：

```python
# 基于概率分布做采样
# 固定随机种子，种子一样每次的运行结果都一样
g = torch.Generator().manual_seed(2147483647)
for i in range(5):
    out = []
    # 行索引
    ix = 0
    while True:
        # 从第一行开始
        # 第一行的概率分布
        p = P[ix]
        # 采样到的字符索引
        # multinomial 是基于概率分布做的采样，所以种子一样的情况下，每次运行的结果都一样
        ix = torch.multinomial(p, num_samples=1, replacement=True, generator=g).item()
        # 根据索引获取字符
        out.append(itos[ix])
        # 如果采样结果的索引是 0，也就是采样到结束符 .，代表结束
        if ix == 0:
            break
    print(''.join(out))

cexze.
momasurailezitynn.
konimittain.
llayn.
ka.
```
可以看到基于概率分布的 bigram 模型可以做基本的预测，但输出结果质量一般，接下来我们用神经网络做实现和优化。

## 神经网络

### 测试数据构建

这里先用第一个 word 来解释清楚整个过程，然后再做完整的神经网络训练。

神经网络的核心是数学函数计算，例如矩阵乘法、加法、非线性变换。字符本身不能直接参与这些数学运算，所以需要先将字符映射成整数编号。

```Python
xs, ys = [], []

for w in words[:1]:
    chs = ['.'] + list(w) + ['.']
    for ch1, ch2 in zip(chs, chs[1:]):
        ix1 = stoi[ch1]
        ix2 = stoi[ch2]
        # print(ch1, ch2)
        xs.append(ix1)
        ys.append(ix2)

xs = torch.tensor(xs)
ys = torch.tensor(ys)
print("xs's shape", xs.shape)
print("ys's shape", ys.shape)
# 输出结果
[0, 5, 13, 13, 1]
[5, 13, 13, 1, 0]
xs's shape torch.Size([5])
ys's shape torch.Size([5])
```

这里先将字符映射为了数字索引列表，但 Python list 更适合收集数据，并不能直接用作更复杂的运算，因此我们需要将其转为 Tensor（张量），这是 PyTorch 的核心数据结构，可以视为带有 shape、dtype、device 等信息的多维数组，对于设置了 requires_grad=True 的浮点 Tensor，PyTorch 会跟踪其梯度。基于以上处理我们得到：
- xs：输入字符编号
- ys：输入为 x 时的真实的输出字符编号

### 独热编码

数字索引依然是离散的数字符号，而神经网络只能对数值张量做连续的向量运算，我们需要将字符索引转为可参与矩阵乘法运算的向量，这里我们用 **独热编码（one-hot）** 表示，xs 中有 5 个字符样本，每个元素都是一个字符编号，取值范围是 0~26。因此可以用一个 27 维的向量表示 27 个字符索引，只有对应的字符索引处值为 1，其他的都是 0，

```Python
import torch.nn.functional as F
xenc = F.one_hot(xs, num_classes=27).float()
xenc
```
编码后的数据表示如下：

```
tensor([[1., 0., 0., 0., 0., 0., 0., 0., 0., 0., 0., 0., 0., 0., 0., 0., 0., 0.,
         0., 0., 0., 0., 0., 0., 0., 0., 0.],
        [0., 0., 0., 0., 0., 1., 0., 0., 0., 0., 0., 0., 0., 0., 0., 0., 0., 0.,
         0., 0., 0., 0., 0., 0., 0., 0., 0.],
        [0., 0., 0., 0., 0., 0., 0., 0., 0., 0., 0., 0., 0., 1., 0., 0., 0., 0.,
         0., 0., 0., 0., 0., 0., 0., 0., 0.],
        [0., 0., 0., 0., 0., 0., 0., 0., 0., 0., 0., 0., 0., 1., 0., 0., 0., 0.,
         0., 0., 0., 0., 0., 0., 0., 0., 0.],
        [0., 1., 0., 0., 0., 0., 0., 0., 0., 0., 0., 0., 0., 0., 0., 0., 0., 0.,
         0., 0., 0., 0., 0., 0., 0., 0., 0.]])
```

用图表示示例如下，可以看到只有 xs 样本对应的索引处值为 1，其他的都是 0.
```Python
import matplotlib.pyplot as plt
plt.imshow(xenc)
```
![](https://pub-08b57ed9c8ce4fadab4077a9d577e857.r2.dev/xenc_one_hot.png)

### 初始预测

有了第一个 word 的独热编码张量，我们可以拿这个数据集做基本的训练了。首先我们随机初始化权重矩阵：
```Python
# 采用固定随机种子，每次得到的随机值都一样
g = torch.Generator().manual_seed(2147483647)
W = torch.randn((27, 27), generator=g)
```
这里的权重矩阵是 27 * 27：
- 我们的输入数据是 5 * 27 的矩阵，表示有 5 个样本，每个样本有 27 个维度，因此为了满足矩阵乘法运算，权重矩阵的行必须等于 27。
- 输出数据的范围是 0 ~ 26 共 27 种可能，因此列的维度也必须是 27，代表神经网络的输出是对 27 种可能的 logits 分数。

现在我们做矩阵运算，基于随机初始化得到的权重矩阵来做预测：

```Python
logits = xenc @ W
# softmax 运算，得到概率分布
counts = logits.exp()
probs = counts / counts.sum(1, keepdims=True)

print(probs.shape)
print(probs)
```
- `@`：代表矩阵乘法，计算后得到 logits，代表未经归一化的预测分数。
- `softmax`：基于 logits 的指数和做概率统计，得到每个结果的概率大小。

最终结果如下，probs[i] 表示模型根据第 i 个输入字符，对下一个字符给出的概率分布。例如 xs[1] 是字符 e 的编号，因此 probs[1] 表示输入为 e 时下一个字母的概率预测，总和为 1。上面提到 ys 是真实的数据输出，我们的模型越准确，probs 里 ys[i] 对应的概率就越大，这样我们就完成的最基本的神经网络实现。
![](https://pub-08b57ed9c8ce4fadab4077a9d577e857.r2.dev/softmax_01.jpg)

#### 负对数似然

有了初始的神经网络后，我们需要评估神经网络的好坏，一般用 LOSS（损失函数）表示，LOSS 越低，说明神经网络越靠谱。

这里采用负对数似然来表示 LOSS，其适合作为 LOSS 的原因是：我们的输入是 xs，预期的正确输出为 ys，因此神经网络预测到获得 emma 结果的概率就是 .e、em、mm、ma、a.这 5 个 bigram 的概率积，也就是

$$
P(\text{emma})
= P(e \mid .) \cdot P(m \mid e) \cdot P(m \mid m) \cdot P(a \mid m) \cdot P(. \mid a)
$$

用上面得到的结果计算大致就是：

```
0.0123 × 0.0181 × 0.0267 × 0.0737 × 0.0150
≈ 0.00000000657
≈ 6.57e-9
= 0.000000657%
```
可以看到如果直接使用概率计算，得到的结果非常小，不便于运算和评估。为此 AI 研究者们通常用对数来执行上述计算，对数计算有个特点是：可以将乘法运算转为加法。

$$
\log(a \cdot b \cdot c) = \log a + \log b + \log c
$$

这样我们的概率计算用对数表示后就可以变成：

$$
\begin{aligned}
\log P(\text{emma})
&= \log P(e \mid .)
 + \log P(m \mid e)
 + \log P(m \mid m)
 + \log P(a \mid m)
 + \log P(. \mid a) \\
&\approx \log(0.0123)
 + \log(0.0181)
 + \log(0.0267)
 + \log(0.0737)
 + \log(0.0150) \\
&\approx -18.84
\end{aligned}
$$

这个就是**对数似然（log likelihood）**，可以看到整个结果可读性好了很多。另外对于概率的对数计算特点是，概率都是 0 ~ 1 的小数，因此其对数计算后都是负数，概率越大，其对数越接近 0，概率越小，其绝对值越大。

我们对于神经网络的预期是，对真实的单词的概率越大越好，对应到对数似然就是其**绝对值越小越好**，因此我们将对数似然取负得到正数的**负对数似然（NLL, Negative Log-Likelihood）**来作为 LOSS 评估神经网络的好坏。

上面近似计算得到的负对数似然就是 18.84，平均 LOSS 就是 3.768。我们可以遍历整个计算过程，用真实的概率值做运算，最终得到的各个 bigram 负对数似然如下，可以看到神经网络对对 ys[e,m,m,a,.] 的 loss 依次是 4.399、4.015、3.623、2.608、4.201，然后总的平均负对数似然是 3.7693049907684326。

```Python
nlls = torch.zeros(5)
for i in range(5):
  # 输入字符 x，依次是 . e m m a
  x = xs[i].item() # input character index
  # 实际下个字符 y，依次是 e m m a .
  y = ys[i].item() # label character index
  print('--------')
  # 真实的 bigram 对
  print(f'bigram example {i+1}: {itos[x]}{itos[y]} (indexes {x},{y})')
  print('input to the neural net:', x)
  # 概率分布
  print('output probabilities from the neural net:', probs[i])
  print('label (actual next character):', y)
  # 神经网络中，该 bigram 的概率
  p = probs[i, y]
  print('probability assigned by the net to the the correct character:', p.item())
  # 求自然对数
  logp = torch.log(p)
  print('log likelihood:', logp.item())
  nll = -logp
  print('negative log likelihood:', nll.item())
  nlls[i] = nll

print('=========')
# 平均负对数似然
print('average negative log likelihood, i.e. loss =', nlls.mean().item())

bigram example 1: .e (indexes 0,5)
input to the neural net: 0
output probabilities from the neural net: tensor([0.0607, 0.0100, 0.0123, 0.0042, 0.0168, 0.0123, 0.0027, 0.0232, 0.0137,
        0.0313, 0.0079, 0.0278, 0.0091, 0.0082, 0.0500, 0.2378, 0.0603, 0.0025,
        0.0249, 0.0055, 0.0339, 0.0109, 0.0029, 0.0198, 0.0118, 0.1537, 0.1459])
label (actual next character): 5
probability assigned by the net to the the correct character: 0.012286250479519367
log likelihood: -4.3992743492126465
negative log likelihood: 4.3992743492126465
--------
bigram example 2: em (indexes 5,13)
input to the neural net: 5
output probabilities from the neural net: tensor([0.0290, 0.0796, 0.0248, 0.0521, 0.1989, 0.0289, 0.0094, 0.0335, 0.0097,
        0.0301, 0.0702, 0.0228, 0.0115, 0.0181, 0.0108, 0.0315, 0.0291, 0.0045,
        0.0916, 0.0215, 0.0486, 0.0300, 0.0501, 0.0027, 0.0118, 0.0022, 0.0472])
label (actual next character): 13
probability assigned by the net to the the correct character: 0.018050704151391983
log likelihood: -4.014570713043213
negative log likelihood: 4.014570713043213
--------
bigram example 3: mm (indexes 13,13)
input to the neural net: 13
output probabilities from the neural net: tensor([0.0312, 0.0737, 0.0484, 0.0333, 0.0674, 0.0200, 0.0263, 0.0249, 0.1226,
        0.0164, 0.0075, 0.0789, 0.0131, 0.0267, 0.0147, 0.0112, 0.0585, 0.0121,
        0.0650, 0.0058, 0.0208, 0.0078, 0.0133, 0.0203, 0.1204, 0.0469, 0.0126])
label (actual next character): 13
probability assigned by the net to the the correct character: 0.026691533625125885
log likelihood: -3.623408794403076
negative log likelihood: 3.623408794403076
--------
bigram example 4: ma (indexes 13,1)
input to the neural net: 13
output probabilities from the neural net: tensor([0.0312, 0.0737, 0.0484, 0.0333, 0.0674, 0.0200, 0.0263, 0.0249, 0.1226,
        0.0164, 0.0075, 0.0789, 0.0131, 0.0267, 0.0147, 0.0112, 0.0585, 0.0121,
        0.0650, 0.0058, 0.0208, 0.0078, 0.0133, 0.0203, 0.1204, 0.0469, 0.0126])
label (actual next character): 1
probability assigned by the net to the the correct character: 0.07367684692144394
log likelihood: -2.6080667972564697
negative log likelihood: 2.6080667972564697
--------
bigram example 5: a. (indexes 1,0)
input to the neural net: 1
output probabilities from the neural net: tensor([0.0150, 0.0086, 0.0396, 0.0100, 0.0606, 0.0308, 0.1084, 0.0131, 0.0125,
        0.0048, 0.1024, 0.0086, 0.0988, 0.0112, 0.0232, 0.0207, 0.0408, 0.0078,
        0.0899, 0.0531, 0.0463, 0.0309, 0.0051, 0.0329, 0.0654, 0.0503, 0.0091])
label (actual next character): 0
probability assigned by the net to the the correct character: 0.01497753243893385
log likelihood: -4.2012038230896
negative log likelihood: 4.2012038230896
=========
average negative log likelihood, i.e. loss = 3.7693049907684326
```

上面是拿第一个名字 emma 做的演示，接下来我们用完整的数据集对神经网络做训练来降低 LOSS 了。

### 构建完整数据集

这里我们要使用完整的名字数据集来做训练。
```Python
# 1. 构建数据集
xs, ys = [],[]

for w in words:
    chs = ['.'] + list(w) + ['.']
    for ch1, ch2 in zip(chs, chs[1:]):
        ix1 = stoi[ch1]
        ix2 = stoi[ch2]
        xs.append(ix1)
        ys.append(ix2)

# 这次是 22 万多个 bigram 样本数据
xs = torch.tensor(xs)
ys = torch.tensor(ys)
print(xs.shape)
print(ys.shape)
# torch.Size([228146])
# torch.Size([228146])
```

然后我们初始化权重矩阵，并对训练数据做独热编码

```Python
# 对数据做独热编码，转为矩阵
xenc = F.one_hot(xs, num_classes=27).float()
# 初始化权重参数。必须带 requires_grad=True，否则反向传播没用
g = torch.Generator().manual_seed(2147483647)
W = torch.randn((27, 27), generator=g, requires_grad=True)
num = xs.nelement()
```
### 梯度下降

有了数据和权重矩阵，我们就可以进行梯度下降了，和之前 macrograd 里提到的流程一样：

- 前向运算
- 计算 LOSS
- 重置梯度
- 反向传播
- 更新参数
- 继续循环

代码如下：

```Python
# 执行 1000 次
for k in range(1000):
    # 前向计算
    logits = xenc @ W

    # softmax 运算，将计算后的未经归一化的预测分数转为概率分布
    counts = logits.exp()
    probs = counts / counts.sum(1, keepdims=True)

    # 模型为真实的下一个字符分配的概率
    target_probs = probs[torch.arange(num), ys]
    # 负对数似然 LOSS
    nll_loss = -target_probs.log().mean()
    # 正则化损失
    reg_loss = 0.01 * (W ** 2).mean()
    # 总 loss
    loss = nll_loss + reg_loss

    # 重置梯度，反向传播
    W.grad = None # set to zero the gradient
    loss.backward()
    # 更新权重参数，这里学习率采用 50
    W.data += -50 * W.grad
```

相关代码含义如下：

- `target_probs = probs[torch.arange(num), ys]`：这里取所有真实数据 ys 的概率，等价于如下代码，这里的概率应该越高越好。

```Python
target_probs = []
for i in range(num):
    real_index = ys[i]
    real_prob = probs[i, real_index]
    target_probs.append(real_prob)
#合并为一维 Tensor
target_probs = torch.stack(target_probs)
```
- `nll_loss = -target_probs.log().mean()`：求负对数似然，这里的 .log().mean() 相当于给 target_probs 的每个值先求对数然后在求平均值得到平均对数似然，最后取负号得到负对数似然。

- `reg_loss`：正则化损失，也叫权重衰减，用来加在主 loss 上，防止过拟合。

- `-50`：50 代表学习率，负号表示沿着梯度相反的反向更新，也就是梯度下降。

执行上述计算，经过 1000 次梯度下降后得到的 LOSS 大约为 2.48，并且继续迭代也不会再有很明显的变化了，这样我们就完成了基础的神经网络版本的 bigram 模型。

最后我们在总结下两者的区别，其核心差异在于**计算得到概率的方式不同**：

- 统计版本的 bigram，通过频率计算和归一化处理得到每个 bigram 字母对的概率分布，然后基于概率分布做预测。
- 神经网络版本的 bigram 是随机初始化一个权重矩阵，代表为每个 bigram 的权重分配，通过矩阵乘法和 softmax 运算得到概率分布后做预测。然后以负对数似然作为 LOSS，通过训练不断调整权重，尽可能的为真实的 bigram 赋予更大的权重，从而提高预测的准确性。

用优化后的神经网络测试下效果：

```Python
g = torch.Generator().manual_seed(2147483647)

for i in range(5):

  out = []
  ix = 0
  while True:

    xenc = F.one_hot(torch.tensor([ix]), num_classes=27).float()
    logits = xenc @ W # predict log-counts
    # softmax
    counts = logits.exp() # 先求指数，然后做归一化处理
    p = counts / counts.sum(1, keepdims=True) # probabilities for next character

    ix = torch.multinomial(p, num_samples=1, replacement=True, generator=g).item()
    if ix == 0:
      break
    out.append(itos[ix])

  print(''.join(out))
# 预测结果
cexze
momasurailezityha
konimittain
llayn
ka
```
可以看到虽然已经可以做预测了，但得到的结果还是不太令人满意，接下来我们使用多层感知机神经网络继续做优化。
