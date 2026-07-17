---
title: "Jenkins 使用简记"
date: 2020-01-03T18:56:47+08:00
tags:
  - Jenkins
  - DevOps
categories:
  - 软件工程
source: "https://blog.csdn.net/Ahri_J/article/details/103825358"
---
最近用 Jenkins 将原来公司自研的 CICD 工具给替换掉了， Jenkins 本身的文档并不是很明晰，很多问题都需要自己尝试和搜索才能解决，这里简要记录下期间遇到的一些问题的解决方法。

#### 一. 安装启动 Jenkins

##### 1. 安装 Java

```
sudo apt update
sudo apt install openjdk-8-jdk
```

##### 2. 添加密钥与仓库

```
wget -q -O - https://pkg.jenkins.io/debian/jenkins.io.key | sudo apt-key add -

sudo sh -c 'echo deb http://pkg.jenkins.io/debian-stable binary/ > /etc/apt/sources.list.d/jenkins.list'
```

##### 3. 安装 Jenkins

```
sudo apt update
sudo apt install jenkins
```

安装完成后通过 systemctl 命令可以查看状态

```
$ systemctl status jenkins
● jenkins.service - LSB: Start Jenkins at boot time
Loaded: loaded (/etc/init.d/jenkins; generated)
Active: active (exited) since Wed 2018-08-22 13:03:08 PDT; 2min 16s ago
    Docs: man:systemd-sysv-generator(8)
    Tasks: 0 (limit: 2319)
CGroup: /system.slice/jenkins.service
```

##### 4. 修改相关配置

通过 apt-get 安装启动后， Jenkins 工作目录如下：

- `/etc/default/jenkins`: 配置文件地址
- `/var/lib/jenkins` : Jenkins 工作目录
- `/var/cache/jenkins` : Jenkins 缓存目录
- `/var/log/jenkins` : Jenkins 日志目录

打开 `/etc/default/jenkins` 文件可以针对我们的要求对相应的配置进行设置，我最常改的设置有两个：

***修改端口***

```
# 默认是 8080，我这里改成了 8081
HTTP_PORT=8081
```

***修改用户和用户组***

Jenkins 启动时会创建名为 `jenkins` 的用户名和用户组，这是 Jenkins 默认执行命令的用户，如果采用默认的用户，执行某些操作时可能会报没有权限的问题，因此建议改成自己常用的 user，比如我最常用的用户是 `ubuntu`，修改如下：

```
# 默认是 jenkins
JENKINS_USER  = ubuntu
JENKINS_GROUP = ubuntu
```

启动之前将 Jenkins 的各个目录所属用户和组进行修改，如下：

```shell
chown -R ubuntu:ubuntu /var/lib/jenkins
chown -R ubuntu:ubuntu /var/cache/jenkins
chown -R ubuntu:ubuntu /var/log/jenkins
```

修改完重启 Jenkins 之后就可以通过 http://server_ip:8081 进行访问了，第一次访问会要求输入管理员密码，该密码会在 Jenkins 第一次启动时打印到日志中，从日志中复制出来填入即可。

![](https://pub-08b57ed9c8ce4fadab4077a9d577e857.r2.dev/csdn-2b9e586b9a91303b5cd0f6d355fec78c70d6c353184c0d20f598fa78418c4c02.png)

![](https://pub-08b57ed9c8ce4fadab4077a9d577e857.r2.dev/csdn-b97f0bb3752269b754c2e7cdab6adfd4a74ce56ca3d9b75c0eec1b2b8740dae7.png)

初次访问一般会提示安装插件，选择安装默认插件即可。

#### 二. 参数与环境变量的定义

##### 1. 定义环境变量

Jenkins pipeline 允许我们定义全局或者 stage 范围的环境变量，定义好通过 env.name 访问即可，对于一些需要在整个 pipeline 中用到的信息，可以考虑用环境变量进行定义，示例如下：

```
pipeline {
    agent any

    environment {
        GLOBAL_ENV = 'global'
    }

    stages {
        stage('Build') {
            environment {
                STAGE_ENV = "stage"
            }
            steps {
                echo "${env.GLOBAL_ENV}"
                echo "${env.stage}"

            }
        }
    }
}
```

##### 2. 定义参数

对于一些动态的内容，可以考虑采用参数的形式，Jenkins pipeline 定义参数有两种形式：

- ***Jenkins 管理界面定义***
- ***pipeline 代码定义***

###### 【1】Jenkins 界面设置参数

首先可以在 Jenkins 的 Job 配置界面进行参数化构建，选择对应类型的参数，填入参数名、默认值和描述即可，如图：

![](https://pub-08b57ed9c8ce4fadab4077a9d577e857.r2.dev/csdn-4a43cab8ee38f494f2b2f6c49ae4edd64be8d20931a7f35a5c0faf8dc1a814f3.png)

###### 【2】pipeline 内定义参数

Jenkins 提供了 `parameters` 块来定义参数，官方文档示例如下，定义了 `string` 类型的 `PERSON` 参数，并设置了默认值为 `Mr Jenkins`，然后通过 `${params.PERSON}` 即可访问。

```
Jenkinsfile (Declarative Pipeline)
pipeline {
    agent any
    parameters {
        string(name: 'PERSON', defaultValue: 'Mr Jenkins', description: 'Who should I say hello to?')
    }
    stages {
        stage('Example') {
            steps {
                echo "Hello ${params.PERSON}"
            }
        }
    }
}
```

###### 【3】参数覆盖问题

在 pipeline 中定义的参数，会自动同步到 Jenkins Job 配置界面中显示，如果一个参数同时在配置界面和 pipeline 中进行了定义，那么 pipeline 中定义的默认值会覆盖掉在 Jenkins Job 设置界面设定的值。

理想的方式是在 pipeline 中通过 `parameters` 定义参数并设置默认值，如果在 Jenkins Job 中没有显式配置参数，则使用默认值，如果进行了显式配置，则使用配置的值，可以通过三元运算符解决这个问题，示例如下：

```
Jenkinsfile (Declarative Pipeline)
pipeline {
    agent any
    parameters {
        string(name: 'PERSON', defaultValue: params.PERSION ?:'Mr Jenkins', description: 'Who should I say hello to?')
    }
    stages {
        stage('Example') {
            steps {
                echo "Hello ${params.PERSON}"
            }
        }
    }
}
```

这样每次定义参数前都先判断一下是否已经传递了参数值了，如果已经传递，则参数的值就是传递过来的值，如果没有则采用默认值。

#### 三. Github
 Push
 与 Github PR 触发任务

##### 1. Github 设置 webhook

首先需要在 Github 对应的仓库中配置 webhook，地址是 https://jenkins_addr/github-webhook/，

![](https://pub-08b57ed9c8ce4fadab4077a9d577e857.r2.dev/csdn-65d15fb3f6fccfbbba1476e4cd7d79a1764726803dcb70f258eb07644e6b10a5.png)

然后选择需要发送请求的事件，我需要在代码 Push 和提交 PR 的时候触发 pipeline 执行，因此勾选了下面两个：

![](https://pub-08b57ed9c8ce4fadab4077a9d577e857.r2.dev/csdn-75bdcd14c49bd2ab39a2a454875c552f63b60a41a3cf7a6d42ad90bf76d75321.png)

这样在仓库有代码 Push 和 PR 操作的时候就会向我们的 hook 地址发送请求了，每次发送都会在 webhook 下面生成记录，如图所示：

![](https://pub-08b57ed9c8ce4fadab4077a9d577e857.r2.dev/csdn-8207124d5539833ee42e2dbdfc5d01d59377d6b4387f9b9ade5f5e8dc1194780.png)

可以在这里手动重新发送便于测试。

##### 2. Jenkins 创建 pipeline 设置项目地址

首先在 Jenkins 中创建 pipeline，然后在 Github 项目中填入地址，用于标识该 pipeline 监听的项目，如图：

![](https://pub-08b57ed9c8ce4fadab4077a9d577e857.r2.dev/csdn-d2f09eaa97562d2b7cfc649aa1c6b5f12abd09e6ea4829f745a9b708ad03cff8.png)

##### 3. Github Push 触发

Github Push 的触发需要安装 `Github plugin` 插件，然后在 Job 的 `Build Trigger` 中勾选 `GitHub hook trigger for GITScm polling` 即可，如图：
 ![](https://pub-08b57ed9c8ce4fadab4077a9d577e857.r2.dev/csdn-105040d728b8ca845cec7126cf21478415b2f3638d9d19bf46721eb447b7ea66.png)

为了保证触发，项目中必须已经添加了 Jenkinsfile 文件，并在 Job 中指定，如图所示，设置分支和 Jenkinsfile 路径，该 Job 就会监听对应分支的 Github Push 事件。

![](https://pub-08b57ed9c8ce4fadab4077a9d577e857.r2.dev/csdn-1aa2de0b0226c1dc3da1bd2af083a79827f887d35e3c213fa7b2689918277c5d.png)

***注意事项***

- 我们必须先手动执行一次任务，后续才可以通过 Github Push 触发。

##### 2. Github PR 触发

PR 的触发需要使用 `GitHub Integration Plugin` 插件，安装后在 Job 的 Build Trigger 就会有对应的选项，如下：

![](https://pub-08b57ed9c8ce4fadab4077a9d577e857.r2.dev/csdn-dbf5ac878291314e12aceb0eee0d3521c2e348ff3228739ae9771f5777fd8822.png)

可以看到有四种触发的方式，这里选择了 hook 触发，然后在下面选择要监听的事件，这里选择了 打开、关闭 PR 以及 PR 中的 commit 发生变化时执行触发。

除了在 Job 中配置 PR 触发之外，还需要在 `Manage Jenkins -> Configure System -> Github Server` 配置
 Server
，如图

![](https://pub-08b57ed9c8ce4fadab4077a9d577e857.r2.dev/csdn-5e8267822a60bda5fdfd3e50d1e19a53bd9091d579b061357024e6cfe0674886.png)

Name 可以自定义，API URL 填写默认的 `https://api.github.com` 即可，
 token
 填写在 Github 中生成的 token，这里有两点要求：

- 生成 token 的成员必须对仓库有 admin 权限
- 选中 `admin:repo_hook` 选项

#### 四. 接入 SonarQube 代码检测

Jenkins 可以通过接入 [SonarQube](https://www.sonarqube.org/) 在 CI/CD 过程中执行代码检测并将结果传送到 SonarQube Server 中，具体步骤如下：

##### 1. 安装插件

Jenkins 需要先安装 `SonarQube Scanner for Jenkins` 插件，在 `Manage Jenkins -> Plugin Manager` 下搜索安装即可：

![](https://pub-08b57ed9c8ce4fadab4077a9d577e857.r2.dev/csdn-79c04d92fcb2cd16e2e09fab8ea9bfcce508bbed47aa4965c965a9107a6a062a.png)

##### 2. 部署并配置 SonarServer

参考官方文档 [Get Started in Two Minutes Guide](https://docs.sonarqube.org/latest/setup/get-started-2-minutes/) 即可，这里不再赘述。
 安装完成后就可以在 Jenkins 中配置 SonarQube Server 的地址了，需要用到 token 进行验证，点击 SonarQube 的用户信息，在安全配置下生成对应的 token 复制即可，如图：

![](https://pub-08b57ed9c8ce4fadab4077a9d577e857.r2.dev/csdn-d21645177aafe76e9cb9242e1132ff725cbe8ceaf43f90cac689efc30bc5f60c.png)

完成 SonarServer 的 安装和 token 生成后，在 `Manage Jenkins -> Configure System ->SonarQube servers（只有安装 SonarQube Scanner for Jenkins 插件后才会有该配置项）` 中设置 Server 地址，如下：

![](https://pub-08b57ed9c8ce4fadab4077a9d577e857.r2.dev/csdn-9b477894da640638e357f49848da763cc97f3a95cbb8ebfc360f7ef4c8d0556a.png)

- Name 是自定义的标识名称
- Server_URL 和 token 就是我们部署的 server 地址和上面生成的 token 了，填上后保存即可。

##### 3. 安装并配置 SonarScanner

首先要下载安装 SonarScanner，Linux 下载地址是 [sonar-scanner-cli-4.2.0.1873-linux.zip](https://binaries.sonarsource.com/Distribution/sonar-scanner-cli/sonar-scanner-cli-4.2.0.1873-linux.zip)，下载完成解压后放到对应的目录即可，比如我放到了 `/opt/sonar_scanner` 下。

```
➜  ~  |> mv sonar-scanner-4.2.0.1873-linux /opt/sonar_scanner
```

下载完成后在 `Manage Jenkins -> Global Tool Configuration -> SonarQube Scanner` 下配置，因为我是安装在本地，直接配置工作目录，取好对应的名字即可，如下：

![](https://pub-08b57ed9c8ce4fadab4077a9d577e857.r2.dev/csdn-d828ec8a29cc8fed683b3ee3fafaf0083dc293525026f393b4550ecaee986999.png)

##### 4. 执行代码质量检测

Jenkins 提供了 [withSonarQubeEnv](https://jenkins.io/doc/pipeline/steps/sonar/#withsonarqubeenv-prepare-sonarqube-scanner-environment) 块来执行代码检测。关于 Jenkins 的使用在 SonarQube 中有专门的文档[SonarScanner for Jenkins](https://docs.sonarqube.org/latest/analysis/scan/sonarscanner-for-jenkins/) 介绍，还算详细，参考文档照着做就行，这里只简单给两个示例：

###### 【1】分析 Maven 项目

对于 Maven 项目可以直接通过 mvn 命令执行，如下：

```groovy
pipeline {
    agent any
    stages {
        stage('Sonar') {
            steps {
                script {
                    # 填入 SonarQube servers 中配置的名称，检测完成后就会自动发送到 SonarQube Server 中。
                    withSonarQubeEnv('server name'){
                        sh "mvn clean verify sonar:sonar -DskipTests"
                    }
                }
            }
        }
    }
}
```

***sonar scanner 指定参数执行***

上面是 Maven 项目的执行方式，还有更通用的是使用 `sonar-scanner` 命令指定参数执行，

```groovy
pipeline {
    agent any
    stages {
        stage('Sonar') {
            steps {
                script {
                    # 填入 SonarQube servers 中配置的名称，检测完成后就会自动发送到 SonarQube Server 中。
                    withSonarQubeEnv('server name'){
                        sh "${scannerHome}/bin/sonar-scanner -Dsonar.projectKey=${PROJECT_NAME} -Dsonar.projectName=${PROJECT_NAME} -Dsonar.projectVersion=1.0 -Dsonar.projectBaseDir=${PROJECT_DIR} -Dsonar.sources=src  -Dsonar.sourceEncoding=UTF-8"
                    }
                }
            }
        }
    }
}
```

`sonar-scanner` 命令通过 -D 传递参数，具体如下：

- sonar.projectKey：项目 key
- sonar.projectName： 项目名称
- sonar.projectBaseDir： 项目目录
- sonar.projectVersion： 项目版本
- sonar.sources： 源代码目录
- sonar.sourceEncoding：编码方式

除此之外还可以将配置写入到一个 `myproject.properties`文件中，然后指定文件进行分析即可：

```groovy
pipeline {
    agent any
    stages {
        stage('Sonar') {
            steps {
                script {
                    withSonarQubeEnv('server name'){
                        sh "${scannerHome}/bin/sonar-scanner  -Dproject.settings=../myproject.properties
                    }
                }
            }
        }
    }
}
```

#### 五. 读取 Yaml/Json 文件内容

在执行 CICD 时，有些环境、项目相关的配置我们可能会以 Yaml、Json 配置文件的形式进行管理，Jenkins 需要读取到对应的配置进行解析，可以通过 [pipeline-utility-steps-plugin](https://github.com/jenkinsci/pipeline-utility-steps-plugin/blob/master/docs/STEPS.md) 插件实现，该插件提供了很多有用的功能，比如读写 Yaml、Json、Jar Manifest、Java Properties、CSV 文件、zip 解压缩文件等功能。这里仅简单介绍下读取 Yaml 、Json 文件的使用方式。

文件内容简单如下：

```yml
project:
  name: test
  dockerFilePath: rootfs/Dockerfile
  config:
    port: 8000
```

```json
{
    "project": {
        "name": "test",
        "dockerFilePath": "rootfs/Dockerfile",
        "config": {
            "port": 8000
        }
    }
}
```

插件提供的读取方式非常简单，直接调用插件中的 readYaml 和 readJSON 方法即可。Pipeline 中使用方式如下：

```
pipeline {
   agent any

   stages {
      stage('Read Yaml') {
         steps {
             script {
                yaml_datas = readYaml file: "/home/ubuntu/backdemo/test.yaml"

                echo "${yaml_datas}"
                echo "${yaml_datas.project}"
                echo "${yaml_datas.project.name}"
                echo "${yaml_datas.project.config}"
             }
         }
      }
       stage('Read Json') {
         steps {
             script {
                json_datas = readJSON file: "/home/ubuntu/backdemo/test.json"

                echo "${json_datas}"
                echo "${json_datas.project}"
                echo "${json_datas.project.name}"
                echo "${json_datas.project.config}"
             }
         }
      }
   }
}
```

读取内容赋值给变量，其实还是一个字典对象，可以通过 key 读取到对应的值，上述 Pipeline 执行结果打印如下：

![](https://pub-08b57ed9c8ce4fadab4077a9d577e857.r2.dev/csdn-1329ffca360655658cf10aa108c2ed2a4ec12e91aaf0373504fe2844e000f993.png)

#### 六. 创建共享库封装通用代码

在使用 Jenkins 执行 CICD 过程中，很多步骤和操作都是重复的。对于重复的步骤，如果在每个项目的 Jenkinsfile 里面都写一遍的话，维护起来就太麻烦了。Jenkins 提供了 [共享库](https://jenkins.io/doc/book/pipeline/shared-libraries/) 的方式使我们可以将 pipeline、通用代码、配置文件等抽取到一个项目中，然后配置引用即可。

##### 1. Shared Libraries 简介

Jenkins 共享库是一个用 Groovy 编写的项目，结构如下：

***Project structure***

```
// 引用自官方文档
+- src                     # Groovy source files
|   +- org
|       +- foo
|           +- Bar.groovy  # for org.foo.Bar class
+- vars
|   +- foo.groovy          # for global 'foo' variable
|   +- foo.txt             # help for 'foo' variable
+- resources               # resource files (external libraries only)
|   +- org
|       +- foo
|           +- bar.json    # static helper data for org.foo.Bar
```

可以看到项目有三个目录：

- `src`: 和标准 Java 项目一样，src 下的定义的类将会在执行时加入到 classpath 中。
- `vars`: 该目录用于创建一些脚本，一些通用的方法可以放在这里直接引用。
- `resources`: 主要放置一些非 Groovy 类型的文件，比如 Json 文件。

下面看一些编写共享库的示例：

***创建类***

```groovy
// src/com.ahri/Foo.groovy
package com.ahri

class Foo {

    String getName() {
        return  "This is Foo class";
    }
}
```

***编写脚本,封装通用方法***

```groovy
// vars/utils.groovy

def info(message) {
    echo "INFO: ${message}"
}
```

***封装 pipeline***

```groovy
//vars/deploy-pipelne.groovy
def call() {
    pipeline {
        agent any
    }

    stages {
        stage ("First Stage"){
            steps {
                echo "This is First Stage"
            }
        }

        stage ("Second Stage"){
            steps {
                echo "This is Second Stage"
            }
        }
    }
}
```

***封装配置文件***

```json
// resources/config.json
{
  "Config": {
    "host": "127.0.0.1",
    "port": 8080,
    "minio": {
      "name": "TestProject",
      "user": "Ahri",
      "passwd": "1234"
    }
  }
}
```

##### 2. 使用简介

###### 【1】Jenkins 配置

- `Manager Jenkins` -> `Configure System` -> `Global Pipeline Libraries`

![image](https://pub-08b57ed9c8ce4fadab4077a9d577e857.r2.dev/csdn-54a8f56adfa9d79baff2fe3d8e1daa46296a3594da8d2bcb9763eb6c2469fbf6.png)

##### 【2】引入类

```
@Library("JenkinsHelper")
import com.ahri.Foo
pipeline {
   agent any

   stages {
      stage('Hello') {
         steps {
            echo 'Hello World'
            script {
                Foo foo = new Foo()
                def name = foo.getName()
                echo "${name}"
            }
         }
      }
   }
}
```

##### 【3】使用脚本方法

```
@Library("JenkinsHelper")
import com.ahri.Foo
pipeline {
   agent any

   stages {
      stage('Hello') {
         steps {
            echo 'Hello World'
            script {
                Foo foo = new Foo()
                def name = foo.getName()
                echo "${name}"
                utils.info("This is utils info")
            }
         }
      }
   }
}
```

##### 【5】Jenkinsfile 引用 pipeline

```
// Jenkinsfile
@Library(value='JenkinsHelper', changelog=false) _
deploy-pipeline()
```

##### 【6】加载 json

对于 resources 中的文件，Jenkins 可以通过 `libraryResource` 关键字直接读取，然后我们根据需要进行转换即可，下面是对 config.json 文件的解析示例：

```groovy
import groovy.json.JsonSlurper

def loadJson() {
    // 读取文件内容
    def config_text = libraryResource 'config.json'

    // 转为 json 对象
    def jsonSlurper = new JsonSlurper()
    def config_object = jsonSlurper.parseText(config_text)

    // 操作对象，读取配置
    echo "${config_object}"
    echo "${config_object.config.minio}"
    echo "${config_object.config.minio.name}"

}
```

上面就是遇到的一些使用场景的简单总结，欢迎交流。
