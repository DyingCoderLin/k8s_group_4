import time
import threading
import json
import datetime
import requests

from pkg.config.uriConfig import URIConfig
from pkg.apiObject.horizontalPodAutoScaler import HorizontalPodAutoscaler, STATUS as HPA_STATUS

class ResourceMetricsClient:
    def __init__(self):
        print('[INFO]ResourceMetricsClient initializing...')
        # 这里可以初始化获取资源指标的客户端
        # 例如连接到Docker或cAdvisor

    def get_pod_metrics(self, pod_name, namespace):
        """获取Pod的资源使用情况"""
        try:
            # 这里应该实现实际的指标收集逻辑
            # 这是一个简化的示例，返回模拟数据
            return {
                'cpu': 50.0,  # CPU使用率50%
                'memory': 60.0  # 内存使用率60%
            }
        except Exception as e:
            print(f'[ERROR]Failed to get metrics for pod {pod_name}: {str(e)}')
            return None

class HorizontalPodAutoscalerController:
    def __init__(self, uri_config):
        print('[INFO]HorizontalPodAutoscalerController starting...')
        self.uri_config = uri_config
        self.base_url = f"http://{uri_config.HOST}:{uri_config.PORT}"
        self.metrics_client = ResourceMetricsClient()  # 资源指标客户端
        self.stop_flag = False
        self.reconcile_interval = 15  # 15秒检查一次

    def get_all_hpas(self):
        """从API Server获取所有HPA"""
        hpas = []
        
        # 使用全局HPA URL获取所有HPA
        url = f"{self.base_url}{self.uri_config.GLOBAL_HPA_URL}"
        try:
            response = requests.get(url)
            if response.status_code == 200:
                data = response.json()
                # 处理不同格式的响应
                if isinstance(data, list):
                    for hpa_data in data:
                        hpa = HorizontalPodAutoscaler(hpa_data)
                        hpas.append(hpa)
                elif isinstance(data, dict) and 'items' in data:
                    for hpa_data in data['items']:
                        hpa = HorizontalPodAutoscaler(hpa_data)
                        hpas.append(hpa)
            else:
                print(f"[ERROR]Failed to get HPAs: {response.status_code}")
        except Exception as e:
            print(f"[ERROR]Exception when getting HPAs: {str(e)}")
            
        return hpas

    def get_target_resource(self, hpa):
        """获取HPA的目标资源"""
        if hpa.target_kind == 'ReplicaSet':
            url = f"{self.base_url}{self.uri_config.REPLICA_SET_SPEC_URL.format(namespace=hpa.namespace, name=hpa.target_name)}"
            try:
                response = requests.get(url)
                if response.status_code == 200:
                    return response.json()
                else:
                    print(f"[ERROR]Failed to get target ReplicaSet {hpa.target_name}: {response.status_code}")
            except Exception as e:
                print(f"[ERROR]Exception when getting target ReplicaSet: {str(e)}")
        return None

    def get_pod_metrics(self, pod_names, namespace):
        """获取Pod的资源指标"""
        metrics = {}
        for pod_name in pod_names:
            pod_metrics = self.metrics_client.get_pod_metrics(pod_name, namespace)
            if pod_metrics:
                metrics[pod_name] = pod_metrics
        return metrics

    def calculate_target_replicas(self, hpa, current_replicas, metrics):
        """根据当前指标计算目标副本数量"""
        if not metrics:
            return current_replicas
        
        target_replicas = current_replicas
        
        # 处理每个指标
        for metric_spec in hpa.metrics:
            metric_name = metric_spec.get('name')
            target_value = metric_spec.get('target', {}).get('averageUtilization', 50)  # 默认目标值50%
            
            if not metric_name or metric_name not in ['cpu', 'memory']:
                continue
            
            # 计算当前平均值
            total_value = 0
            count = 0
            for pod_metrics in metrics.values():
                if metric_name in pod_metrics:
                    total_value += pod_metrics[metric_name]
                    count += 1
            
            if count == 0:
                continue
            
            average_value = total_value / count
            
            # 计算根据此指标应该有的副本数
            metric_replicas = int(current_replicas * (average_value / target_value))
            
            # 取最大值
            target_replicas = max(target_replicas, metric_replicas)
        
        # 确保在min和max范围内
        return max(hpa.min_replicas, min(hpa.max_replicas, target_replicas))

    def scale_target(self, hpa, target_resource, target_replicas):
        """调整目标资源的副本数量"""
        current_replicas = target_resource.get('current_replicas', 0)
        if current_replicas == target_replicas:
            return False  # 无需调整
        
        if hpa.last_scale_time and (datetime.datetime.now() - hpa.last_scale_time).total_seconds() < hpa.cooldown_seconds:
            return False  # 冷却期内，不进行调整
        
        print(f'[INFO]Scaling {hpa.target_kind} {hpa.target_name} from {current_replicas} to {target_replicas} replicas')
        
        # 通过API更新目标资源的副本数
        if hpa.target_kind == 'ReplicaSet':
            url = f"{self.base_url}{self.uri_config.REPLICA_SET_SPEC_URL.format(namespace=hpa.namespace, name=hpa.target_name)}"
            
            # 构建更新数据
            update_data = {
                'metadata': {
                    'name': hpa.target_name,
                    'namespace': hpa.namespace
                },
                'spec': {
                    'replicas': target_replicas
                }
            }
            
            try:
                response = requests.put(url, json=update_data)
                if response.status_code == 200:
                    # 更新HPA状态
                    hpa.last_scale_time = datetime.datetime.now()
                    hpa.current_replicas = current_replicas
                    hpa.target_replicas = target_replicas
                    return True
                else:
                    print(f"[ERROR]Failed to scale ReplicaSet {hpa.target_name}: {response.status_code}")
                    return False
            except Exception as e:
                print(f"[ERROR]Exception when scaling ReplicaSet: {str(e)}")
                return False
        
        return False

    def update_hpa_status(self, hpa):
        """更新HPA状态"""
        url = f"{self.base_url}{self.uri_config.HPA_SPEC_URL.format(namespace=hpa.namespace, name=hpa.name)}"
        
        # 构建更新数据
        update_data = {
            'metadata': {
                'name': hpa.name,
                'namespace': hpa.namespace
            },
            'status': hpa.status,
            'current_replicas': hpa.current_replicas,
            'target_replicas': hpa.target_replicas,
            'current_metrics': hpa.current_metrics,
            'last_scale_time': hpa.last_scale_time.isoformat() if hpa.last_scale_time else None
        }
        
        try:
            response = requests.put(url, json=update_data)
            if response.status_code != 200:
                print(f"[ERROR]Failed to update HPA {hpa.name}: {response.status_code}")
        except Exception as e:
            print(f"[ERROR]Exception when updating HPA {hpa.name}: {str(e)}")

    def reconcile(self, hpa):
        """协调HPA"""
        try:
            # 获取目标资源
            target_resource = self.get_target_resource(hpa)
            if not target_resource:
                print(f'[ERROR]Target {hpa.target_kind} {hpa.target_name} not found for HPA {hpa.name}')
                hpa.status = HPA_STATUS.FAILED
                self.update_hpa_status(hpa)
                return
            
            # 更新当前副本数
            hpa.current_replicas = target_resource.get('current_replicas', 0)
            
            # 获取Pod实例列表
            pod_instances = target_resource.get('pod_instances', [])
            
            # 获取Pod资源指标
            pod_metrics = self.get_pod_metrics(pod_instances, hpa.namespace)
            hpa.current_metrics = pod_metrics
            
            # 计算目标副本数
            target_replicas = self.calculate_target_replicas(hpa, hpa.current_replicas, pod_metrics)
            hpa.target_replicas = target_replicas
            
            # 调整目标资源的副本数
            scaled = self.scale_target(hpa, target_resource, target_replicas)
            
            # 更新HPA状态
            hpa.status = HPA_STATUS.RUNNING
            self.update_hpa_status(hpa)
            
            if scaled:
                print(f'[INFO]HPA {hpa.name} scaled {hpa.target_kind} {hpa.target_name} to {target_replicas} replicas')
            
        except Exception as e:
            print(f'[ERROR]Error reconciling HPA {hpa.name}: {str(e)}')
            hpa.status = HPA_STATUS.FAILED
            self.update_hpa_status(hpa)

    def reconcile_loop(self):
        """HPA控制循环"""
        while not self.stop_flag:
            try:
                # 获取所有HPA
                hpas = self.get_all_hpas()
                print(f'[INFO]Found {len(hpas)} HPAs to reconcile')
                
                # 协调每个HPA
                for hpa in hpas:
                    self.reconcile(hpa)
                
                # 等待下一次循环
                time.sleep(self.reconcile_interval)
            except Exception as e:
                print(f'[ERROR]Error in HPA reconcile loop: {str(e)}')
                time.sleep(self.reconcile_interval)

    def run(self):
        """启动控制器"""
        print('[INFO]HorizontalPodAutoscalerController running...')
        self.thread = threading.Thread(target=self.reconcile_loop)
        self.thread.daemon = True
        self.thread.start()

    def stop(self):
        """停止控制器"""
        self.stop_flag = True
        if hasattr(self, 'thread'):
            self.thread.join(timeout=5)
        print('[INFO]HorizontalPodAutoscalerController stopped.')