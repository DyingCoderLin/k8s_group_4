import time
import threading
from pkg.apiServer.apiClient import ApiClient
from pkg.config.uriConfig import URIConfig
from pkg.apiObject.hpa import HorizontalPodAutoscaler, STATUS as HPA_STATUS

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
    def __init__(self, uri_config=None):
        print('[INFO]HorizontalPodAutoscalerController starting...')
        self.uri_config = uri_config or URIConfig()
        self.api_client = ApiClient(host=self.uri_config.HOST, port=self.uri_config.PORT)
        self.metrics_client = ResourceMetricsClient()
        self.stop_flag = False
        self.reconcile_interval = 15  # 15秒检查一次

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

    def reconcile(self, hpa):
        """协调单个HPA"""
        try:
            print(f'[INFO]Reconciling HPA {hpa.name}...')
            
            # 1. 检查目标类型
            if hpa.target_kind != 'ReplicaSet':
                print(f'[WARN]HPA {hpa.name} targets {hpa.target_kind}, only ReplicaSet is supported')
                return
            
            # 2. 获取目标ReplicaSet
            target_rs = hpa.get_target_resource()
            if not target_rs:
                print(f'[ERROR]Target ReplicaSet {hpa.target_name} not found for HPA {hpa.name}')
                hpa.status = HPA_STATUS.FAILED
                hpa.update()
                return
            
            # 3. 更新当前副本数
            hpa.current_replicas = target_rs.current_replicas
            
            # 4. 获取Pod资源指标
            pod_metrics = self.get_pod_metrics(target_rs.pod_instances, hpa.namespace)
            hpa.current_metrics = pod_metrics
            
            # 5. 计算目标副本数
            target_replicas = self.calculate_target_replicas(hpa, hpa.current_replicas, pod_metrics)
            hpa.target_replicas = target_replicas
            
            # 6. 检查是否需要扩缩容
            if target_replicas == target_rs.current_replicas:
                print(f'[INFO]HPA {hpa.name}: No scaling needed, current replicas = {target_rs.current_replicas}')
                hpa.status = HPA_STATUS.RUNNING
                hpa.update()
                return
            
            # 7. 执行扩缩容
            print(f'[INFO]HPA {hpa.name}: Scaling {hpa.target_kind} {hpa.target_name} from {target_rs.current_replicas} to {target_replicas} replicas')
            scaling_success = hpa.scale_target(target_replicas)
            
            if scaling_success:
                hpa.status = HPA_STATUS.RUNNING
                print(f'[INFO]HPA {hpa.name}: Successfully scaled to {target_replicas} replicas')
            else:
                # 更新状态但不标记为失败
                hpa.status = HPA_STATUS.RUNNING
                print(f'[INFO]HPA {hpa.name}: Scaling skipped (cooldown or other reason)')
            
            # 8. 更新HPA状态
            hpa.update()
            
        except Exception as e:
            print(f'[ERROR]Error reconciling HPA {hpa.name}: {str(e)}')
            try:
                hpa.status = HPA_STATUS.FAILED
                hpa.update()
            except:
                pass

    def reconcile_loop(self):
        """HPA控制循环"""
        while not self.stop_flag:
            try:
                # 获取所有HPA
                hpas = HorizontalPodAutoscaler.list(
                    namespace='default',  # 简化为只处理default命名空间
                    api_client=self.api_client,
                    uri_config=self.uri_config
                )
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