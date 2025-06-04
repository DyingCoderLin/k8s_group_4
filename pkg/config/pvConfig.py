class PVConfig:
    """Persistent Volume 配置类（简化版）"""
    
    def __init__(self, arg_json):
        # 基本元数据
        metadata = arg_json.get("metadata", {})
        self.name = metadata.get("name")
        
        # PV 规格
        spec = arg_json.get("spec", {})
        
        # 存储类型配置（只支持hostPath和nfs）
        self.volume_source = self._parse_volume_source(spec)
        
        # 状态信息
        status = arg_json.get("status", {})
        self.status = arg_json.get("status", "Available")  # Available, Bound, Released
        self.claim_ref = arg_json.get("claimRef", None)  # 绑定的 PVC 引用
        
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
            },
            "spec": {
            },
            "status": self.status,
            "claimRef": self.claim_ref
        }
        
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
    
    def bind_to_pvc(self, pvc_config):
        """绑定到指定的 PVC"""
        self.status = "Bound"
        self.claim_ref = pvc_config.name
    
    def release(self):
        """释放 PV(PVC 被删除时调用）"""
        self.status = "Released"
        self.claim_ref = None
