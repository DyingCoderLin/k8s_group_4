import os
import shutil
from pkg.storage.provisioner import BaseProvisioner


class HostPathProvisioner(BaseProvisioner):
    """HostPath 类型的存储供应器"""

    def __init__(self, storage_class_config):
        super().__init__(storage_class_config)
        # 默认基础路径
        self.base_path = self.parameters.get("path", "/tmp/minik8s-hostpath")
        self.ensure_base_path()

    def ensure_base_path(self):
        """确保基础路径存在"""
        if not os.path.exists(self.base_path):
            os.makedirs(self.base_path, exist_ok=True)
            print(f"[INFO] Created hostPath base directory: {self.base_path}")

    def provision(self, pvc_config):
        """动态供应 hostPath PV"""
        pv_name = self.generate_pv_name(pvc_config)

        # 创建 PV 目录
        pv_path = os.path.join(self.base_path, pv_name)
        os.makedirs(pv_path, exist_ok=True)

        # 设置权限（如果在参数中指定）
        mode = self.parameters.get("mode")
        if mode:
            os.chmod(pv_path, int(mode, 8))

        print(f"[INFO] Created hostPath directory: {pv_path}")

        # 生成 PV 配置
        pv_spec = self.get_default_pv_spec(pvc_config, pv_name)
        pv_spec["spec"]["hostPath"] = {"path": pv_path, "type": "DirectoryOrCreate"}

        return pv_spec

    def delete(self, pv_config):
        """删除 hostPath PV"""
        volume_source = pv_config.volume_source
        if volume_source["type"] != "hostPath":
            raise ValueError("PV is not a hostPath volume")

        path = volume_source["path"]

        try:
            if os.path.exists(path):
                # 检查是否在我们管理的路径下
                if path.startswith(self.base_path):
                    shutil.rmtree(path)
                    print(f"[INFO] Deleted hostPath directory: {path}")
                else:
                    print(
                        f"[WARN] hostPath {path} is outside managed directory, skipping deletion"
                    )
        except Exception as e:
            print(f"[ERROR] Failed to delete hostPath {path}: {e}")
            raise

    def validate_path(self, path):
        """验证路径是否安全"""
        # 检查路径是否在允许的目录下
        abs_path = os.path.abspath(path)
        abs_base = os.path.abspath(self.base_path)

        return abs_path.startswith(abs_base)
