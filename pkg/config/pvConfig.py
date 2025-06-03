class PVConfig:
    """Persistent Volume 配置类（简化版）"""
    
    def __init__(self, arg_json):
        # 基本元数据
        metadata = arg_json.get("metadata", {})
        self.name = metadata.get("name")
        self.labels = metadata.get("labels", {})
        
        # PV 规格
        spec = arg_json.get("spec", {})
        
        # 容量配置
        capacity = spec.get("capacity", {})
        self.storage = capacity.get("storage", "1Gi")
        
        # 存储类型配置（只支持hostPath和nfs）
        self.volume_source = self._parse_volume_source(spec)
        
        # 状态信息
        status = arg_json.get("status", {})
        self.phase = status.get("phase", "Available")  # Available, Bound, Released
        self.claim_ref = status.get("claimRef", None)  # 绑定的 PVC 引用
        
    def _parse_volume_source(self, spec):
        """解析存储源配置"""
        # hostPath 类型
        if "hostPath" in spec:
            return {
                "type": "hostPath",
                "path": spec["hostPath"]["path"]
            }
        
        # NFS 类型
        elif "nfs" in spec:
            return {
                "type": "nfs",
                "server": spec["nfs"]["server"],
                "path": spec["nfs"]["path"]
            }
        
        # 默认类型（临时目录）
        else:
            return {
                "type": "hostPath",
                "path": f"/tmp/pv-{self.name or 'unnamed'}"
            }
        
    def to_dict(self):
        """转换为字典格式"""
        result = {
            "apiVersion": "v1",
            "kind": "PersistentVolume",
            "metadata": {
                "name": self.name,
                "labels": self.labels,
            },
            "spec": {
                "capacity": {
                    "storage": self.storage
                }
            },
            "status": {
                "phase": self.phase,
            }
        }
        
        # 添加 PVC 引用（如果已绑定）
        if self.claim_ref:
            result["status"]["claimRef"] = self.claim_ref
        
        # 添加存储源配置
        if self.volume_source["type"] == "hostPath":
            result["spec"]["hostPath"] = {
                "path": self.volume_source["path"]
            }
        elif self.volume_source["type"] == "nfs":
            result["spec"]["nfs"] = {
                "server": self.volume_source["server"],
                "path": self.volume_source["path"]
            }
        
        return result
    
    def get_capacity_bytes(self):
        """获取容量（字节数）"""
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
    
    def matches_pvc(self, pvc_config):
        """检查是否匹配指定的 PVC（简化版：只检查容量）"""
        # 检查容量
        if self.get_capacity_bytes() < pvc_config.get_capacity_bytes():
            return False
        return True
    
    def bind_to_pvc(self, pvc_config):
        """绑定到指定的 PVC"""
        self.phase = "Bound"
        self.claim_ref = {
            "kind": "PersistentVolumeClaim",
            "namespace": pvc_config.namespace,
            "name": pvc_config.name,
            "uid": f"pvc-{pvc_config.name}-{pvc_config.namespace}"
        }
    
    def release(self):
        """释放 PV（PVC 被删除时调用）"""
        self.phase = "Released"
        self.claim_ref = None
