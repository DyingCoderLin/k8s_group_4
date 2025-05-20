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
            print(f"[INFO]Updating HPA {hpa.name} in namespace {hpa.namespace}, hpa config: {hpa.to_config_dict()}")
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
        """评估当前指标，决定是扩容还是缩容"""
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
        
        # 如果没有设置目标，保持当前副本数
        if cpu_target is None and memory_target is None:
            print("[INFO]No valid metric targets found")
            return target_resource['spec']['replicas']
        
        # 获取当前资源使用情况
        try:
            # 直接使用HPA对象提供的方法获取整机CPU和内存使用率
            cpu_usage = hpa.get_cpu_usage_percentage()
            memory_usage = hpa.get_memory_usage_percentage()
            
            print(f"[INFO]CPU使用率: {cpu_usage if cpu_usage is not None else 'N/A'}%, " 
                f"目标: {cpu_target}%")
            print(f"[INFO]内存使用率: {memory_usage if memory_usage is not None else 'N/A'}%, " 
                f"目标: {memory_target}%")
            
            # 获取期望副本数
            replica_count = target_resource['spec']['replicas']
            
            # 判断是扩容还是缩容
            should_scale_up = False
            should_scale_down = True  # 默认缩容，除非有指标超过阈值
            
            # 检查CPU是否需要扩容
            if cpu_target is not None and cpu_usage is not None:
                # CPU使用率超过目标值，需要扩容
                if cpu_usage > cpu_target:
                    should_scale_up = True
                    should_scale_down = False
                # CPU使用率低于目标值，可能需要缩容
                elif cpu_usage < cpu_target:
                    pass  # 维持should_scale_down为True
            
            # 检查内存是否需要扩容
            if memory_target is not None and memory_usage is not None:
                # 内存使用率超过目标值，需要扩容
                if memory_usage > memory_target:
                    should_scale_up = True
                    should_scale_down = False
                # 内存使用率低于目标值，可能需要缩容
                elif memory_usage < memory_target:
                    pass  # 维持should_scale_down为True
            
            # 保存当前指标
            hpa.current_metrics = {
                'cpu': cpu_usage,
                'memory': memory_usage
            }
            
            # 决定新的副本数
            new_replicas = replica_count
            
            if should_scale_up and replica_count < hpa.max_replicas:
                # 扩容：增加一个副本
                new_replicas = replica_count + 1
                print(f"[INFO]资源使用率超过阈值，需扩容：{replica_count} → {new_replicas}")
            elif should_scale_down and replica_count > hpa.min_replicas:
                # 缩容：减少一个副本
                new_replicas = replica_count - 1
                print(f"[INFO]资源使用率低于阈值，需缩容：{replica_count} → {new_replicas}")
            else:
                print(f"[INFO]资源使用率适中或已达到副本数限制，维持当前副本数：{replica_count}")
            
            return new_replicas
            
        except Exception as e:
            print(f"[ERROR]获取资源使用情况出错: {e}")
            import traceback
            print(f"[ERROR]详细错误: {traceback.format_exc()}")
            # 出错时保持当前副本数
            return target_resource['spec']['replicas']
        
    def update_rs_config(self, rs_config):
        """更新ReplicaSet配置"""
        try:
            print(f"[INFO]Updating ReplicaSet {rs_config['metadata']['name']} in namespace {rs_config['metadata']['namespace']},rs config: {rs_config}")
            url = self.uri_config.REPLICA_SET_SPEC_URL.format(namespace=rs_config['metadata']['namespace'], name=rs_config['metadata']['name'])
            response = self.api_client.put(url, rs_config)
            if response:
                print(f"[INFO]Updated ReplicaSet {rs_config['metadata']['name']}")
                return True
            else:
                print(f"[ERROR]Failed to update ReplicaSet")
        except Exception as e:
            print(f"[ERROR]Error updating ReplicaSet : {str(e)}")
        return False

    def scale_target(self, hpa, target_replicas,target=None):
        """调整目标资源的副本数量"""
        # 获取目标资源
        if not target:
            print(f"[ERROR]Target {hpa.target_kind} {hpa.target_name} not found")
            return False
                
        if target['spec']['replicas'] == target_replicas:
            return True  # 已经是目标数量，无需调整
        
        # 检查冷却期
        if hpa.last_scale_time and (datetime.datetime.now() - hpa.last_scale_time).total_seconds() < self.cooldown_seconds:
            print(f"[INFO]In cooldown period, skipping scaling")
            return False  # 冷却期内，不进行调整
        
        # 执行扩缩容
        print(f"[INFO]Scaling {hpa.target_kind} {hpa.target_name} to {target_replicas} replicas")
        # scaling_success = target.scale(target_replicas)
        target['spec']['replicas'] = target_replicas
        scaling_success = self.update_rs_config(target)
        
        if scaling_success:
            # 更新HPA状态
            hpa.last_scale_time = datetime.datetime.now()
            hpa.current_replicas = target_replicas
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
            print(f"[INFO]Target resource: {target}")
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
            replica_count = 0
            if hasattr(target, 'spec') and 'replicas' in target['spec']:
                replica_count = target['spec']['replicas']
                print(f"[INFO]Current rs replicas: {replica_count}")
            
            # 更新HPA状态
            hpa.current_replicas = replica_count
            
            # 如果需要调整副本数
            if new_replicas != replica_count:
                scaling_result = self.scale_target(hpa, new_replicas,target)
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