---
title: Openssl & Keytool 自签名证书命令备忘
date: 2024-11-25T10:43:20+08:00
tags:
  - TLS
categories:
  - TLS
draft: true
---
之前工作中经常遇到 TLS 证书配置的情况，比如 Kafka 的 SALA + TLS 安全配置，ES 的 TLS 配置等。通常这些场景下使用自签名证书就足够了。

这里对这些常用的命令做记录备忘，方便后续使用。

首先，我们需要生成 CA 的密钥和证书。命令如下：

```bash
openssl req -new -x509 -keyout ca-key -out ca-cert -days 3650
```

参数说明：
- `-new`：生成一个新的证书请求
- `-x509`：生成一个自签名证书
- `-keyout`：指定输出 CA 密钥的文件名
- `-out`：指定输出 CA 证书的文件名
- `-days`：指定证书的有效期（天）

然后我们就可以生成服务的私钥并签发证书了。

  - 生成私钥

```bash
openssl genpkey -algorithm RSA -aes256 -out server-key.pem
```


### 1. 生成 CA 的密钥和证书
```bash
openssl req -new -x509 -keyout ca-key -out ca-cert -days 3650
```
参数说明：
- `-new`：生成一个新的证书请求
- `-x509`：生成一个自签名证书
- `-keyout`：指定输出 CA 密钥的文件名
- `-out`：指定输出 CA 证书的文件名
- `-days`：指定证书的有效期（天）


### 2. 生成服务密钥库和密钥对


```bash
keytool -keystore kafka.server.keystore.jks -alias kafka_server -validity 3650 -genkey -keyalg RSA -storepass spirit-2426GPU -keypass spirit-2426GPU

# 为服务器证书生成证书签名请求（CSR）
keytool -keystore kafka.server.keystore.jks -alias kafka_server -certreq -file kafka_server.csr -storepass spirit-2426GPU

# 使用 CA 签署服务器的 CSR
openssl x509 -req -CA ca-cert -CAkey ca-key -in kafka_server.csr -out kafka_server-signed.crt -days 3650 -CAcreateserial -passin pass:spirit-2426GPU

# 将 CA 证书导入服务器密钥库
keytool -keystore kafka.server.keystore.jks -alias kafka_ca -import -file ca-cert -storepass spirit-2426GPU

# 将签名后的服务器证书导入服务器密钥库
keytool -keystore kafka.server.keystore.jks -alias kafka_server -import -file kafka_server-signed.crt -storepass spirit-2426GPU

# 创建服务器信任库并导入 CA 证书
keytool -keystore kafka.server.truststore.jks -alias kafka_ca -import -file ca-cert -storepass spirit-1024Serverless