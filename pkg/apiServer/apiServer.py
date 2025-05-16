import etcd3
import json
import pickle
import docker
from docker.errors import APIError
from flask import Flask, request
from confluent_kafka import Producer, KafkaException
from confluent_kafka.admin import AdminClient, NewTopic
import platform

from pkg.apiObject.pod import STATUS as POD_STATUS

from pkg.config.uriConfig import URIConfig
from pkg.config.etcdConfig import EtcdConfig
from pkg.config.overlayConfig import OverlayConfig
from pkg.config.kafkaConfig import KafkaConfig
from pkg.config.nodeConfig import NodeConfig
from pkg.config.podConfig import PodConfig
from pkg.config.replicaSetConfig import ReplicaSetConfig
from pkg.config.hpaConfig import HorizontalPodAutoscalerConfig

class ApiServer():
    def __init__(self, uri_config : URIConfig, etcd_config: EtcdConfig, overlay_config: OverlayConfig, kafka_config : KafkaConfig):
        print('[INFO]ApiServer starting...')
        self.uri_config = uri_config
        self.etcd_config = etcd_config
        self.overlay_config = overlay_config
        self.kafka_config = kafka_config

        self.app = Flask(__name__)
        self.etcd = etcd3.client(host=etcd_config.HOST, port=etcd_config.PORT)

        if platform.system() == 'Windows':
            self.docker = docker.DockerClient(base_url='npipe:////./pipe/docker_engine', version='1.25', timeout=5)
        else:
            self.docker = docker.DockerClient(base_url='unix://var/run/docker.sock', version='1.25', timeout=5)
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
        # node相关
        self.app.route(config.NODE_SPEC_URL, methods=['POST'])(self.add_node)
        # pod相关
        self.app.route(config.GLOBAL_PODS_URL, methods=['GET'])(self.get_pods)
        self.app.route(config.POD_SPEC_URL, methods=['GET'])(self.get_pod)
        self.app.route(config.POD_SPEC_URL, methods=['POST'])(self.add_pod)
        self.app.route(config.POD_SPEC_URL, methods=['PUT'])(self.update_pod)
        self.app.route(config.POD_SPEC_URL, methods=['DELETE'])(self.delete_pod)
        
        # replicaSet相关
        # 三种不同的读取逻辑，可以先不着急写，读取全部的rs，读取某个namespace下的rs，读取某个rs
        self.app.route(config.GLOBAL_REPLICA_SETS_URL, methods=['GET'])(self.get_replica_sets)
        # 这个有确定的namespace
        self.app.route(config.REPLICA_SETS_URL, methods=['GET'])(self.get_replica_sets)
        # 这个有确定的namespace和name
        self.app.route(config.REPLICA_SET_SPEC_URL, methods=['GET'])(self.get_replica_set)
        # 创建rs
        self.app.route(config.REPLICA_SET_SPEC_URL, methods=['POST'])(self.create_replica_set)
        # 更新rs
        self.app.route(config.REPLICA_SET_SPEC_URL, methods=['PUT'])(self.update_replica_set)
        # 删除rs
        self.app.route(config.REPLICA_SET_SPEC_URL, methods=['DELETE'])(self.delete_replica_set)
        
        # hpa相关
        # 三种不同的读取逻辑，可以先不着急写，读取全部的hpa，读取某个namespace下的hpa，读取某个hpa
        self.app.route(config.GLOBAL_HPA_URL, methods=['GET'])(self.get_global_hpas)
        self.app.route(config.HPA_SPEC_URL, methods=['GET'])(self.get_hpas)
        self.app.route(config.HPA_SPEC_URL, methods=['GET'])(self.get_hpa)
        # 创建hpa
        self.app.route(config.HPA_SPEC_URL, methods=['POST'])(self.create_hpa)
        # 更新hpa
        self.app.route(config.HPA_SPEC_URL, methods=['PUT'])(self.update_hpa)
        # 删除hpa
        self.app.route(config.HPA_SPEC_URL, methods=['DELETE'])(self.delete_hpa)

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
    
    def get_global_replica_sets(self):
        print('[INFO]Get global ReplicaSets.')
        key = self.etcd_config.REPLICA_SETS_KEY
        replica_sets = self.get(key)
        
        # 格式化输出
        result = []
        for rs in replica_sets:
            result.append({
                'name': rs.name,
                'namespace': rs.namespace,
                'replicas': f'{rs.current_replicas}/{rs.desired_replicas}',
                'selector': rs.selector,
                'labels': rs.labels,
                'status': rs.status
            })
        
        return json.dumps(result)
    
    # 支持global和某个namesapce
    def get_replica_sets(self, namespace):
        print(f'[INFO]Get all ReplicaSets in namespace {namespace}')
        key = self.etcd_config.REPLICA_SETS_KEY.format(namespace=namespace)
        replica_sets = self.get(key)
        
        # 格式化输出
        result = []
        for rs in replica_sets:
            result.append({
                'name': rs.name,
                'namespace': rs.namespace,
                'replicas': f'{rs.current_replicas}/{rs.desired_replicas}',
                'selector': rs.selector,
                'labels': rs.labels,
                'status': rs.status
            })
        
        return json.dumps(result)
    
    def get_replica_set(self, namespace, name):
        """获取特定ReplicaSet的详细信息"""
        print(f'[INFO]Get ReplicaSet {name} in namespace {namespace}')
        key = self.etcd_config.REPLICA_SETS_KEY.format(namespace=namespace)
        replica_sets = self.get(key)
        
        for rs in replica_sets:
            if rs.name == name:
                result = {
                    'name': rs.name,
                    'namespace': rs.namespace,
                    'replicas': f'{rs.current_replicas}/{rs.desired_replicas}',
                    'selector': rs.selector,
                    'labels': rs.labels,
                    'pod_instances': rs.pod_instances,
                    'status': rs.status
                }
                return json.dumps(result)
        
        return json.dumps({'error': f'ReplicaSet {name} not found in namespace {namespace}'}), 404

    # replicaset在api server这里最重要的函数，决定了存入的类型
    def create_replica_set(self, namespace, name):
        """创建一个新的ReplicaSet"""
        print(f'[INFO]Create ReplicaSet {name} in namespace {namespace}')
        
        try:
            rs_json = request.json
            if isinstance(rs_json, str):
                rs_json = json.loads(rs_json)
            
            # 检查名称是否匹配
            if rs_json.get('metadata', {}).get('name') != name:
                return json.dumps({'error': 'Name in URL does not match name in request body'}), 400
            
            # 创建ReplicaSetConfig
            rs_config = ReplicaSetConfig(rs_json)
            
            # 初始化运行时状态
            rs_config.status = 'PENDING'
            rs_config.current_replicas = 0
            rs_config.pod_instances = []
            
            # 存储到etcd
            key = self.etcd_config.REPLICA_SETS_KEY.format(namespace=namespace)
            replica_sets = self.get(key)
            
            # 检查是否已存在
            for rs in replica_sets:
                if rs.name == name:
                    return json.dumps({'error': f'ReplicaSet {name} already exists'}), 409
            
            # 添加
            replica_sets.append(rs_config)
            self.put(key, replica_sets)
            
            return json.dumps({'message': f'ReplicaSet {name} created successfully'})
        except Exception as e:
            print(f'[ERROR]Failed to create ReplicaSet: {str(e)}')
            return json.dumps({'error': str(e)}), 500

    def update_replica_set(self, namespace, name):
        """更新现有的ReplicaSet"""
        print(f'[INFO]Update ReplicaSet {name} in namespace {namespace}')
        
        try:
            rs_json = request.json
            if isinstance(rs_json, str):
                rs_json = json.loads(rs_json)
            
            # 检查名称是否匹配
            if rs_json.get('metadata', {}).get('name') != name:
                return json.dumps({'error': 'Name in URL does not match name in request body'}), 400
            
            # 获取现有ReplicaSet
            key = self.etcd_config.REPLICA_SETS_KEY.format(namespace=namespace)
            replica_sets = self.get(key)
            
            found = False
            for i, rs in enumerate(replica_sets):
                if rs.name == name:
                    # 创建更新后的配置
                    updated_config = ReplicaSetConfig(rs_json)
                    
                    # 保留原有的运行时信息
                    updated_config.status = rs.status
                    updated_config.current_replicas = rs.current_replicas
                    updated_config.pod_instances = rs.pod_instances
                    
                    # 更新
                    replica_sets[i] = updated_config
                    found = True
                    break
            
            if not found:
                return json.dumps({'error': f'ReplicaSet {name} not found'}), 404
            
            # 保存更新
            self.put(key, replica_sets)
            
            return json.dumps({'message': f'ReplicaSet {name} updated successfully'})
        except Exception as e:
            print(f'[ERROR]Failed to update ReplicaSet: {str(e)}')
            return json.dumps({'error': str(e)}), 500

    def delete_replica_set(self, namespace, name):
        """删除ReplicaSet及其所有Pod"""
        print(f'[INFO]Delete ReplicaSet {name} in namespace {namespace}')
        
        try:
            # 获取ReplicaSet
            key = self.etcd_config.REPLICA_SETS_KEY.format(namespace=namespace)
            replica_sets = self.get(key)
            
            target_rs = None
            updated_replica_sets = []
            
            for rs in replica_sets:
                if rs.name == name:
                    target_rs = rs
                else:
                    updated_replica_sets.append(rs)
            
            if not target_rs:
                return json.dumps({'error': f'ReplicaSet {name} not found'}), 404
            
            # 删除所有关联的Pod
            if hasattr(target_rs, 'pod_instances') and target_rs.pod_instances:
                pods_key = self.etcd_config.PODS_KEY.format(namespace=namespace)
                pods = self.get(pods_key)
                
                updated_pods = []
                deleted_pods = []
                
                for pod in pods:
                    if hasattr(pod, 'owner_reference') and pod.owner_reference == name:
                        deleted_pods.append(pod)
                    else:
                        updated_pods.append(pod)
                
                # 更新Pod列表
                self.put(pods_key, updated_pods)
                
                # 向Kubelet发送删除消息
                for pod in deleted_pods:
                    nodes = self.get(self.etcd_config.NODES_KEY)
                    for node in nodes:
                        if node.id == pod.node_id:
                            topic = self.kafka_config.POD_TOPIC.format(name=node.name)
                            self.kafka.produce(topic, key='DELETE', value=json.dumps(vars(pod)).encode('utf-8'))
                            print(f'[INFO]Sent DELETE message for pod {pod.name} to topic {topic}')
            
            # 更新ReplicaSet列表
            self.put(key, updated_replica_sets)
            
            return json.dumps({'message': f'ReplicaSet {name} and its pods deleted successfully'})
        except Exception as e:
            print(f'[ERROR]Failed to delete ReplicaSet: {str(e)}')
            return json.dumps({'error': str(e)}), 500
        
    def get_hpas(self, namespace=None):
        """获取HPA列表"""
        print(f'[INFO]Get HPAs in namespace {namespace if namespace else "all"}')
        
        # 如果提供了namespace参数，获取指定命名空间的HPA
        if namespace:
            key = self.etcd_config.HPA_KEY.format(namespace=namespace)
            hpas = self.get(key)
        else:
            # 否则获取所有命名空间的HPA
            hpas = []
            for ns in self._get_namespaces():
                key = self.etcd_config.HPA_KEY.format(namespace=ns)
                ns_hpas = self.get(key)
                hpas.extend(ns_hpas)
        
        # 格式化输出
        result = []
        for hpa in hpas:
            result.append({
                'name': hpa.name,
                'namespace': hpa.namespace,
                'target': f'{hpa.target_kind}/{hpa.target_name}',
                'min_replicas': hpa.min_replicas,
                'max_replicas': hpa.max_replicas,
                'current_replicas': getattr(hpa, 'current_replicas', 0),
                'metrics': hpa.metrics
            })
        
        return json.dumps(result)
    
    def get_hpa(self, namespace, name):
        """获取特定HPA的详细信息"""
        print(f'[INFO]Get HPA {name} in namespace {namespace}')
        key = self.etcd_config.HPA_KEY.format(namespace=namespace)
        hpas = self.get(key)
        
        for hpa in hpas:
            if hpa.name == name:
                result = {
                    'name': hpa.name,
                    'namespace': hpa.namespace,
                    'target': f'{hpa.target_kind}/{hpa.target_name}',
                    'min_replicas': hpa.min_replicas,
                    'max_replicas': hpa.max_replicas,
                    'current_replicas': hpa.current_replicas,
                    'target_replicas': hpa.target_replicas,
                    'metrics': hpa.metrics,
                    'current_metrics': hpa.current_metrics,
                    'last_scale_time': hpa.last_scale_time,
                    'status': hpa.status
                }
                return json.dumps(result)
        
        return json.dumps({'error': f'HPA {name} not found in namespace {namespace}'}), 404

    def create_hpa(self, namespace, name):
        """创建一个新的HPA"""
        print(f'[INFO]Create HPA {name} in namespace {namespace}')
        
        try:
            hpa_json = request.json
            if isinstance(hpa_json, str):
                hpa_json = json.loads(hpa_json)
            
            # 检查名称是否匹配
            if hpa_json.get('metadata', {}).get('name') != name:
                return json.dumps({'error': 'Name in URL does not match name in request body'}), 400
            
            # 创建HPA配置
            hpa_config = HorizontalPodAutoscalerConfig(hpa_json)
            
            # 检查目标资源是否存在
            if hpa_config.target_kind == 'ReplicaSet':
                rs_key = self.etcd_config.REPLICA_SETS_KEY.format(namespace=namespace)
                replica_sets = self.get(rs_key)
                
                target_found = False
                for rs in replica_sets:
                    if rs.name == hpa_config.target_name:
                        target_found = True
                        rs.hpa_controlled = True
                        break
                
                if not target_found:
                    return json.dumps({'error': f'Target ReplicaSet {hpa_config.target_name} not found'}), 404
                
                # 更新ReplicaSet的HPA控制状态
                self.put(rs_key, replica_sets)
            
            # 存储HPA
            key = self.etcd_config.HPA_KEY.format(namespace=namespace)
            hpas = self.get(key)
            
            # 检查是否已存在
            for hpa in hpas:
                if hpa.name == name:
                    return json.dumps({'error': f'HPA {name} already exists'}), 409
            
            # 添加
            hpas.append(hpa_config)
            self.put(key, hpas)
            
            return json.dumps({'message': f'HPA {name} created successfully'})
        except Exception as e:
            print(f'[ERROR]Failed to create HPA: {str(e)}')
            return json.dumps({'error': str(e)}), 500

    def update_hpa(self, namespace, name):
        """更新现有的HPA"""
        print(f'[INFO]Update HPA {name} in namespace {namespace}')
        
        try:
            hpa_json = request.json
            if isinstance(hpa_json, str):
                hpa_json = json.loads(hpa_json)
            
            # 检查名称是否匹配
            if hpa_json.get('metadata', {}).get('name') != name:
                return json.dumps({'error': 'Name in URL does not match name in request body'}), 400
            
            # 获取现有HPA
            key = self.etcd_config.HPA_KEY.format(namespace=namespace)
            hpas = self.get(key)
            
            found = False
            for i, hpa in enumerate(hpas):
                if hpa.name == name:
                    # 创建更新后的配置
                    updated_config = HorizontalPodAutoscalerConfig(hpa_json)
                    
                    # 保留原有的运行时信息
                    updated_config.status = hpa.status
                    updated_config.current_replicas = hpa.current_replicas
                    updated_config.target_replicas = hpa.target_replicas
                    updated_config.current_metrics = hpa.current_metrics
                    updated_config.last_scale_time = hpa.last_scale_time
                    
                    # 处理目标变更
                    if hpa.target_kind != updated_config.target_kind or hpa.target_name != updated_config.target_name:
                        # 旧目标移除HPA控制
                        if hpa.target_kind == 'ReplicaSet':
                            self._release_hpa_control(namespace, hpa.target_name)
                        
                        # 新目标添加HPA控制
                        if updated_config.target_kind == 'ReplicaSet':
                            rs_key = self.etcd_config.REPLICA_SETS_KEY.format(namespace=namespace)
                            replica_sets = self.get(rs_key)
                            
                            target_found = False
                            for rs in replica_sets:
                                if rs.name == updated_config.target_name:
                                    rs.hpa_controlled = True
                                    target_found = True
                                    break
                            
                            if not target_found:
                                return json.dumps({'error': f'Target ReplicaSet {updated_config.target_name} not found'}), 404
                            
                            # 更新ReplicaSet
                            self.put(rs_key, replica_sets)
                    
                    # 更新HPA
                    hpas[i] = updated_config
                    found = True
                    break
            
            if not found:
                return json.dumps({'error': f'HPA {name} not found'}), 404
            
            # 保存更新
            self.put(key, hpas)
            
            return json.dumps({'message': f'HPA {name} updated successfully'})
        except Exception as e:
            print(f'[ERROR]Failed to update HPA: {str(e)}')
            return json.dumps({'error': str(e)}), 500

    def delete_hpa(self, namespace, name):
        """删除HPA"""
        print(f'[INFO]Delete HPA {name} in namespace {namespace}')
        
        try:
            # 获取HPA
            key = self.etcd_config.HPA_KEY.format(namespace=namespace)
            hpas = self.get(key)
            
            target_hpa = None
            updated_hpas = []
            
            for hpa in hpas:
                if hpa.name == name:
                    target_hpa = hpa
                else:
                    updated_hpas.append(hpa)
            
            if not target_hpa:
                return json.dumps({'error': f'HPA {name} not found'}), 404
            
            # 移除目标资源的HPA控制标记
            if target_hpa.target_kind == 'ReplicaSet':
                self._release_hpa_control(namespace, target_hpa.target_name)
            
            # 更新HPA列表
            self.put(key, updated_hpas)
            
            return json.dumps({'message': f'HPA {name} deleted successfully'})
        except Exception as e:
            print(f'[ERROR]Failed to delete HPA: {str(e)}')
            return json.dumps({'error': str(e)}), 500
        
    def _release_hpa_control(self, namespace, replica_set_name):
        """移除ReplicaSet的HPA控制标记"""
        rs_key = self.etcd_config.REPLICA_SETS_KEY.format(namespace=namespace)
        replica_sets = self.get(rs_key)
        
        for rs in replica_sets:
            if rs.name == replica_set_name:
                rs.hpa_controlled = False
                break
        
        self.put(rs_key, replica_sets)
            
if __name__ == '__main__':
    api_server = ApiServer(URIConfig, EtcdConfig, OverlayConfig, KafkaConfig)
    api_server.run()