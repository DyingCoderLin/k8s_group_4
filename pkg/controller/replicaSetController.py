import time
import threading
import json
import uuid
import requests
import copy

from pkg.config.uriConfig import URIConfig
from pkg.apiObject.replicaSet import ReplicaSet, STATUS as RS_STATUS
from pkg.config.podConfig import PodConfig

class ReplicaSetController:
    def __init__(self, uri_config):
        print('[INFO]ReplicaSetController starting...')
        self.uri_config = uri_config
        self.base_url = f"http://{uri_config.HOST}:{uri_config.PORT}"
        self.stop_flag = False
        self.reconcile_interval = 10  # 调整循环间隔，单位秒

    def get_all_replica_sets(self):
        """从API Server获取所有ReplicaSet"""
        replica_sets = []
        
        # 使用全局ReplicaSet URL获取所有ReplicaSet
        url = f"{self.base_url}{self.uri_config.GLOBAL_REPLICA_SETS_URL}"
        try:
            response = requests.get(url)
            if response.status_code == 200:
                data = response.json()
                if isinstance(data, list):
                    for rs_data in data:
                        # 构建ReplicaSet对象
                        rs = ReplicaSet(rs_data)
                        replica_sets.append(rs)
                elif isinstance(data, dict) and 'replica_sets' in data:
                    for rs_data in data['replica_sets']:
                        rs = ReplicaSet(rs_data)
                        replica_sets.append(rs)
            else:
                print(f"[ERROR]Failed to get ReplicaSets: {response.status_code}")
        except Exception as e:
            print(f"[ERROR]Exception when getting ReplicaSets: {str(e)}")
            
        return replica_sets

    def get_pods_for_replica_set(self, rs):
        """获取属于特定ReplicaSet的所有Pod"""
        all_pods = []
        
        # 获取特定命名空间下的所有Pod
        url = f"{self.base_url}{self.uri_config.PODS_URL.format(namespace=rs.namespace)}"
        try:
            response = requests.get(url)
            if response.status_code == 200:
                pods_data = response.json()
                # 筛选出属于当前ReplicaSet的Pod
                for pod_data in pods_data:
                    if ('metadata' in pod_data and 
                        'ownerReferences' in pod_data['metadata'] and 
                        any(ref['name'] == rs.name for ref in pod_data['metadata']['ownerReferences'])):
                        all_pods.append(pod_data)
        except Exception as e:
            print(f"[ERROR]Exception when getting Pods for ReplicaSet {rs.name}: {str(e)}")
            
        return all_pods

    def create_pod_for_replica_set(self, rs):
        """为ReplicaSet创建新的Pod"""
        # 创建Pod配置
        pod_template = copy.deepcopy(rs.pod_template)
        
        # 生成唯一的Pod名称
        pod_name = f"{rs.name}-{uuid.uuid4().hex[:5]}"
        pod_template['metadata']['name'] = pod_name
        
        # 添加所有者引用
        if 'metadata' not in pod_template:
            pod_template['metadata'] = {}
        pod_template['metadata']['ownerReferences'] = [{
            'apiVersion': 'v1',
            'kind': 'ReplicaSet',
            'name': rs.name,
            'uid': rs.name  # 简化，实际应使用UID
        }]
        
        # 通过API Server创建Pod
        url = f"{self.base_url}{self.uri_config.POD_SPEC_URL.format(namespace=rs.namespace, name=pod_name)}"
        try:
            response = requests.post(url, json=pod_template)
            if response.status_code == 200:
                print(f"[INFO]Created Pod {pod_name} for ReplicaSet {rs.name}")
                # 更新ReplicaSet中的Pod列表
                rs.add_pod(pod_name)
                return pod_name
            else:
                print(f"[ERROR]Failed to create Pod {pod_name}: {response.status_code}")
                return None
        except Exception as e:
            print(f"[ERROR]Exception when creating Pod for ReplicaSet {rs.name}: {str(e)}")
            return None

    def delete_pod_from_replica_set(self, rs, pod_name):
        """从ReplicaSet中删除Pod"""
        # 通过API Server删除Pod
        url = f"{self.base_url}{self.uri_config.POD_SPEC_URL.format(namespace=rs.namespace, name=pod_name)}"
        try:
            response = requests.delete(url)
            if response.status_code == 200:
                print(f"[INFO]Deleted Pod {pod_name} from ReplicaSet {rs.name}")
                # 更新ReplicaSet中的Pod列表
                rs.remove_pod(pod_name)
                return True
            else:
                print(f"[ERROR]Failed to delete Pod {pod_name}: {response.status_code}")
                return False
        except Exception as e:
            print(f"[ERROR]Exception when deleting Pod from ReplicaSet {rs.name}: {str(e)}")
            return False

    def update_replica_set_in_api_server(self, rs):
        """更新API Server中的ReplicaSet状态"""
        url = f"{self.base_url}{self.uri_config.REPLICA_SET_SPEC_URL.format(namespace=rs.namespace, name=rs.name)}"
        
        # 构建更新数据
        update_data = {
            'metadata': {
                'name': rs.name,
                'namespace': rs.namespace
            },
            'status': rs.status,
            'current_replicas': rs.current_replicas,
            'pod_instances': rs.pod_instances
        }
        
        try:
            response = requests.put(url, json=update_data)
            if response.status_code != 200:
                print(f"[ERROR]Failed to update ReplicaSet {rs.name}: {response.status_code}")
        except Exception as e:
            print(f"[ERROR]Exception when updating ReplicaSet {rs.name}: {str(e)}")

    def reconcile(self, rs):
        """协调ReplicaSet的期望状态和实际状态"""
        # 获取当前Pod列表
        pods = self.get_pods_for_replica_set(rs)
        rs.current_replicas = len(pods)
        rs.pod_instances = [pod['metadata']['name'] for pod in pods]
        
        # 判断是否需要扩缩容
        if rs.needs_scaling():
            if rs.current_replicas < rs.desired_replicas:
                # 需要扩容
                scale_up_count = rs.scale_up()
                print(f'[INFO]ReplicaSet {rs.name} needs to scale up by {scale_up_count}')
                for _ in range(scale_up_count):
                    self.create_pod_for_replica_set(rs)
            elif rs.current_replicas > rs.desired_replicas:
                # 需要缩容
                scale_down_count = rs.scale_down()
                print(f'[INFO]ReplicaSet {rs.name} needs to scale down by {scale_down_count}')
                for _ in range(scale_down_count):
                    if rs.pod_instances:
                        # 删除最后一个Pod
                        pod_to_delete = rs.pod_instances[-1]
                        self.delete_pod_from_replica_set(rs, pod_to_delete)
        
        # 更新ReplicaSet状态
        rs.update_status()
        self.update_replica_set_in_api_server(rs)
        print(f'[INFO]ReplicaSet {rs.name} reconciled: {rs.current_replicas}/{rs.desired_replicas} pods')

    def reconcile_loop(self):
        """主循环，定期协调所有ReplicaSet"""
        while not self.stop_flag:
            try:
                # 获取所有ReplicaSet
                replica_sets = self.get_all_replica_sets()
                print(f'[INFO]Found {len(replica_sets)} ReplicaSets to reconcile')
                
                # 对每个ReplicaSet进行协调
                for rs in replica_sets:
                    self.reconcile(rs)
                
                # 等待下一次循环
                time.sleep(self.reconcile_interval)
            except Exception as e:
                print(f'[ERROR]Error in reconcile loop: {str(e)}')
                time.sleep(self.reconcile_interval)

    def run(self):
        """启动控制器"""
        print('[INFO]ReplicaSetController running...')
        self.thread = threading.Thread(target=self.reconcile_loop)
        self.thread.daemon = True
        self.thread.start()

    def stop(self):
        """停止控制器"""
        self.stop_flag = True
        if hasattr(self, 'thread'):
            self.thread.join(timeout=5)
        print('[INFO]ReplicaSetController stopped.')