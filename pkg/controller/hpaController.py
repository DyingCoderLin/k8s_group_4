import time
import threading
import datetime
from pkg.apiServer.apiClient import ApiClient
from pkg.config.uriConfig import URIConfig
from pkg.config.hpaConfig import HorizontalPodAutoscalerConfig
from pkg.apiObject.hpa import HorizontalPodAutoscaler, STATUS

class HPAController:
    def __init__(self, uri_config=None):
        """初始化HPA控制器"""
        print("[INFO]HPAController initializing...")
        self.uri_config = uri_config or URIConfig()
        self.api_client = ApiClient(self.uri_config.HOST, self.uri_config.PORT)
        self.cooldown_seconds = 60  # 冷却时间，防止频繁扩缩
        
        # 控制器状态
        self.running = False
        self.main_thread = None
        self.reconcile_interval = 15  # 调整检查间隔，单位秒
        self.hpas = {}  # 存储所有活动的HPA {namespace/name: hpa_object}
        
        # 节点信息缓存
        self.node_cadvisor_urls = {}  # {node_id: cadvisor_url}

    def get_all_hpas(self):
        """获取所有HPA配置"""
        try:
            url = self.uri_config.GLOBAL_HPA_URL
            response = self.api_client.get(url)
            if response:
                print(f"[INFO]Found {len(response)} HPAs")
                return response
            else:
                print("[INFO]No HPAs found")
        except Exception as e:
            print(f"[ERROR]Failed to get HPAs: {str(e)}")
        return []

    def get_hpa(self, namespace, name):
        """获取指定HPA"""
        try:
            url = self.uri_config.HPA_SPEC_URL.format(namespace=namespace, name=name)
            response = self.api_client.get(url)
            if response:
                return response
            else:
                print(f"[ERROR]Failed to get HPA {name}")
        except Exception as e:
            print(f"[ERROR]Failed to get HPA {name}: {str(e)}")
        return None

    def update_hpa(self, hpa):
        """更新HPA状态"""
        try:
            url = self.uri_config.HPA_SPEC_URL.format(namespace=hpa.namespace, name=hpa.name)
            response = self.api_client.put(url, hpa.to_config_dict())
            if response:
                print(f"[INFO]Updated HPA {hpa.name}")
                return True
            else:
                print(f"[ERROR]Failed to update HPA {hpa.name}")
        except Exception as e:
            print(f"[ERROR]Error updating HPA {hpa.name}: {str(e)}")
        return False

    def get_node_cadvisor_url(self, node_id):
        """获取节点的cAdvisor URL (现在不使用，但预留接口)"""
        # 如果已经缓存，直接返回
        if node_id in self.node_cadvisor_urls:
            return self.node_cadvisor_urls[node_id]
            
        # 实际实现中应该通过API获取节点IP，这里简化处理
        # 例如：通过node_id查询节点信息获取IP
        # 现在简单返回默认值
        cadvisor_url = f"http://10.119.15.182:8080"  # 与hpa.py中保持一致，使用固定地址
        
        # 缓存URL
        self.node_cadvisor_urls[node_id] = cadvisor_url
        return cadvisor_url

    def evaluate_metrics(self, hpa, target_resource):
        """评估当前指标，计算需要的副本数"""
        cpu_target = None
        memory_target = None
        
        # 查找CPU和内存指标的目标值
        for metric in hpa.metrics:
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
        
        try:
            # 直接使用根路径获取整体机器的CPU和内存使用情况
            # 这里使用hpa中的方法，不做进一步处理，直接调用根路径的数据
            cpu_usage = hpa.get_cpu_usage_percentage()
            memory_usage = hpa.get_memory_usage_percentage()
            
            if cpu_usage is not None:
                avg_cpu_usage = cpu_usage  # 直接使用整机CPU使用率
                
            if memory_usage is not None:
                avg_memory_usage = memory_usage  # 直接使用整机内存使用率
                
            # 设置container_count为1，避免除零错误
            container_count = 1
        
        except Exception as e:
            print(f"[ERROR]获取整机资源使用情况出错: {e}")
            # 如果获取整机信息失败，尝试原来的方法获取单个容器
            
            # 遍历ReplicaSet控制的所有Pod
            pod_instances = target_resource.pod_instances or []
            
            if not pod_instances:
                print("[INFO]No pods found for this ReplicaSet")
                return 1  # 默认返回1个副本
            
            for group in pod_instances:
                for pod_name in group:
                    # 使用新的获取容器路径的方法
                    container_paths = hpa.get_pod_container_path(pod_name)
                    
                    for container_path in container_paths:
                        # 从路径中提取容器ID
                        container_id = container_path.replace('/docker/', '')
                        
                        # 获取CPU使用率
                        cpu_usage = hpa.get_cpu_usage_percentage(container_id)
                        if cpu_usage is not None:
                            avg_cpu_usage += cpu_usage
                        
                        # 获取内存使用率
                        memory_usage = hpa.get_memory_usage_percentage(container_id)
                        if memory_usage is not None:
                            avg_memory_usage += memory_usage
                        
                        container_count += 1
        
        # 计算平均值
        if container_count > 0:
            avg_cpu_usage /= container_count
            avg_memory_usage /= container_count
        else:
            print("[WARN]No valid containers found for resource metrics collection")
            return target_resource.current_replicas
        
        # 保存当前指标
        hpa.current_metrics = {
            'cpu': avg_cpu_usage,
            'memory': avg_memory_usage
        }
        
        # 计算基于CPU和内存的需要副本数
        cpu_replicas = target_resource.current_replicas
        memory_replicas = target_resource.current_replicas
        
        # 计算基于CPU的需要副本数
        if cpu_target is not None and avg_cpu_usage > 0:
            cpu_ratio = avg_cpu_usage / cpu_target
            cpu_replicas = int(round(cpu_ratio * target_resource.current_replicas))
            print(f"[INFO]CPU使用比率: {cpu_ratio:.2f}, 建议副本数: {cpu_replicas}")
        
        # 计算基于内存的需要副本数
        if memory_target is not None and avg_memory_usage > 0:
            memory_ratio = avg_memory_usage / memory_target
            memory_replicas = int(round(memory_ratio * target_resource.current_replicas))
            print(f"[INFO]内存使用比率: {memory_ratio:.2f}, 建议副本数: {memory_replicas}")
        
        # 取两者的最大值
        new_replicas = max(cpu_replicas, memory_replicas)
        new_replicas = max(new_replicas, hpa.min_replicas)  # 不低于最小值
        new_replicas = min(new_replicas, hpa.max_replicas)  # 不超过最大值
        
        print(f"[INFO]Metrics - CPU: {avg_cpu_usage:.1f}% (target: {cpu_target}%), Memory: {avg_memory_usage:.1f}% (target: {memory_target}%)")
        print(f"[INFO]Replicas calculation - Current: {target_resource.current_replicas}, New: {new_replicas}")
        
        return new_replicas

    def scale_target(self, hpa, target_replicas):
        """调整目标资源的副本数量"""
        # 获取目标资源
        target = hpa.get_target_resource()
        if not target:
            print(f"[ERROR]Target {hpa.target_kind} {hpa.target_name} not found")
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
        if hpa.last_scale_time and (datetime.datetime.now() - hpa.last_scale_time).total_seconds() < self.cooldown_seconds:
            print(f"[INFO]In cooldown period, skipping scaling")
            return False  # 冷却期内，不进行调整
        
        # 执行扩缩容
        print(f"[INFO]Scaling {hpa.target_kind} {hpa.target_name} from {current_replicas} to {target_replicas} replicas")
        scaling_success = target.scale(target_replicas)
        
        if scaling_success:
            # 更新HPA状态
            hpa.last_scale_time = datetime.datetime.now()
            hpa.current_replicas = current_replicas
            hpa.target_replicas = target_replicas
            hpa.status = STATUS.SCALING
            self.update_hpa(hpa)
            return True
        
        return False

    def reconcile_hpa(self, hpa):
        """协调单个HPA的状态"""
        print(f"[INFO]Reconciling HPA {hpa.name} in namespace {hpa.namespace}")
        try:
            # 获取目标资源
            target = hpa.get_target_resource()
            if not target:
                print(f"[ERROR]Target {hpa.target_kind} {hpa.target_name} not found")
                hpa.status = STATUS.FAILED
                self.update_hpa(hpa)
                return
            
            # 未来扩展：根据节点ID设置正确的cAdvisor URL
            # 现在我们先使用hpa.py中预设的URL
            # node_id = target.node_id
            # if node_id:
            #     cadvisor_url = self.get_node_cadvisor_url(node_id)
            #     hpa.cadvisor_base_url = cadvisor_url
                
            # 评估指标，计算需要的副本数
            new_replicas = self.evaluate_metrics(hpa, target)
            
            # 获取当前副本数
            current_replicas = 0
            if hasattr(target, 'current_replicas'):
                if isinstance(target.current_replicas, list):
                    current_replicas = target.current_replicas[0] if target.current_replicas else 0
                else:
                    current_replicas = target.current_replicas
            
            # 更新HPA状态
            hpa.current_replicas = current_replicas
            
            # 如果需要调整副本数
            if new_replicas != current_replicas:
                scaling_result = self.scale_target(hpa, new_replicas)
                if not scaling_result:
                    print(f"[ERROR]Failed to scale {hpa.target_kind} {hpa.target_name}")
            else:
                # 非扩缩阶段，更新状态为RUNNING
                if hpa.status != STATUS.RUNNING:
                    hpa.status = STATUS.RUNNING
                    self.update_hpa(hpa)
                    
        except Exception as e:
            print(f"[ERROR]Error reconciling HPA {hpa.name}: {str(e)}")
            import traceback
            print(f"[ERROR]详细错误: {traceback.format_exc()}")
            hpa.status = STATUS.FAILED
            self.update_hpa(hpa)

    def reconcile(self):
        """协调所有HPA的状态"""
        print("[INFO]Reconciling HPAs...")
        try:
            # 获取所有HPA，结构可能是多层嵌套的，需要处理
            all_hpas = self.get_all_hpas()
            
            # 跟踪当前处理的HPA，用于后续清理
            current_hpas = set()
            
            # 处理每个HPA
            for hpa_entry in all_hpas:
                if len(hpa_entry) != 1:  # 确保格式正确
                    continue
                    
                hpa_name = list(hpa_entry.keys())[0]
                hpa_data = hpa_entry[hpa_name]
                
                namespace = hpa_data.get('namespace', 'default')
                
                # 构造唯一键
                hpa_key = f"{namespace}/{hpa_name}"
                current_hpas.add(hpa_key)
                
                # 如果HPA不在已管理的字典中，获取并添加
                if hpa_key not in self.hpas:
                    # 这里的hpa就是一个HPA的API对象
                    hpa = HorizontalPodAutoscaler.get(namespace, hpa_name, self.api_client, self.uri_config)
                    if hpa:
                        self.hpas[hpa_key] = hpa
                    else:
                        continue  # 如果获取失败，跳过此HPA
                
                # 协调HPA
                self.reconcile_hpa(self.hpas[hpa_key])
            
            # 清理不再存在的HPA
            to_remove = [key for key in self.hpas if key not in current_hpas]
            for key in to_remove:
                print(f"[INFO]Removing HPA {key} from controller")
                del self.hpas[key]
                
        except Exception as e:
            print(f"[ERROR]Error in reconcile: {str(e)}")

    def main_loop(self):
        """控制器主循环"""
        print("[INFO]HPAController main loop started")
        
        while self.running:
            try:
                self.reconcile()
            except Exception as e:
                print(f"[ERROR]Unhandled exception in main loop: {str(e)}")
                
            # 等待下一次循环
            time.sleep(self.reconcile_interval)
            
        print("[INFO]HPAController main loop terminated")

    def start(self):
        """启动控制器"""
        if self.running:
            print("[INFO]HPAController is already running")
            return
            
        self.running = True
        self.main_thread = threading.Thread(target=self.main_loop)
        self.main_thread.daemon = True
        self.main_thread.start()
        
        print("[INFO]HPAController started")

    def stop(self):
        """停止控制器"""
        if not self.running:
            print("[INFO]HPAController is not running")
            return
            
        print("[INFO]Stopping HPAController...")
        self.running = False
        
        if self.main_thread and self.main_thread.is_alive():
            self.main_thread.join(timeout=10)
            
        print("[INFO]HPAController stopped")