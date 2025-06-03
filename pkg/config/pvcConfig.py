class PVCConfig:
    """Persistent Volume Claim 配置类（简化版）"""
    
    def __init__(self, arg_json):
        # 基本元数据
        metadata = arg_json.get("metadata", {})
        self.name = metadata.get("name")
        self.namespace = metadata.get("namespace", "default")
        self.labels = metadata.get("labels", {})
        
        # PVC 规格
        spec = arg_json.get("spec", {})
        
        # 资源请求
        resources = spec.get("resources", {})
        requests = resources.get("requests", {})
        self.storage = requests.get("storage", "1Gi")
        
        # 状态信息
        status = arg_json.get("status", {})
        self.phase = status.get("phase", "Pending")  # Pending, Bound, Lost
        self.volume_name = status.get("volumeName", None)  # 绑定的 PV 名称
        self.capacity = status.get("capacity", {})
        
    def to_dict(self):
        """转换为字典格式"""
        result = {
            "apiVersion": "v1",
            "kind": "PersistentVolumeClaim",
            "metadata": {
                "name": self.name,
                "namespace": self.namespace,
                "labels": self.labels,
            },
            "spec": {
                "resources": {
                    "requests": {
                        "storage": self.storage
                    }
                }
            },
            "status": {
                "phase": self.phase,
            }
        }
        
        # 添加绑定信息（如果已绑定）
        if self.volume_name:
            result["status"]["volumeName"] = self.volume_name
        
        if self.capacity:
            result["status"]["capacity"] = self.capacity
        
        return result
    
    def get_capacity_bytes(self):
        """获取容量需求（字节数）"""
        return self._parse_storage_size(self.storage)
    
    def _parse_storage_size(self, size_str):
        """解析存储大小字符串为字节数"""
        if not size_str:
            return 0
        
        size_str = size_str.strip().upper()
        
        # 提取数字和单位
        import re
        match = re.match(r'^(\d+(?:\.\d+)?)\s*([KMGTPE]?I?B?)$', size_str)
        if not match:
            raise ValueError(f"Invalid storage size format: {size_str}")
        
        number = float(match.group(1))
        unit = match.group(2) or "B"
        
        # 单位转换
        units = {
            "B": 1,
            "K": 1024, "KB": 1024, "KI": 1024, "KIB": 1024,
            "M": 1024**2, "MB": 1024**2, "MI": 1024**2, "MIB": 1024**2,
            "G": 1024**3, "GB": 1024**3, "GI": 1024**3, "GIB": 1024**3,
            "T": 1024**4, "TB": 1024**4, "TI": 1024**4, "TIB": 1024**4,
            "P": 1024**5, "PB": 1024**5, "PI": 1024**5, "PIB": 1024**5,
            "E": 1024**6, "EB": 1024**6, "EI": 1024**6, "EIB": 1024**6,
        }
        
        return int(number * units.get(unit, 1))
    
    def bind_to_pv(self, pv_config):
        """绑定到指定的 PV"""
        self.phase = "Bound"
        self.volume_name = pv_config.name
        self.capacity = {"storage": pv_config.storage}
    
    def unbind(self):
        """解除绑定"""
        self.phase = "Lost"
        self.volume_name = None
        self.capacity = {}
