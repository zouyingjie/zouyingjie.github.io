---
title: "Scrapy 入门学习笔记（三）Item 与 ItemLoader"
date: 2017-05-18T14:02:16+08:00
draft: true
tags:
  - Scrapy
  - Python
categories:
  - 软件工程
source: "https://blog.csdn.net/Ahri_J/article/details/72466231"
---
***最近学习用 Scrapy 框架写爬虫，简单来说爬虫就是从网上抓取网页，解析网页，然后进行数据的存储与分析，将从网页的解析到数据的转换存储。将学习过程中用到的解析技术，Scrapy 的各个模块使用与进阶到分布式爬虫学到的知识点、遇到的问题以及解决方法记录于此，以作总结与备忘，也希望对需要的同学有所帮助。***

本篇主要讲解 Item
 类
封装数据以及 ItemLoader 加载数据机制。

---

#### 一. 创建 Item 类

为了将网页解析后获取的数据进行格式化，便于数据的传递与进一步的操作，Scrapy 提供了 Item 类来对数据进行封装。

要使用 Item 类非常简单，直接继承 scrapy 的 Item 类即可，然后可以定义相应的属性字段来对数据进行存储，其字段类型为 scrapy.Field()。 Scrapy 只提供了 Field() 一种字段类型，可以用来存储任意类型的数据。

现在我们根据上一节解析到的 StackoverFlow 的问题来创建我们的 Item 类，代码如下：

```Python
class StackQuestionItem(scrapy.Item):

    queston_title = scrapy.Field()
    question_votes = scrapy.Field()
    question_answers = scrapy.Field()
    question_views = scrapy.Field()
    tags = scrapy.Field()
```

创建完成后就可以在 parse 方法中将解析到的数据进行封装了, 结合上一篇文章中的解析代码如下:

```Python
def parse_by_css(self, response):

       questions = response.css('div.question-summary')
       for question in questions:

           question_votes = question.css('.votes strong::text').extract_first()
           question_title = question.css("a.question-hyperlink::text").extract_first()
           question_answers = question.css('.answered strong::text').extract_first()
           question_views = question.css('.views::attr(title)').extract_first()
           tags = question.css('.tags a::text').extract()

           question_item = StackQuestionItem()
           question_item["question_title"] = question_title
           question_item["question_votes"] = question_votes
           question_item['question_answers'] = question_answers
           question_item['question_views'] = question_views
           question_item['tags'] = tags

           yield question_item
```

生成的 Item 类通过 yield 返回时，Scrapy 会根据 settings 文件中的配置来传输到对应的 pipeline 类中，其默认已经给我们创建好了一个 pipeline 类，配置文件如下:

```Python
class StackoverflowspiderPipeline:

    def process_item(self, item, spider):

        # 获取到 Item 中的所有值
        title = item.get('question_title')
        votes = item.get('question_votes')
        answers = item.get('question_answers')
        views = item.get('question_views')
        tags = item.get('tags')
        return item
```

上面就是默认生成的 pipeline 类，可以看到自动生成了一个 process_item() 方法来处理传递过来的 Item，关于 pipeline 的内容后面会专门介绍，Item 类的基本使用就像上面这样，非常简单，下面我们看下其 ItemLoader 机制。

#### 二. 使用 ItemLoader 解析数据

##### 1. ItemLoader 简介

通过之前的学习，已经知道网页的基本解析流程就是先通过 css/xpath 方法进行解析，然后再把值封装到 Item 中，如果有特殊需要的话还要对解析到的数据进行转换处理，这样当解析代码或者数据转换要求过多的时候，会导致代码量变得极为庞大，从而降低了可维护性。同时在 sipider 中编写过多的
 数据处理
 代码某种程度上也违背了单一职责的代码设计原则。我们需要使用一种更加简洁的方式来获取与处理网页数据，ItemLoader 就是用来完成这件事情的。

ItemLoader 类位于 scrapy.loader ，它可以接收一个 Item 实例来指定要加载的 Item, 然后指定 response 或者 selector 来确定要解析的内容，最后提供了 add_css()、 add_xpath() 方法来对通过 css 、 xpath 解析赋值，还有 add_value() 方法来单独进行赋值。

示例代码如下：

```Python
from scrapy.loader import ItemLoader

def parse(self, response):
    questions = response.css('div.question-summary')
    for question in questions:

        # 指定了 StackQuestionItem 实例，另外因为我们已经解析了 response 获取到了所有问题的 selector，因此这里指定的是 selector 而不是 response。
        item_loader = DefaultItemLoader(item=StackQuestionItem(),  selector=question)

        # 下面是使用 add_css 方法，传递 Item 类的字段名称和对应的 css 解析语法
        # 如果使用 add_xpath 方法的话只需要传递对应的 xpath 解析语法几个
        item_loader.add_css('question_title', 'a.question-hyperlink::text')
        item_loader.add_css('question_votes', '.votes strong::text')
        item_loader.add_css('question_answers', '.answered strong::text')
        item_loader.add_css('question_views', '.views::attr(title)')
        item_loader.add_css('tags', '.tags a::text'))

        # 添加值示例.可以直接设置值
        item_loader.add_value('url', response.url)
```

上面就是简要的示例代码，可以看到相比之前的解析，赋值和解析代码合并在了一起，爬虫文件中的代码量减少了一半。当解析的数据很多而且还需要进行

特殊转换比如通过正则进行匹配替换的时候其效果更佳的明显。

上面代码解析完成后生成的都是一个 list，其值如下:

![ItemLoader 默认解析结果](https://img-blog.csdn.net/20170518140027092?watermark/2/text/aHR0cDovL2Jsb2cuY3Nkbi5uZXQvQWhyaV9K/font/5a6L5L2T/fontsize/400/fill/I0JBQkFCMA==/dissolve/70/gravity/SouthEast)

可以看到无论解析出来的值的数量是多少，ItemLoader 默认都会返回一个 list。在之前的方式中我们都是通过 extract_first() 获取第一个值或者通过 extract() 解析到值后进行遍历的。在 ItemLoader 中，为我们提供了 processor 来对数据进行处理。

在 ItemLoader 类中，提供了 default_output_processor 和 default_input_processor 来对数据的输入与输出进行解析，

如果我们需要只获取解析后的第一个值，可以指定 default_output_processor 为 TakeFirst() 即可，这是 Scrapy 提供的一个解析处理类，

用来获取第一个元素，代码如下:

```Python
class DefaultItemLoader(ItemLoader):
    default_output_processor = TakeFirst()
```

完成自定义的 ItemLoader 类之后就可以在 parse 中使用了

```
item_loader = DefaultItemLoader(item=StackQuestionItem(),  selector=question)

item_loader.add_css('question_title', 'a.question-hyperlink::text')
item_loader.add_css('question_votes', '.votes strong::text')
item_loader.add_css('question_answers', '.answered strong::text')
item_loader.add_css('question_views', '.views::attr(title)')
item_loader.add_css('tags', '.tags a::text')

question_item = item_loader.load_item()
```

上面的代码使用了自定义的 DefaultItemLoader，因为会获取到 list 中的第一个值，但是对于 tags 而言我们要的是 list 而不是通用的获取的第一个值，

对于这种特殊的处理情况，就需要在 Item 类中进行设置了。

Scrapy 允许我们在声明 Item 类定义其字段时，为每一个字段设置单独的数据处理方法，代码如下：

```Python
from scrapy.loader.processors import MapCompose, TakeFirst, Join

def add_prefix(value):
  return  'Question:' + value

class StackQuestionItem(scrapy.Item):
  question_title = scrapy.Field(
        # 指定任意函数对值进行处理
        # 指定 lambda
        # input_processor=MapCompose(lambda x: 'Question:' + x ),
        # 指定处理函数
        input_processor=MapCompose(add_prefix),

        # 使用 TakeFirst 来取到第一个值进行返回
        # output_processor=TakeFirst(),
    )
    question_votes = scrapy.Field()
    question_answers = scrapy.Field()
    question_views = scrapy.Field()
    tags = scrapy.Field(
        output_processor=Join(','),
    )
```

可以看到，我们可以在字段定义时想 scrapy.Field() 中指定 input_processor 和 output_processor 两个参数来指定对数据的处理。

scrapy 提供 的 MapCompose 方法允许我们指定一系列的处理方法，Scrapy 会将 解析到的 list 中的值依次传递到每个方法中对值进行处理，这里

我们在 title 前面加了 ‘Question:’ 前缀。然后在 tags 中通过 Join() 设置了分隔符来连接每一个
 tag
。关于更多的处理方法可以参阅官方文档，解析后获取到的结果如下：

![ItemLoader 解析结果](https://img-blog.csdn.net/20170518140126717?watermark/2/text/aHR0cDovL2Jsb2cuY3Nkbi5uZXQvQWhyaV9K/font/5a6L5L2T/fontsize/400/fill/I0JBQkFCMA==/dissolve/70/gravity/SouthEast)

可以看到 tag 已经使用逗号分隔符连接起来了，title 前面也加上了 ‘Question:’ 前缀。

最后在总结一下操作过程，首先定义一个 ItemLoader 类同时指定通用的 input/output 处理方法，然后在 parse 方法中声明 ItemLoader ，传递 Item 实例 和 response/selector。 通过 ItemLoader 的 add_css/add_xpath/add_value 来进行赋值。

如果对数据有特殊的处理，就在 Item 类的 Field 中传递 input_processor 和 output_processor 来指定处理函数，来完成整个数据的解析和处理。

关于 ItemLoader 的说明就到这里了，更加详细的操作可以参阅官方文档。接下来就是讲 Item 实例传递到 pipeline 进行处理了。下一篇将简要介绍 Pipeline 的使用，包括 Scrapy 提供的常用 Pipeline 类以及自定义 Pipeline 类。
