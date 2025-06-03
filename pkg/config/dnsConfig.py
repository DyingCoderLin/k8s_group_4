from pkg.config.etcdConfig import EtcdConfig
from pkg.apiServer.etcd import Etcd
import pickle

class DNSConfig:
    def __init__(self, arg_json, etcd=None):
        metadata = arg_json.get("metadata")
        self.name = metadata.get("name")  # DNS 配置名称
        self.namespace = metadata.get("namespace", "default")  # 命名空间，默认为 default

        spec = arg_json.get("spec")
        self.host = spec.get("host")  # 域名主路径，如 example.com
        self.paths = spec.get("paths")  # 子路径列表，包含 path、serviceName、servicePort

        self.status = "Pending"  # 初始状态
        self.etcd = Etcd  # Etcd 客户端，用于验证 Service 和存储映射

    def validate(self):
        """验证 DNS 配置的有效性"""
        if not self.name or not self.host:
            raise ValueError("DNSConfig: name 和 host 为必填项")
        if not self.paths:
            raise ValueError("DNSConfig: 至少需要一个路径")
        if self.etcd:
            for path in self.paths:
                if not path.get("path") or not path.get("serviceName") or not path.get("servicePort"):
                    raise ValueError("DNSConfig: 每个路径必须包含 path、serviceName 和 servicePort")
                # 验证 Service 是否存在
                service_key = EtcdConfig.SERVICE_SPEC_KEY.format(namespace=self.namespace, name=path["serviceName"])
                service_data = self.etcd.get(service_key)
                if not service_data:
                    raise ValueError(f"DNSConfig: 在命名空间 {self.namespace} 中未找到 Service {path['serviceName']}")
        return True

    def get_service_mapping(self):
        """获取路径到 Service IP:Port 的映射"""
        if not self.etcd:
            raise ValueError("DNSConfig: 需要 etcd 客户端来查询 Service")
        mapping = {}
        for path in self.paths:
            service_key = EtcdConfig.SERVICE_SPEC_KEY.format(namespace=self.namespace, name=path["serviceName"])
            service_data = self.etcd.get(service_key)
            if service_data:
                service_info = pickle.loads(service_data)
                service_ip = service_info.get("spec", {}).get("clusterIP")
                service_port = path["servicePort"]
                mapping[path["path"]] = f"{service_ip}:{service_port}"
        return mapping

    def to_dict(self):
        return {
            "metadata": {
                "name": self.name,
                "namespace": self.namespace,
            },
            "spec": {
                "host": self.host,
                "paths": self.paths,  # 假设 paths 是字典列表
            },
            "status": self.status
        }
