import os
import uuid
from abc import ABC, abstractmethod

class BaseProvisioner(ABC):
    """存储供应器基类"""
    
    def __init__(self, storage_class_config):
        self.storage_class = storage_class_config
        self.parameters = storage_class_config.parameters
    
    @abstractmethod
    def provision(self, pvc_config):
        """动态供应 PV"""
        pass
    
    @abstractmethod
    def delete(self, pv_config):
        """删除 PV"""
        pass
    
    def generate_pv_name(self, pvc_config):
        """生成 PV 名称"""
        return f"pvc-{pvc_config.name}-{str(uuid.uuid4())[:8]}"
    
    def get_default_pv_spec(self, pvc_config, pv_name):
        """获取默认的 PV 规格"""
        return {
            "apiVersion": "v1",
            "kind": "PersistentVolume",
            "metadata": {
                "name": pv_name,
                "labels": {
                    "pv.kubernetes.io/provisioned-by": self.storage_class.provisioner
                }
            },
            "spec": {
                "capacity": {
                    "storage": pvc_config.storage
                },
                "accessModes": pvc_config.access_modes,
                "persistentVolumeReclaimPolicy": self.storage_class.reclaim_policy,
                "storageClassName": self.storage_class.name,
                "volumeMode": pvc_config.volume_mode,
            }
        }
