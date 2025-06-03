class DNSConfig:
    def __init__(self, arg_json, etcd=None):
        # --- static information ---
        metadata = arg_json.get("metadata")
        self.name = metadata.get("name")  # DNS 配置名称
        self.namespace = metadata.get("namespace", "default")  # 命名空间，默认为 default

        spec = arg_json.get("spec")
        self.host = spec.get("host")  # 域名主路径，如 example.com
        self.paths = spec.get("paths")  # 子路径列表，包含 pathName、serviceName、servicePort

    #     # --- dynamic information ---
    #     self.status = "Pending"  # 初始状态为 Pending
    #     self.etcd = etcd  # Etcd 客户端，用于验证 Service 存在

    # def validate(self):
    #     """验证 DNS 配置的有效性"""
    #     if not self.name or not self.host:
    #         raise ValueError("DNSConfig: name and host are required")
    #     if not self.paths:
    #         raise ValueError("DNSConfig: at least one path is required")
    #     if self.etcd:
    #         for path in self.paths:
    #             if not path.get("path") or not path.get("serviceName") or not path.get("servicePort"):
    #                 raise ValueError("DNSConfig: each path must have path, serviceName, and servicePort")
    #             # 验证 Service 是否存在
    #             service_key = EtcdConfig.SERVICE_SPEC_KEY.format(namespace=self.namespace, name=path["serviceName"])
    #             service_data = self.etcd.get(service_key)
    #             if not service_data:
    #                 raise ValueError(f"DNSConfig: Service {path['serviceName']} not found in namespace {self.namespace}")
    #     return True

    def to_dict(self):
        return {
            "metadata": {
                "name": self.name,
                "namespace": self.namespace,
            },
            "spec": {
                "host": self.host,
                "paths": [path.to_dict() for path in self.paths],
            },
        }