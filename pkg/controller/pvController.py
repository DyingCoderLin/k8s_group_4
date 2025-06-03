import time
import threading
from pkg.apiServer.etcd import Etcd
from pkg.config.etcdConfig import EtcdConfig
from pkg.config.pvConfig import PVConfig
from pkg.config.pvcConfig import PVCConfig
from pkg.apiObject.persistentVolume import PersistentVolume
from pkg.apiObject.persistentVolumeClaim import PersistentVolumeClaim
import os
import subprocess


class PVController:
    """
    PV控制器
    功能：
    1. 监控PVC，为未绑定的PVC动态创建PV
    2. 处理PV/PVC绑定
    3. 支持hostPath和NFS两种存储类型
    """
    
    def __init__(self, etcd_config: EtcdConfig):
        self.etcd = Etcd(etcd_config)
        self.running = False
        self.dynamic_pv_counter = 0
        
    def start(self):
        """启动控制器"""
        print("[INFO] PVController starting...")
        self.running = True
        
        # 启动主循环
        self.controller_thread = threading.Thread(target=self._controller_loop, daemon=True)
        self.controller_thread.start()
        
        print("[INFO] PVController started")
    
    def stop(self):
        """停止控制器"""
        print("[INFO] PVController stopping...")
        self.running = False
        if hasattr(self, 'controller_thread'):
            self.controller_thread.join()
        print("[INFO] PVController stopped")
    
    def _controller_loop(self):
        """控制器主循环"""
        while self.running:
            try:
                # 处理PVC绑定
                self._process_pvcs()
                
                # 短暂休眠
                time.sleep(5)
                
            except Exception as e:
                print(f"[ERROR] PVController error: {str(e)}")
                time.sleep(10)
    
    def _process_pvcs(self):
        """处理所有PVC"""
        try:
            # 获取所有PVC
            pvcs_list = self.etcd.get_prefix(EtcdConfig.GLOBAL_PVCS_KEY)
            
            if not pvcs_list:
                print("[INFO] No PVCs found in etcd")
                return
                
            for pvc in pvcs_list:
                if hasattr(pvc, 'phase') and pvc.phase == "Pending":
                    print(f"[INFO] Found pending PVC: {pvc.namespace}/{pvc.name}")
                    self._handle_pending_pvc(pvc)
                    
        except Exception as e:
            print(f"[ERROR] Failed to process PVCs: {str(e)}")
    
    def _handle_pending_pvc(self, pvc):
        """处理Pending状态的PVC"""
        print(f"[INFO] Processing pending PVC: {pvc.namespace}/{pvc.name}")
        
        # 先尝试绑定现有的可用PV
        available_pv = self._find_available_pv(pvc)
        
        if available_pv:
            # 绑定到现有PV
            self._bind_pvc_to_pv(pvc, available_pv)
        else:
            # 动态创建PV
            self._create_dynamic_pv(pvc)
    
    def _find_available_pv(self, pvc):
        """查找可用的PV"""
        try:
            pvs = self.etcd.get_prefix(EtcdConfig.GLOBAL_PVS_KEY)
            
            for pv in pvs:
                if pv.phase == "Available" and pv.matches_pvc(pvc):
                    return pv
                    
            return None
            
        except Exception as e:
            print(f"[ERROR] Failed to find available PV: {str(e)}")
            return None
    
    def _bind_pvc_to_pv(self, pvc, pv):
        """绑定PVC到PV"""
        try:
            print(f"[INFO] Binding PVC {pvc.namespace}/{pvc.name} to PV {pv.name}")
            
            # 更新PV状态
            pv.bind_to_pvc(pvc)
            pv_key = EtcdConfig.PV_SPEC_KEY.format(name=pv.name)
            self.etcd.put(pv_key, pv)
            
            # 更新PVC状态
            pvc.bind_to_pv(pv)
            pvc_key = EtcdConfig.PVC_SPEC_KEY.format(namespace=pvc.namespace, name=pvc.name)
            self.etcd.put(pvc_key, pvc)
            
            print(f"[INFO] Successfully bound PVC {pvc.namespace}/{pvc.name} to PV {pv.name}")
            
        except Exception as e:
            print(f"[ERROR] Failed to bind PVC to PV: {str(e)}")
    
    def _create_dynamic_pv(self, pvc):
        """为PVC动态创建PV"""
        try:
            self.dynamic_pv_counter += 1
            pv_name = f"pv-dynamic-{self.dynamic_pv_counter}"
            
            print(f"[INFO] Creating dynamic PV {pv_name} for PVC {pvc.namespace}/{pvc.name}")
            
            # 创建PV配置
            pv_spec = self._generate_pv_spec(pv_name, pvc)
            pv_config = PVConfig(pv_spec)
            pv = PersistentVolume(pv_config)
            
            # 创建实际存储目录
            self._provision_storage(pv_config, pvc)
            
            # 保存PV到etcd
            pv_key = EtcdConfig.PV_SPEC_KEY.format(name=pv_name)
            self.etcd.put(pv_key, pv)
            
            # 绑定PVC到新创建的PV
            self._bind_pvc_to_pv(pvc, pv)
            
            print(f"[INFO] Successfully created and bound dynamic PV {pv_name}")
            
        except Exception as e:
            print(f"[ERROR] Failed to create dynamic PV: {str(e)}")
    
    def _generate_pv_spec(self, pv_name, pvc):
        """生成PV规格"""
        # 从PVC标签中确定存储类型
        use_nfs = pvc.labels.get("storage-type") == "nfs"
        
        if use_nfs:
            # NFS类型（需要配置NFS服务器）
            nfs_server = os.environ.get("NFS_SERVER", "localhost")
            storage_path = f"/exports/dynamic/{pvc.namespace}/{pvc.name}"
            
            return {
                "apiVersion": "v1",
                "kind": "PersistentVolume",
                "metadata": {
                    "name": pv_name,
                    "labels": {
                        "provisioned-by": "minik8s-dynamic",
                        "pvc-namespace": pvc.namespace,
                        "pvc-name": pvc.name,
                        "storage-type": "nfs"
                    }
                },
                "spec": {
                    "capacity": {
                        "storage": pvc.storage
                    },
                    "nfs": {
                        "server": nfs_server,
                        "path": storage_path
                    }
                }
            }
        else:
            # 默认使用hostPath类型
            storage_path = f"/tmp/minik8s-dynamic/{pvc.namespace}/{pvc.name}"
            
            return {
                "apiVersion": "v1",
                "kind": "PersistentVolume",
                "metadata": {
                    "name": pv_name,
                    "labels": {
                        "provisioned-by": "minik8s-dynamic",
                        "pvc-namespace": pvc.namespace,
                        "pvc-name": pvc.name,
                        "storage-type": "hostPath"
                    }
                },
                "spec": {
                    "capacity": {
                        "storage": pvc.storage
                    },
                    "hostPath": {
                        "path": storage_path
                    }
                }
            }
    
    def _provision_storage(self, pv_config, pvc):
        """提供实际存储"""
        if pv_config.volume_source["type"] == "hostPath":
            storage_path = pv_config.volume_source["path"]
            
            # 创建目录
            os.makedirs(storage_path, exist_ok=True)
            
            # 设置权限
            try:
                os.chmod(storage_path, 0o755)
                print(f"[INFO] Created hostPath storage at {storage_path}")
                
                # 添加默认文件作为示例
                with open(os.path.join(storage_path, "README.txt"), "w") as f:
                    f.write(f"This is a dynamically provisioned volume for PVC {pvc.namespace}/{pvc.name}\n")
                    f.write("Created by MiniK8s PV Controller\n")
                    f.write(f"Capacity: {pvc.storage}\n")
                    
            except Exception as e:
                print(f"[WARN] Failed to set permissions for {storage_path}: {str(e)}")
                
        elif pv_config.volume_source["type"] == "nfs":
            # NFS存储的创建
            server = pv_config.volume_source["server"]
            path = pv_config.volume_source["path"]
            
            print(f"[INFO] Configuring NFS storage at {server}:{path}")
            
            try:
                # 检查是否在NFS服务器上运行
                is_nfs_server = os.environ.get("IS_NFS_SERVER", "false").lower() == "true"
                
                if is_nfs_server:
                    # 在NFS服务器上创建目录
                    os.makedirs(path, exist_ok=True)
                    os.chmod(path, 0o777)  # 确保NFS客户端可以写入
                    
                    # 添加默认文件
                    with open(os.path.join(path, "README.txt"), "w") as f:
                        f.write(f"This is a dynamically provisioned NFS volume for PVC {pvc.namespace}/{pvc.name}\n")
                        f.write("Created by MiniK8s PV Controller\n")
                        f.write(f"Capacity: {pvc.storage}\n")
                    
                    print(f"[INFO] Created NFS directory at {path}")
                    
                    # 确保目录已导出
                    try:
                        export_cmd = f"exportfs -o rw,no_root_squash,async,no_subtree_check *:{path}"
                        subprocess.run(export_cmd, shell=True, check=True)
                        print(f"[INFO] Exported NFS path: {path}")
                    except subprocess.CalledProcessError as e:
                        print(f"[WARN] Failed to export NFS path: {str(e)}")
                else:
                    # 非NFS服务器，仅记录配置
                    print(f"[INFO] NFS storage configured at {server}:{path}, but not creating directory (not running on NFS server)")
            except Exception as e:
                print(f"[ERROR] Failed to provision NFS storage: {str(e)}")


if __name__ == "__main__":
    controller = PVController(EtcdConfig)
    
    try:
        controller.start()
        
        # 保持运行
        while True:
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("\n[INFO] Received shutdown signal")
        controller.stop()
