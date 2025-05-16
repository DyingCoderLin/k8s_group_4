# minik8使用指南：

## docker python api

https://docker-py.readthedocs.io/en/stable/networks.html


## 首先需要启动etcd和kafka两个docker
### etcd一键安装
```docker
docker run -d \
  --name etcd \
  -p 2379:2379 \
  -p 2380:2380 \
  quay.io/coreos/etcd:v3.5.0 \
  /usr/local/bin/etcd \
  --listen-client-urls http://0.0.0.0:2379 \
  --advertise-client-urls http://localhost:2379
```

### kafka一键安装
打开代理将无法访问远端kafka
- 下面为docker-compose.yml文件
  ```
  version: '3'
  services:
    zookeeper:
      image: bitnami/zookeeper:3.9.0
      container_name: zookeeper
      ports:
        - 2181:2181
      environment:
        # 时区
        - TZ=Asia/Shanghai
        # 允许匿名登录
        - ALLOW_ANONYMOUS_LOGIN=yes
        # zk在集群中的序号（1~255）
        - ZOO_SERVER_ID=1
        # 端口
        - ZOO_PORT_NUMBER=2181
      volumes:
        - ./zookeeper:/bitnami/zookeeper
    kafka:
      image: bitnami/kafka:3.9.0
      container_name: kafka
      ports:
        - 9092:9092
      environment:
        - TZ=Asia/Shanghai
        # broker id>=0
        - KAFKA_BROKER_ID=0
        # kk配置zk连接
        - KAFKA_CFG_ZOOKEEPER_CONNECT=zookeeper:2181
        # 允许使用PLAINTEXT协议
        - ALLOW_PLAINTEXT_LISTENER=yes
        # kk配置监听器
        - KAFKA_CFG_LISTENERS=PLAINTEXT://:9092
        # kk配置发布到zk的监听器 要公网访问需要配置公网ip 可以配置私网公网分流
        - KAFKA_CFG_ADVERTISED_LISTENERS=PLAINTEXT://47.103.11.77:9092
      volumes:
        - ./kafka/data:/bitnami/kafka/data
      depends_on:
        - zookeeper
    kafka-manager:
      image: sheepkiller/kafka-manager:stable
      container_name: kafka-manager
      ports:
        - 9000:9000
      environment:
        # zk地址
        - ZK_HOSTS=47.103.11.77:2181
        # 应用秘钥
        - APPLICATION_SECRET=xcrj_km_secret
        # km用户名
        - KAFKA_MANAGER_USERNAME=xcrj_kkm_user
        # km密码
        - KAFKA_MANAGER_PASSWORD=xcrj_kkm_pwd
      depends_on:
        - kafka
  ```
- 使用方式：
  ```
  vim docker-compose.yml # 然后把文件粘贴进去
  mkdir ./zookeeper ./kafka
  sudo chown -R 1001:1001 ./zookeeper
  sudo chown -R 1001:1001 ./kafka
  sudo docker-compose up -d
  ```
- 此时kafka和zookeeper都正常启动
    - 可使用docker ps -a查看运行情况

## 运行环境创建
- 创建虚拟环境（也可以选择在本机上直接运行）并配置python包
  ```
  conda create -n k8s python=3.12
  pip install -r requirements.txt
  ```

- 如果在一台新机器上，创建overlay网络需要Docker Swarm运行中
  ```
  sudo docker swarm init
  ```

