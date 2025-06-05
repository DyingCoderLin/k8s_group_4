import json
import time
from pkg.config.pvcConfig import PVCConfig


class PersistentVolumeClaim:
    """Persistent Volume Claim 对象类"""

    def __init__(self, config_data):
        if isinstance(config_data, dict):
            self.config = PVCConfig(config_data)
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
        self.config = PVCConfig(new_config_data)
        self.last_update_time = time.time()

        # 如果状态改变，记录日志
        if old_phase != self.config.phase:
            print(
                f"[INFO] PVC {self.config.name} phase changed: {old_phase} -> {self.config.phase}"
            )

    def get_name(self):
        """获取 PVC 名称"""
        return self.config.name

    def get_namespace(self):
        """获取命名空间"""
        return self.config.namespace

    def get_phase(self):
        """获取当前状态"""
        return self.config.phase

    def is_pending(self):
        """检查是否等待绑定"""
        return self.config.phase == "Pending"

    def is_bound(self):
        """检查是否已绑定"""
        return self.config.phase == "Bound"

    def is_lost(self):
        """检查是否丢失"""
        return self.config.phase == "Lost"

    def get_capacity_bytes(self):
        """获取容量需求（字节数）"""
        return self.config.get_capacity_bytes()

    def get_storage_class_name(self):
        """获取存储类名称"""
        return self.config.storage_class_name

    def get_access_modes(self):
        """获取访问模式"""
        return self.config.access_modes

    def bind_to_pv(self, pv_config):
        """绑定到指定的 PV"""
        print(f"[INFO] Binding PVC {self.config.name} to PV {pv_config.name}")
        self.config.bind_to_pv(pv_config)
        self.last_update_time = time.time()

    def unbind(self):
        """解除绑定"""
        print(f"[INFO] Unbinding PVC {self.config.name}")
        self.config.unbind()
        self.last_update_time = time.time()

    def get_bound_pv_name(self):
        """获取绑定的 PV 名称"""
        return self.config.volume_name

    def matches_selector(self, pv_labels):
        """检查 PV 标签是否匹配选择器"""
        return self.config.matches_selector(pv_labels)

    def needs_dynamic_provisioning(self):
        """检查是否需要动态供应"""
        return (
            self.is_pending()
            and self.config.storage_class_name
            and self.config.storage_class_name != ""
        )

    def get_volume_mount_info(self):
        """获取卷挂载信息（供 Pod 使用）"""
        if not self.is_bound():
            return None

        return {
            "pvc_name": self.config.name,
            "pv_name": self.config.volume_name,
            "capacity": self.config.capacity,
            "access_modes": self.config.access_modes,
        }

    def __str__(self):
        """字符串表示"""
        return f"PVC({self.config.name}, {self.config.storage}, {self.config.phase})"

    def __repr__(self):
        """调试用字符串表示"""
        return self.__str__()
