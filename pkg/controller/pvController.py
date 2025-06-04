import time
import threading
from pkg.config.pvConfig import PVConfig
from pkg.config.pvcConfig import PVCConfig
from pkg.apiObject.persistentVolume import PersistentVolume
from pkg.apiObject.persistentVolumeClaim import PersistentVolumeClaim
from pkg.apiServer.apiClient import ApiClient
from pkg.config.uriConfig import URIConfig
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
    
    def __init__(self):
        self.apiclient = ApiClient()
        self.uri_config = URIConfig()
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
                
    def _get_all_pvcs(self):
        """获取所有PVC"""
        try:
            # 从etcd获取所有PVC
            global_pvc_key = self.uri_config.GLOBAL_PVCS_URL
            response_list = self.apiclient.get(global_pvc_key)
                  
            return response_list
        except Exception as e:
            print(f"[ERROR] Failed to get PVCs from etcd: {str(e)}")
            return []
    
    def _process_pvcs(self):
        """处理所有PVC"""
        try:
            # 获取所有PVC
            pvcs_list = self._get_all_pvcs()
            
            if not pvcs_list:
                print("[INFO] No PVCs found in etcd")
                return
                
            for pvc in pvcs_list:
                if pvc.get("status","") == "Pending":
                    print(f"[INFO] Found pending PVC: {pvc.get("metadata",{}).get("namespace")}/{pvc.get("metadata",{}).get("name")}")
                    self._handle_pending_pvc(pvc)
                    
        except Exception as e:
            print(f"[ERROR] Failed to process PVCs: {str(e)}")
    
    def _handle_pending_pvc(self, pvc):
        """处理Pending状态的PVC"""
        # 这里刚刚传入的pvc是一个dict类，要先转成pvcconfig类
        # 检查是否指定了特定的PV名称，没有指定的话进行报错
        pvc = PVCConfig(pvc)
        if pvc.spec["volumeName"]:
            # 尝试绑定到指定的PV
            self._bind_to_specific_pv(pvc)
        else:
            # 不存在volumeName，直接报错
            print(f"[ERROR] PVC {pvc.namespace}/{pvc.name} does not specify a volumeName, cannot bind to specific PV")
            
    def get_pv_by_name(self, name, namespace):
        try:
            # 从etcd获取指定名称的PV
            pv_key = self.uri_config.PV_SPEC_URL.format(namespace=namespace, name=name)
            pv_data = self.apiclient.get(pv_key)
            
            if pv_data.get("message","") == "PersistentVolume not found":
                print(f"[INFO] PV {name} not found in etcd")
                return None
            
            # 解析PV数据
            pv_config = PVConfig(pv_data)
            
            if pv_config.namespace != namespace:
                print(f"[ERROR] PV {name} is in namespace {pv_config.namespace}, expected {namespace}")
                return None
            
            return pv_config
        except Exception as e:
            print(f"[ERROR] Failed to get PV by name {name}: {str(e)}")
            return None
        
    def _update_pvc_status(self, name,namespace , status):
        """更新PVC状态"""
        try:
            pvc_uri = self.uri_config.PVC_SPEC_STATUS_URL.format(namespace=namespace, name=name)
            data = {
                "status": status
            }
            pvc_data = self.apiclient.post(pvc_uri, data)
            print(f"[INFO] Updated PVC {name} status to {status}")
            
        except Exception as e:
            print(f"[ERROR] Failed to update PVC {name} status: {str(e)}")
    
    def _bind_to_specific_pv(self, pvc):
        """绑定到指定的PV"""
        try:
            # 获取指定的PV
            pv = self.get_pv_by_name(pvc.volume_name, pvc.namespace)
            
            if not pv:
                # PV不存在，创建新的PV
                print(f"[INFO] PV {pvc.volume_name} does not exist, creating new PV")
                pv = self._create_specific_pv(pvc)
            
            # 检查存储类型是否匹配
            if not pvc.matches_storage_type(pv):
                # 类型不匹配，报错
                print(f"[ERROR] PV {pvc.volume_name} type does not match PVC {pvc.namespace}/{pvc.name} storageClassName")
                pvc.status = "Failed"
                self._update_pvc_status(pvc.name, pvc.namespace, "Failed")
                return
            
            # 检查PV是否可用
            if pv.status != "Available":
                print(f"[ERROR] PV {pvc.volume_name} is not available (current status: {pv.status})")
                return
            
            # 绑定到PV
            self._bind_pvc_to_pv(pvc, pv)
            
        except Exception as e:
            print(f"[ERROR] Failed to bind to specific PV: {str(e)}")
            
    def _create_pv_remote(self, json_data):
        """在etcd中创建PV"""
        try:
            pv_name = json_data["metadata"]["name"]
            pv_namespace = json_data["metadata"].get("namespace", "default")
            pv_key = self.uri_config.PV_SPEC_URL.format(name=pv_name,namespace = pv_namespace)
            
            # 检查PV是否已存在
            response = self.apiclient.post(pv_key, json_data)
            
            if response.status_code ==200:
                print(f"[INFO] Created PV {pv_name} in etcd")
            
        except Exception as e:
            print(f"[ERROR] Failed to create PV in etcd: {str(e)}")
    
    def _create_specific_pv(self, pvc):
        """因为PV不存在，所以为PVC创建指定名称的PV"""
        try:
            pv_name = pvc.volume_name
            print(f"[INFO] Creating specific PV {pv_name} for PVC {pvc.namespace}/{pvc.name}")
            
            # 创建PV配置
            pv_spec = self._generate_specific_pv_spec(pv_name, pvc)
            pv_config = PVConfig(pv_spec)
            
            self._create_pv_remote(pv_spec)
            
            # 创建实际存储目录
            self._provision_storage(pv_config, pvc)
            
            # 绑定PVC到新创建的PV
            self._bind_pvc_to_pv(pvc, pv_config)
            
            print(f"[INFO] Successfully created and bound specific PV {pv_name}")
            
        except Exception as e:
            print(f"[ERROR] Failed to create specific PV: {str(e)}")
    
    def _generate_specific_pv_spec(self, pv_name, pvc):
        """生成指定名称的PV规格"""
        if pvc.storage_class_name == "nfs":
            # NFS类型
            nfs_server = "10.119.15.190"
            storage_path = f"/exports/specific/{pvc.namespace}/{pvc.name}"
            
            return {
                "apiVersion": "v1",
                "kind": "PersistentVolume",
                "metadata": {
                    "name": pv_name,
                },
                "spec": {
                    "nfs": {
                        "server": nfs_server,
                        "path": storage_path
                    }
                }
            }
        else:
            # hostPath类型
            storage_path = f"/tmp/minik8s-specific/{pvc.namespace}/{pvc.name}"
            
            return {
                "apiVersion": "v1",
                "kind": "PersistentVolume",
                "metadata": {
                    "name": pv_name,
                },
                "spec": {
                    "hostPath": {
                        "path": storage_path
                    }
                }
            }
    
    def _find_available_pv(self, pvc):
        """查找可用的PV"""
        try:
            pvs = self.etcd.get_prefix(EtcdConfig.GLOBAL_PVS_KEY)
            
            for pv in pvs:
                if (pv.phase == "Available" and 
                    pv.matches_pvc(pvc) and 
                    pvc.matches_storage_type(pv)):
                    return pv
                    
            return None
            
        except Exception as e:
            print(f"[ERROR] Failed to find available PV: {str(e)}")
            return None
        
    def _update_pv_remote(self, pv):
        json_data = pv.to_dict()
        name = pv.name
        namespace = pv.namespace or "default"
        pv_key = self.uri_config.PV_SPEC_URL.format(name=name, namespace=namespace)
        """更新PV到etcd"""
        try:
            print(f"[INFO] Updating PV {name} in etcd")
            response = self.apiclient.put(pv_key, json_data)
            
            if response.status_code == 200:
                print(f"[INFO] Successfully updated PV {name} in etcd")
            else:
                print(f"[ERROR] Failed to update PV {name} in etcd: {response.text}")
        except Exception as e:
            print(f"[ERROR] Failed to update PV {name} in etcd: {str(e)}")
        
    def _update_pvc_remote(self, pvc):
        """更新PVC到etcd"""
        json_data = pvc.to_dict()
        pvc_key = self.uri_config.PVC_SPEC_STATUS_URL.format(namespace=pvc.namespace, name=pvc.name)
        
        try:
            print(f"[INFO] Updating PVC {pvc.name} in etcd")
            response = self.apiclient.put(pvc_key, json_data)
            
            if response.status_code == 200:
                print(f"[INFO] Successfully updated PVC {pvc.name} in etcd")
            else:
                print(f"[ERROR] Failed to update PVC {pvc.name} in etcd: {response.text}")
        except Exception as e:
            print(f"[ERROR] Failed to update PVC {pvc.name} in etcd: {str(e)}")
    
    def _bind_pvc_to_pv(self, pvc, pv):
        """绑定PVC到PV"""
        try:
            print(f"[INFO] Binding PVC {pvc.namespace}/{pvc.name} to PV {pv.name}")
            
            # 更新PV状态
            pv.bind_to_pvc(pvc)
            
            # 保存PV到etcd
            self._update_pv_remote(pv)
            
            # 更新PVC状态
            pvc.bind_to_pv(pv)
            self._update_pvc_status(pvc.name, pvc.namespace, pvc.status)
            
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
        # 从PVC的storageClassName确定存储类型
        use_nfs = pvc.storage_class_name == "nfs"
        
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
    controller = PVController()
    
    try:
        controller.start()
        
        # 保持运行
        while True:
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("\n[INFO] Received shutdown signal")
        controller.stop()
