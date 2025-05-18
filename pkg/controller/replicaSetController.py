import time
import threading
import json
import copy
from pkg.config.uriConfig import URIConfig
from pkg.apiServer.apiClient import ApiClient
from pkg.config.replicaSetConfig import ReplicaSetConfig
from pkg.config.podConfig import PodConfig
import random
import string

class ReplicaSetController:
    def __init__(self, uri_config):
        print('[INFO]ReplicaSetController starting...')
        self.uri_config = uri_config
        self.api_client = ApiClient(uri_config.HOST, uri_config.PORT)
        
        # 控制器状态
        self.running = False
        self.main_thread = None
        self.reconcile_interval = 5  # 调整循环间隔，单位秒
        
        # 用于生成新副本的计数器
        self.replica_counters = {}  # 格式: {(base_pod_name): count}

    def get_all_replica_sets(self):
        """获取所有ReplicaSet配置"""
        try:
            url = self.uri_config.GLOBAL_REPLICA_SETS_URL
            response = self.api_client.get(url)
            # print(f"response: {response}")
            if response:
                print(f"[INFO]Found {len(response)} ReplicaSets")
                return response
            else:
                # print("[ERROR]Failed to get ReplicaSets")
                print("[INFO]No ReplicaSets found")
        except Exception as e:
            print(f"[ERROR]Failed to get ReplicaSets: {str(e)}")
        return []

    def get_pods_for_namespace(self, namespace):
        """获取指定命名空间的所有Pod"""
        try:
            url = self.uri_config.PODS_URL.format(namespace=namespace)
            response = self.api_client.get(url)
            if response:
                return response
            else:
                print(f"[ERROR]Failed to get pods for namespace {namespace}")
        except Exception as e:
            print(f"[ERROR]Failed to get pods for namespace {namespace}: {str(e)}")
        return []

    def get_pod_config(self, namespace, name):
        """获取指定Pod的配置"""
        try:
            url = self.uri_config.POD_SPEC_URL.format(namespace=namespace, name=name)
            response = self.api_client.get(url)
            if response:
                return response
            else:
                print(f"[ERROR]Failed to get pod config for {name}")
        except Exception as e:
            print(f"[ERROR]Failed to get pod config for {name}: {str(e)}")
        return None
    
    def generate_unique_uid(self,existing_names, length=6,base_pod_name=''):
        while True:
            uid = ''.join(random.choices(string.ascii_lowercase + string.digits, k=length))
            candidate = f"{base_pod_name}-{uid}"
            if candidate not in existing_names:
                return candidate,uid

    def create_pod_from_template(self, namespace, base_pod_name, namespace_pods):
        """根据基础Pod创建副本"""
        # 获取基础Pod的配置
        base_pod = self.get_pod_config(namespace, base_pod_name)
        print(f"[INFO]Base pod config: {base_pod}")
        if not base_pod:
            print(f"[ERROR]Failed to get base pod {base_pod_name}")
            return None
        
        # 避免重复
        existing_names = set()
        for pod_entry in namespace_pods:
            if len(pod_entry) == 1:
                pod_name = list(pod_entry.keys())[0]
                existing_names.add(pod_name)

        replica_name,uid = self.generate_unique_uid(existing_names,6,base_pod_name)
        
        # 复制配置并修改
        pod_config = copy.deepcopy(base_pod)
        pod_config['metadata']['name'] = replica_name
        
        if pod_config['spec'] and pod_config['spec'].get('containers'): #如果存在
            for container in pod_config['spec']['containers']:
                if 'name' in container:
                    container['name'] = f"{container['name']}-{uid}"
                
        print(f"[INFO]Modified pod config for {replica_name}: {pod_config}")
        
        # 创建Pod
        try:
            url = self.uri_config.POD_SPEC_URL.format(namespace=namespace, name=replica_name)
            response = self.api_client.post(url, pod_config)
            
            if response:
                print(f"[INFO]Created Pod {replica_name} based on {base_pod_name}")
                return replica_name
            else:
                print(f"[ERROR]Failed to create Pod {replica_name}")
        except Exception as e:
            print(f"[ERROR]Error creating Pod {replica_name}: {str(e)}")
        
        return None

    def delete_pod(self, namespace, name):
        """删除指定的Pod"""
        try:
            url = self.uri_config.POD_SPEC_URL.format(namespace=namespace, name=name)
            response = self.api_client.delete(url)
            
            if response:
                print(f"[INFO]Deleted Pod {name}")
                return True
            else:
                print(f"[ERROR]Failed to delete Pod {name}")
        except Exception as e:
            print(f"[ERROR]Error deleting Pod {name}: {str(e)}")
            
        return False

    def update_replica_set(self, namespace, name, rs_data):
        """更新ReplicaSet状态"""
        try:
            url = self.uri_config.REPLICA_SET_SPEC_URL.format(namespace=namespace, name=name)
            response = self.api_client.put(url, rs_data)
            
            if response:
                print(f"[INFO]Updated ReplicaSet {name}")
                return True
            else:
                print(f"[ERROR]Failed to update ReplicaSet {name}")
        except Exception as e:
            print(f"[ERROR]Error updating ReplicaSet {name}: {str(e)}")
            
        return False

    def is_pod_alive(self, pod_data):
        """检查Pod是否活跃"""
        status = pod_data.get('status')
        if status not in ['Failed', 'Unknown', 'KILLED', 'STOPPING']:
            return True
        return False

    def reconcile(self):
        """协调所有ReplicaSet的状态"""
        try:
            # 获取所有ReplicaSet
            all_rs_data = self.get_all_replica_sets()
            
            # 处理每个ReplicaSet
            for rs_entry in all_rs_data:
                if len(rs_entry) != 1:
                    continue
                    
                rs_name = list(rs_entry.keys())[0]
                rs = rs_entry[rs_name]
                
                namespace = rs['metadata']['namespace']
                desired_replicas = rs['spec']['replicas']
                
                print(f"[INFO]Reconciling ReplicaSet {rs_name} in namespace {namespace}")
                
                # 获取所有Pod组
                if 'pod_instances' not in rs or not rs['pod_instances']:
                    # 没有Pod组，先跳过
                    print(f"[INFO]ReplicaSet {rs_name} has no pod instances")
                    continue
                    
                # 获取该命名空间的所有Pod
                namespace_pods = self.get_pods_for_namespace(namespace)
                pods_map = {}
                
                # 构建Pod名称到数据的映射
                for pod_entry in namespace_pods:
                    if len(pod_entry) == 1:
                        pod_name = list(pod_entry.keys())[0]
                        pods_map[pod_name] = pod_entry[pod_name]
                
                # 处理每个Pod组
                updated_groups = [] # 这个是更新完毕的pod_instances，如果更新了，就替换掉原来的
                isModified = False
                for group in rs['pod_instances']:
                    if not group:
                        continue
                        
                    # 基础Pod名称
                    base_pod_name = group[0] # 后续可能需要考虑base_pod挂掉导致拿到的base_pod_name不对的问题，现在先不管
                    print(f"[INFO]Processing group with base pod {base_pod_name}")
                    
                    # 检查组内所有Pod的状态
                    alive_pods = []
                    for pod_name in group:
                        if pod_name in pods_map and self.is_pod_alive(pods_map[pod_name]):
                            alive_pods.append(pod_name)
                    print(f"[INFO]Original alive pods in group {base_pod_name}: {alive_pods}")
                    
                    # 计算这个组需要创建或删除的Pod数量
                    diff = desired_replicas - len(alive_pods)
                    
                    if diff > 0:
                        # 需要创建更多Pod
                        isModified = True
                        print(f"[INFO]Group {base_pod_name} needs {diff} more pods")
                            
                        # 创建新Pod
                        for _ in range(diff):
                            replica_name = self.create_pod_from_template(
                                namespace, 
                                base_pod_name,
                                namespace_pods
                            )
                            
                            if replica_name:
                                alive_pods.append(replica_name)
                                
                    elif diff < 0:
                        # 需要删除多余的Pod，这个还没测行不行，而且测试也会比较麻烦
                        print(f"WARNING]Delete haven't been tested yet")
                        isModified = True
                        print(f"[INFO]Group {base_pod_name} has {abs(diff)} excess pods")
                        
                        # 从后往前删除
                        to_delete = abs(diff)
                        for _ in range(to_delete):
                            if not alive_pods:
                                break
                                
                            pod_to_delete = alive_pods.pop()
                            self.delete_pod(namespace, pod_to_delete)
                    
                    # 保存更新后的组
                    if alive_pods:
                        updated_groups.append(alive_pods)
                    print(f"[INFO]Updated group {base_pod_name}: {updated_groups}")
                
                # 更新ReplicaSet状态
                if isModified:
                    rs['pod_instances'] = updated_groups
                    rs['current_replicas'] = [len(group) for group in updated_groups]
                    
                    # # 计算总Pod数以判断状态
                    total_pods = sum(len(group) for group in updated_groups)
                    total_expected = desired_replicas * len(updated_groups) if updated_groups else 0
                    # 这里认为status是一个数组
                    rs['status'] = []
                    for group in updated_groups:
                        if len(group) == desired_replicas:
                            rs['status'].append('Ready')
                        else:
                            rs['status'].append('Scaling')
                    
                    print(f"[INFO]ReplicaSet {rs_name} config: {rs}")
                    
                    # 更新ReplicaSet
                    self.update_replica_set(namespace, rs_name, rs)
                    
                    print(f"[INFO]ReplicaSet {rs_name} reconciled: {total_pods}/{total_expected} total pods")
                else:
                    print(f"[INFO]No changes needed for ReplicaSet {rs_name}")
                
        except Exception as e:
            print(f"[ERROR]Error in reconcile: {str(e)}")

    def main_loop(self):
        """控制器主循环"""
        print("[INFO]ReplicaSetController main loop started")
        
        while self.running:
            try:
                self.reconcile()
            except Exception as e:
                print(f"[ERROR]Unhandled exception in main loop: {str(e)}")
                
            # 等待下一次循环
            time.sleep(self.reconcile_interval)
            
        print("[INFO]ReplicaSetController main loop terminated")

    def start(self):
        """启动控制器"""
        if self.running:
            print("[INFO]ReplicaSetController is already running")
            return
            
        self.running = True
        self.main_thread = threading.Thread(target=self.main_loop)
        self.main_thread.daemon = True
        self.main_thread.start()
        
        print("[INFO]ReplicaSetController started")

    def stop(self):
        """停止控制器"""
        if not self.running:
            print("[INFO]ReplicaSetController is not running")
            return
            
        print("[INFO]Stopping ReplicaSetController...")
        self.running = False
        
        if self.main_thread and self.main_thread.is_alive():
            self.main_thread.join(timeout=10)
            
        print("[INFO]ReplicaSetController stopped")