---
title: "Scrapy 入门学习笔记（一）Scrapy 项目搭建与架构介绍"
date: 2017-05-12T08:37:03+08:00
draft: true
tags:
  - Scrapy
  - Python
categories:
  - 软件工程
source: "https://blog.csdn.net/Ahri_J/article/details/71703001"
---
***最近学习用 Scrapy 框架写爬虫，简单来说爬虫就是从网上抓取网页，解析网页，然后进行数据的存储与分析，将从网页的解析到数据的转换存储。将学习过程中用到的解析技术，Scrapy 的各个模块使用与进阶到分布式爬虫学到的知识点、遇到的问题以及解决方法记录于此，以作总结与备忘，也希望对需要的同学有所帮助。***

本篇文章作为开篇，主要介绍 Scrapy 项目以及爬虫的创建，也简要概述了 Scrapy 项目各个部分的作用以及大致的执行流程。

---

#### 一. Scrapy 项目创建与介绍

首先是 Scrapy 的安装，这里直接使用 pip 进行安装即可

```bash
pip install scrapy
```

安装完成后就可以使用 scrapy 命令来创建项目了，如下：

```
scrapy startproject FirstSpider
```

上面的命令只是生成了一个 Scrapy 项目，之后还需要创建爬虫才能爬取，创建爬虫的命令如下：

```
scrapy genspider stack http://stackoverflow.com/
```

使用 scrapy genspider 来创建一个爬虫，并且指定名称为 stack, 起始爬取路径为 [http://stackoverflow.com/](http://stackoverflow.com/)

创建完成后的项目目录结构如下：

![Scrapy 项目结构图](https://img-blog.csdn.net/20170512083446151?watermark/2/text/aHR0cDovL2Jsb2cuY3Nkbi5uZXQvQWhyaV9K/font/5a6L5L2T/fontsize/400/fill/I0JBQkFCMA==/dissolve/70/gravity/SouthEast)

可以看到在项目目录下会有一个与项目名同名的 FirstSpider 包，里面是我们 Scrapy 项目的各个模块。下面对项目的每个部分做简要解释：

- spiders/

顾名思义就是爬虫的 package。我们创建的爬虫文件都会自动生成在该 package 下, 可以看到之前创建的 stack 已经在这里了。

- items.py

用来存放 Item
 类
的文件，Item 类可以理解为数据的中转类，我们爬取网页后需要将进行解析，并将解析后的数据进行存储分析。为了便于数据的迁移存储，我们可以将数据封装为一个 Item 类，然后在对 Item 类进行操作，这样可以避免很多不必要的错误。

- middlewares.py

中间层文件， Scrapy 自带的 middleware 可以分为 spider middleware 和 downloader middleware 两类, 我们也可以自定义 middleware 类。我们爬取网页的网络请求和响应都会经过 middleware 进行处理, 因此可以在这里做一些个性化的操作，比如设置用户代理，设置代理 IP 等。

- piplines.py

用来处理保存数据的模块，我们爬取网页后解析生成的 Item 类会被传递到这里进行存储解析等操作。 Scrapy 提供了许多有用的 Pipeline 类来处理数据，我们也可以自定义 Pipeline 类进行处理。

- settings

Scrapy 项目的配置文件，对整个项目进行设置。比如设置请求和响应的中间层，指定操作数据的 Pipeline 类等。

---

介绍完了各个模块之后让我们在看一下刚才创建的爬虫文件，其源代码如下:

```Python
import scrapy

class StackSpider(scrapy.Spider):
    name = "stack"
    allowed_domains = ["http://stackoverflow.com/"]

    start_urls = ['https://www.baidu.com/']

    # 默认的解析方法，可以自己定义其他解析方法解析对应的请求
    def parse(self, response):

        html = response.text
        print(html)
        pass

    # 指定起始请求，生成一个 scrapy.Request() 请求对象
    def start_requests(self):
        yield scrapy.Request(url='http://stackoverflow.com/', callback=self.parse)
```

可以看到我们指定的爬虫名和起始 url 都在里面。默认生成的代码是没有 start_requests 方法的，我们在命令中添加的起始网址会被声明为 start_urls 中的元素。Scrapy 将 start_urls 中的 url 作为起始路径进行爬取。除此之外我们可以重写 Scrapy 提供的 start_requests() 方法来发送 scrapy.Request 请求自行设定。

如代码中所示，我们自定义了 start_requests 方法生成了一个 scrapy.Request 请求，并指定了请求 url 和回调函数，callback 默认值是调用 parse 方法，我们也可以自定义其他解析方法来针对不同的网页爬取请求做解析。

之后就是执行爬虫进行爬取了，其命令 为 scrapy crawl + 爬虫名，如下：

```
scrapy crawl stack
```

爬取成功后会将 response 对象传递到我们指定的解析方法中进行解析，这样一个爬虫就创建运行成功了。如代码所示，我们获取了 response.text 属性，会返回其页面的 HTML 代码。

通过网页解析的技术我们可以获取页面中任何我们需要的数据，关于解析的技术将在下一篇文章中讲解，现在简要讲解下 Scrapy 的
 架构
以及执行流程，结合前面各个模块的讲解帮助大家对 Scrapy 有个宏观的印象，便于后面的学习。

#### 二. Scrapy 爬虫执行流程概述

Scrapy 架构图如下：

![Scrapy 架构图](https://img-blog.csdn.net/20170512083531884?watermark/2/text/aHR0cDovL2Jsb2cuY3Nkbi5uZXQvQWhyaV9K/font/5a6L5L2T/fontsize/400/fill/I0JBQkFCMA==/dissolve/70/gravity/SouthEast)

从上面的架构图中可以看到我们熟悉的几个模块，包括 Spiders、Item、middleware、pipeline 模块。另外还多了 ENGIN 引擎、SCHEDULER 和 DOWNLOADER 下载模块。

下面结合图中的各个流程做简要讲解：

1. Spider 爬虫部分发送请求，通过 spidermiddleware 中间层处理后发送给 ENGINE 引擎模块
2. 引擎模块将请求发送给 SCHEDULER 模块进行调度
3. SCHEDULER 模块将可以执行的请求调度给引擎模块
4. 引擎模块将请求发送给 DOWNLOADER 下载模块进行下载，期间会经过 download middleware 进行处理
5. 下载模块将爬取好的网页响应经过 downloadermiddleware 中间层处理后传递给引擎模块
6. 引擎模块将响应传递给 Spider 爬虫模块
7. 在爬虫模块我们自定义解析方式对响应解析完成后生成 Item 对象或者新的 Request对象,经过 spiddermiddleware 发送给引擎模块
8. 如果是 Item 对象传递给 item 和 pipeline 来进行对应的处理; 如果是 Request 对象则继续调度下载，重复之前的步骤。

上面就是整个 Scrapy 的执行流程了，了解了大致的流程后，后面就是对各个流程中的知识点进行学习了，包括网页的解析，请求响应的中间层处理，item 与 pipeline 对数据的处理以及可能遇到的问题以及解决方案，将在后面的文章中逐个讲解，梳理内容，巩固所学，也希望对需要的同学有所帮助。
