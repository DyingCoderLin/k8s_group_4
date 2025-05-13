import etcd3
import json
import docker
from docker.errors import APIError
from flask import Flask, request
from confluent_kafka import Producer

from pkg.apiObject.pod import STATUS as POD_STATUS

from pkg.config.uriConfig import URIConfig
from pkg.config.etcdConfig import EtcdConfig
from pkg.config.overlayConfig import OverlayConfig
from pkg.config.kafkaConfig import KafkaConfig
from pkg.config.nodeConfig import NodeConfig

class ApiServer():
    def __init__(self, uri_config : URIConfig, etcd_config: EtcdConfig, overlay_config: OverlayConfig, kafka_config : KafkaConfig):
        print('[INFO]ApiServer starting...')
        self.uri_config = uri_config
        self.etcd_config = etcd_config
        self.overlay_config = overlay_config
        self.kafka_config = kafka_config

        self.app = Flask(__name__)
        self.etcd = etcd3.client(host=etcd_config.HOST, port=etcd_config.PORT)
        self.docker = docker.DockerClient(base_url='npipe:////./pipe/docker_engine', version='1.25', timeout=5)
        self.kafka = Producer({'bootstrap.servers': kafka_config.BOOTSTRAP_SERVER})

        self.bind(uri_config)
        try: self.overlay_network = self.docker.networks.create(**overlay_config().dockerapi_args())
        except APIError as e:
            if "Conflict" in str(e) and "network with name" in str(e) and "already exists" in str(e):
                print(f"[INFO]Overlay network exists, skip creating.")
            else: raise e
        print('[INFO]ApiServer init success.')

    def bind(self, config):
        self.app.route('/', methods=['GET'])(self.index)
        self.app.route(config.NODE_SPEC_URL, methods=['POST'])(self.add_node)
        self.app.route(config.GLOBAL_PODS_URL, methods=['GET'])(self.get_pods)
        self.app.route(config.POD_SPEC_URL, methods=['GET'])(self.get_pod)
        self.app.route(config.POD_SPEC_URL, methods=['POST'])(self.add_pod)
        self.app.route(config.POD_SPEC_URL, methods=['PUT'])(self.update_pod)
        self.app.route(config.POD_SPEC_URL, methods=['DELETE'])(self.delete_pod)

    def run(self):
        print('[INFO]ApiServer running...')
        self.app.run(host='0.0.0.0', port=self.uri_config.PORT, processes=True)

    def index(self):
        return 'ApiServer Demo'

    def add_node(self, name : str):
        node_json = request.json
        print(node_json)
        new_node_config = NodeConfig(node_json)

        nodes = self.etcd.get(self.etcd_config.NODES_KEY)
        ips = [node.subnet_ip for node in nodes]
        for subnet in self.overlay_config.SUBMETS:
            if subnet["Subnet"] not in ips:
                new_node_config.subnet_ip = subnet["Subnet"]
                nodes.append(new_node_config)
                self.etcd.put(self.etcd_config.NODES_KEY, nodes)

                return {
                    subnet_ip: subnet["Subnet"],
                    overlay_name: self.overlay_config.NAME,
                    kafka_server: self.kafka_config.BOOTSTRAP_SERVER,
                    kafka_topic: self.kafka_config.POD_TOPIC.format(name)
                }

        print('[ERROR]No subnet ip left.')

    def get_pods(self):
        print('[INFO]Get global pods.')

    def get_pod(self, namespace : str, name : str):
        pass

    def add_pod(self, namespace : str, name : str):
        pod_json = request.json
        new_pod_config = PodConfig(pod_json)

        # 写etcd
        pods = self.etcd.get(self.etcd_config.PODS_KEY.format(namespace = namespace))
        pods.append(new_pod_config)
        self.etcd.put(self.etcd_config.PODS_KEY.format(namespace = namespace), pods)

        # TODO: 给scheduler队列推消息
        # TODO: 接收scheduler回复的Node_id
        nodes = self.etcd.get(self.etcd_config.NODES_KEY)
        node_id = nodes[0].id

        # 写etcd Node_id
        pods = self.etcd.get(self.etcd_config.PODS_KEY.format(namespace = namespace))
        for i, pod in enumerate(pods):
            if pod.name == new_pod_config.name:
                pods[i].node_id = node_id
                break
        self.etcd.put(self.etcd_config.PODS_KEY.format(namespace = namespace), pods)

        # TODO: 给scheduler回ACK

        # 给kubelet队列推消息
        nodes = self.etcd.get(self.etcd_config.NODES_KEY)
        for node in nodes:
            if node.id == node_id:
                topic = self.kafka_config.POD_TOPIC.format(node.name)
        producer.produce(topic, json.dump(pod_json).encode('utf-8'))

        # 写etcd status
        pods = self.etcd.get(self.etcd_config.PODS_KEY.format(namespace=namespace))
        for i, pod in enumerate(pods):
            if pod.name == new_pod_config.name:
                pods[i].status = POD_STATUS.RUNNING
                break
        self.etcd.put(self.etcd_config.PODS_KEY.format(namespace=namespace), pods)

    def update_pod(self):
        pass

    def delete_pod(self):
        pass


if __name__ == '__main__':
    api_server = ApiServer(URIConfig, EtcdConfig, OverlayConfig, KafkaConfig)
    api_server.run()