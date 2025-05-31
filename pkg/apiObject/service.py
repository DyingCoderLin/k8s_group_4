import logging
import ipaddress
import random
from typing import List, Dict, Optional, Tuple
from pkg.config.serviceConfig import ServiceConfig
from pkg.network.serviceProxy import ServiceProxy
from pkg.loadbalancer.loadBalancer import create_load_balancer


class Service:
    """Service核心类，负责服务发现、负载均衡和网络代理"""
    
    # ClusterIP分配池
    CLUSTER_IP_POOL = "10.96.0.0/16"  # Kubernetes默认Service CIDR
    allocated_ips = set()
    
    def __init__(self, config: ServiceConfig, etcd_client=None):
        self.config = config
        self.etcd_client = etcd_client
        self.logger = logging.getLogger(__name__)
        
        # 网络组件
        self.service_proxy = ServiceProxy()
        self.load_balancer = create_load_balancer("round_robin")  # 默认轮询
        
        # 端点管理
        self.endpoints = []  # [(ip, port), ...]
        self.endpoint_pods = {}  # {endpoint: pod_info}
        
        # 分配ClusterIP
        if not self.config.cluster_ip or self.config.cluster_ip == "None":
            self.config.cluster_ip = self._allocate_cluster_ip()
        
        self.logger.info(f"Service {self.config.name} 初始化完成，ClusterIP: {self.config.cluster_ip}")
    
    def _allocate_cluster_ip(self) -> str:
        """分配ClusterIP"""
        network = ipaddress.IPv4Network(self.CLUSTER_IP_POOL)
        
        # 跳过网络地址和广播地址
        available_ips = list(network.hosts())
        
        # 过滤已分配的IP
        available_ips = [ip for ip in available_ips if str(ip) not in self.allocated_ips]
        
        if not available_ips:
            raise RuntimeError("ClusterIP池已耗尽")
        
        # 随机选择一个IP
        selected_ip = str(random.choice(available_ips))
        self.allocated_ips.add(selected_ip)
        
        return selected_ip
    
    @classmethod
    def release_cluster_ip(cls, ip: str):
        """释放ClusterIP"""
        cls.allocated_ips.discard(ip)
    
    def discover_endpoints(self, pods: List) -> List[Tuple[str, int]]:
        """发现匹配的Pod端点"""
        endpoints = []
        self.endpoint_pods.clear()
        
        for pod in pods:
            # 检查Pod是否匹配Service的选择器
            if not self.config.matches_pod(pod.labels):
                continue
            
            # 检查Pod是否处于运行状态
            if pod.status != "Running":
                continue
            
            # 获取Pod的IP地址
            pod_ip = self._get_pod_ip(pod)
            if not pod_ip:
                continue
            
            # 获取目标端口
            target_port = self._get_target_port(pod)
            if not target_port:
                continue
            
            endpoint = (pod_ip, target_port)
            endpoints.append(endpoint)
            
            # 保存Pod信息
            self.endpoint_pods[f"{pod_ip}:{target_port}"] = {
                "name": pod.name,
                "namespace": pod.namespace,
                "node_name": getattr(pod, 'node_name', 'unknown'),
                "labels": pod.labels
            }
        
        self.logger.info(f"Service {self.config.name} 发现了 {len(endpoints)} 个端点")
        return endpoints
    
    def _get_pod_ip(self, pod) -> Optional[str]:
        """获取Pod的IP地址"""
        try:
            # 从Pod的网络配置中获取IP
            if hasattr(pod, 'pod_ip') and pod.pod_ip:
                return pod.pod_ip
            
            # 尝试从Docker容器中获取IP
            if hasattr(pod, 'containers') and pod.containers:
                container = pod.containers[0]  # 使用第一个容器
                if hasattr(container, 'attrs'):
                    networks = container.attrs.get('NetworkSettings', {}).get('Networks', {})
                    for network_name, network_info in networks.items():
                        ip_address = network_info.get('IPAddress')
                        if ip_address:
                            return ip_address
            
            # 如果以上方法都失败，尝试通过docker inspect获取
            if hasattr(pod, 'config') and hasattr(pod.config, 'name'):
                import subprocess
                try:
                    result = subprocess.run([
                        'docker', 'inspect', '-f', 
                        '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}',
                        f"pause_{pod.config.namespace}_{pod.config.name}"
                    ], capture_output=True, text=True, check=True)
                    
                    ip = result.stdout.strip()
                    if ip:
                        return ip
                except subprocess.CalledProcessError:
                    pass
            
            self.logger.warning(f"无法获取Pod {getattr(pod, 'name', 'unknown')} 的IP地址")
            return None
            
        except Exception as e:
            self.logger.error(f"获取Pod IP失败: {e}")
            return None
    
    def _get_target_port(self, pod) -> Optional[int]:
        """获取Pod的目标端口"""
        try:
            port_config = self.config.get_port_config()
            if not port_config:
                return None
            
            target_port = port_config.get('targetPort')
            if target_port:
                return int(target_port)
            
            # 如果没有指定targetPort，使用port
            return int(port_config.get('port', 80))
            
        except Exception as e:
            self.logger.error(f"获取目标端口失败: {e}")
            return None
    
    def update_endpoints(self, pods: List):
        """更新Service端点"""
        try:
            # 发现新的端点
            new_endpoints = self.discover_endpoints(pods)
            
            # 更新负载均衡器
            endpoint_strings = [f"{ip}:{port}" for ip, port in new_endpoints]
            self.load_balancer.update_endpoints(endpoint_strings)
            
            # 更新iptables规则
            if self.config.ports:
                port_config = self.config.ports[0]  # 使用第一个端口配置
                self.service_proxy.update_service_endpoints(
                    service_name=self.config.name,
                    cluster_ip=self.config.cluster_ip,
                    port=port_config['port'],
                    protocol=port_config.get('protocol', 'TCP'),
                    endpoints=endpoint_strings,
                    node_port=port_config.get('nodePort')
                )
            
            self.endpoints = new_endpoints
            self.config.status = "Running" if new_endpoints else "Pending"
            
            self.logger.info(f"Service {self.config.name} 端点已更新: {len(new_endpoints)} 个端点")
            
        except Exception as e:
            self.logger.error(f"更新Service端点失败: {e}")
            self.config.status = "Failed"
    
    def get_endpoint(self) -> Optional[str]:
        """获取下一个可用端点（用于客户端负载均衡）"""
        return self.load_balancer.get_next_endpoint()
    
    def start(self, pods: List):
        """启动Service"""
        try:
            self.logger.info(f"启动Service {self.config.name}")
            
            # 更新端点
            self.update_endpoints(pods)
            
            if not self.endpoints:
                self.logger.warning(f"Service {self.config.name} 没有可用的端点")
                self.config.status = "Pending"
                return
            
            self.config.status = "Running"
            self.logger.info(f"Service {self.config.name} 启动成功")
            
        except Exception as e:
            self.logger.error(f"启动Service失败: {e}")
            self.config.status = "Failed"
            raise
    
    def stop(self):
        """停止Service"""
        try:
            self.logger.info(f"停止Service {self.config.name}")
            
            # 删除iptables规则
            if self.config.ports:
                port_config = self.config.ports[0]
                self.service_proxy.delete_service_rules(
                    service_name=self.config.name,
                    cluster_ip=self.config.cluster_ip,
                    port=port_config['port'],
                    protocol=port_config.get('protocol', 'TCP'),
                    node_port=port_config.get('nodePort')
                )
            
            # 释放ClusterIP
            self.release_cluster_ip(self.config.cluster_ip)
            
            self.config.status = "Stopped"
            self.logger.info(f"Service {self.config.name} 已停止")
            
        except Exception as e:
            self.logger.error(f"停止Service失败: {e}")
    
    def get_stats(self) -> dict:
        """获取Service统计信息"""
        stats = {
            "name": self.config.name,
            "namespace": self.config.namespace,
            "type": self.config.type,
            "cluster_ip": self.config.cluster_ip,
            "status": self.config.status,
            "endpoints": len(self.endpoints),
            "endpoint_details": []
        }
        
        # 添加端点详情
        for endpoint in self.endpoints:
            endpoint_key = f"{endpoint[0]}:{endpoint[1]}"
            pod_info = self.endpoint_pods.get(endpoint_key, {})
            stats["endpoint_details"].append({
                "endpoint": endpoint_key,
                "pod_name": pod_info.get("name", "unknown"),
                "node_name": pod_info.get("node_name", "unknown")
            })
        
        # 添加iptables统计
        iptables_stats = self.service_proxy.get_service_stats(self.config.name)
        stats["iptables_stats"] = iptables_stats
        
        return stats
    
    def to_dict(self):
        """转换为字典格式"""
        return self.config.to_dict()
