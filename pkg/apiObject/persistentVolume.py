import json
import time
from pkg.config.pvConfig import PVConfig

class PersistentVolume:
    """Persistent Volume 对象类"""
    
    def __init__(self, config_data):
        if isinstance(config_data, dict):
            self.config = PVConfig(config_data)
        else:
            self.config = config_data
        
        self.creation_time = time.time()
        self.last_update_time = self.creation_time
    
    def to_dict(self):
        """转换为字典格式"""
        result = self.config.to_dict()
        
        # 添加时间戳
        result["metadata"]["creationTimestamp"] = time.strftime(
            "%Y-%m-%dT%H:%M:%SZ", time.gmtime(self.creation_time)
        )
        
        return result
    
    def to_json(self):
        """转换为 JSON 字符串"""
        return json.dumps(self.to_dict(), indent=2)
    
    def update_config(self, new_config_data):
        """更新配置"""
        old_phase = self.config.phase
        self.config = PVConfig(new_config_data)
        self.last_update_time = time.time()
        
        # 如果状态改变，记录日志
        if old_phase != self.config.phase:
            print(f"[INFO] PV {self.config.name} phase changed: {old_phase} -> {self.config.phase}")
    
    def get_name(self):
        """获取 PV 名称"""
        return self.config.name
    
    def get_namespace(self):
        """获取命名空间"""
        return self.config.namespace
    
    def get_phase(self):
        """获取当前状态"""
        return self.config.phase
    
    def is_available(self):
        """检查是否可用"""
        return self.config.phase == "Available"
    
    def is_bound(self):
        """检查是否已绑定"""
        return self.config.phase == "Bound"
    
    def is_released(self):
        """检查是否已释放"""
        return self.config.phase == "Released"
    
    def get_capacity_bytes(self):
        """获取容量（字节数）"""
        return self.config.get_capacity_bytes()
    
    def get_volume_source(self):
        """获取存储源配置"""
        return self.config.volume_source
    
    def matches_pvc(self, pvc_config):
        """检查是否匹配指定的 PVC"""
        return self.config.matches_pvc(pvc_config)
    
    def bind_to_pvc(self, pvc_config):
        """绑定到指定的 PVC"""
        print(f"[INFO] Binding PV {self.config.name} to PVC {pvc_config.name}")
        self.config.bind_to_pvc(pvc_config)
        self.last_update_time = time.time()
    
    def release(self):
        """释放 PV（PVC 被删除时调用）"""
        print(f"[INFO] Releasing PV {self.config.name}")
        action = self.config.release()
        self.last_update_time = time.time()
        return action
    
    def get_bound_pvc(self):
        """获取绑定的 PVC 信息"""
        return self.config.claim_ref
    
    def __str__(self):
        """字符串表示"""
        return f"PV({self.config.name}, {self.config.storage}, {self.config.phase})"
    
    def __repr__(self):
        """调试用字符串表示"""
        return self.__str__()
