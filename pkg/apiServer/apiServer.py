import json
import pickle
import docker
import random
import requests
import os
from readerwriterlock import rwlock
from docker.errors import APIError
from flask import Flask, request
from confluent_kafka import Producer, KafkaException
from confluent_kafka.admin import AdminClient, NewTopic
import platform
from time import time, sleep, ctime
from threading import Thread

from pkg.utils.atomicCounter import AtomicCounter
from pkg.apiObject.pod import STATUS as POD_STATUS
from pkg.apiObject.node import Node, STATUS as NODE_STATUS
from pkg.apiObject.function import Function
from pkg.apiServer.etcd import Etcd
from pkg.controller.scheduler import Scheduler
from pkg.apiObject.workflow import Workflow

from pkg.config.uriConfig import URIConfig
from pkg.config.etcdConfig import EtcdConfig
from pkg.config.kafkaConfig import KafkaConfig
from pkg.config.nodeConfig import NodeConfig
from pkg.config.podConfig import PodConfig
from pkg.config.replicaSetConfig import ReplicaSetConfig
from pkg.config.hpaConfig import HorizontalPodAutoscalerConfig
from pkg.config.serviceConfig import ServiceConfig
from pkg.config.dnsConfig import DNSConfig
from pkg.config.serverlessConfig import ServerlessConfig
from pkg.config.functionConfig import FunctionConfig
from pkg.config.workflowConfig import WorkflowConfig

class ApiServer:
    def __init__(
        self, uri_config: URIConfig, etcd_config: EtcdConfig, kafka_config: KafkaConfig, serverless_config: ServerlessConfig
    ):
        print("[INFO]ApiServer starting...")
        self.uri_config = uri_config
        self.etcd_config = etcd_config
        self.kafka_config = kafka_config
        self.serverless_config = serverless_config
        self.NODE_TIMEOUT = 10

        # 创建 Flask 应用实例，用于提供 HTTP API 服务
        self.app = Flask(__name__)
        # 创建 etcd 客户端，连接到指定的主机和端口
        self.etcd = Etcd(host=etcd_config.HOST, port=etcd_config.PORT)

        # 根据操作系统（Windows 或类 Unix 系统）初始化 Docker 客户端，用于管理容器
        if platform.system() == "Windows":
            self.docker = docker.DockerClient(
                base_url="npipe:////./pipe/docker_engine", version="1.25", timeout=5
            )
        else:
            self.docker = docker.DockerClient(
                base_url="unix://var/run/docker.sock", version="1.25", timeout=5
            )
        
        # 创建调度器实例，负责 Pod 的调度和管理
        self.kafka = AdminClient({"bootstrap.servers": kafka_config.BOOTSTRAP_SERVER})
        self.kafka_producer = Producer(
            {"bootstrap.servers": kafka_config.BOOTSTRAP_SERVER}
        )

        # --- 调试时使用 ---
        self.etcd.reset()
        self.kafka.delete_topics(
            [self.kafka_config.SCHEDULER_TOPIC], operation_timeout=10
        )
        self.kafka_producer.flush()
        # --- end ---

        os.makedirs(serverless_config.PERSIST_BASE, exist_ok = True)
        self.SLlock = rwlock.RWLockFair()
        self.func_cnt = AtomicCounter()

        self.bind(uri_config)
        print("[INFO]ApiServer init success.")

    
    # 配置 Flask 应用的路由表
    def bind(self, config):
        self.app.route("/", methods=["GET"])(self.index)

        # node相关
        # 注册一个新Node
        self.app.route(config.NODE_SPEC_URL, methods=["POST"])(self.add_node)
        # 获得集群全部Node
        self.app.route(config.NODES_URL, methods=['GET'])(self.get_nodes)
        # 更新Node信息，结点心跳
        self.app.route(config.NODE_SPEC_URL, methods=['PUT'])(self.update_node)
        # 获得结点上所有Pod信息
        self.app.route(config.NODE_ALL_PODS_URL, methods=['GET'])(self.get_node_pods)

        # scheduler相关
        self.app.route(config.SCHEDULER_URL, methods=["POST"])(self.add_scheduler)
        self.app.route(config.SCHEDULER_POD_URL, methods=["PUT"])(self.bind_pod)

        # pod相关
        # 获取全部Pod信息
        self.app.route(config.GLOBAL_PODS_URL, methods=["GET"])(self.get_global_pods)
        self.app.route(config.PODS_URL, methods=["GET"])(self.get_pods)
        # 指定的Pod增删改查
        self.app.route(config.POD_SPEC_URL, methods=["GET"])(self.get_pod)
        self.app.route(config.POD_SPEC_URL, methods=["POST"])(self.add_pod)
        self.app.route(config.POD_SPEC_URL, methods=["PUT"])(self.update_pod)
        self.app.route(config.POD_SPEC_URL, methods=["DELETE"])(self.delete_pod)
        # 指定Pod状态改和查
        self.app.route(config.POD_SPEC_STATUS_URL, methods=["GET"])(self.get_pod_status)
        self.app.route(config.POD_SPEC_STATUS_URL, methods=["PUT"])(self.update_pod_status)
        self.app.route(config.POD_SPEC_IP_URL, methods=["PUT"])(self.update_pod_subnet_ip)
        self.app.route(config.POD_SPEC_IP_URL, methods=["GET"])(self.get_pod_subnet_ip)

        # replicaSet相关
        # 三种不同的读取逻辑，可以先不着急写，读取全部的rs，读取某个namespace下的rs，读取某个rs
        self.app.route(config.GLOBAL_REPLICA_SETS_URL, methods=["GET"])(self.get_global_replica_sets)
        # 这个有确定的namespace
        self.app.route(config.REPLICA_SETS_URL, methods=["GET"])(self.get_replica_sets)
        # 这个有确定的namespace和name
        self.app.route(config.REPLICA_SET_SPEC_URL, methods=["GET"])(self.get_replica_set)
        # 创建rs
        self.app.route(config.REPLICA_SET_SPEC_URL, methods=["POST"])(self.create_replica_set)
        # 更新rs
        self.app.route(config.REPLICA_SET_SPEC_URL, methods=["PUT"])(self.update_replica_set)
        # 删除rs
        self.app.route(config.REPLICA_SET_SPEC_URL, methods=["DELETE"])(self.delete_replica_set)

        # hpa相关
        # 三种不同的读取逻辑，可以先不着急写，读取全部的hpa，读取某个namespace下的hpa，读取某个hpa
        self.app.route(config.GLOBAL_HPA_URL, methods=["GET"])(self.get_global_hpas)
        self.app.route(config.HPA_URL, methods=["GET"])(self.get_hpas)
        self.app.route(config.HPA_SPEC_URL, methods=["GET"])(self.get_hpa)
        # 创建hpa
        self.app.route(config.HPA_SPEC_URL, methods=["POST"])(self.create_hpa)
        # 更新hpa
        self.app.route(config.HPA_SPEC_URL, methods=["PUT"])(self.update_hpa)
        # 删除hpa
        self.app.route(config.HPA_SPEC_URL, methods=["DELETE"])(self.delete_hpa)

        # service相关
        # 获取全部Service和指定namespace下的Service
        self.app.route(config.GLOBAL_SERVICES_URL, methods=["GET"])(self.get_global_services)
        self.app.route(config.SERVICE_URL, methods=["GET"])(self.get_services)
        # 指定Service的增删改查
        self.app.route(config.SERVICE_SPEC_URL, methods=["GET"])(self.get_service)
        self.app.route(config.SERVICE_SPEC_URL, methods=["POST"])(self.create_service)
        self.app.route(config.SERVICE_SPEC_URL, methods=["PUT"])(self.update_service)
        self.app.route(config.SERVICE_SPEC_URL, methods=["DELETE"])(self.delete_service)
        # Service状态和统计信息
        self.app.route(config.SERVICE_SPEC_STATUS_URL, methods=["GET"])(self.get_service_status)

        # DNS 相关路由
        # 查找
        self.app.route(config.DNS_URL, methods=["GET"])(self.get_dns_list)
        self.app.route(config.DNS_SPEC_URL, methods=["GET"])(self.get_dns_spec)
        # 创建
        self.app.route(config.DNS_SPEC_URL, methods=["POST"])(self.create_dns)
        # 更新
        self.app.route(config.DNS_SPEC_URL, methods=["PUT"])(self.update_dns)
        # 删除
        self.app.route(config.DNS_SPEC_URL, methods=["DELETE"])(self.delete_dns)

        # function相关
        # 增删改查function
        self.app.route(config.FUNCTION_SPEC_URL, methods=['POST'])(self.add_function)
        self.app.route(config.FUNCTION_SPEC_URL, methods=['DELETE'])(self.delete_function)
        self.app.route(config.FUNCTION_SPEC_URL, methods=['PUT'])(self.update_function)
        self.app.route(config.FUNCTION_SPEC_URL, methods=['GET'])(self.get_function)
        self.app.route(config.GLOBAL_FUNCTIONS_URL, methods=['GET'])(self.get_functions)
        # 调用function
        self.app.route(config.FUNCTION_SPEC_URL, methods=['PATCH'])(self.exec_function)

        # workflow相关
        # 创建workflow
        self.app.route(config.WORKFLOW_SPEC_URL, methods=['POST'])(self.add_workflow)
        # 调用workflow
        self.app.route(config.WORKFLOW_SPEC_URL, methods=['PATCH'])(self.exec_workflow)



    def get_dns_list(self, namespace: str):
       """获取指定命名空间的 DNS 列表"""
       print(f"[INFO]Get DNS list in namespace {namespace}")
       try:
           key_prefix = self.etcd_config.DNS_KEY.format(namespace=namespace)
           DNSs = self.etcd.get_prefix(key_prefix)
           print(f"[DEBUG]Found DNS resources: {DNSs}")
           dns_list = []
           for value in DNSs:
                print(f"[DEBUG]Processing DNS resource: {value}")
                dns_list.append(value.to_dict())
           if not dns_list:
               return json.dumps({"message": f"No DNS resources found in namespace {namespace}"}), 200
           return json.dumps(dns_list), 200
       
       except Exception as e:
           print(f"[ERROR]Failed to get DNS list: {str(e)}")
           return json.dumps({"error": str(e)}), 500

    def get_dns_spec(self, namespace: str, name: str):
       """获取指定 DNS 配置"""
       print(f"[INFO]Get DNS {name} in namespace {namespace}")
       try:
           key = self.etcd_config.DNS_SPEC_KEY.format(namespace=namespace, name=name)
           dns = self.etcd.get(key)
           if dns is None:
               return json.dumps({"error": "DNS not found"}), 404
           return json.dumps(dns.to_dict()), 200
       except Exception as e:
           print(f"[ERROR]Failed to get DNS: {str(e)}")
           return json.dumps({"error": str(e)}), 500

    def create_dns(self, namespace: str, name: str):
       """创建 DNS 配置"""
       print(f"[INFO]Create DNS {name} in namespace {namespace}")
       try:
           dns_json = request.json
           
        #    # 验证 namespace 和 name 是否匹配
        #    if dns_json.get("metadata", {}).get("name") != name:
        #        return json.dumps({
        #            "error": "Name in URL does not match name in request body"
        #        }), 400
           
        #    if dns_json.get("metadata", {}).get("namespace", "default") != namespace:
        #        return json.dumps({
        #            "error": "Namespace in URL does not match namespace in request body"
        #        }), 400

           key = self.etcd_config.DNS_SPEC_KEY.format(namespace=namespace, name=name)
           
           # 检查 DNS 是否已存在
           existing_dns = self.etcd.get(key)
           if existing_dns is not None:
               return json.dumps({"error": "DNS already exists"}), 409

           # 创建 DNS 配置
           dns_config = DNSConfig(dns_json)

           # 保存到 etcd
           self.etcd.put(key, dns_config)

           print(f"[INFO]DNS {name} created successfully")
           return json.dumps({"message": f"DNS {name} created successfully"}), 200

       except Exception as e:
           print(f"[ERROR]Failed to create DNS: {str(e)}")
           return json.dumps({"error": str(e)}), 500

    def update_dns(self, namespace: str, name: str):
       """更新 DNS 配置"""
       print(f"[INFO]Update DNS {name} in namespace {namespace}")
       try:
           dns_json = request.json

           # 获取现有 DNS 配置
           key = self.etcd_config.DNS_SPEC_KEY.format(namespace=namespace, name=name)
           existing_dns = self.etcd.get(key)
           if existing_dns is None:
               return json.dumps({"error": "DNS not found"}), 404

           # 创建新的 DNS 配置
           updated_dns = DNSConfig(dns_json)

        #    # 验证 namespace 和 name 是否一致
        #    if updated_dns.name != name:
        #        return json.dumps({
        #            "error": "Name in request body does not match existing DNS name"
        #        }), 400
        #    if updated_dns.namespace != namespace:
        #        return json.dumps({
        #            "error": "Namespace in request body does not match existing DNS namespace"
        #        }), 400

           # 保存更新
           self.etcd.put(key, updated_dns)

           print(f"[INFO]DNS {name} updated successfully")
           return json.dumps({"message": f"DNS {name} updated successfully"}), 200

       except Exception as e:
           print(f"[ERROR]Failed to update DNS: {str(e)}")
           return json.dumps({"error": str(e)}), 500

    def delete_dns(self, namespace: str, name: str):
       """删除 DNS 配置"""
       print(f"[INFO]Delete DNS {name} in namespace {namespace}")
       try:
           key = self.etcd_config.DNS_SPEC_KEY.format(namespace=namespace, name=name)
           dns = self.etcd.get(key)
           if dns is None:
               return json.dumps({"error": "DNS not found"}), 404

           # 删除 DNS 配置
           self.etcd.delete(key)

           print(f"[INFO]DNS {name} deleted successfully")
           return json.dumps({"message": f"DNS {name} deleted successfully"}), 200

       except Exception as e:
           print(f"[ERROR]Failed to delete DNS: {str(e)}")
           return json.dumps({"error": str(e)}), 500
       
    def run(self):
        print('[INFO]ApiServer running...')
        Thread(target = self.node_health).start()
        Thread(target = self.serverless_scale).start()
        self.app.run(host='0.0.0.0', port=self.uri_config.PORT, threaded=True)

    def node_health(self):
        while True:
            sleep(5.0)
            now = time()
            nodes = self.etcd.get_prefix(self.etcd_config.NODES_KEY)
            for node in nodes:
                if node.status == NODE_STATUS.ONLINE and now - node.heartbeat_time > self.NODE_TIMEOUT:
                    node.status = NODE_STATUS.OFFLINE
                    self.etcd.put(self.etcd_config.NODE_SPEC_KEY.format(name=node.name), node)
                    print(f'[INFO]Node {node.name} offline. Last heartbeat {ctime(node.heartbeat_time)}')

    def serverless_scale(self):
        while True:
            sleep(self.serverless_config.CHECK_TIME)

            with self.SLlock.gen_wlock():
                functions = self.etcd.get_prefix(self.etcd_config.GLOBAL_FUNCTION_KEY)
                for function_config in functions:
                    key = function_config.namespace + '/' + function_config.name
                    pod_num = len(function_config.pod_list)
                    # 如果存在函数实例，则看情况增加或者减少
                    if pod_num != 0:
                        function = Function(function_config, self.serverless_config, None)

                        if self.func_cnt.get(key) / pod_num > self.serverless_config.MAX_REQUESTS_PER_POD:
                            print(f'[INFO]Function {function_config.namespace}/{function_config.name} increse scale to {pod_num + 1}')
                            pod_namespace, pod_name, pod_yaml = function.pod_info(id = pod_num)
                            url = self.uri_config.PREFIX + self.uri_config.POD_SPEC_URL.format(namespace=pod_namespace, name=pod_name)
                            response = requests.post(url, json=pod_yaml)
                            function_config.pod_list.append(PodConfig(pod_yaml))
                        elif self.func_cnt.get(key) / pod_num < self.serverless_config.MIN_REQUESTS_PER_POD:
                            pod_namespace, pod_name, pod_yaml = function.pod_info(id = pod_num - 1)
                            url = self.uri_config.PREFIX + self.uri_config.POD_SPEC_URL.format(namespace=pod_namespace, name=pod_name)
                            print(f'[INFO]Function {function_config.namespace}/{function_config.name} decrease scale to {pod_num - 1}')
                            response = requests.delete(url)
                            del function_config.pod_list[-1]

                        # 更新etcd中的function状态
                        self.etcd.put(
                            self.etcd_config.FUNCTION_SPEC_KEY.format(namespace=function_config.namespace, name=function_config.name),
                            function_config)
                        # 清空计数器
                        self.func_cnt.reset(key)

    def index(self):
        return "ApiServer Demo"

    # # kafka与dns相关
    # def set_dns_topic(self, topic: str):
    #     """
    #     设置 DNS 主题，用于 Kafka 消息传递。
    #     这个方法可以在 ApiServer 初始化时调用，确保 DNS 相关操作的消息能够正确发送到指定的 Kafka 主题。
    #     """
    #     dns_topic = self.kafka_config.DNS_TOPIC            
    #     fs = self.kafka.create_topics(
    #         [NewTopic(dns_topic, num_partitions=1, replication_factor=1)]
    #     )

    #     for topic, f in fs.items():
    #         f.result()
    #         print(f"[INFO]Topic '{topic}' created successfully.")

    #     return {
    #         "kafka_server": self.kafka_config.BOOTSTRAP_SERVER,
    #         "kafka_dns_topic": dns_topic,
    #     }

    # 注册调度器
    def add_scheduler(self):
        try:
            kafka_topic = self.kafka_config.SCHEDULER_TOPIC
            fs = self.kafka.create_topics(
                [NewTopic(kafka_topic, num_partitions=1, replication_factor=1)]
            )
            for topic, f in fs.items():
                f.result()
                print(f"[INFO]Topic '{topic}' created successfully.")

        except KafkaException as e:
            if not e.args[0].code() == 36:  # 忽略“主题已存在”的错误
                raise
            else:
                print(f"[INFO]Topic '{topic}' already created.")

        return {
            "kafka_server": self.kafka_config.BOOTSTRAP_SERVER,
            "kafka_topic": kafka_topic,
        }

    # 注册一个新结点
    def add_node(self, name: str):
        node_json = request.json
        new_node_config = NodeConfig(node_json)

        # 如果Node存在且状态为ONLINE
        node = self.etcd.get(self.etcd_config.NODE_SPEC_KEY.format(name=name))
        if node is not None:
            if node.status == NODE_STATUS.OFFLINE:
                print(f'[INFO]Node {name} reconnect.')
            else:
                print(f'[ERROR] Node {name} already exists and is still online.')
                return json.dumps({'error': 'Node name duplicated'}), 403

        try:
            # 创建Pod主题（用于kubelet）
            pod_topic = self.kafka_config.POD_TOPIC.format(name=name)
            # 创建ServiceProxy主题（用于ServiceProxy）
            serviceproxy_topic = self.kafka_config.SERVICE_PROXY_TOPIC.format(name=name)
            
            # 批量创建主题
            topics_to_create = [
                NewTopic(pod_topic, num_partitions=1, replication_factor=1),
                NewTopic(serviceproxy_topic, num_partitions=1, replication_factor=1)
            ]
            
            fs = self.kafka.create_topics(topics_to_create)
            for topic, f in fs.items():
                f.result()
                print(f"[INFO]Topic '{topic}' created successfully.")
            
            # 发送心跳消息到Pod主题
            self.kafka_producer.produce(
                pod_topic, key="HEARTBEAT", value=json.dumps({}).encode("utf-8")
            )
        except KafkaException as e:
            if not e.args[0].code() == 36:  # 忽略"主题已存在"的错误
                raise

        # 创建成功，向etcd写入实际状态
        new_node_config.kafka_server = self.kafka_config.BOOTSTRAP_SERVER
        new_node_config.topic = pod_topic
        new_node_config.status = NODE_STATUS.ONLINE
        new_node_config.heartbeat_time = time()
        self.etcd.put(self.etcd_config.NODE_SPEC_KEY.format(name=name), new_node_config)

        return {
            "kafka_server": self.kafka_config.BOOTSTRAP_SERVER,
            "kafka_topic": pod_topic,
            # "serviceproxy_topic": serviceproxy_topic,
        }

    # 获取集群中所有node
    def get_nodes(self):
        nodes = self.etcd.get_prefix(self.etcd_config.NODES_KEY)
        return pickle.dumps(nodes)

    # 获取某个node上所有pod
    def get_node_pods(self, name : str):
        pods = self.etcd.get_prefix(self.etcd_config.GLOBAL_PODS_KEY)
        node_pods = [pod for pod in pods if pod.node_name == name]
        return pickle.dumps(node_pods)

    # 结点心跳
    def update_node(self, name : str):
        node_json = request.json
        node_config = NodeConfig(node_json)
        node_config.heartbeat_time = time()
        node_config.status = NODE_STATUS.ONLINE

        node = self.etcd.get(self.etcd_config.NODE_SPEC_KEY.format(name=name))
        if node is None:
            return json.dumps({'error': 'Node not found. Need to register before update.'}), 404
        self.etcd.put(self.etcd_config.NODE_SPEC_KEY.format(name=name), node_config)
        return json.dumps({'message': f'Receive heartbeat timestamp {node_config.heartbeat_time}'}), 200

    # 查询系统中所有Pod
    def get_global_pods(self):
        print("[INFO]Get global pods.")
        # wcc: 确定可以这样查？修改后如下
        pods = self.etcd.get_prefix(self.etcd_config.GLOBAL_PODS_KEY)

        # 格式化输出
        result = []
        for pod in pods:
            # result.append({
            #     'name': pod.name,
            #     'namespace': pod.namespace,
            #     'status': pod.status,
            #     'node_name': pod.node_name,
            #     'labels': pod.labels,
            #     'owner_reference': pod.owner_reference
            # })
            result.append(
                {pod.name: pod.to_dict() if hasattr(pod, "to_dict") else vars(pod)}
            )

        return json.dumps(result)

    # 查询命名空间中所有Pod
    def get_pods(self, namespace: str):
        print("[INFO]Get pods in namespace %s" % namespace)
        pods = self.etcd.get_prefix(
            self.etcd_config.PODS_KEY.format(namespace=namespace)
        )

        # 格式化输出
        result = [
            {pod.name: pod.to_dict() if hasattr(pod, "to_dict") else vars(pod)}
            for pod in pods
        ]
        return json.dumps(result)

    # 查询一个Pod
    def get_pod(self, namespace: str, name: str):
        print("[INFO]Get pod %s in namespace %s" % (name, namespace))
        key = self.etcd_config.POD_SPEC_KEY.format(namespace=namespace, name=name)
        pod = self.etcd.get(key)
        if pod is None:
            return json.dumps({"error": "Pod not found."}), 404

        print(f"[INFO]Found pod: {pod.to_dict()}")
        return json.dumps(pod.to_dict() if hasattr(pod, "to_dict") else vars(pod))

    # 创建一个Pod
    def add_pod(self, namespace: str, name: str):
        pod_json = request.json
        new_pod_config = PodConfig(pod_json)

        # 写etcd
        # lcl mark: create会出现的bug：没有确保没有重名的pod出现
        # 再标一句，如果add_pod考虑update的话，我写的这个逻辑应该也有问题，但这里先不进一步考虑
        # wcc: 我可以在Kubelet处进行名字检查
        pod = self.etcd.get(
            self.etcd_config.POD_SPEC_KEY.format(namespace=namespace, name=name)
        )
        if pod is not None:
            return json.dumps({"error": "Pod name already exists"}), 409
        new_pod_config.status = POD_STATUS.CREATING
        self.etcd.put(
            self.etcd_config.POD_SPEC_KEY.format(namespace=namespace, name=name),
            new_pod_config,
        )

        # 向scheduler推送消息
        try:
            self.kafka_producer.produce(
                self.kafka_config.SCHEDULER_TOPIC, value=pickle.dumps(new_pod_config)
            )
            return json.dumps({"message": "Pod is creating."}), 200
        except Exception as e:
            print(f"[ERROR]Scheduler error {e}, maybe scheduler is offline.")
            return json.dumps({"error": "Scheduler is not ready"}), 409

    # scheduler调用，给Pod分配Node id
    def bind_pod(self, namespace: str, name: str, node_name: str):
        # 写etcd Node_name
        pod = self.etcd.get(
            self.etcd_config.POD_SPEC_KEY.format(namespace=namespace, name=name)
        )
        if pod is None:
            return json.dumps({"error": "Pod not found."}), 404

        pod.node_name = node_name
        self.etcd.put(
            self.etcd_config.POD_SPEC_KEY.format(namespace=namespace, name=name), pod
        )

        # 创建Pod，给kubelet队列推消息
        node = self.etcd.get(self.etcd_config.NODE_SPEC_KEY.format(name=node_name))
        if node is None:
            return json.dumps({"error": "Node not found."}), 404
        topic = self.kafka_config.POD_TOPIC.format(name=node.name)
        self.kafka_producer.produce(
            topic, key="ADD", value=json.dumps(pod.to_dict()).encode("utf-8")
        )
        return json.dumps({"message": "Pod bind successfully"}), 200

    def get_pod_status(self, namespace: str, name: str):
        pass

    # kubelet调用，更新Pod状态
    def update_pod_status(self, namespace: str, name: str):
        status = request.json["status"]
        # lcl: 确保pod的namespace和name匹配
        # wcc: 说实话，我觉得这个地方客户端可以保证，就是说url中的namespace和name应该是用yaml中的信息填入的

        # 更新容器状态，写etcd status
        # lcl: 下面这一段代码会莫名其妙执行PodConfig的init并导致标签丢失
        # wcc: 我漏掉了label这一项，没有考虑到rs需要用。莫名其妙执行PodConfig的init还真是！这是为啥啊
        pod = self.etcd.get(
            self.etcd_config.POD_SPEC_KEY.format(namespace=namespace, name=name)
        )
        if pod is None:
            return (
                json.dumps({"message": f"Pod {namespace}:{name} is already deleted."}),
                404,
            )
        pod.status = status
        self.etcd.put(
            self.etcd_config.POD_SPEC_KEY.format(namespace=namespace, name=name), pod
        )
        print(f"[INFO]Pod {namespace}:{name} status change to {status}.")
        return (
            json.dumps(
                {"message": f"Pod {namespace}:{name} status change to {status}"}
            ),
            200,
        )
    
    def get_pod_subnet_ip(self, namespace: str, name: str):
        # 获取容器的子网IP，读取etcd subnet_ip
        pod = self.etcd.get(
            self.etcd_config.POD_SPEC_KEY.format(namespace=namespace, name=name)
        )
        if pod is None:
            return (
                json.dumps({"message": f"Pod {namespace}:{name} is already deleted."}),
                404,
            )
        if pod.subnet_ip is None:
            return json.dumps({"subnet_ip": "None"}), 200
        print(f"[INFO]Pod {namespace}:{name} subnet_ip is {pod.subnet_ip}.")
        return json.dumps({"subnet_ip": pod.subnet_ip}), 200
        
    def update_pod_subnet_ip(self, namespace: str, name: str):
        subnet_ip = request.json["subnet_ip"]
        if not subnet_ip:
            return json.dumps({"error": "subnet_ip is required"}), 400
        # 更新容器的子网IP，写etcd subnet_ip
        pod = self.etcd.get(
            self.etcd_config.POD_SPEC_KEY.format(namespace=namespace, name=name)
        )
        if pod is None:
            return (
                json.dumps({"message": f"Pod {namespace}:{name} is already deleted."}),
                404,
            )
        if pod.subnet_ip:
            print(f"[INFO]updating pod {namespace}:{name} subnet_ip from {pod.subnet_ip} to {subnet_ip}")
        pod.subnet_ip = subnet_ip
        self.etcd.put(
            self.etcd_config.POD_SPEC_KEY.format(namespace=namespace, name=name), pod
        )
        print(f"[INFO]Pod {namespace}:{name} subnet_ip change to {subnet_ip}.")
        return (
            json.dumps({"message": f"Pod {namespace}:{name} subnet_ip change to {subnet_ip}"}),
            200,
        )

    # 更新一个Pod
    def update_pod(self, namespace: str, name: str):
        print("[INFO]Receive update pod in ApiServer")
        pod_json = request.json
        this_pod, topic = None, None

        key = self.etcd_config.POD_SPEC_KEY.format(namespace=namespace, name=name)
        pod = self.etcd.get(key)
        if pod is None:
            return json.dumps({"error": "Pod not found."}), 404
        node = self.etcd.get(self.etcd_config.NODE_SPEC_KEY.format(name=pod.node_name))
        if node is None:
            return json.dumps({"error": "Pod's Node not found."}), 404

        topic = self.kafka_config.POD_TOPIC.format(name=node.name)
        self.kafka_producer.produce(
            topic, key="UPDATE", value=json.dumps(pod_json).encode("utf-8")
        )
        return json.dumps({"message": "Pod update successfully"}), 200

    # 删除一个Pod
    def delete_pod(self, namespace: str, name: str):
        print("[INFO]Receive delete pod in ApiServer")
        data = {"namespace": namespace, "name": name}

        this_pod, topic = None, None

        key = self.etcd_config.POD_SPEC_KEY.format(namespace=namespace, name=name)
        pod = self.etcd.get(key)
        if pod is None:
            return json.dumps({"error": "Pod not found"}), 404

        node = self.etcd.get(self.etcd_config.NODE_SPEC_KEY.format(name=pod.node_name))
        if node is None:
            return json.dumps({"error": "Node not found"}), 404

        topic = self.kafka_config.POD_TOPIC.format(name=node.name)
        self.kafka_producer.produce(
            topic, key="DELETE", value=json.dumps(data).encode("utf-8")
        )
        self.etcd.delete(key)
        return json.dumps({"message": "Pod delete successfully"}), 200

    def get_global_replica_sets(self):
        print("[INFO]Get global ReplicaSets.")
        key = self.etcd_config.GLOBAL_REPLICA_SETS_KEY
        replica_sets = self.etcd.get_prefix(key)

        # 格式化输出
        result = []
        for rs in replica_sets:
            # result.append({
            #     'name': rs.name,
            #     'namespace': rs.namespace,
            #     'replicas': f'{rs.current_replicas}/{rs.replica_count}',
            #     'selector': rs.selector,
            #     'labels': rs.labels,
            #     'status': rs.status
            # })
            result.append(
                {rs.name: rs.to_dict() if hasattr(rs, "to_dict") else vars(rs)}
            )

        return json.dumps(result)

    # 支持global和某个namesapce
    def get_replica_sets(self, namespace):
        print(f"[INFO]Get all ReplicaSets in namespace {namespace}")
        # wcc mark: 貌似只传了namespace
        key = self.etcd_config.REPLICA_SETS_KEY.format(namespace=namespace)
        replica_sets = self.etcd.get_prefix(key)

        # 格式化输出
        result = []
        for rs in replica_sets:
            # result.append({
            #     'name': rs.name,
            #     'namespace': rs.namespace,
            #     'replicas': f'{rs.current_replicas}/{rs.replica_count}',
            #     'selector': rs.selector,
            #     'labels': rs.labels,
            #     'status': rs.status
            # })
            result.append(
                {rs.name: rs.to_dict() if hasattr(rs, "to_dict") else vars(rs)}
            )

        return json.dumps(result)

    def get_replica_set(self, namespace, name):
        """获取特定ReplicaSet的详细信息"""
        print(f"[INFO]Get ReplicaSet {name} in namespace {namespace}")
        key = self.etcd_config.REPLICA_SET_SPEC_KEY.format(
            namespace=namespace, name=name
        )
        rs = self.etcd.get(key)

        if rs is None:
            return (
                json.dumps(
                    {"error": f"ReplicaSet {name} not found in namespace {namespace}"}
                ),
                404,
            )

        print(f"[INFO]Found ReplicaSet: {rs}")
        # result = {
        #     'name': rs.name,
        #     'namespace': rs.namespace,
        #     'replicas': f'{rs.current_replicas}/{rs.replica_count}',
        #     'selector': rs.selector,
        #     'labels': rs.labels,
        #     'pod_instances': rs.pod_instances,
        #     'status': rs.status
        # }
        # return json.dumps(result)
        # return json.dumps(vars(rs))
        return json.dumps(rs.to_dict() if hasattr(rs, "to_dict") else vars(rs))

    # replicaset在api server这里最重要的函数，决定了存入的类型
    def create_replica_set(self, namespace, name):
        """创建一个新的ReplicaSet"""
        print(f"[INFO]Create ReplicaSet {name} in namespace {namespace}")
        # 存储到etcd
        key = self.etcd_config.REPLICA_SET_SPEC_KEY.format(
            namespace=namespace, name=name
        )
        rs = self.etcd.get(key)

        # 检查是否已存在
        if rs is not None:
            return json.dumps({"error": f"ReplicaSet {name} already exists"}), 409

        try:
            rs_json = request.json
            print(f"[INFO]Received JSON: {rs_json}")
            if isinstance(rs_json, str):
                rs_json = json.loads(rs_json)

            # 检查名称是否匹配
            if rs_json.get("metadata", {}).get("name") != name:
                return (
                    json.dumps(
                        {"error": "Name in URL does not match name in request body"}
                    ),
                    400,
                )

            # 创建ReplicaSetConfig
            rs_config = ReplicaSetConfig(rs_json)
            rs_config.selector = rs_config.selector or {}

            # 初始化运行时状态
            # rs_config.status = 'PENDING'
            # rs_config.current_replicas = 0
            rs_config.status = []
            rs_config.current_replicas = (
                []
            )  # 当前实际的副本数量，应该是一个数组，因为会控制多个Pod
            rs_config.pod_instances = []

            # 首先要使用get_pods获取同namespace的，然后通过selector进一步筛选
            pod_configs = self.etcd.get_prefix(
                self.etcd_config.PODS_KEY.format(namespace=namespace)
            )
            
            print(f"[INFO]Pods in namespace {namespace}: {pod_configs}")
            # 通过selector找到对应的pod_configs
            selector_app = rs_config.get_selector_app()
            selector_env = rs_config.get_selector_env()
            print(f"[INFO]Selector app: {selector_app}, env: {selector_env}")
            # if not pod_configs:
            #     print(f'[WARNING]No pods found in namespace {namespace}')
            if pod_configs and (selector_app or selector_env):  # 如果有selector
                for pod in pod_configs:
                    print(
                        f"pod.labels.app: {pod.get_app_label()}, pod.labels.env: {pod.get_env_label()}"
                    )
                    if selector_app and pod.get_app_label() != selector_app:
                        print(
                            f"[INFO]Pod {pod.name} does not match selector app {selector_app}"
                        )
                        continue
                    if selector_env and pod.get_env_label() != selector_env:
                        print(
                            f"[INFO]Pod {pod.name} does not match selector env {selector_env}"
                        )
                        continue
                    # 如果pod符合selector条件，添加到pod_configs
                    print(f"[INFO]Adding pod {pod.name} to ReplicaSet {name}")
                    rs_config.add_pod_group(pod.name)
            else:  # 如果没有selector，直接添加所有pod_configs
                print(
                    f"[INFO]No selector provided, adding all pods in namespace {namespace}"
                )
                for pod in pod_configs:
                    # replica_sets.append(pod_config.name)
                    rs_config.add_pod_group(pod.name)
            if not rs_config.pod_instances:
                print(
                    f"[WARNING]No pods found in namespace {namespace} with selector {selector_app} or {selector_env}"
                )
            else:
                # 如果有pod_instances，更新ReplicaSet的current_replicas数组
                groups = rs_config.get_all_groups()
                for group in groups:
                    rs_config.current_replicas.append(len(group))

            print(f"[INFO]ReplicaSetConfig created: {rs_config}")
            # 添加
            self.etcd.put(key, rs_config)

            # for node in nodes:
            #     if node.name == pod_configs[0].node_name:
            #         topic = self.kafka_config.POD_TOPIC.format(name=node.name)
            #         break
            # 最后，将rs_config传入给replicasetcontroller，让他以config为基础对replicaset进行管理

            return json.dumps({"message": f"ReplicaSet {name} created successfully"})
        except Exception as e:
            print(f"[ERROR]Failed to create ReplicaSet: {str(e)}")
            return json.dumps({"error": str(e)}), 500

    def update_replica_set(self, namespace, name):
        """更新现有的ReplicaSet"""
        print(f"[INFO]Update ReplicaSet {name} in namespace {namespace}")

        try:
            rs_json = request.json
            print(f"[INFO]Update Replica set: Received JSON: {rs_json}")
            if isinstance(rs_json, str):
                rs_json = json.loads(rs_json)

            # 检查名称是否匹配
            if rs_json.get("metadata", {}).get("name") != name:
                return (
                    json.dumps(
                        {"error": "Name in URL does not match name in request body"}
                    ),
                    400,
                )

            # 获取现有ReplicaSet
            key = self.etcd_config.REPLICA_SET_SPEC_KEY.format(
                namespace=namespace, name=name
            )
            rs = self.etcd.get(key)

            if rs is None:
                return json.dumps({"error": f"ReplicaSet {name} not found"}), 404

            # 目前只更新运行时信息和副本数量，且不会同时进行（一个大概率由hpa发起，一个大概率由rs controller发起）
            if rs.replica_count == rs_json.get("spec", {}).get(
                "replicas", rs.replica_count
            ):
                # 更新运行时信息
                rs.status = rs_json.get("status", rs.status)
                rs.current_replicas = rs_json.get(
                    "current_replicas", rs.current_replicas
                )
                rs.pod_instances = rs_json.get("pod_instances", rs.pod_instances)
                # print(f'[INFO]Updated ReplicaSet: {rs}')
                # updated_config.status = rs.status
                # updated_config.current_replicas = rs.current_replicas
                # updated_config.pod_instances = rs.pod_instances
            else:
                # 更新副本数量
                rs.replica_count = rs_json.get("spec", {}).get(
                    "replicas", rs.replica_count
                )
                # print(f'[INFO]Updated ReplicaSet replica count: {rs.replica_count}')
            # 保存更新
            self.etcd.put(key, rs)

            return json.dumps({"message": f"ReplicaSet {name} updated successfully"})
        except Exception as e:
            print(f"[ERROR]Failed to update ReplicaSet: {str(e)}")
            return json.dumps({"error": str(e)}), 500

    def delete_replica_set(self, namespace, name):
        """删除ReplicaSet及其所有Pod"""
        print(f"[INFO]Delete ReplicaSet {name} in namespace {namespace}")

        try:
            # 获取ReplicaSet
            key = self.etcd_config.REPLICA_SET_SPEC_KEY.format(
                namespace=namespace, name=name
            )
            target_rs = self.etcd.get(key)

            if not target_rs:
                return json.dumps({"error": f"ReplicaSet {name} not found"}), 404

            # 删除所有关联的Pod
            count = 0
            if hasattr(target_rs, "pod_instances") and target_rs.pod_instances:
                for group in target_rs.pod_instances:
                    if group:
                        for pod_name in group:
                            self.delete_pod(
                                namespace, pod_name
                            )  # 调用delete_pod方法删除Pod
                            count += 1
            else:
                print(f"[WARNING]ReplicaSet {name} has no associated pods to delete.")
            print(f"[INFO]Deleted {count} pods associated with ReplicaSet {name}.")
            
            if target_rs.hpa_controlled:
                # 如果ReplicaSet被HPA控制，删除HPA
                hpa_key = self.etcd_config.HPA_KEY.format(
                    namespace=namespace
                )
                hpas = self.etcd.get(hpa_key)
                for hpa in hpas:
                    if hpa.target_name == name:
                        self.etcd.delete(
                            self.etcd_config.HPA_SPEC_KEY.format(
                                namespace=namespace, name=hpa.name
                            )
                        )
                        print(f"[INFO]Deleted HPA {hpa.name} controlling ReplicaSet {name}.")

            # 更新ReplicaSet列表
            self.etcd.delete(key)
            
            # 如果hpa托管了，删除托管它的hpa

            return json.dumps(
                {"message": f"ReplicaSet {name} and its pods deleted successfully"}
            )
        except Exception as e:
            print(f"[ERROR]Failed to delete ReplicaSet: {str(e)}")
            return json.dumps({"error": str(e)}), 500

    def get_global_hpas(self):
        """获取所有HPA"""
        print("[INFO]Get global HPAs")
        key = self.etcd_config.GLOBAL_HPA_KEY
        hpas = self.etcd.get_prefix(key)

        # 格式化输出
        result = []
        for hpa in hpas:
            result.append(
                {hpa.name: hpa.to_dict() if hasattr(hpa, "to_dict") else vars(hpa)}
            )

        return json.dumps(result)

    def get_hpas(self, namespace):
        """获取HPA列表"""
        print(f'[INFO]Get HPAs in namespace {namespace}')

        # 如果提供了namespace参数，获取指定命名空间的HPA
        key = self.etcd_config.HPA_KEY.format(namespace=namespace)
        hpas = self.etcd.get_prefix(key)

        # 格式化输出
        result = []
        if hpas:
            for hpa in hpas:
                result.append(
                    {hpa.name: hpa.to_dict() if hasattr(hpa, "to_dict") else vars(hpa)}
                )

        return json.dumps(result)

    def get_hpa(self, namespace, name):
        """获取特定HPA的详细信息"""
        print(f"[INFO]Get HPA {name} in namespace {namespace}")
        key = self.etcd_config.HPA_SPEC_KEY.format(namespace=namespace, name=name)
        hpa = self.etcd.get(key)

        if hpa:
            return json.dumps(hpa.to_dict() if hasattr(hpa, "to_dict") else vars(hpa))

        return (
            json.dumps({"error": f"HPA {name} not found in namespace {namespace}"}),
            404,
        )

    def create_hpa(self, namespace, name):
        """创建一个新的HPA"""
        print(f"[INFO]Create HPA {name} in namespace {namespace}")

        try:
            hpa_json = request.json
            if isinstance(hpa_json, str):
                hpa_json = json.loads(hpa_json)

            # 检查名称是否匹配
            if hpa_json.get("metadata", {}).get("name") != name:
                return (
                    json.dumps(
                        {"error": "Name in URL does not match name in request body"}
                    ),
                    400,
                )

            # 创建HPA配置
            hpa_config = HorizontalPodAutoscalerConfig(hpa_json)

            # 检查目标资源是否存在
            if hpa_config.target_kind == "ReplicaSet":
                rs_key = self.etcd_config.REPLICA_SET_SPEC_KEY.format(
                    namespace=namespace, name=hpa_config.target_name
                )
                rs = self.etcd.get(rs_key)

                if not rs:
                    return (
                        json.dumps(
                            {
                                "error": f"Target ReplicaSet {hpa_config.target_name} not found"
                            }
                        ),
                        404,
                    )
                rs.hpa_controlled = True

                # 更新ReplicaSet的HPA控制状态
                self.etcd.put(rs_key, rs)

            print(f"[INFO]HPAConfig created: {hpa_config} and target found")
            # 存储HPA
            key = self.etcd_config.HPA_SPEC_KEY.format(namespace=namespace, name=name)
            hpa = self.etcd.get(key)

            # 检查是否已存在
            if hpa is not None:
                return json.dumps({"error": f"HPA {name} already exists"}), 409

            # 添加
            self.etcd.put(key, hpa_config)

            return json.dumps({"message": f"HPA {name} created successfully"})
        except Exception as e:
            print(f"[ERROR]Failed to create HPA: {str(e)}")
            return json.dumps({"error": str(e)}), 500

    def update_hpa(self, namespace, name):
        """更新现有的HPA"""
        print(f"[INFO]Update HPA {name} in namespace {namespace}")

        try:
            print(f"[INFO]Received JSON: {request.json}")
            hpa_json = request.json
            if isinstance(hpa_json, str):
                hpa_json = json.loads(hpa_json)

            # 检查名称是否匹配
            if hpa_json.get("metadata", {}).get("name") != name:
                return (
                    json.dumps(
                        {"error": "Name in URL does not match name in request body"}
                    ),
                    400,
                )

            # 获取现有HPA
            key = self.etcd_config.HPA_SPEC_KEY.format(namespace=namespace, name=name)
            hpa = self.etcd.get(key)

            if not hpa:
                return json.dumps({"error": f"HPA {name} not found"}), 404
            hpa
            # 创建更新后的配置
            # updated_config = HorizontalPodAutoscalerConfig(hpa_json)

            # 更新运行时信息
            hpa.current_replicas = hpa_json.get("spec",{}).get(
                "currentReplicas", hpa.current_replicas
            )
            
            # 保存更新
            self.etcd.put(key, hpa)

            return json.dumps({"message": f"HPA {name} updated successfully"})
        except Exception as e:
            print(f"[ERROR]Failed to update HPA: {str(e)}")
            return json.dumps({"error": str(e)}), 500

    def delete_hpa(self, namespace, name):
        """删除HPA"""
        print(f"[INFO]Delete HPA {name} in namespace {namespace}")

        try:
            # 获取HPA
            key = self.etcd_config.HPA_SPEC_KEY.format(namespace=namespace, name=name)
            target_hpa = self.etcd.get(key)

            if not target_hpa:
                return json.dumps({"error": f"HPA {name} not found"}), 404

            # 移除目标资源的HPA控制标记
            if target_hpa.target_kind == "ReplicaSet":
                self._release_hpa_control(namespace, target_hpa.target_name)

            # 更新HPA列表
            self.etcd.delete(key)

            return json.dumps({"message": f"HPA {name} deleted successfully"})
        except Exception as e:
            print(f"[ERROR]Failed to delete HPA: {str(e)}")
            return json.dumps({"error": str(e)}), 500

    def _release_hpa_control(self, namespace, replica_set_name):
        """移除ReplicaSet的HPA控制标记"""
        rs_key = self.etcd_config.REPLICA_SET_SPEC_KEY.format(
            namespace=namespace, name=replica_set_name
        )
        rs = self.etcd.get(rs_key)

        rs.hpa_controlled = False

        self.etcd.put(rs_key, rs)

    # ===================== Service相关方法 =====================
    
    def get_global_services(self):
        """获取全部Service"""
        print("[INFO]Get global services")
        try:
            services = self.etcd.get_prefix(self.etcd_config.GLOBAL_SERVICES_KEY)
            print(f"[INFO]Found {len(services)} global services")
            print(f"[INFO]Services: {services}")
            result = []
            for service in services:
                result.append({service.name: service.to_dict()})
            return json.dumps(result)
        except Exception as e:
            print(f"[ERROR]Failed to get global services: {str(e)}")
            return json.dumps({"error": str(e)}), 500

    def get_services(self, namespace: str):
        """获取指定namespace下的Service"""
        print(f"[INFO]Get services in namespace {namespace}")
        try:
            services = self.etcd.get_prefix(
                self.etcd_config.SERVICES_KEY.format(namespace=namespace)
            )
            result = []
            for service in services:
                result.append({service.name: service.to_dict()})
            return json.dumps(result)
        except Exception as e:
            print(f"[ERROR]Failed to get services: {str(e)}")
            return json.dumps({"error": str(e)}), 500

    def get_service(self, namespace: str, name: str):
        """获取指定Service"""
        print(f"[INFO]Get service {name} in namespace {namespace}")
        try:
            key = self.etcd_config.SERVICE_SPEC_KEY.format(namespace=namespace, name=name)
            service = self.etcd.get(key)
            if service is None:
                return json.dumps({"error": "Service not found"}), 404
            return json.dumps(service.to_dict())
        except Exception as e:
            print(f"[ERROR]Failed to get service: {str(e)}")
            return json.dumps({"error": str(e)}), 500

    # service 只在 apiserver里存进etcd，后续的 service 对pod的管理是在servicecontroller中实现的
    def create_service(self, namespace: str, name: str):
        """创建Service"""
        print(f"[INFO]Create service {name} in namespace {namespace}")
        try:
            service_json = request.json
            
            # 验证namespace和name是否匹配
            if service_json.get("metadata", {}).get("name") != name:
                return json.dumps({
                    "error": "Name in URL does not match name in request body"
                }), 400
            
            if service_json.get("metadata", {}).get("namespace", "default") != namespace:
                return json.dumps({
                    "error": "Namespace in URL does not match namespace in request body"
                }), 400

            # 检查Service是否已存在
            key = self.etcd_config.SERVICE_SPEC_KEY.format(namespace=namespace, name=name)
            existing_service = self.etcd.get(key)
            if existing_service is not None:
                return json.dumps({"error": "Service already exists"}), 409

            # 创建Service配置
            service_config = ServiceConfig(service_json)
            # service_config.namespace = namespace
            # service_config.name = name
            # service_config.status = "Pending"

            # 保存到etcd
            self.etcd.put(key, service_config)

            print(f"[INFO]Service {name} created successfully")
            return json.dumps({"message": f"Service {name} created successfully"}), 200

        except Exception as e:
            print(f"[ERROR]Failed to create service: {str(e)}")
            return json.dumps({"error": str(e)}), 500

    def update_service(self, namespace: str, name: str):
        """更新Service"""
        # 只有clusterIP可以更新，其他的都不允许更新
        print(f"[INFO]Update service {name} in namespace {namespace}")
        try:
            cluster_ip_json = request.json
            
            if not cluster_ip_json.get("cluster_ip", {}): # 如果没有cluster_ip字段
                return json.dumps({
                    "error": "No cluster_ip provided for update"
            }), 400

            # 获取现有Service
            key = self.etcd_config.SERVICE_SPEC_KEY.format(namespace=namespace, name=name)
            existing_service = self.etcd.get(key)
            if existing_service is None:
                return json.dumps({"error": "Service not found"}), 404

            # 创建新的Service配置
            if existing_service.cluster_ip:
                print(f"[ERROR]Service {name} already has cluster_ip, cannot update.")
                print(f"[ERROR]Existing service: {existing_service.to_dict()}")
                print(f"[ERROR]trying to update Cluster IP to: {cluster_ip_json.get('cluster_ip')}")
                return json.dumps({"error": "Service already has a cluster IP"}), 400
                
            existing_service.cluster_ip = cluster_ip_json.get("cluster_ip", existing_service.cluster_ip)

            # 保存更新
            self.etcd.put(key, existing_service)

            return json.dumps({"message": f"Service {name} updated successfully"})

        except Exception as e:
            print(f"[ERROR]Failed to update service: {str(e)}")
            return json.dumps({"error": str(e)}), 500

    def delete_service(self, namespace: str, name: str):
        """删除Service"""
        print(f"[INFO]Delete service {name} in namespace {namespace}")
        try:
            key = self.etcd_config.SERVICE_SPEC_KEY.format(namespace=namespace, name=name)
            service = self.etcd.get(key)
            if service is None:
                return json.dumps({"error": "Service not found"}), 404

            # 删除Service
            self.etcd.delete(key)

            return json.dumps({"message": f"Service {name} deleted successfully"})

        except Exception as e:
            print(f"[ERROR]Failed to delete service: {str(e)}")
            return json.dumps({"error": str(e)}), 500

    def get_service_status(self, namespace: str, name: str):
        """获取Service状态和统计信息"""
        print(f"[INFO]Get service status {name} in namespace {namespace}")
        try:
            key = self.etcd_config.SERVICE_SPEC_KEY.format(namespace=namespace, name=name)
            service = self.etcd.get(key)
            if service is None:
                return json.dumps({"error": "Service not found"}), 404

            return json.dumps(service.to_dict()), 200

        except Exception as e:
            print(f"[ERROR]Failed to get service status: {str(e)}")
            return json.dumps({"error": str(e)}), 500

    def get_function(self, namespace: str, name : str):
        """获取指定Service"""
        print(f"[INFO]Get function {name} in namespace {namespace}")
        try:
            key = self.etcd_config.FUNCTION_SPEC_KEY.format(namespace=namespace, name=name)
            function = self.etcd.get(key)
            if function is None:
                return json.dumps({"error": "Function not found"}), 999
            return json.dumps(function.to_dict())
        except Exception as e:
            print(f"[ERROR]Failed to get function: {str(e)}")
            return json.dumps({"error": str(e)}), 500
    
    def get_functions(self, namespace: str, name : str):
        """获取指定Funcctions"""
        print(f"[INFO]Get functions in namespace {namespace}")
        try:
            functions = self.etcd.get_prefix(self.etcd_config.GLOBAL_FUNCTION_KEY)
            
            result = []
            for func in functions:
                result.append(func.to_dict())
            return json.dumps(result)
        except Exception as e:
            print(f"[ERROR]Failed to get functions: {str(e)}")
            return json.dumps({"error": str(e)}), 500
    
    def add_function(self, namespace : str, name : str):
        print(f"[INFO]Add function {name} in namespace {namespace}")
        if 'file' not in request.files or not request.files['file']:
            return json.dumps({"error": f"Fail to add function {name}. You should upload an *.zip or *.py."}), 409

        trigger = request.form.get('trigger', None)
        if not trigger:
            return json.dumps({"error": f"Fail to add function {name}. You should give trigger type in yaml"}), 409

        if '/' in namespace or '/' in name:
            return json.dumps({"error": f"Function name or namespace should not contain /."}), 409

        if self.etcd.get(self.etcd_config.FUNCTION_SPEC_KEY.format(namespace=namespace, name=name)):
            return json.dumps({"error": f"Function {namespace}/{name} already exists."}), 409

        file = request.files['file']
        code_dir = self.serverless_config.CODE_PATH.format(namespace=namespace, name=name)
        function_config = FunctionConfig(namespace, name, trigger, code_dir)
        function = Function(function_config, self.serverless_config, file)

        try:
            # 检查并存入源代码
            function.download_unzip_code()
            # 检查并构建image
            function.build_image()
            # 上传dockerhub
            function_config.target_image = function.push_image()
            # 写etcd
            self.etcd.put(self.etcd_config.FUNCTION_SPEC_KEY.format(namespace=namespace, name=name), function_config)

        except Exception as e:
            return json.dumps({"error": str(e)}), 409
        print(f"[INFO]Function {name} added successfully in namespace {namespace}")
        return json.dumps({"message": "Successfully add function"}), 200

    def update_function(self, namespace : str, name : str):
        # 由于函数更改后，旧的Pod实例必须删除，所以逻辑就等价于增加再删除
        try:
            url = self.uri_config.PREFIX + self.uri_config.FUNCTION_SPEC_URL.format(namespace=namespace, name=name)
            delete_reponse = requests.delete(url)
            if not delete_reponse.ok():
                raise ValueError(f'Delete failed {delete_reponse.json}')

            url = self.uri_config.PREFIX + self.uri_config.FUNCTION_SPEC_URL.format(namespace=namespace, name=name)
            add_response = requests.post(url, json=request.json, file=request.file)
            if not delete_reponse.ok():
                raise ValueError(f'Add failed {add_response.json}')
        except Exception as e:
            print(f"[ERROR]Failed to update function: {str(e)}")
            return json.dumps({"error": str(e)}), 500

    def delete_function(self, namespace: str, name: str):
        """删除Function"""
        print(f"[INFO]Delete function {name} in namespace {namespace}")
        try:
            # 先拿读锁，保证对该function的互斥访问，这样请求就不会转发，并且不会自动扩缩容
            with self.SLlock.gen_wlock():
                key = self.etcd_config.FUNCTION_SPEC_KEY.format(namespace=namespace, name=name)
                function_config = self.etcd.get(key)
                if function_config is None:
                    return json.dumps({"error": "Function not found"}), 404

                # 在etcd删除function
                self.etcd.delete(key)
                # 然后再释放存活的Pod
                while True:
                    key = function_config.namespace + '/' + function_config.name
                    pod_num = len(function_config.pod_list)
                    if pod_num == 0:
                        break
                    function = Function(function_config, self.serverless_config, None)
                    pod_namespace, pod_name, pod_yaml = function.pod_info(id = pod_num - 1)
                    url = self.uri_config.PREFIX + self.uri_config.POD_SPEC_URL.format(namespace=pod_namespace, name=pod_name)
                    response = requests.delete(url)
                    del function_config.pod_list[-1]

            return json.dumps({"message": f"Function {name} deleted successfully"})
        except Exception as e:
            print(f"[ERROR]Failed to delete service: {str(e)}")
            return json.dumps({"error": str(e)}), 500

    def exec_function(self, namespace : str, name : str):
        # 对于function_config资源获取读锁
        rlock = self.SLlock.gen_rlock()
        rlock.acquire()
        self.func_cnt.increment(namespace + '/' + name)
        function_config = self.etcd.get(self.etcd_config.FUNCTION_SPEC_KEY.format(namespace=namespace, name=name))
        if function_config is None:
            rlock.release()
            return json.dumps({"error": f"Function {namespace}/{name} does not exists."}), 404
        if function_config.trigger != "http":
            rlock.release()
            return json.dumps({"error": f"Function {namespace}/{name} trigger type '{function_config.trigger}' is not http."}), 409

        if len(function_config.pod_list) == 0:
            # 对于function_config资源释放读锁获取写锁
            rlock.release()
            with self.SLlock.gen_wlock():
                # double check条件
                function_config = self.etcd.get(
                    self.etcd_config.FUNCTION_SPEC_KEY.format(namespace=namespace, name=name))
                if function_config is None:
                    return json.dumps({"error": f"Function {namespace}/{name} does not exists."}), 404
                function_config = self.etcd.get(
                    self.etcd_config.FUNCTION_SPEC_KEY.format(namespace=namespace, name=name))
                if len(function_config.pod_list) == 0:
                    function = Function(function_config, self.serverless_config, None)
                    pod_namespace, pod_name, pod_yaml = function.pod_info(id=0)
                    url = self.uri_config.PREFIX + self.uri_config.POD_SPEC_URL.format(namespace=pod_namespace,
                                                                                       name=pod_name)
                    print(f'[INFO]Starting a new function Pod {pod_namespace}/{pod_name}.')
                    response = requests.post(url, json=pod_yaml)
                    function_config.pod_list.append(PodConfig(pod_yaml))

                    while True:
                        sleep(0.5)
                        pod = self.etcd.get(
                            self.etcd_config.POD_SPEC_KEY.format(namespace=pod_namespace, name=pod_name))
                        if pod.status == POD_STATUS.RUNNING:
                            sleep(1.0)
                            break
                    self.etcd.put(
                        self.etcd_config.FUNCTION_SPEC_KEY.format(namespace=namespace, name=name),
                        function_config)
            rlock.acquire()

        # 获取读锁
        try:
            pod_config = random.choice(function_config.pod_list)
            pod = self.etcd.get(
                self.etcd_config.POD_SPEC_KEY.format(namespace=pod_config.namespace, name=pod_config.name))

            print(f'[INFO]Forwarding function call "{name}" to Pod {pod.namespace}/{pod.name}')
            url = self.serverless_config.POD_URL.format(host=pod.subnet_ip, port=self.serverless_config.POD_PORT, function_name = name)
            response = requests.post(url, json=request.json)
            rlock.release()
            return response.json(), 200
        except Exception as e:
            print(f'[INFO]Unable to call function "{name}" to Pod {pod.namespace}/{pod.name}: {str(e)}')
            rlock.release()
            return json.dumps({"error": str(e)}), 409

    def add_workflow(self, namespace: str, name: str):
        workflow_json = request.json
        new_workflow_config = WorkflowConfig(workflow_json)

        workflow = self.etcd.get(
            self.etcd_config.WORKFLOW_SPEC_KEY.format(namespace=namespace, name=name)
        )
        if workflow is not None:
            return json.dumps({"error": "Workflow name already exists"}), 409
        self.etcd.put(
            self.etcd_config.WORKFLOW_SPEC_KEY.format(namespace=namespace, name=name),
            new_workflow_config,
        )
        return json.dumps({"message": "Successfully add workflow"}), 200

    def exec_workflow(self, namespace: str, name: str):
        context = request.json
        workflow_config = self.etcd.get(
            self.etcd_config.WORKFLOW_SPEC_KEY.format(namespace=namespace, name=name)
        )
        if workflow_config is None:
            return json.dumps({"error": f"Workflow {namespace}:{name} not found."}), 404
        
        workflow = Workflow(workflow_config, self.uri_config)
        try:
            result = workflow.exec(context)
            return json.dumps(result), 200
        except Exception as e:
            print(f'[ERROR]Error occur during workflow execution: {str(e)}')
            return json.dumps({"error": f"Error occur during workflow execution: {str(e)}"}), 500


if __name__ == "__main__":
    api_server = ApiServer(URIConfig, EtcdConfig, KafkaConfig, ServerlessConfig)
    api_server.run()
