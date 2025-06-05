import json
import time
import threading
import logging
from typing import Dict, List, Set
from confluent_kafka import Producer, KafkaException
from pkg.apiObject.service import Service
from pkg.config.serviceConfig import ServiceConfig
from pkg.apiServer.apiClient import ApiC    def handle_po        try:
            self._sync_services()
            self.logger.info("强制同步完成")
        except Exception as e:ent(self, event_type: str, pod):
        """处理Pod事件（添加、删除、更新）"""
        try:
            print.info(f"处理Pod事件: {event_type}, Pod: {pod.get('name', 'unknown') if isinstance(pod, dict) else getattr(pod, 'name', 'unknown')}")
            
            # 对于Pod变化，我们简单地触发一次同步
class ServiceController:
    """Service控制器，负责Service的生命周期管理"""
    
    def __init__(self, etcd_client, uri_config, kafka_config=None):
        self.etcd_client = etcd_client
        self.uri_config = uri_config
        self.kafka_config = kafka_config
        # self.namespace = namespace
        print = logging.getLogger(__name__)
        
        # API客户端
        self.api_client = ApiClient(uri_config.HOST, uri_config.PORT)
        
        # Kafka生产者（用于向ServiceProxy发送规则更新）
        self.kafka_producer = None
        if kafka_config:
            try:
                self.kafka_producer = Producer({
                    'bootstrap.servers': kafka_config.BOOTSTRAP_SERVER
                })
                print("ServiceController已连接到Kafka")
            except Exception as e:
                print(f"连接Kafka失败: {e}")
        
        # Service缓存
        self.services: Dict[str, Service] = {}  # service_name -> Service
        self.service_configs: Dict[str, ServiceConfig] = {}  # service_name -> ServiceConfig
        
        # 控制器状态
        self.running = False
        self.sync_thread = None
        self.sync_interval = 10  # 同步间隔（秒）
        
        # print(f"ServiceController初始化完成，namespace: {namespace}")
    
    def start(self):
        """启动Service控制器"""
        if self.running:
            print("ServiceController已经在运行")
            return
        
        self.running = True
        self.sync_thread = threading.Thread(target=self._sync_loop, daemon=True)
        self.sync_thread.start()
        print("ServiceController已启动")
    
    def stop(self):
        """停止Service控制器"""
        self.running = False
        if self.sync_thread:
            self.sync_thread.join(timeout=5)
        
        # 清理所有Service
        for service in self.services.values():
            try:
                service.stop()
            except Exception as e:
                print(f"停止Service失败: {e}")
        
        self.services.clear()
        self.service_configs.clear()
        print.info("ServiceController已停止")
    
    def _sync_loop(self):
        """同步循环"""
        while self.running:
            try:
                self._sync_services()
                time.sleep(self.sync_interval)
            except Exception as e:
                print.error(f"同步Service失败: {e}")
                time.sleep(self.sync_interval)
    
    def _sync_services(self):
        """同步所有Service"""
        try:
            # 从API Server获取所有Service
            services_data = self._get_all_services()
            if not services_data:
                print.warning("从API Server获取Service列表失败或者目前还没有service")
                return
            
            # 获取所有Pod
            pods = self._get_all_pods()
            
            # 处理每个Service
            print(f"[DEBUG]self.services: {self.services.keys()}")
            current_services = set()
            for service_dict in services_data:
                try:
                    # 解析Service数据
                    service_name = list(service_dict.keys())[0]
                    # service_name = next(iter(service_dict.keys()))
                    service_info = service_dict[service_name]
                    
                    # 创建Service配置
                    service_config = ServiceConfig(service_info)
                    current_services.add(service_name)
                    
                    # 检查Service是否已经在缓存中
                    if service_name in self.services:
                        # 更新现有Service
                        self._update_service(service_name, service_config, pods)
                    else:
                        # 创建新Service
                        self._create_service(service_name, service_config, pods)
                        
                except Exception as e:
                    print.error(f"处理Service {service_name} 失败: {e}")
            
            # 清理不再存在的Service
            self._cleanup_services(current_services)
            
            print.info(f"同步所有Service完成，self.services: {self.services.keys()}")
        except Exception as e:
            print.error(f"同步所有Service失败: {e}")
    
    def _get_all_services(self):
        """从API Server获取所有Service"""
        try:
            # 获取指定namespace的Service
            services_url = self.uri_config.GLOBAL_SERVICES_URL
            response = self.api_client.get(services_url)
            
            print(f"[DEBUG]获取Service列表: {response}")
            
            if response:
                return response
            return []
            
        except Exception as e:
            print.error(f"获取Service列表失败: {e}")
            return []
    
    def _get_all_pods(self) -> List:
        """获取所有Pod"""
        try:
            # 使用API客户端获取Pod
            pods_url = self.uri_config.GLOBAL_PODS_URL
            response = self.api_client.get(pods_url)
            
            # if response and isinstance(response, str):
            #     return json.loads(response)
            # return []
            # 格式为:result.append(
            #    {pod.name: pod.to_dict() if hasattr(pod, "to_dict") else vars(pod)}
            #)
            result = []
            if response:
                # 返回一个Dict list
                for pod_item in response:
                    # 解析Service数据
                    pod_name= list(pod_item.keys())[0]
                    # service_name = next(iter(service_dict.keys()))
                    pod_dict = pod_item[pod_name]
                    result.append(pod_dict)
                # print(f"[DEBUG]获取Pod列表: {result}")
                return result
            return []
        except Exception as e:
            print.error(f"获取Pod列表失败: {e}")
            return []
    
    def _create_service(self, service_name: str, service_config: ServiceConfig, pods: List):
        """创建新的Service"""
        try:
            print.info(f"创建新Service: {service_name}")
            
            # 创建Service实例
            service = Service(service_config)
            
            # 过滤匹配的Pod
            matching_pods = [
                pod for pod in pods 
                if service_config.matches_pod(pod.get("metadata",{}).get("labels", {}))
            ]
            
            # 启动Service
            service.start(matching_pods)
            
            # 缓存Service
            self.services[service_name] = service
            self.service_configs[service_name] = service_config
            
            # 向所有节点广播Service创建规则
            endpoints = [f"{pod.get('subnet_ip', '')}:{service_config.get_port_config()['targetPort']}" 
                        for pod in matching_pods if pod.get('subnet_ip')]
            self._broadcast_service_rules("CREATE", service_name, service_config, endpoints)
            
            print.info(f"Service {service_name} 创建成功")
            
        except Exception as e:
            print.error(f"创建Service {service_name} 失败: {e}")
            raise
    
    def _update_service(self, service_name: str, new_config: ServiceConfig, pods: List):
        """更新现有Service"""
        try:
            print.info(f"更新Service: {service_name}")
            
            old_service = self.services[service_name]
            
            # 配置未变化，只更新端点
            # print(f"pods: {pods}")
            matching_pods = [
                pod for pod in pods 
                if new_config.matches_pod(pod.get("metadata", {}).get("labels", {}))
            ]
            # print(f"matching_pods: {matching_pods}")
            old_service.update_endpoints(matching_pods)
            
            # 向所有节点广播Service更新规则
            endpoints = [f"{pod.get("subnet_ip","")}:{new_config.get_port_config()['targetPort']}" 
                        for pod in matching_pods if pod.get('subnet_ip')]
            self._broadcast_service_rules("UPDATE", service_name, new_config, endpoints)

        except Exception as e:
            print.error(f"更新Service {service_name} 失败: {e}")
            raise
    
    def _cleanup_services(self, current_services: Set[str]):
        """清理不再存在的Service"""
        for service_name in list(self.services.keys()):
            if service_name not in current_services:
                try:
                    print.info(f"清理不再存在的Service: {service_name}")
                    service = self.services[service_name]
                    service_config = self.service_configs[service_name]
                    
                    # 向所有节点广播Service删除规则
                    self._broadcast_service_rules("DELETE", service_name, service_config, [])
                    
                    service.stop()
                    del self.services[service_name]
                    del self.service_configs[service_name]
                except Exception as e:
                    print.error(f"清理Service {service_name} 失败: {e}")
    
    def get_service(self, service_name: str) -> Service:
        """获取Service"""
        if service_name not in self.services:
            raise ValueError(f"Service {service_name} 不存在")
        return self.services[service_name]
    
    def list_services(self) -> List[Service]:
        """列出所有Service"""
        return list(self.services.values())
    
    def get_service_stats(self, service_name: str = None) -> Dict:
        """统计信息"""
        if service_name:
            if service_name not in self.services:
                return {"error": f"Service {service_name} 不存在"}
            return self.services[service_name].get_stats()
        else:
            # 返回所有Service的统计信息
            stats = {
                "total_services": len(self.services),
                "namespace": self.namespace,
                "services": []
            }
            
            for service in self.services.values():
                stats["services"].append(service.get_stats())
            
            return stats
    
    def handle_pod_event(self, event_type: str, pod):
        """处理Pod事件（添加、删除、更新）"""
        try:
            print(f"处理Pod事件: {event_type}, Pod: {pod.get('name', 'unknown') if isinstance(pod, dict) else getattr(pod, 'name', 'unknown')}")
            
            # 对于Pod变化，我们简单地触发一次同步
            self._sync_services()
            
        except Exception as e:
            print.error(f"处理Pod事件失败: {e}")
    
    def force_sync(self):
        """强制同步所有Service"""
        try:
            self._sync_services()
            print("强制同步完成")
        except Exception as e:
            print.error(f"强制同步失败: {e}")
            raise
    
    def _get_all_nodes(self) -> List:
        """获取所有节点信息"""
        try:
            nodes_url = self.uri_config.NODES_URL
            response = self.api_client.get(nodes_url)
            
            if response:
                # API客户端已经自动解析了pickled数据，直接返回即可
                return response
            return []
            
        except Exception as e:
            print.error(f"获取节点列表失败: {e}")
            return []
    
    def _broadcast_service_rules(self, action: str, service_name: str, service_config: ServiceConfig, endpoints: List[str] = None):
        """向所有节点广播Service规则更新"""
        if not self.kafka_producer:
            print.warning("Kafka生产者未配置，无法广播Service规则")
            return
            
        try:
            # 获取所有节点
            nodes = self._get_all_nodes()
            if not nodes:
                print.warning("未找到任何节点，无法广播Service规则")
                return
            
            # 准备Service规则数据
            port_config = service_config.get_port_config()
            rule_data = {
                'service_name': service_name,
                'cluster_ip': service_config.cluster_ip,
                'port': port_config['port'],
                'protocol': port_config['protocol'],
                'endpoints': endpoints or [],
                'node_port': port_config.get('nodePort')
            }
            
            # 向每个节点发送规则更新
            for node in nodes:
                try:
                    node_name = node.name if hasattr(node, 'name') else str(node)
                    topic = f"serviceproxy.{node_name}"
                    
                    self.kafka_producer.produce(
                        topic,
                        key=action,
                        value=json.dumps(rule_data).encode('utf-8')
                    )
                    
                    print.debug(f"已向节点 {node_name} 发送Service {action}消息")
                    
                except Exception as e:
                    print.error(f"向节点发送Service规则失败: {e}")
            
            # 确保消息发送
            self.kafka_producer.flush()
            print(f"已向 {len(nodes)} 个节点广播Service {action}规则: {service_name}")
            
        except Exception as e:
            print.error(f"广播Service规则失败: {e}")
