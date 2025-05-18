import datetime
import requests
from pkg.apiServer.apiClient import ApiClient
from pkg.config.uriConfig import URIConfig
from pkg.config.hpaConfig import HorizontalPodAutoscalerConfig
from pkg.apiObject.replicaSet import ReplicaSet
from typing import Optional

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
        
        # 运行时状态
        self.status = STATUS.PENDING
        self.current_replicas = 0
        self.target_replicas = 0
        self.current_metrics = {}
        self.last_scale_time = None
        # self.cadvisor_base_url = f"http://{URIConfig.HOST}:8080"
        # 非常重要！在mac上因为无法运行cadvisor，所以使用必须使用云主机上的cadvisor docker，只是用来测试获取的正确性的
        self.cadvisor_base_url = f"http://10.119.15.182:8080"
        
        # API通信
        self.api_client = None
        self.uri_config = None

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
        
    def get_machine_realtime_metrics(self):
        """获取机器的指标数据"""
        try:
            url = f"{self.cadvisor_base_url}/api/v1.3/docker/"
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                return response.json()
            
            return None
        except Exception as e:
            print(f"[ERROR]Error getting container metrics: {e}")
            return None
            
    def get_machine_info(self):
        """获取机器信息，包括 CPU 核心数等"""
        try:
            url = f"{self.cadvisor_base_url}/api/v2.0/machine"
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                return response.json()
            
            print(f"[ERROR]Failed to get machine info, status: {response.status_code}")
            return None
        except Exception as e:
            print(f"[ERROR]Error getting machine info: {e}")
            return None
        
    def get_machine_metrics_summary(self):
        """获取机器的指标摘要数据 (v2.0 API)"""
        try:
            url = f"{self.cadvisor_base_url}/api/v2.0/summary"
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                return response.json()
            
            print(f"[ERROR]Failed to get metrics summary, status: {response.status_code}")
            return None
        except Exception as e:
            print(f"[ERROR]Error getting metrics summary: {e}")
            return None
    
    def get_cpu_usage_percentage(self, container_id=None):
        """获取CPU使用率百分比 - 使用 v2.0 API"""
        try:
            # 获取摘要数据
            summary = self.get_machine_metrics_summary()
            if not summary:
                print("[ERROR]未获取到指标摘要数据")
                return None
                
            # v2.0 API 中的 CPU 使用率已经是百分比形式
            # 获取根容器 ("/") 的数据，或者使用特定容器路径
            container_path = "/" if container_id is None else f"/docker/{container_id}"
            
            if container_path not in summary:
                print(f"[ERROR]在摘要中未找到容器路径: {container_path}")
                return None
            
            # 获取最新 CPU 使用率（百分比）
            cpu_percent = summary[container_path].get("latest_usage", {}).get("cpu")
            
            # 如果 latest_usage 中没有 CPU 数据，尝试使用 minute_usage
            if cpu_percent is None:
                minute_data = summary[container_path].get("minute_usage", {})
                if minute_data.get("percent_complete", 0) > 0 and minute_data.get("cpu", {}).get("present", False):
                    cpu_percent = minute_data.get("cpu", {}).get("mean")
            
            if cpu_percent is None:
                print("[ERROR]未找到有效的 CPU 使用率数据")
                return None
                
            print(f"[DEBUG]CPU使用率: {cpu_percent:.2f}%")
            return float(cpu_percent)
            
        except Exception as e:
            print(f"[ERROR]计算CPU使用率时出错: {e}")
            import traceback
            print(f"[ERROR]详细错误: {traceback.format_exc()}")
            return None

    def get_memory_usage_percentage(self, container_id=None):
        """获取内存使用率百分比 - 使用 v2.0 API"""
        try:
            # 获取摘要数据
            summary = self.get_machine_metrics_summary()
            if not summary:
                print("[ERROR]未获取到指标摘要数据")
                return None
                
            # 获取机器信息，用于计算内存总量
            machine_info = self.get_machine_info()
            if not machine_info or "memory_capacity" not in machine_info:
                print("[ERROR]未获取到机器内存容量信息")
                return None
                
            total_memory = machine_info.get("memory_capacity")
            
            # 获取根容器 ("/") 的数据，或者使用特定容器路径
            container_path = "/" if container_id is None else f"/docker/{container_id}"
            
            if container_path not in summary:
                print(f"[ERROR]在摘要中未找到容器路径: {container_path}")
                return None
            
            # 获取最新内存使用量（字节）
            memory_usage = summary[container_path].get("latest_usage", {}).get("memory")
            
            # 如果 latest_usage 中没有内存数据，尝试使用 minute_usage
            if memory_usage is None:
                minute_data = summary[container_path].get("minute_usage", {})
                if minute_data.get("percent_complete", 0) > 0 and minute_data.get("memory", {}).get("present", False):
                    memory_usage = minute_data.get("memory", {}).get("mean")
            
            if memory_usage is None or total_memory <= 0:
                print("[ERROR]未找到有效的内存使用数据或总内存容量")
                return None
                
            # 计算内存使用率百分比
            memory_percent = (float(memory_usage) / float(total_memory)) * 100
            print(f"[DEBUG]内存使用率: {memory_percent:.2f}% (使用: {memory_usage} 字节, 总量: {total_memory} 字节)")
            return memory_percent
            
        except Exception as e:
            print(f"[ERROR]计算内存使用率时出错: {e}")
            import traceback
            print(f"[ERROR]详细错误: {traceback.format_exc()}")
            return None

    def get_pod_container_path(self, pod_name):
        """获取与 Pod 名称相关的容器路径"""
        try:
            # 对 v2.0 API，我们需要获取所有容器列表
            url = f"{self.cadvisor_base_url}/api/v2.0/ps"
            response = requests.get(url, timeout=5)
            if response.status_code != 200:
                print(f"[ERROR]Failed to get container processes, status: {response.status_code}")
                return []
                
            containers_info = response.json()
            pod_containers = []
            
            # 遍历容器信息，查找与 Pod 名称匹配的容器
            for container in containers_info:
                # 容器名称通常包含 Pod 名称
                if pod_name in container.get("name", ""):
                    container_path = f"/docker/{container.get('id', '')}"
                    pod_containers.append(container_path)
            
            return pod_containers
            
        except Exception as e:
            print(f"[ERROR]Error getting pod container paths: {e}")
            return []

def test_hpa():
    """测试HPA功能"""
    import yaml
    import os
    import time
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
        # 测试CPU和内存指标获取
        print("[TEST]获取CPU和内存指标...")        
        # 创建HPA配置
        hpa_config = HorizontalPodAutoscalerConfig(config_dict)
        
        # 创建HPA对象
        hpa = HorizontalPodAutoscaler(hpa_config)
        
        # 获取机器信息
        print("[TEST]获取机器信息...")
        machine_info = hpa.get_machine_info()
        if machine_info:
            print(f"[INFO]机器内存容量: {machine_info.get('memory_capacity')} 字节")
            print(f"[INFO]CPU核心数: {machine_info.get('num_cores', '未知')}")
        else:
            print("[WARN]无法获取机器信息")
        
        # 获取指标摘要
        print("[TEST]获取指标摘要...")
        metrics_summary = hpa.get_machine_metrics_summary()
        if metrics_summary:
            # 只打印根容器的信息以避免过多输出
            root_metrics = metrics_summary.get("/", {})
            print(f"[INFO]根容器时间戳: {root_metrics.get('timestamp', '未知')}")
            print(f"[INFO]根容器最新CPU使用率: {root_metrics.get('latest_usage', {}).get('cpu')}%")
            print(f"[INFO]根容器最新内存使用量: {root_metrics.get('latest_usage', {}).get('memory')} 字节")
        else:
            print("[WARN]无法获取指标摘要")
        
        # 获取CPU和内存使用率
        cpu_percent = hpa.get_cpu_usage_percentage()
        memory_percent = hpa.get_memory_usage_percentage()
        
        if cpu_percent is not None:
            print(f"[INFO]CPU使用率: {cpu_percent:.2f}%")
        else:
            print("[WARN]无法获取CPU使用率")
            
        if memory_percent is not None:
            print(f"[INFO]内存使用率: {memory_percent:.2f}%")
        else:
            print("[WARN]无法获取内存使用率")
            
        return
        
        # 以下是创建、获取、删除HPA的测试，暂不执行
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
        import traceback
        print(f"[ERROR]详细错误: {traceback.format_exc()}")

if __name__ == '__main__':
    print("[INFO]Testing HPA functionality")
    test_hpa()