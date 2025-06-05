import logging
import ipaddress
import random
from typing import List, Dict, Optional, Tuple
from pkg.config.serviceConfig import ServiceConfig
from pkg.network.serviceProxy import ServiceProxy
from pkg.loadbalancer.loadBalancer import create_load_balancer
from pkg.config.uriConfig import URIConfig
from pkg.apiServer.apiClient import ApiClient
import json


class Service:
    """Service核心类，负责服务发现、负载均衡和网络代理"""

    # ClusterIP分配池
    CLUSTER_IP_POOL = "10.96.0.0/16"  # Kubernetes默认Service CIDR
    allocated_ips = set()

    def __init__(self, config: ServiceConfig):
        self.logger = logging.getLogger(__name__)

        # 保存配置
        self.config = config

        # 网络组件
        self.service_proxy = ServiceProxy()
        self.load_balancer = create_load_balancer("round_robin")  # 默认轮询

        # 端点管理
        self.endpoints = []  # [(ip, port), ...]
        self.endpoint_pods = {}  # {endpoint: pod_info}

        self.api_client = None  # API客户端
        self.uri_config = None

        self.set_api_client()  # 初始化API客户端和URI配置

        # 分配ClusterIP,如果没有分配过cluster_ip，则分配一个新的
        if not self.config.cluster_ip or self.config.cluster_ip == "None":
            self.config.cluster_ip = self._allocate_cluster_ip()
            # 告知apiServer分配的ClusterIP
            self.update_service_cluster_ip(
                namespace=self.config.namespace,
                name=self.config.name,
                cluster_ip=self.config.cluster_ip,
            )

        self.logger.info(
            f"Service {self.config.name} 初始化完成，ClusterIP: {self.config.cluster_ip}"
        )

    def set_api_client(self, api_client=None, uri_config=None):
        """设置API客户端，用于与API Server通信"""
        self.api_client = api_client or ApiClient()
        self.uri_config = uri_config or URIConfig()
        return self

    def _ensure_api_client(self):
        """确保API客户端已初始化"""
        if not self.api_client:
            self.api_client = ApiClient()
            self.uri_config = URIConfig()

    def update_service_cluster_ip(self, namespace, name, cluster_ip) -> bool:
        """更新ReplicaSet状态"""
        try:
            url = self.uri_config.SERVICE_SPEC_URL.format(
                namespace=namespace, name=name
            )
            response = self.api_client.put(url, data={"cluster_ip": cluster_ip})

            if response:
                print(f"[INFO]Updated ReplicaSet {name}")
                return True
            else:
                print(f"[ERROR]Failed to update ReplicaSet {name}")
        except Exception as e:
            print(f"[ERROR]Error updating ReplicaSet {name}: {str(e)}")

        return False

    def _allocate_cluster_ip(self) -> str:
        """分配ClusterIP"""
        network = ipaddress.IPv4Network(self.CLUSTER_IP_POOL)

        # 跳过网络地址和广播地址
        available_ips = list(network.hosts())

        # 过滤已分配的IP
        available_ips = [
            ip for ip in available_ips if str(ip) not in self.allocated_ips
        ]

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

    # def discover_endpoints(self, pods: List) -> List[Tuple[str, int]]:
    #     """发现匹配的Pod端点

    #     Returns:
    #         List[Tuple[str, int]]: 端点列表，每个端点为(ip, port)元组
    #     """
    #     endpoints = []
    #     self.endpoint_pods.clear()

    #     for pod in pods:
    #         # 检查Pod是否匹配Service的选择器
    #         pod_labels = pod.get("labels", {}) if isinstance(pod, dict) else getattr(pod, "labels", {})
    #         if not self.config.matches_pod(pod_labels):
    #             continue

    #         # 获取Pod的IP地址
    #         pod_ip = self._get_pod_ip(pod)
    #         if not pod_ip:
    #             continue

    #         # 创建端点
    #         endpoint = (pod_ip, self.config.target_port)
    #         endpoints.append(endpoint)

    #         # 保存Pod信息
    #         endpoint_key = f"{pod_ip}:{self.config.target_port}"
    #         self.endpoint_pods[endpoint_key] = {
    #             "name": pod.get("name") if isinstance(pod, dict) else getattr(pod, "name", "unknown"),
    #             "namespace": pod.get("namespace") if isinstance(pod, dict) else getattr(pod, "namespace", "default"),
    #             "node_name": pod.get("node_name") if isinstance(pod, dict) else getattr(pod, "node_name", "unknown"),
    #             "labels": pod_labels
    #         }

    #     self.logger.info(f"Service {self.config.name} 发现了端点: {endpoints}")
    #     return endpoints

    def convert_pods_to_endpoints(self, pods: List) -> List[Tuple[str, int]]:
        """将Pod列表转换为端点列表

        Args:
            pods (List): Pod对象列表

        Returns:
            List[Tuple[str, int]]: 端点列表，每个端点为(ip, port)元组
        """
        endpoints = []

        for pod in pods:
            pod_ip = (
                pod.get("subnet_ip")
                if isinstance(pod, dict)
                else getattr(pod, "subnet_ip", None)
            )
            if pod_ip:
                endpoints.append((pod_ip, self.config.target_port))

        return endpoints

    def _get_pod_ip(self, pod) -> Optional[str]:
        """从apiserver获取Pod的IP地址"""
        try:
            name = pod.get("metadata", {}).get("name")
            namespace = pod.get("metadata", {}).get("namespace", "default")
            print(f"[INFO]获取Pod {name} 的IP地址，命名空间: {namespace}")
            if self.api_client is None:
                self._ensure_api_client()
            # 返回格式为: return json.dumps({"subnet_ip": "None"}), 200
            response = self.api_client.get(
                self.uri_config.POD_SPEC_IP_URL.format(namespace=namespace, name=name),
            )
            # 提取出subnet_ip
            if response:
                response_data = json.loads(response)
                pod_ip = response_data.get("subnet_ip")
                if pod_ip and pod_ip != "None":
                    return pod_ip
            return None
        except Exception as e:
            self.logger.error(f"获取Pod IP失败: {e}")
            return None

    def update_endpoints(self, new_pods: List):
        """更新Service端点"""
        try:
            # 发现新的端点
            new_endpoints = self.convert_pods_to_endpoints(new_pods)

            # 将self.endpoints和new_endpoints比较，如果没有变化，直接返回
            if self._are_endpoints_equal(self.endpoints, new_endpoints):
                self.logger.info(f"Service {self.config.name} 端点未变化，跳过更新")
                return

            self.endpoint_pods.clear()

            for pod in new_pods:
                pod_ip = (
                    pod.get("subnet_ip")
                    if isinstance(pod, dict)
                    else getattr(pod, "subnet_ip", None)
                )
                if pod_ip:
                    pod_labels = (
                        pod.get("metadata", {}).get("labels", {})
                        if isinstance(pod, dict)
                        else getattr(pod, "labels", {})
                    )

                    endpoint_key = f"{pod_ip}:{self.config.target_port}"
                    metadata = (
                        pod.get("metadata", {})
                        if isinstance(pod, dict)
                        else getattr(pod, "metadata", {})
                    )
                    self.endpoint_pods[endpoint_key] = {
                        "name": metadata.get("name"),
                        "namespace": metadata.get("namespace", "default"),
                        "node_name": (
                            pod.get("node_name")
                            if isinstance(pod, dict)
                            else getattr(pod, "node_name", "unknown")
                        ),
                        "labels": pod_labels,
                    }

            # 更新负载均衡器
            endpoint_strings = [f"{ip}:{port}" for ip, port in new_endpoints]
            self.load_balancer.update_endpoints(endpoint_strings)

            # 更新iptables规则
            port_config = self.config.get_port_config()
            self.service_proxy.update_service_endpoints(
                service_name=self.config.name,
                cluster_ip=self.config.cluster_ip,
                port=port_config["port"],
                protocol=port_config["protocol"],
                endpoints=endpoint_strings,
                node_port=port_config["nodePort"],
            )

            self.endpoints = new_endpoints
            self.config.status = "Running" if new_endpoints else "Pending"

            self.logger.info(f"Service {self.config.name} 端点已更新: {new_endpoints}")

        except Exception as e:
            self.logger.error(f"更新Service端点失败: {e}")
            self.config.status = "Failed"

    def get_endpoint(self) -> Optional[str]:
        """获取下一个可用端点（用于客户端负载均衡）"""
        if not self.endpoints:
            return None

        return self.load_balancer.get_next_endpoint()

    def start(self, pods: List):
        """启动Service"""
        try:
            self.logger.info(f"启动Service {self.config.name}")

            # 更新端点
            self.update_endpoints(pods)

            if not self.endpoints:
                self.logger.warning(f"Service {self.config.name} 没有可用的端点")
                # self.config.status = "Pending"
                return

            # self.config.status = "Running"
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
            port_config = self.config.get_port_config()
            self.service_proxy.delete_service_rules(
                service_name=self.config.name,
                cluster_ip=self.config.cluster_ip,
                port=port_config["port"],
                protocol=port_config["protocol"],
                node_port=port_config["nodePort"],
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
            "endpoint_details": [],
        }

        # 添加端点信息
        for endpoint in self.endpoints:
            endpoint_key = f"{endpoint[0]}:{endpoint[1]}"
            pod_info = self.endpoint_pods.get(endpoint_key, {})
            stats["endpoint_details"].append(
                {
                    "endpoint": endpoint_key,
                    "pod_name": pod_info.get("name", "unknown"),
                    "node_name": pod_info.get("node_name", "unknown"),
                }
            )

        # 添加iptables统计
        port_config = self.config.get_port_config()
        stats["iptables_stats"] = self.service_proxy.get_service_stats(self.config.name)

        return stats

    def to_dict(self):
        """转换为字典格式"""
        return self.config.to_dict()

    def _are_endpoints_equal(
        self, endpoints1: List[Tuple[str, int]], endpoints2: List[Tuple[str, int]]
    ) -> bool:
        """比较两组端点是否相同

        Args:
            endpoints1: 第一组端点，每个端点为(ip, port)元组
            endpoints2: 第二组端点，每个端点为(ip, port)元组

        Returns:
            bool: 如果两组端点相同，则返回True，否则返回False
        """
        # 如果长度不同，则端点组不同
        if len(endpoints1) != len(endpoints2):
            return False

        # 将端点转换为集合，便于比较
        set1 = set((ip, port) for ip, port in endpoints1)
        set2 = set((ip, port) for ip, port in endpoints2)

        # 如果两个集合相同，则端点组相同
        return set1 == set2

    # 写一个测试，用test-service-clusterip.yaml导入，完成service创建的测试


if __name__ == "__main__":

    # 测试Service类
    try:
        import yaml
        import os
        from pkg.config.globalConfig import GlobalConfig
        import requests

        config = GlobalConfig()
        test_file = "test-service-clusterip.yaml"
        test_yaml = os.path.join(config.TEST_FILE_PATH, test_file)
        with open(test_yaml, "r", encoding="utf-8") as file:
            data = yaml.safe_load(file)

            uri = URIConfig.PREFIX + URIConfig.SERVICE_SPEC_URL.format(
                namespace=data["metadata"]["namespace"],
                name=data["metadata"]["name"],
            )
            print(f"测试Service创建，API请求地址: {uri}")
            response = requests.post(uri, json=data)
            print(f"[INFO]响应状态码: {response.status_code}")
        if response.status_code == 200:
            print(f"[INFO]Service创建成功: {response.json()}")

    except Exception as e:
        print(f"[ERROR]测试Service失败: {e}")
