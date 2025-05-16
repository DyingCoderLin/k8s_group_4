import etcd3
import json
import pickle
import docker
from docker.errors import APIError
from flask import Flask, request
from confluent_kafka import Producer, KafkaException
from confluent_kafka.admin import AdminClient, NewTopic

from pkg.apiObject.pod import STATUS as POD_STATUS

from pkg.config.uriConfig import URIConfig
from pkg.config.etcdConfig import EtcdConfig
from pkg.config.overlayConfig import OverlayConfig
from pkg.config.kafkaConfig import KafkaConfig
from pkg.config.nodeConfig import NodeConfig
from pkg.config.podConfig import PodConfig

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
        self.kafka = AdminClient({'bootstrap.servers': kafka_config.BOOTSTRAP_SERVER})
        self.kafka_producer = Producer({'bootstrap.servers': kafka_config.BOOTSTRAP_SERVER})

        # --- 调试时使用 ---
        keys = self.etcd.get_all()
        for value, metadata in keys:
            key = metadata.key.decode('utf-8')
            self.etcd.delete(key)

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

    def get(self, key, ret_meta = False):
        val, meta = self.etcd.get(key)
        val = [] if val is None else pickle.loads(val)
        if ret_meta:
            return val, meta
        else:
            return val

    def put(self, key, val):
        val = pickle.dumps(val)
        self.etcd.put(key, val)

    def add_node(self, name : str):
        node_json = request.json
        new_node_config = NodeConfig(node_json)

        nodes = self.get(self.etcd_config.NODES_KEY)
        ips = [node.subnet_ip for node in nodes]
        for subnet in self.overlay_config.SUBNETS:
            if subnet["Subnet"] not in ips:
                nodes.append(new_node_config)
                self.put(self.etcd_config.NODES_KEY, nodes)

                try:
                    kafka_topic = self.kafka_config.POD_TOPIC.format(name = name)
                    fs = self.kafka.create_topics([NewTopic(kafka_topic, num_partitions=1, replication_factor=1)])
                    for topic, f in fs.items():
                        f.result()
                        print(f"[INFO]Topic '{topic}' created successfully.")
                    self.kafka_producer.produce(topic, key='HEARTBEAT', value=json.dumps({}).encode('utf-8'))
                except KafkaException as e:
                    if not e.args[0].code() == 36:
                        raise

                return {
                    'subnet_ip': subnet["Subnet"],
                    'overlay_name': self.overlay_config.NAME,
                    'kafka_server': self.kafka_config.BOOTSTRAP_SERVER,
                    'kafka_topic': kafka_topic
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
        pods = self.get(self.etcd_config.PODS_KEY.format(namespace = namespace))
        pods.append(new_pod_config)
        self.put(self.etcd_config.PODS_KEY.format(namespace = namespace), pods)

        # TODO: 给scheduler队列推消息
        # TODO: 接收scheduler回复的Node_id
        nodes = self.get(self.etcd_config.NODES_KEY)
        node_id = nodes[0].id

        # 写etcd Node_id
        pods = self.get(self.etcd_config.PODS_KEY.format(namespace = namespace))
        for i, pod in enumerate(pods):
            if pod.name == new_pod_config.name:
                pods[i].node_id = node_id
                break
        self.put(self.etcd_config.PODS_KEY.format(namespace = namespace), pods)

        # TODO: 给scheduler回ACK

        # 给kubelet队列推消息
        nodes = self.get(self.etcd_config.NODES_KEY)
        for node in nodes:
            if node.id == node_id:
                topic = self.kafka_config.POD_TOPIC.format(name = node.name)
                break
        self.kafka_producer.produce(topic, key='ADD', value=json.dumps(pod_json).encode('utf-8'))
        print(f'[INFO]Producing one message to topic {topic}')

        # 写etcd status
        pods = self.get(self.etcd_config.PODS_KEY.format(namespace=namespace))
        for i, pod in enumerate(pods):
            if pod.name == new_pod_config.name:
                pods[i].status = POD_STATUS.RUNNING
                break
        self.put(self.etcd_config.PODS_KEY.format(namespace=namespace), pods)
        return ''

    def update_pod(self):
        pass

    def delete_pod(self):
        pass


if __name__ == '__main__':
    api_server = ApiServer(URIConfig, EtcdConfig, OverlayConfig, KafkaConfig)
    api_server.run()