---
title: "Scrapy 入门笔记（四）使用 Pipeline 保存数据"
date: 2017-05-18T15:57:48+08:00
tags:
  - Scrapy
  - Python
categories:
  - 软件工程
source: "https://blog.csdn.net/Ahri_J/article/details/72472170"
---
***最近学习用 Scrapy 框架写爬虫，简单来说爬虫就是从网上抓取网页，解析网页，然后进行数据的存储与分析，将从网页的解析到数据的转换存储。将学习过程中用到的解析技术，Scrapy 的各个模块使用与进阶到分布式爬虫学到的知识点、遇到的问题以及解决方法记录于此，以作总结与备忘，也希望对需要的同学有所帮助。***

本篇主要讲解 pipeline 保存数据模块的使用，包括将数据存储为 Json 文件，存储到 MySQL 数据库以及保存图片

---

Scrapy 提供了 pipeline 模块来执行保存数据的操作。在创建的 Scrapy 项目中自动创建了一个 pipeline.py 文件，同时创建了一个默认的 Pipeline
 类
。我们可以根据需要自定义 Pipeline 类，然后在 settings.py 文件中进行配置即可，如下

```Python
# 指定用来处理数据的 Pipeline 类，后面的数字代表执行顺序,取值范围是  0-1000 range.
# 数值小的 Pipeline 类优先执行
ITEM_PIPELINES = {
   'StackoverFlowSpider.pipelines.StackoverflowspiderPipeline': 2,
}
```

接下来我们自定义 Pipeline 类来对将 Item 转为 Json 文件进行存储。

Pipeline 类会在 process_item 方法中处理数据，然后在结束时调用 close_spider 方法，因此我们

需要自定义这两个方法做相应的处理。

##### ***两点提示***

- 在 process_item() 方法处理完成后要返回 item 供后面的 Pipeline 类继续操作
- 记得在 close_spider() 中释放资源

##### 1. 自定义 Pipeline 存储 Json 数据

```Python
import json
import codecs
class StackJsonPipeline:

    # 初始化时指定要操作的文件
    def __init__(self):
        self.file = codecs.open('questions.json', 'w', encoding='utf-8')

    # 存储数据，将 Item 实例作为 json 数据写入到文件中
    def process_item(self, item, spider):
        lines = json.dumps(dict(item), ensure_ascii=False) + '\n'
        self.file.write(lines)
        return item
    # 处理结束后关闭 文件 IO 流
    def close_spider(self, spider):
        self.file.close()
```

##### 2. 使用 Scrapy 提供的 exporter 存储 Json 数据

Scrapy 为我们提供了一个 JsonItemExporter 类来进行 Json 数据的存储，非常方便，下面是使用该类

进行存储的自定义 Pipeline 类示例。

```Python
from scrapy.exporters import JsonItemExporter
class JsonExporterPipeline:
    # 调用 scrapy 提供的 json exporter 导出 json 文件
    def __init__(self):
        self.file = open('questions_exporter.json', 'wb')
        # 初始化 exporter 实例，执行输出的文件和编码
        self.exporter = JsonItemExporter(self.file,encoding='utf-8',ensure_ascii=False)
        # 开启倒数
        self.exporter.start_exporting()

    def close_spider(self, spider):
        self.exporter.finish_exporting()
        self.file.close()

    # 将 Item 实例导出到 json 文件
    def process_item(self, item, spider):
        self.exporter.export_item(item)
        return item
```

上面就是两个使用自定义 Pipeline 类生成 Json 数据的示例，有一点需要强调的是，我们使用 exporter 生成的

其实是一个数组， 下面是我使用上面两个类生成的两个文件截图，第一个生成的是许多个 Json 数据，后者是一个由

Json 数据组成的数组：

- 使用 json 模块生成的文件

![使用 json 模块存储](https://pub-08b57ed9c8ce4fadab4077a9d577e857.r2.dev/csdn-c531dc93549ebeea0f59c3a2360ef1f9ff1a580d4f53ceed2afc770eb0a1a6b1.png)

- 使用 scrapy.exporters.JsonItemExporter 生成的文件

![使用 exporter 存储](https://pub-08b57ed9c8ce4fadab4077a9d577e857.r2.dev/csdn-604f744c1beaf0d26ecffb4b4b53dd8accebb793dc60fde76cf719bc4aa59c49.png)

##### 3. 将数据保存到 MySQL 数据库

下面是一个将我们的数据保存到 MySQL 数据库的 Pipeline 类

```Python
# 这里我们使用 mysql-connector-python 驱动，可以使用 pip 进行安装
import mysql.connector

class MysqlPipeline:
    def __init__(self):
        self.conn = mysql.connector.connect(user='root', password='root', database='stack_db', )
        self.cursor = self.conn.cursor()

    def process_item(self, item, spider):

        title = item.get('question_title')
        votes = item.get('question_votes')
        answers = item.get('question_answers')
        views = item.get('question_views')
        tags = item.get('tags')
        insert_sql = """
            insert into stack_questions(title, votes, answers, views,tags)
            VALUES (%s, %s, %s, %s,%s);
        """
        self.cursor.execute(insert_sql, (title, votes, answers, views, tags))
        self.conn.commit()
        return item

    def close_spider(self, spider):
        self.cursor.close()
        self.conn.close()
```

将 MysqlPipeline 配置在
 settings
 文件中后就可以将爬取到的数据存储到 MySQL 数据库了，这里方便起见直接将 SQL 语句写在了

process_item() 方法中，实际开发中最好将 SQL 语句封装进方法，然后再封装其专门的 Item 类中，这样我们的处理方法就可以根据传递

过来的不同 Item 调用不同的 SQL 语句，可以极大的提高程序的扩展性和我们
 爬虫代码
 的可重用性。

##### 4. 实现 MySQL 存储的异步操作

上面的 Pipeline 类虽然可以将数据写在 MySQL 数据中，但是在 Scrapy 对数据的处理是同步执行的，当爬取数据量很大的时候，会出现插入数据的速度跟不上网页的爬取解析速度，造成阻塞，为了解决这个问题需要将 MySQL 的数据存储异步化。Python 中提供了 Twisted 框架来实现异步操作，该框架提供了一个连接池，通过连接池可以实现数据插入 MySQL 的异步化。

下面是集合 Twisted 框架实现的 Pipeline 类，可以完成 MySQL 的异步化操作：

这里使用的是 pymysql 模块，在初始化 Pipeline 的时候，通过参数创建数据库连接池 dbpool,

然后在 process_item 方法中来对连接池进行配置，执行其执行方法和数据。这里我们没有写出上面例子中出现的 SQL 语句，而是将其封装到了具体的 Item类中，这样我们的 Pipeline 类可以处理各种不同的数据。

```
import pymysql
from twisted.enterprise import adbapi
class MysqlTwistedPipline(object):
    def __init__(self, ):
        dbparms = dict(
            host='localhost',
            db='stack_db',
            user='root',
            passwd='root',
            charset='utf8',
            cursorclass=pymysql.cursors.DictCursor, # 指定 curosr 类型
            use_unicode=True,
        )
        # 指定擦做数据库的模块名和数据库参数参数
        self.dbpool = adbapi.ConnectionPool("pymysql", **dbparms)

    # 使用twisted将mysql插入变成异步执行
    def process_item(self, item, spider):
        # 指定操作方法和操作的数据
        query = self.dbpool.runInteraction(self.do_insert, item)
        # 指定异常处理方法
        query.addErrback(self.handle_error, item, spider) #处理异常

    def handle_error(self, failure, item, spider):
        #处理异步插入的异常
        print (failure)

    def do_insert(self, cursor, item):
        #执行具体的插入
        #根据不同的item 构建不同的sql语句并插入到mysql中
        insert_sql, params = item.get_insert_sql()
        cursor.execute(insert_sql, params)
```

QuestionItem 中的 get_insert_sql() 方法代码如下：

```
 def get_insert_sql(self):
      insert_sql = """
                 insert into stack_questions(title, votes, answers, views,tags)
                 VALUES (%s, %s, %s, %s,%s);
             """
      params = (self["question_title"], self["question_votes"], self["question_answers"], self["question_views"],self["tags"])
      return insert_sql,params
```

##### 5. 使用 Scrapy 自带的 ImagesPipeline 保存图片

上面基本都是我们自定义的 Pipeline 类来操作数据的，现在简要介绍一下 Scrapy 提供的一个 Pipeline 类 — ImagesPipeline。

通过执行该类然后进行配置，可以在爬取的同时自动将
 图片数据
 保存到本地，下面简要介绍其用法：

- 配置 settings 文件

在 ITEM_PIPELINES 中配置

```
ITEM_PIPELINES = {
  'scrapy.pipelines.images.ImagesPipeline': 1,
}
```

- 配置保存的字段和本地路径

因为我们的数据都是封装在 Item 类里面的，因此配置完 ImagesPipeline 类后要做的就是让该类知道应该保存哪个字段的数据以及保存到何处。

需要在 settings 中配置如下变量：

```
# 要保存的字段，即在 Item 类中的字段名为 image_url
IMAGES_URLS_FIELD = 'image_url'

import os
# 配置数据保存路径，为当前工程目录下的 images 目录中
project_dir = os.path.abspath(os.path.dirname(__file__))
IMAGES_STORE = os.path.join(project_dir, 'images')

# 设置图片的最大最小值
# IMAGES_MIN_HEIGHT = 100
# IMAGES_MIN_WIDTH = 100
```

- 在传递参数时传递数组

ImagesPipeline 要求传递数据必须是以数据形式的，否则会报错

```Python
item_loader.add_value("image_url", [image_url])
```

经过上面三步再次爬取时，如果爬取的内容有图片数据，就可以按照上面的步骤将图片进行下载了。

以上介绍了比较常用的 Pipeline 类的用法，Scrapy 还提供了更多的自带 Pipeline 类，有兴趣的同学可以参阅文档继续深入学习。

现在关于 Scrapy 的所有操作已经基本完成了，从爬虫的创建、爬取解析、Item 封装到 Pipeline 保存都已经讲解完毕。
