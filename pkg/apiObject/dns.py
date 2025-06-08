import logging
from typing import List, Dict, Optional, Tuple
from pkg.config.dnsConfig import DNSConfig
from pkg.apiServer.apiClient import ApiClient
from pkg.config.uriConfig import URIConfig
import json

class DNS:
    """DNS核心类，负责域名解析和路径路由到服务端点"""
    def __init__(self, config: DNSConfig):
        self.logger = logging.getLogger(__name__)

        # 保存配置
        self.config = config

        self.api_client = None  # API客户端
        self.uri_config = None
        self.set_api_client()  # 初始化API客户端和URI配置

        self.dns_records = {}  # 存储 DNS 记录: { "host/path": (service_name, cluster_ip, port) }

        # 初始化 DNS 记录
        self._initialize_dns_records()
        print(f"DNS {self.config.name} 初始化完成，域名: {self.config.host}")

    def set_api_client(self, api_client = None, uri_config=None):
        """设置API客户端，用于与API Server通信"""
        self.api_client = api_client or ApiClient()
        self.uri_config = uri_config or URIConfig()
        return self

    def _ensure_api_client(self):
        """确保 API 客户端已初始化"""
        if not self.api_client:
            self.api_client = ApiClient()
            self.uri_config = URIConfig()

    def _initialize_dns_records(self):
        """根据 DNSConfig 初始化 DNS 记录"""
        try:
            namespace = self.config.namespace
            if not namespace:
                namespace = "default"

            for path in self.config.paths:
                service_name = path.get("serviceName")
                service_port = path.get("servicePort")

                key = self.uri_config.SERVICE_SPEC_URL.format(namespace=namespace, name=service_name)
                response = self.api_client.get(key)

                if not response:
                    print(f"Service '{service_name}' not found in namespace '{namespace}'")
                    return

                print(f"获取服务 {response}")

                spec = response.get("spec")
                # TODO
                # cluster_ip = "0.0.0.0"  # 默认值，实际获取时需要从 spec 中提取
                cluster_ip = spec.get("clusterIP")

                if not cluster_ip:
                    self.logger.warning(f"服务 {service_name} 未分配 ClusterIP")
                    continue
                ports =spec.get('ports')

                # 构造 DNS 记录的键（host + path）
                dns_key = f"{self.config.host}{path.get("path")}"
                self.dns_records[dns_key] = (service_name, cluster_ip, ports)
                print(f"添加 DNS 记录: {dns_key} -> ({service_name}, {cluster_ip}, {ports})")
                
            # # 更新 API Server 的 DNS 配置
            # self._update_dns_config()

        except Exception as e:
            self.logger.error(f"初始化 DNS 记录失败: {e}")

    # def _get_service_info(self, namespace: str, service_name: str) -> Optional[Dict]:
    #     """从 API Server 获取服务信息"""
    #     try:
    #         self._ensure_api_client()
    #         response = self.api_client.get(
    #             self.uri_config.SERVICE_SPEC_URL.format(
    #                 namespace=namespace, name=service_name
    #             )
    #         )
    #         if response:
    #             try:
    #                 return json.loads(response)
    #             except json.JSONDecodeError:
    #                 self.logger.error(f"服务 {namespace}/{service_name} 响应格式错误")
    #                 return None
                
    #         self.logger.error(f"获取服务 {namespace}/{service_name} 信息失败")
    #         return None
    #     except Exception as e:
    #         self.logger.error(f"获取服务信息失败: {e}")
    #         return None

    def resolve(self, host: str, path: str) -> Optional[Tuple[str, int]]:
        """解析域名和路径，返回对应的服务端点 (ClusterIP, port)"""
        try:
            dns_key = f"{host}{path}"
            if dns_key in self.dns_records:
                service_name, cluster_ip, port = self.dns_records[dns_key]
                print(f"DNS 解析成功: {dns_key} -> ({service_name}, {cluster_ip}, {port})")
                return (cluster_ip, port)
            
            self.logger.warning(f"DNS 解析失败: 未找到记录 {dns_key}")
            return None
        
        except Exception as e:
            self.logger.error(f"DNS 解析错误: {e}")
            return None

    # def update_dns_records(self):
    #     """当服务信息变化时，更新 DNS 记录"""
    #     try:
    #         self.dns_records.clear()
    #         self._initialize_dns_records()
    #         print(f"DNS {self.config.name} 记录已更新")
    #         return True
    #     except Exception as e:
    #         self.logger.error(f"更新 DNS 记录失败: {e}")
    #         return False

    # def add_path(self, path: Dict):
    #     """动态添加新的路径映射"""
    #     try:
    #         service_name = path.get("serviceName")
    #         service_port = path.get("servicePort")
    #         path_str = path.get("path")
    #         namespace = self.config.namespace

    #         # 验证服务是否存在
    #         service_info = self._get_service_info(namespace, service_name)
    #         if not service_info:
    #             self.logger.error(f"无法添加路径: 服务 {service_name} 不存在")
    #             return False

    #         cluster_ip = service_info.get("spec", {}).get("cluster_ip")
    #         if not cluster_ip or cluster_ip == "None":
    #             self.logger.error(f"无法添加路径: 服务 {service_name} 未分配 ClusterIP")
    #             return False

    #         # 更新 DNS 记录
    #         dns_key = f"{self.config.host}{path_str}"
    #         self.dns_records[dns_key] = (service_name, cluster_ip, service_port)
    #         self.config.paths.append(path)
    #         print(f"添加路径成功: {dns_key} -> ({service_name}, {cluster_ip}, {service_port})")

    #         # 更新 API Server 的 DNS 配置
    #         self._update_dns_config()
    #         return True
    #     except Exception as e:
    #         self.logger.error(f"添加路径失败: {e}")
    #         return False

    def remove_path(self, path_str: str):
        """删除指定的路径映射"""
        try:
            dns_key = f"{self.config.host}{path_str}"
            if dns_key in self.dns_records:
                del self.dns_records[dns_key]
                self.config.paths = [p for p in self.config.paths if p["path"] != path_str]
                print(f"删除路径成功: {dns_key}")

                # 更新 API Server 的 DNS 配置
                self._update_dns_config()
                return True
            self.logger.warning(f"删除路径失败: 未找到 {dns_key}")
            return False
        except Exception as e:
            self.logger.error(f"删除路径失败: {e}")
            return False

    def _update_dns_config(self):
        """更新 API Server 中的 DNS 配置"""
        try:
            url = self.uri_config.DNS_SPEC_URL.format(
                namespace=self.config.namespace, name=self.config.name
            )
            response = self.api_client.put(url, data=self.config.to_dict())
            
            if response:
                print(f"更新 DNS 配置成功: {self.config.name}")
                return True
            self.logger.error(f"更新 DNS 配置失败: {self.config.name}")
            return False
        except Exception as e:
            self.logger.error(f"更新 DNS 配置错误: {e}")
            return False

    def get_stats(self) -> Dict:
        """获取 DNS 统计信息"""
        return {
            "name": self.config.name,
            "namespace": self.config.namespace,
            "host": self.config.host,
            "paths_count": len(self.config.paths),
            "records": [
                {"path": path, "service": info[0], "cluster_ip": info[1], "port": info[2]}
                for path, info in self.dns_records.items()
            ]
        }

    def to_dict(self):
        """转换为字典格式"""
        return self.config.to_dict()
    
