class PVCConfig:
    """Persistent Volume Claim 配置类（标准版）"""
    
    def __init__(self, arg_json):
        # 基本元数据
        metadata = arg_json.get("metadata", {})
        self.name = metadata.get("name")
        self.namespace = metadata.get("namespace", "default")
        self.labels = metadata.get("labels", {})
        
        # PVC 规格
        spec = arg_json.get("spec", {})
        
        self.capacity = spec.get("capacity","1Gi")  # 默认容量为 1Gi
        
        # 存储类名（hostPath 或 nfs）
        self.storage_class_name = spec.get("storageClassName", "hostPath")
        
        # 指定的卷名（用于绑定到特定PV），这个属性不能为空，就算要创立也必须用这个名字
        self.volume_name = spec.get("volumeName", None)
        
        # 状态信息
        self.status = arg_json.get("status", "Pending")
        
    def to_dict(self):
        """转换为字典格式"""
        result = {
            "apiVersion": "v1",
            "kind": "PersistentVolumeClaim",
            "metadata": {
                "name": self.name,
                "namespace": self.namespace,
            },
            "spec": {
                "storageClassName": self.storage_class_name,
                "volumeName": self.volume_name,
                "capacity": self.capacity,
            },
            "status": self.status
        }
        
        return result
    
    def bind_to_pv(self):
        """绑定到指定的 PV"""
        self.status = "Bound"
    
    def unbind(self):
        """解除绑定"""
        self.status = "Lost"
    
    def matches_storage_type(self, pv_config):
        """检查存储类型是否匹配"""
        # 检查存储的要求大小是否相同
        if pv_config.capacity and self.capacity:
            if self.capacity != pv_config.capacity:
                print(f"[ERROR] PVC '{self.name}' capacity '{self.capacity}' does not match PV '{pv_config.name}' capacity '{pv_config.capacity}'")
                return False
        pv_type = pv_config.volume_source.get("type", "hostPath")
        if self.storage_class_name == "nfs" and pv_type == "nfs":
            return True
        elif self.storage_class_name == "hostPath" and pv_type == "hostPath":
            return True
        return False
