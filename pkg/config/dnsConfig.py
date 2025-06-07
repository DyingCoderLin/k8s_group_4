class DNSConfig:
    def __init__(self, arg_json):
        # if not isinstance(arg_json, dict) or "metadata" not in arg_json or "spec" not in arg_json:
        #     raise ValueError("Invalid DNS configuration: missing metadata or spec")

        metadata = arg_json.get("metadata")
        self.name = metadata.get("name")  # DNS 配置名称
        self.namespace = metadata.get("namespace", "default")  # 命名空间，默认为 default

        spec = arg_json.get("spec")
        self.host = spec.get("host")  # 域名主路径，如 example.com
        self.paths = spec.get("paths")  # 子路径列表，包含 path、serviceName、servicePort

    def to_dict(self):
        """转换为字典格式用于API返回或序列化"""
        return {
            "metadata": {
                "name": self.name,
                "namespace": self.namespace,
            },
            "spec": {
                "host": self.host,
                "paths": self.paths,  # 假设 paths 是字典列表
            }
        }