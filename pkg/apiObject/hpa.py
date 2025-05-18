import datetime
import time
import json
import requests
import threading
from pkg.apiServer.apiClient import ApiClient
from pkg.config.uriConfig import URIConfig
from pkg.config.hpaConfig import HorizontalPodAutoscalerConfig
from pkg.apiObject.replicaSet import ReplicaSet

class STATUS:
    PENDING = 'PENDING'
    RUNNING = 'RUNNING'
    FAILED = 'FAILED'
    SCALING = 'SCALING'

class HorizontalPodAutoscaler:
    def __init__(self, config):
        """初始化HPA对象"""
        # 保存原始配置
        self.config = config
        
        # 基本信息
        self.name = config.name
        self.namespace = config.namespace
        
        # 目标资源
        self.target_kind = config.target_kind
        self.target_name = config.target_name
        
        # 副本数量限制
        self.min_replicas = config.min_replicas
        self.max_replicas = config.max_replicas
        
        # 指标和调整参数
        self.metrics = config.metrics
        self.cooldown_seconds = 60  # 冷却时间，防止频繁扩缩
        
        # 运行时状态
        self.status = STATUS.PENDING
        self.current_replicas = 0
        self.target_replicas = 0
        self.current_metrics = {}
        self.last_scale_time = None
        self.cadvisor_base_url = f"http://{URIConfig.HOST}:8080"
        
        # API通信
        self.api_client = None
        self.uri_config = None
        
        # 开关
        self.running = False
        self.controller_thread = None

    def set_api_client(self, api_client, uri_config=None):
        """设置API客户端，用于与API Server通信"""
        self.api_client = api_client
        self.uri_config = uri_config or URIConfig()
        return self

    def _ensure_api_client(self):
        """确保API客户端已初始化"""
        if not self.api_client:
            self.api_client = ApiClient()
            self.uri_config = URIConfig()

    def to_config_dict(self):
        """将HPA转换为配置字典"""
        hpa_dict = {
            'metadata': {
                'name': self.name,
                'namespace': self.namespace
            },
            'spec': {
                'scaleTargetRef': {
                    'apiVersion': 'apps/v1',
                    'kind': self.target_kind,
                    'name': self.target_name
                },
                'minReplicas': self.min_replicas,
                'maxReplicas': self.max_replicas,
                'metrics': self.metrics
            },
            'status': self.status,
            'current_replicas': self.current_replicas,
            'target_replicas': self.target_replicas,
            'current_metrics': self.current_metrics
        }
        
        # 处理last_scale_time (转换为ISO格式字符串)
        if self.last_scale_time:
            hpa_dict['last_scale_time'] = self.last_scale_time.isoformat()
        else:
            hpa_dict['last_scale_time'] = None
        
        return hpa_dict

    # API操作方法
    def create(self):
        """创建HPA"""
        self._ensure_api_client()
        
        # 构建API路径
        path = self.uri_config.HPA_SPEC_URL.format(
            namespace=self.namespace, 
            name=self.name
        )
        
        # 发送创建请求
        create_result = self.api_client.post(path, self.to_config_dict())
        if not create_result:
            print(f"[ERROR]Failed to create HPA {self.name}")
            return False
        
        print(f"[INFO]HPA {self.name} created successfully")
        return True

    @staticmethod
    def get(namespace, name, api_client=None, uri_config=None):
        """获取HPA（静态方法）"""
        # 初始化API客户端
        _api_client = api_client or ApiClient()
        _uri_config = uri_config or URIConfig()
        
        # 构建API路径
        path = _uri_config.HPA_SPEC_URL.format(
            namespace=namespace, 
            name=name
        )
        
        # 获取HPA配置
        hpa_config_dict = _api_client.get(path)
        if not hpa_config_dict:
            print(f"[ERROR]HPA {name} not found in namespace {namespace}")
            return None
        
        # 创建HPAConfig
        try:
            hpa_config = HorizontalPodAutoscalerConfig(hpa_config_dict)
            
            # 创建HPA并设置API客户端
            hpa = HorizontalPodAutoscaler(hpa_config)
            hpa.set_api_client(_api_client, _uri_config)
            
            # 复制运行时状态
            if 'status' in hpa_config_dict:
                hpa.status = hpa_config_dict['status']
            if 'current_replicas' in hpa_config_dict:
                hpa.current_replicas = hpa_config_dict['current_replicas']
            if 'target_replicas' in hpa_config_dict:
                hpa.target_replicas = hpa_config_dict['target_replicas']
            if 'current_metrics' in hpa_config_dict:
                hpa.current_metrics = hpa_config_dict['current_metrics']
            if 'last_scale_time' in hpa_config_dict and hpa_config_dict['last_scale_time']:
                try:
                    hpa.last_scale_time = datetime.datetime.fromisoformat(hpa_config_dict['last_scale_time'])
                except:
                    pass
            
            return hpa
        except Exception as e:
            print(f"[ERROR]Failed to parse HPA config: {e}")
            return None

    @staticmethod
    def list(namespace='default', api_client=None, uri_config=None):
        """列出命名空间下的所有HPA（静态方法）"""
        # 初始化API客户端
        _api_client = api_client or ApiClient()
        _uri_config = uri_config or URIConfig()
        
        # 构建API路径
        path = _uri_config.HPAS_URL.format(namespace=namespace)
        
        # 获取HPA列表
        hpa_list_data = _api_client.get(path)
        if not hpa_list_data:
            return []
        
        # 转换为HPA对象
        hpas = []
        
        if isinstance(hpa_list_data, list):
            for hpa_data in hpa_list_data:
                try:
                    hpa_config = HorizontalPodAutoscalerConfig(hpa_data)
                    hpa = HorizontalPodAutoscaler(hpa_config)
                    hpa.set_api_client(_api_client, _uri_config)
                    
                    # 设置运行时状态
                    if 'status' in hpa_data:
                        hpa.status = hpa_data['status']
                    if 'current_replicas' in hpa_data:
                        hpa.current_replicas = hpa_data['current_replicas']
                    
                    hpas.append(hpa)
                except Exception as e:
                    print(f"[ERROR]Failed to parse HPA: {e}")
        
        return hpas

    def update(self):
        """更新HPA"""
        self._ensure_api_client()
        
        # 构建API路径
        path = self.uri_config.HPA_SPEC_URL.format(
            namespace=self.namespace, 
            name=self.name
        )
        
        # 发送更新请求
        update_result = self.api_client.put(path, self.to_config_dict())
        if not update_result:
            print(f"[ERROR]Failed to update HPA {self.name}")
            return False
        
        return True

    def delete(self):
        """删除HPA"""
        # 如果控制器正在运行，先停止
        self.stop_controller()
        
        self._ensure_api_client()
        
        # 构建API路径
        path = self.uri_config.HPA_SPEC_URL.format(
            namespace=self.namespace, 
            name=self.name
        )
        
        # 发送删除请求
        delete_result = self.api_client.delete(path)
        if not delete_result:
            print(f"[ERROR]Failed to delete HPA {self.name}")
            return False
        
        print(f"[INFO]HPA {self.name} deleted")
        return True

    def get_target_resource(self):
        """获取目标资源"""
        self._ensure_api_client()
        
        if self.target_kind == 'ReplicaSet':
            return ReplicaSet.get(
                self.namespace, 
                self.target_name,
                self.api_client,
                self.uri_config
            )
        
        return None

    # 资源监控方法
    def get_container_metrics(self, container_id):
        """获取容器的指标数据"""
        try:
            url = f"{self.cadvisor_base_url}/api/v1.3/docker/{container_id}"
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                return response.json()
            
            print(f"[ERROR]Failed to get metrics for container {container_id}, status: {response.status_code}")
            return None
        except Exception as e:
            print(f"[ERROR]Error getting container metrics: {e}")
            return None
            
    def get_machine_info(self):
        """获取机器信息，用于计算CPU核心数等"""
        try:
            url = f"{self.cadvisor_base_url}/api/v1.3/machine"
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                return response.json()
            
            print(f"[ERROR]Failed to get machine info, status: {response.status_code}")
            return None
        except Exception as e:
            print(f"[ERROR]Error getting machine info: {e}")
            return None
    
    def get_cpu_usage_percentage(self, container_id):
        """获取CPU使用率百分比"""
        metrics = self.get_container_metrics(container_id)
        if not metrics:
            return None
        
        try:
            # 获取机器信息
            machine_info = self.get_machine_info()
            if not machine_info:
                return None
            
            # 获取CPU总核心数
            num_cores = machine_info.get('num_cores', 1)
            
            # 获取最近的两个时间点的数据
            stats = metrics.get('stats', [])
            if len(stats) < 2:
                return None
                
            current = stats[-1]
            previous = stats[-2]
            
            # 计算CPU使用率
            current_usage = current.get('cpu', {}).get('usage', {}).get('total', 0)
            previous_usage = previous.get('cpu', {}).get('usage', {}).get('total', 0)
            
            # 转换为纳秒
            cpu_usage_ns = current_usage - previous_usage
            
            # 计算时间间隔
            current_time = current.get('timestamp', '')
            previous_time = previous.get('timestamp', '')
            
            # 解析时间戳
            from datetime import datetime
            current_dt = datetime.strptime(current_time, '%Y-%m-%dT%H:%M:%S.%fZ')
            previous_dt = datetime.strptime(previous_time, '%Y-%m-%dT%H:%M:%S.%fZ')
            interval_s = (current_dt - previous_dt).total_seconds()
            
            if interval_s <= 0:
                return None
            
            # 计算CPU使用率百分比
            cpu_percent = (cpu_usage_ns / (interval_s * 1e9 * num_cores)) * 100
            return cpu_percent
            
        except Exception as e:
            print(f"[ERROR]Error calculating CPU usage: {e}")
            return None
    
    def get_memory_usage_percentage(self, container_id):
        """获取内存使用率百分比"""
        metrics = self.get_container_metrics(container_id)
        if not metrics:
            return None
        
        try:
            # 获取最近的数据点
            stats = metrics.get('stats', [])
            if not stats:
                return None
                
            current = stats[-1]
            
            # 获取当前内存使用量
            memory_usage = current.get('memory', {}).get('usage', 0)
            
            # 获取限制
            memory_limit = current.get('memory', {}).get('limit', 0)
            
            if memory_limit <= 0:
                return None
            
            # 计算内存使用率百分比
            memory_percent = (memory_usage / memory_limit) * 100
            return memory_percent
            
        except Exception as e:
            print(f"[ERROR]Error calculating memory usage: {e}")
            return None

    def get_pod_container_ids(self, pod_name):
        """获取Pod的容器ID列表"""
        try:
            # 获取所有容器
            url = f"{self.cadvisor_base_url}/api/v1.3/docker"
            response = requests.get(url, timeout=5)
            if response.status_code != 200:
                print(f"[ERROR]Failed to get containers, status: {response.status_code}")
                return []
                
            all_containers = response.json()
            
            # 筛选出属于指定Pod的容器
            pod_containers = []
            for container_id, container_data in all_containers.items():
                # 检查容器名称是否包含Pod名称
                if 'aliases' in container_data:
                    for alias in container_data.get('aliases', []):
                        if pod_name in alias:
                            pod_containers.append(container_id)
                            break
            
            return pod_containers
            
        except Exception as e:
            print(f"[ERROR]Error getting pod container IDs: {e}")
            return []
        
    def evaluate_metrics(self, target_resource):
        """评估当前指标，计算需要的副本数"""
        cpu_target = None
        memory_target = None
        
        # 查找CPU和内存指标的目标值
        for metric in self.metrics:
            if metric.get('type') == 'Resource':
                resource_name = metric.get('resource', {}).get('name', '').lower()
                target_data = metric.get('resource', {}).get('target', {})
                
                if resource_name == 'cpu' and 'averageUtilization' in target_data:
                    cpu_target = target_data.get('averageUtilization')
                elif resource_name == 'memory' and 'averageUtilization' in target_data:
                    memory_target = target_data.get('averageUtilization')
        
        # 如果没有设置目标，返回当前副本数
        if cpu_target is None and memory_target is None:
            print("[INFO]No valid metric targets found")
            return target_resource.current_replicas
        
        # 获取所有容器的指标
        avg_cpu_usage = 0
        avg_memory_usage = 0
        container_count = 0
        
        # 遍历ReplicaSet控制的所有Pod
        pod_instances = target_resource.pod_instances or []
        
        if not pod_instances:
            print("[INFO]No pods found for this ReplicaSet")
            return 1  # 默认返回1个副本
        
        for group in pod_instances:
            for pod_name in group:
                container_ids = self.get_pod_container_ids(pod_name)
                for container_id in container_ids:
                    # 获取CPU使用率
                    cpu_usage = self.get_cpu_usage_percentage(container_id)
                    if cpu_usage is not None:
                        avg_cpu_usage += cpu_usage
                    
                    # 获取内存使用率
                    memory_usage = self.get_memory_usage_percentage(container_id)
                    if memory_usage is not None:
                        avg_memory_usage += memory_usage
                    
                    container_count += 1
        
        # 计算平均值
        if container_count > 0:
            avg_cpu_usage /= container_count
            avg_memory_usage /= container_count
        
        # 保存当前指标
        self.current_metrics = {
            'cpu': avg_cpu_usage,
            'memory': avg_memory_usage
        }
        
        # 计算基于CPU和内存的需要副本数
        cpu_replicas = target_resource.current_replicas
        memory_replicas = target_resource.current_replicas
        
        # 计算基于CPU的需要副本数
        if cpu_target is not None and avg_cpu_usage > 0:
            cpu_replicas = int(round((avg_cpu_usage / cpu_target) * target_resource.current_replicas))
        
        # 计算基于内存的需要副本数
        if memory_target is not None and avg_memory_usage > 0:
            memory_replicas = int(round((avg_memory_usage / memory_target) * target_resource.current_replicas))
        
        # 取两者的最大值
        new_replicas = max(cpu_replicas, memory_replicas)
        new_replicas = max(new_replicas, self.min_replicas)  # 不低于最小值
        new_replicas = min(new_replicas, self.max_replicas)  # 不超过最大值
        
        print(f"[INFO]Metrics - CPU: {avg_cpu_usage:.1f}% (target: {cpu_target}%), Memory: {avg_memory_usage:.1f}% (target: {memory_target}%)")
        print(f"[INFO]Replicas calculation - Current: {target_resource.current_replicas}, New: {new_replicas}")
        
        return new_replicas

    def scale_target(self, target_replicas):
        """调整目标资源的副本数量"""
        # 获取目标资源
        target = self.get_target_resource()
        if not target:
            print(f"[ERROR]Target {self.target_kind} {self.target_name} not found")
            return False
        
        # 检查当前副本数
        current_replicas = 0
        if hasattr(target, 'current_replicas'):
            if isinstance(target.current_replicas, list):
                current_replicas = target.current_replicas[0] if target.current_replicas else 0
            else:
                current_replicas = target.current_replicas
                
        if current_replicas == target_replicas:
            return True  # 已经是目标数量，无需调整
        
        # 检查冷却期
        if self.last_scale_time and (datetime.datetime.now() - self.last_scale_time).total_seconds() < self.cooldown_seconds:
            print(f"[INFO]In cooldown period, skipping scaling")
            return False  # 冷却期内，不进行调整
        
        # 执行扩缩容
        print(f"[INFO]Scaling {self.target_kind} {self.target_name} from {current_replicas} to {target_replicas} replicas")
        scaling_success = target.scale(target_replicas)
        
        if scaling_success:
            # 更新HPA状态
            self.last_scale_time = datetime.datetime.now()
            self.current_replicas = current_replicas
            self.target_replicas = target_replicas
            self.status = STATUS.SCALING
            self.update()
            return True
        
        return False

    # 控制器方法
    def run_controller(self):
        """运行HPA控制器逻辑"""
        self._ensure_api_client()
        
        while self.running:
            try:
                # 获取目标资源
                target = self.get_target_resource()
                if not target:
                    print(f"[ERROR]Target {self.target_kind} {self.target_name} not found, pausing controller")
                    time.sleep(30)  # 等待30秒后重试
                    continue
                
                # 评估指标，计算需要的副本数
                new_replicas = self.evaluate_metrics(target)
                
                # 当前副本数
                current_replicas = 0
                if hasattr(target, 'current_replicas'):
                    if isinstance(target.current_replicas, list):
                        current_replicas = target.current_replicas[0] if target.current_replicas else 0
                    else:
                        current_replicas = target.current_replicas
                
                # 更新HPA状态
                self.current_replicas = current_replicas
                
                # 如果需要调整副本数
                if new_replicas != current_replicas:
                    self.scale_target(new_replicas)
                else:
                    # 非扩缩阶段，更新状态为RUNNING
                    if self.status != STATUS.RUNNING:
                        self.status = STATUS.RUNNING
                        self.update()
            
            except Exception as e:
                print(f"[ERROR]Error in HPA controller: {e}")
                self.status = STATUS.FAILED
                self.update()
            
            # 等待下一个检查周期
            time.sleep(15)  # 每15秒检查一次

    def start_controller(self):
        """启动HPA控制器"""
        if self.running:
            print(f"[INFO]HPA controller for {self.name} is already running")
            return
        
        print(f"[INFO]Starting HPA controller for {self.name}")
        self.running = True
        self.controller_thread = threading.Thread(target=self.run_controller)
        self.controller_thread.daemon = True
        self.controller_thread.start()
        
        # 更新状态
        self.status = STATUS.RUNNING
        self.update()

    def stop_controller(self):
        """停止HPA控制器"""
        if not self.running:
            return
        
        print(f"[INFO]Stopping HPA controller for {self.name}")
        self.running = False
        if self.controller_thread:
            self.controller_thread.join(timeout=5)
            self.controller_thread = None
        
        # 更新状态
        self.status = STATUS.PENDING
        self.update()

# HPA控制器主类
class HPAController:
    def __init__(self, api_client=None, uri_config=None):
        self.api_client = api_client or ApiClient()
        self.uri_config = uri_config or URIConfig()
        self.hpas = {}  # 存储所有活动的HPA
        self.running = False
        self.controller_thread = None
    
    def sync_hpas(self):
        """同步所有HPA"""
        # 获取所有命名空间的所有HPA
        all_hpas = []
        
        # 先尝试获取所有HPA
        global_hpas = self.api_client.get('/v1/hpas')
        if global_hpas:
            for hpa_data in global_hpas:
                if isinstance(hpa_data, dict) and list(hpa_data.keys())[0]:
                    hpa_name = list(hpa_data.keys())[0]
                    namespace = hpa_data[hpa_name].get('namespace', 'default')
                    all_hpas.append((namespace, hpa_name))
        
        # 更新控制的HPA列表
        current_hpas = set()
        
        for namespace, name in all_hpas:
            # 添加到当前HPA集合
            hpa_key = f"{namespace}/{name}"
            current_hpas.add(hpa_key)
            
            # 如果不在已管理的HPA中，添加并启动控制器
            if hpa_key not in self.hpas:
                hpa = HorizontalPodAutoscaler.get(namespace, name, self.api_client, self.uri_config)
                if hpa:
                    self.hpas[hpa_key] = hpa
                    hpa.start_controller()
        
        # 移除不再存在的HPA
        keys_to_remove = []
        for hpa_key in self.hpas:
            if hpa_key not in current_hpas:
                self.hpas[hpa_key].stop_controller()
                keys_to_remove.append(hpa_key)
                
        for key in keys_to_remove:
            del self.hpas[key]
    
    def run(self):
        """运行HPA控制管理器"""
        self.running = True
        
        while self.running:
            try:
                # 同步HPA列表
                self.sync_hpas()
                
                # 每30秒同步一次
                time.sleep(30)
            except Exception as e:
                print(f"[ERROR]Error in HPA controller manager: {e}")
                time.sleep(60)  # 出错时等待较长时间再重试
    
    def start(self):
        """启动HPA控制管理器"""
        if self.controller_thread and self.controller_thread.is_alive():
            print("[INFO]HPA controller manager is already running")
            return
            
        print("[INFO]Starting HPA controller manager")
        self.controller_thread = threading.Thread(target=self.run)
        self.controller_thread.daemon = True
        self.controller_thread.start()
    
    def stop(self):
        """停止HPA控制管理器"""
        print("[INFO]Stopping HPA controller manager")
        self.running = False
        
        # 停止所有HPA控制器
        for hpa in self.hpas.values():
            hpa.stop_controller()
        
        if self.controller_thread:
            self.controller_thread.join(timeout=5)
            self.controller_thread = None

def test_hpa():
    """测试HPA功能"""
    import yaml
    import os
    from pkg.config.globalConfig import GlobalConfig
    
    # 测试配置文件路径
    global_config = GlobalConfig()
    config_file = os.path.join(global_config.TEST_FILE_PATH, 'test-hpa.yaml')
    
    # 加载测试配置
    if os.path.exists(config_file):
        print(f"[INFO]正在加载测试配置文件: {config_file}")
        with open(config_file, 'r') as f:
            config_dict = yaml.safe_load(f)
    else:
        print(f"[ERROR]未找到测试配置文件: {config_file}")
        return
    
    try:
        # 创建HPA配置
        hpa_config = HorizontalPodAutoscalerConfig(config_dict)
        
        # 创建HPA对象
        hpa = HorizontalPodAutoscaler(hpa_config)
        
        # 设置API客户端
        hpa.set_api_client(ApiClient())
        
        # 创建HPA
        print("[TEST]创建HPA...")
        create_success = hpa.create()
        if not create_success:
            print("[FAIL]创建HPA失败")
            return
            
        print("[PASS]创建HPA成功")
        
        # 获取HPA
        print("\n[TEST]获取HPA...")
        retrieved_hpa = HorizontalPodAutoscaler.get(hpa.namespace, hpa.name)
        if not retrieved_hpa:
            print("[FAIL]获取HPA失败")
            return
            
        print(f"[PASS]获取HPA成功: {retrieved_hpa.name}")
        
        # 启动HPA控制器
        print("\n[TEST]启动HPA控制器...")
        hpa.start_controller()
        print("[INFO]HPA控制器已启动，等待60秒观察扩缩容...")
        time.sleep(60)
        
        # 停止HPA控制器
        print("\n[TEST]停止HPA控制器...")
        hpa.stop_controller()
        print("[PASS]HPA控制器已停止")
        
        # 删除HPA
        print("\n[TEST]删除HPA...")
        delete_success = hpa.delete()
        if not delete_success:
            print("[FAIL]删除HPA失败")
            return
            
        print("[PASS]删除HPA成功")
        
        print("\n[SUCCESS]所有测试通过!")
        
    except Exception as e:
        print(f"[ERROR]测试过程中出错: {e}")

if __name__ == '__main__':
    print("[INFO]Testing HPA functionality")
    test_hpa()