---
title: "Scrapy 入门学习笔记（二）XPath 与 CSS 解析"
date: 2017-05-15T20:33:24+08:00
draft: true
tags:
  - Scrapy
  - Python
categories:
  - 软件工程
source: "https://blog.csdn.net/Ahri_J/article/details/72196823"
---
***最近学习用 Scrapy 框架写爬虫，简单来说爬虫就是从网上抓取网页，解析网页，然后进行数据的存储与分析，将从网页的解析到数据的转换存储。将学习过程中用到的解析技术，Scrapy 的各个模块使用与进阶到分布式爬虫学到的知识点、遇到的问题以及解决方法记录于此，以作总结与备忘，也希望对需要的同学有所帮助。***

本篇主要讲解 xpath 、css 解析网页的语法以及在 Scrapy 中的使用方式

---

#### 一. xpath 简介与语法概要

xpath 是 w3c 的一种标准。简单来说就是可以让我们以路径的形式访问 html 网页中的各个元素。其中最
 主要的
两个 为 // 与 /。前者代表 路径下的所有元素， 后者代表路径下的子元素。具体语法如下：

###### 基本语法：

```Python
question      # 选取所有 question 元素的所有子节点
/question     #选取根元素 question
question/a    # 选取 question 元素下所有为 a 的子元素
//div         # 选取所有的 div 元素，不论其出现在文档的任何地方
question//div # 选取 question 元素下所有的 div 后代元素 (/ 选取的是直接子元素，这里是所有的后代元素)
question//span/text() #选取 question 元素下所有 span 元素中的文本值
question//a/@href     #选取 question 元素下所有 a 元素中的 href 属性值。 @ 后面可以是任意属性名，均可以取到值
```

###### 带有限定性质的语法

```Python
/question/div[1]        # 选取 question 的第一个 div 子元素。 注意这里第一个是从索引 1 开始的
/question/div[last()]   # 选取 question 第最后一个 div 子元素
/question/div[last()-1] # 选取 question 的倒数第二个 div 子元素
//div[@lang]            # 选取所有拥有lang 属性的 div 元素
//div[@lang='eng']      # 选取所有 lang 属性为 eng 的 div 元素
```

###### 其他语法补充

```Python
/div/*    # 选取属于 div 元素的所有子节点
//*       # 选取所有元素
//div/a | //div/p #选 取所有 div 元素的 a 元素或者 p 元素
//span | //input  # 选取文档中所有的 span 和 input 元素
```

#### 二. css 语法概要

熟悉前端的同学对 css 选择器一定不会陌生，比如 jquery 中通过各种 css 选择器语法进行 DOM 操作等。这里对其语法进行简要的总结，便于复习。

###### 基本查询语法

```
 *        # 选取所有节点
#title    # 选取 id 为 title 的元素
.col-md   # 选取所有 class 包含 col-md 的元素
li a      # 选取所有 li 下的 a 元素
ul + p    # 选取 ul 后面的第一个 p 元素
div#title > ul   # 选取 id 为 title 的 div 的第一个 ul 子元素
ul ~ p    # 选取 与 url 相邻的所有 p 元素

span#title ::text  # 选取 id 为 title 的 span 元素的文本值
a.link::attr(href) # 选取 class 为 link 的 a 元素的 href 属性值
```

###### 属性相关查询语法

```
a[title]  # 选取所有有 title 属性的 a 元素
a[href='http://stackoverflow.com/'] # 选取所有 href 属性为 http://stackoverflow.com/ 的 a 元素
a[href*="stackoverflow"] # 选取所有 href 属性包含 stackoverflow 的 a 元素
a[href^='https'] # 选取所有 href 属性值以 https 开头的 a 元素
a[href$='.jpg']  # 选取所有 href 属性值以 .jpg 为结尾的 a 元素
input[type=radio]:checked # 选择选中的 radio 的元素
```

###### 其他语法

```Python
div:not(.title)   # 选取所有 class 不是 title 的 div 元素
li:nth-child(3) # 选取第三个元素
tr:nth-child(2n) # 第偶数个元素
```

#### 三. Selector 语法简介 以及 StackoverFlow 问题列表解析示例

介绍完了上面的解析语法，下面来具体看一下在 Scrapy 中的使用。

Scrapy 提供了 Selector 类来对网页进行，它可以接收一段 HTML 代码进行构建，我们的 parse 方法中传递回来的 response 是一个 HTMLResponse 对象，它自带了两个方法 css() 和 xpath() 方法使我们可以方便的使用上面提高的两种方法做解析.

通过 css() 或者 xpath() 解析返回的是一个 SelectorList 对象，为了获取到其中的元素或者文本、属性值，可以使用 extract() 或者 extract_first() 方法来进行获取。extract_first() 方法在没有值的时候返回为 None, 如果直接使用索引 0 进行获取会引发错误，因此推荐前者。

下面我们使用这两种方式来对 StackoverFlow 的问题列表进行解析，获取到一个问题中的数据。

其问题界面和源代码如下：

- 问题列表项

![问题列表项](https://img-blog.csdn.net/20170515202930466?watermark/2/text/aHR0cDovL2Jsb2cuY3Nkbi5uZXQvQWhyaV9K/font/5a6L5L2T/fontsize/400/fill/I0JBQkFCMA==/dissolve/70/gravity/SouthEast)
- 列表源代码

![列表源代码](https://img-blog.csdn.net/20170515203020985?watermark/2/text/aHR0cDovL2Jsb2cuY3Nkbi5uZXQvQWhyaV9K/font/5a6L5L2T/fontsize/400/fill/I0JBQkFCMA==/dissolve/70/gravity/SouthEast)

- 某一个问题的源代码

![某一个问题的源代码](https://img-blog.csdn.net/20170515203120845?watermark/2/text/aHR0cDovL2Jsb2cuY3Nkbi5uZXQvQWhyaV9K/font/5a6L5L2T/fontsize/400/fill/I0JBQkFCMA==/dissolve/70/gravity/SouthEast)

可以看到，问题列表位于 id 为 question 的 div 元素下，每个问题布局用 class=question-summary 表示，后面的 id 用来标识每一个问题，可以获取之后与域名进行拼接访问到具体的问题详情界面。下面我们就图中标注的标题、投票数，查看人数、回答人数以及标签进行解析。

- tip: 这里为了距离分别使用了 xpath 和 css 两种方式，但实际情况一般都是组合使用来达到最简洁的解析。官方文档建议在使用 class 进行解析时要用 css 解析方式。

##### css 解析

```Python
def parse_by_css(self, response):
       '''
       每个网页中有 50 个问题，遍历解析后存储到 mongoDB 数据库中
       :param response:
       :return:
       '''
       questions = response.css('div.question-summary')
       for question in questions:
           # 投票的数量是在 class=vote 的 div 下的 strong 中, css 通过 ::text 或者 ::attr(属性名)
           # 的方式来获取文本或者某一个属性值，因为最多只有一个值，所以直接使用 extract_first() 来获取到文本值即可
           question_votes = question.css('.votes strong::text').extract_first()
           # 标题是在 class=question-hyperlink 的 a 元素中
           question_title = question.css("a.question-hyperlink::text").extract_first()
           # 位于 class 为 answered 的 div 下的 strong 元素下
           question_answers = question.css('.answered strong::text').extract_first()
           # class 为 views 元素里面的 title 属性值
           question_views = question.css('.views::attr(title)').extract_first()
           # class 为 tags 的 div 元素下 所有 a 元素下的文本值，因为可能有多个标签，所以使用 extract() 方法，返回一个 tag 文本组成的 list
           tags = question.css('.tags a::text').extract()
           pass
```

##### xpath 解析

```Python
# 元素解释和上面的 css 解析程序一直，这里只列出代码不作赘述
def parse_by_xpath(self, response):
      questions = response.xpath("//div[@class='question-summary']")
      for question in questions:
          question_votes = question.xpath(".//div[@class='votes']//strong/text()").extract_first()
          question_title = question.xpath(".//a[@class='question-hyperlink']/text()").extract_first()
          question_answers = question.xpath(".//div[ contains(@class, 'answered')]/strong/text()").extract_first()
          question_views = question.xpath(".//div[contains(@class, 'views')]/@title").extract_first()
          tags = question.xpath(".//div[contains(@class, 'tags')]/a/text()").extract()
          pass
```

解析到的结果如下：

![网页解析结果](https://img-blog.csdn.net/20170515203246657?watermark/2/text/aHR0cDovL2Jsb2cuY3Nkbi5uZXQvQWhyaV9K/font/5a6L5L2T/fontsize/400/fill/I0JBQkFCMA==/dissolve/70/gravity/SouthEast)

可以看到数据都在里面了，具体的解释都在注释里面了，关于 Selector 的更详细语法可以参阅 Scrapy 的官方文档。本篇就简要介绍到这里，数据已经解析出来了，下一步就需要封装为 Item 进行传输与处理了，下一篇将介绍 Item 的相关内容。包括创建与属性，Item Loader 机制以及对数据进行过滤，处理的相关方法等。
