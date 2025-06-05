import time
import threading
from pkg.config.pvConfig import PVConfig
from pkg.config.pvcConfig import PVCConfig
from pkg.apiObject.persistentVolume import PersistentVolume
from pkg.apiObject.persistentVolumeClaim import PersistentVolumeClaim
from pkg.apiServer.apiClient import ApiClient
from pkg.config.uriConfig import URIConfig
from pkg.config.etcdConfig import EtcdConfig
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
        # 维护已分配的PVC列表 - 格式: {namespace/name: pvc_config}
        self.allocated_pvcs = {}

    def start(self):
        """启动控制器"""
        print("[INFO] PVController starting...")
        self.running = True

        # 启动主循环
        self.controller_thread = threading.Thread(
            target=self._controller_loop, daemon=True
        )
        self.controller_thread.start()

        print("[INFO] PVController started")

    def stop(self):
        """停止控制器"""
        print("[INFO] PVController stopping...")
        self.running = False
        if hasattr(self, "controller_thread"):
            self.controller_thread.join()
        print("[INFO] PVController stopped")

    def _controller_loop(self):
        """控制器主循环"""
        while self.running:
            try:
                # 处理静态PV（检查status为static的PV并创建存储）
                self._process_static_pvs()

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

            try:
                print("[INFO] Checking allocated PVCs consistency...")

                # 构建当前PVC的键集合（namespace/name）
                current_pvc_keys = set()
                for pvc_data in pvcs_list:
                    metadata = pvc_data.get("metadata", {})
                    namespace = metadata.get("namespace", "")
                    name = metadata.get("name", "")
                    if namespace and name:
                        current_pvc_keys.add(f"{namespace}/{name}")

                # 检查已分配的PVC是否还存在
                allocated_keys_to_remove = []
                for allocated_key in self.allocated_pvcs.keys():
                    if allocated_key not in current_pvc_keys:
                        print(f"[INFO] Found orphaned allocated PVC: {allocated_key}")
                        allocated_keys_to_remove.append(allocated_key)

                # 清理不存在的已分配PVC并解绑相关PV
                for key_to_remove in allocated_keys_to_remove:
                    self._cleanup_orphaned_pvc(key_to_remove)

            except Exception as e:
                print(f"[ERROR] Failed to check PVC consistency: {str(e)}")

            if not pvcs_list:
                print("[INFO] No PVCs found in etcd")
                return

            for pvc in pvcs_list:
                if pvc.get("status", "") == "Pending":
                    print(
                        f"[INFO] Found pending PVC: {pvc.get('metadata',{}).get('namespace')}/{pvc.get('metadata',{}).get('name')}"
                    )
                    self._handle_pending_pvc(pvc)

        except Exception as e:
            print(f"[ERROR] Failed to process PVCs: {str(e)}")

    def _handle_pending_pvc(self, pvc):
        """处理Pending状态的PVC"""
        # 这里刚刚传入的pvc是一个dict类，要先转成pvcconfig类
        # 检查是否指定了特定的PV名称，没有指定的话进行报错
        pvc = PVCConfig(pvc)
        if pvc.volume_name:
            # 尝试绑定到指定的PV
            self._bind_to_specific_pv(pvc)
        else:
            # 不存在volumeName，直接报错
            print(
                f"[ERROR] PVC {pvc.namespace}/{pvc.name} does not specify a volumeName, cannot bind to specific PV"
            )

    def get_pv_by_name(self, name):
        try:
            # 从etcd获取指定名称的PV (PV是集群级别资源，无namespace)
            pv_key = self.uri_config.PV_SPEC_URL.format(name=name)
            pv_data = self.apiclient.get(pv_key)

            if pv_data.get("message", "") == "PersistentVolume not found":
                print(f"[INFO] PV {name} not found in etcd")
                return None

            # 解析PV数据
            pv_config = PVConfig(pv_data)

            return pv_config
        except Exception as e:
            print(f"[ERROR] Failed to get PV by name {name}: {str(e)}")
            return None

    def _update_pvc_status(self, name, namespace, status):
        """更新PVC状态"""
        try:
            pvc_uri = self.uri_config.PVC_SPEC_STATUS_URL.format(
                namespace=namespace, name=name
            )
            data = {"status": status}
            pvc_data = self.apiclient.post(pvc_uri, data)
            print(f"[INFO] Updated PVC {name} status to {status}")

        except Exception as e:
            print(f"[ERROR] Failed to update PVC {name} status: {str(e)}")

    # 核心函数，pvc动态创建pv和绑定已有pv都依靠这个
    def _bind_to_specific_pv(self, pvc):
        """绑定到指定的PV"""
        try:
            # 获取指定的PV (PV是集群级别资源，无需namespace)
            pv = self.get_pv_by_name(pvc.volume_name)

            if not pv:
                # PV不存在，创建新的PV
                print(f"[INFO] PV {pvc.volume_name} does not exist, creating new PV")
                pv = self._create_specific_pv(pvc)

            # 检查存储类型是否匹配
            if not pvc.matches_storage_type(pv):
                # 类型不匹配，报错
                print(
                    f"[ERROR] PV {pvc.volume_name} type does not match PVC {pvc.namespace}/{pvc.name} storageClassName"
                )
                pvc.status = "Failed"
                self._update_pvc_status(pvc.name, pvc.namespace, "Failed")
                return

            # 检查PV是否可用
            if pv.status != "Available":
                print(
                    f"[ERROR] PV {pvc.volume_name} is not available (current status: {pv.status})"
                )
                return

            # 绑定到PV
            self._bind_pvc_to_pv(pvc, pv)

        except Exception as e:
            print(f"[ERROR] Failed to bind to specific PV: {str(e)}")

    def _create_pv_remote(self, json_data):
        """在etcd中创建PV"""
        try:
            pv_name = json_data["metadata"]["name"]
            pv_key = self.uri_config.PV_SPEC_URL.format(name=pv_name)

            # 检查PV是否已存在
            response = self.apiclient.post(pv_key, json_data)

        except Exception as e:
            print(f"[ERROR] Failed to create PV in etcd: {str(e)}")

    def _create_specific_pv(self, pvc):
        """因为PV不存在，所以为PVC创建指定名称的PV"""
        try:
            pv_name = pvc.volume_name
            print(
                f"[INFO] Creating specific PV {pv_name} for PVC {pvc.namespace}/{pvc.name}"
            )

            # 创建PV配置
            pv_spec = self._generate_specific_pv_spec(pv_name, pvc)
            pv_config = PVConfig(pv_spec)

            # 动态创建的PV直接设置为Available（因为会立即provision）
            pv_config.status = "Available"

            # 创建实际存储目录
            self._provision_storage(pv_config, pvc)

            # 保存到etcd（使用更新后的pv_config）
            self._create_pv_remote(pv_config.to_dict())

            # 绑定PVC到新创建的PV
            self._bind_pvc_to_pv(pvc, pv_config)

            print(f"[INFO] Successfully created and bound specific PV {pv_name}")

        except Exception as e:
            print(f"[ERROR] Failed to create specific PV: {str(e)}")

    def _generate_specific_pv_spec(self, pv_name, pvc):
        """生成指定名称的PV规格"""
        if pvc.storage_class_name == "nfs":
            # NFS类型 - 确保路径在/nfs/pv-storage下
            nfs_server = "10.119.15.190"
            # 在NFS导出目录下创建子目录
            storage_path = f"/nfs/pv-storage/specific/{pvc.namespace}/{pvc.name}"

            return {
                "apiVersion": "v1",
                "kind": "PersistentVolume",
                "metadata": {
                    "name": pv_name,
                },
                "spec": {
                    "capacity": pvc.capacity,
                    "nfs": {"server": nfs_server, "path": storage_path},
                },
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
                "spec": {"hostPath": {"path": storage_path}},
            }

    def _find_available_pv(self, pvc):
        """查找可用的PV"""
        try:
            pvs = self.etcd.get_prefix(EtcdConfig.GLOBAL_PVS_KEY)

            for pv in pvs:
                if (
                    pv.phase == "Available"
                    and pv.matches_pvc(pvc)
                    and pvc.matches_storage_type(pv)
                ):
                    return pv

            return None

        except Exception as e:
            print(f"[ERROR] Failed to find available PV: {str(e)}")
            return None

    def _update_pv_remote(self, pv):
        json_data = pv.to_dict()
        name = pv.name
        pv_key = self.uri_config.PV_SPEC_URL.format(name=name)
        """更新PV到etcd"""
        try:
            print(f"[INFO] Updating PV {name} in etcd")
            response = self.apiclient.put(pv_key, json_data)

        except Exception as e:
            print(f"[ERROR] Failed to update PV {name} in etcd: {str(e)}")

    def _unbind_pv_remote(self, name):
        """从etcd中解绑PV"""
        try:
            pv_key = self.uri_config.PV_SPEC_URL.format(name=name)
            print(f"[INFO] Unbinding PV {name} in etcd")
            response = self.apiclient.put(
                pv_key, {"status": "Available", "claimRef": ""}
            )

        except Exception as e:
            print(f"[ERROR] Failed to unbind PV {name} in etcd: {str(e)}")

    def _update_pvc_remote(self, pvc):
        """更新PVC到etcd"""
        json_data = pvc.to_dict()
        pvc_key = self.uri_config.PVC_SPEC_STATUS_URL.format(
            namespace=pvc.namespace, name=pvc.name
        )

        try:
            print(f"[INFO] Updating PVC {pvc.name} in etcd")
            response = self.apiclient.put(pvc_key, json_data)

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
            pvc.bind_to_pv()
            self._update_pvc_status(pvc.name, pvc.namespace, pvc.status)

            print(
                f"[INFO] Successfully bound PVC {pvc.namespace}/{pvc.name} to PV {pv.name}"
            )
            self._add_allocated_pvc(pvc)

        except Exception as e:
            print(f"[ERROR] Failed to bind PVC to PV: {str(e)}")

    def _create_dynamic_pv(self, pvc):
        """为PVC动态创建PV"""
        try:
            self.dynamic_pv_counter += 1
            pv_name = f"pv-dynamic-{self.dynamic_pv_counter}"

            print(
                f"[INFO] Creating dynamic PV {pv_name} for PVC {pvc.namespace}/{pvc.name}"
            )

            # 创建PV配置
            pv_spec = self._generate_pv_spec(pv_name, pvc)
            pv_config = PVConfig(pv_spec)

            # 动态创建的PV直接设置为Available（因为会立即provision）
            pv_config.status = "Available"

            # 创建实际存储目录
            self._provision_storage(pv_config, pvc)

            # 保存到etcd（使用API）
            self._create_pv_remote(pv_config.to_dict())

            # 绑定PVC到新创建的PV
            self._bind_pvc_to_pv(pvc, pv_config)

            print(f"[INFO] Successfully created and bound dynamic PV {pv_name}")

        except Exception as e:
            print(f"[ERROR] Failed to create dynamic PV: {str(e)}")

    def _generate_pv_spec(self, pv_name, pvc):
        """生成PV规格"""
        # 从PVC的storageClassName确定存储类型
        use_nfs = pvc.storage_class_name == "nfs"

        if use_nfs:
            # NFS类型（需要配置NFS服务器）
            nfs_server = "10.119.15.190"
            storage_path = f"/nfs/pv-storage/dynamic/{pvc.namespace}/{pvc.name}"

            return {
                "apiVersion": "v1",
                "kind": "PersistentVolume",
                "metadata": {
                    "name": pv_name,
                    "labels": {
                        "provisioned-by": "minik8s-dynamic",
                        "pvc-namespace": pvc.namespace,
                        "pvc-name": pvc.name,
                        "storage-type": "nfs",
                    },
                },
                "spec": {
                    "capacity": {"storage": pvc.storage},
                    "nfs": {"server": nfs_server, "path": storage_path},
                },
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
                        "storage-type": "hostPath",
                    },
                },
                "spec": {
                    "capacity": {"storage": pvc.storage},
                    "hostPath": {"path": storage_path},
                },
            }

    def _provision_storage(self, pv_config, pvc):
        """提供实际存储"""
        print(f"[INFO] Provisioning storage for PV {pv_config.name}")
        print(f"[INFO] Storage type: {pv_config.volume_source['type']}")
        if pv_config.volume_source["type"] == "hostPath":
            storage_path = pv_config.volume_source["path"]

            print(f"[INFO] Creating hostPath storage at {storage_path}")

            # 创建目录并设置权限
            try:
                os.makedirs(storage_path, exist_ok=True)
                os.chmod(storage_path, 0o755)
                print(f"[INFO] Created hostPath storage at {storage_path}")

                # 添加默认文件作为示例
                with open(os.path.join(storage_path, "README.txt"), "w") as f:
                    if pvc:
                        f.write(
                            f"This is a dynamically provisioned volume for PVC {pvc.namespace}/{pvc.name}\n"
                        )
                        f.write("Created by MiniK8s PV Controller\n")
                        f.write(f"Capacity: {pvc.storage}\n")
                    else:
                        f.write(
                            f"This is a static created PV storage at {storage_path}\n"
                        )

            except Exception as e:
                print(f"[WARN] Failed to set permissions for {storage_path}: {str(e)}")

        elif pv_config.volume_source["type"] == "nfs":
            # NFS存储的创建
            server = pv_config.volume_source["server"]
            path = pv_config.volume_source["path"]

            print(f"[INFO] Configuring NFS storage at {server}:{path}")

            try:
                # 通过SSH远程在NFS服务器上创建目录和配置导出
                self._provision_nfs_storage_remote(server, path, pvc)

            except Exception as e:
                print(f"[ERROR] Failed to provision NFS storage: {str(e)}")

    def _get_all_pvs(self):
        """获取所有PV"""
        try:
            # 从etcd获取所有PV
            global_pv_key = self.uri_config.GLOBAL_PVS_URL
            response_list = self.apiclient.get(global_pv_key)

            return response_list
        except Exception as e:
            print(f"[ERROR] Failed to get PVs from etcd: {str(e)}")
            return []

    def _process_static_pvs(self):
        """处理静态PV - 检查status为static的PV并创建存储"""
        try:
            # 获取所有PV
            print("[INFO] Processing static PVs...")
            pvs_list = self._get_all_pvs()
            # print(f"pv_list: {pvs_list}")

            if not pvs_list:
                return

            for pv_data in pvs_list:
                if pv_data.get("status", "") == "static":
                    print(
                        f"[INFO] Found static PV: {pv_data.get('metadata', {}).get('name')}"
                    )
                    self._provision_static_pv(pv_data)

        except Exception as e:
            print(f"[ERROR] Failed to process static PVs: {str(e)}")

    def _provision_static_pv(self, pv_data):
        """为静态PV创建存储并更新状态为Available"""
        try:
            from pkg.config.pvConfig import PVConfig

            pv_config = PVConfig(pv_data)
            pv_name = pv_config.name

            print(f"[INFO] Provisioning storage for static PV: {pv_name}")

            # 创建实际存储
            self._provision_storage(pv_config, None)  # 静态PV不需要PVC信息

            # 更新PV状态为Available
            self._update_pv_status(pv_name, "Available")

            print(f"[INFO] Successfully provisioned static PV: {pv_name}")

        except Exception as e:
            print(f"[ERROR] Failed to provision static PV: {str(e)}")

    def _update_pv_status(self, pv_name, status):
        """更新PV状态"""
        try:
            pv_status_url = self.uri_config.PV_SPEC_STATUS_URL.format(name=pv_name)
            data = {"status": status}

            response = self.apiclient.put(pv_status_url, data)
            print(f"[INFO] Updated PV {pv_name} status to {status}")

        except Exception as e:
            print(f"[ERROR] Failed to update PV {pv_name} status: {str(e)}")

    def _provision_nfs_storage_remote(self, server, path, pvc):
        """通过SSH远程在NFS服务器上创建存储"""
        try:
            # 使用固定的NFS服务器配置
            nfs_user = "root"
            nfs_password = "Lin040430"

            print(f"[INFO] Connecting to NFS server {server} as user {nfs_user}")

            # 构建SSH命令前缀（使用密码认证）
            ssh_cmd_prefix = f"sshpass -p '{nfs_password}' ssh -o StrictHostKeyChecking=no {nfs_user}@{server}"

            # 1. 首先检查/nfs/pv-storage目录是否存在
            check_base_cmd = f"{ssh_cmd_prefix} 'ls -la /nfs/pv-storage'"
            result = subprocess.run(
                check_base_cmd, shell=True, capture_output=True, text=True
            )

            if result.returncode != 0:
                print(
                    f"[ERROR] Base directory /nfs/pv-storage does not exist or is not accessible"
                )
                print(f"[ERROR] {result.stderr}")
                return False

            print(f"[INFO] Base NFS directory /nfs/pv-storage is accessible")

            # 2. 创建具体的PV目录
            mkdir_cmd = f"{ssh_cmd_prefix} 'mkdir -p {path} && chmod 777 {path}'"
            result = subprocess.run(
                mkdir_cmd, shell=True, capture_output=True, text=True
            )

            if result.returncode != 0:
                print(
                    f"[ERROR] Failed to create directory {path} on NFS server: {result.stderr}"
                )
                return False

            print(
                f"[INFO] Successfully created directory {path} on NFS server {server}"
            )

            # 3. 创建README文件
            readme_content = self._generate_nfs_readme_content(pvc, path)
            create_readme_cmd = (
                f"{ssh_cmd_prefix} 'echo \"{readme_content}\" > {path}/README.txt'"
            )
            result = subprocess.run(
                create_readme_cmd, shell=True, capture_output=True, text=True
            )

            if result.returncode == 0:
                print(f"[INFO] Created README.txt in {path}")
            else:
                print(f"[WARN] Failed to create README.txt: {result.stderr}")

            # 4. 验证目录创建成功
            verify_cmd = f"{ssh_cmd_prefix} 'ls -la {path}'"
            result = subprocess.run(
                verify_cmd, shell=True, capture_output=True, text=True
            )

            if result.returncode == 0:
                print(f"[INFO] Directory verification successful:")
                print(f"[INFO] {result.stdout.strip()}")

            # 5. NFS导出已经预配置为 /nfs/pv-storage *(rw,sync,insecure,anonuid=1000,anongid=1000,no_subtree_check,no_root_squash)
            print(f"[INFO] NFS export already configured for /nfs/pv-storage")

            print(f"[INFO] Successfully provisioned NFS storage at {server}:{path}")
            return True

        except Exception as e:
            print(f"[ERROR] Failed to provision NFS storage remotely: {str(e)}")
            return False

    def _build_ssh_command(self, server, user, password, key_path):
        """构建SSH命令前缀"""
        if key_path and os.path.exists(key_path):
            # 使用SSH密钥
            return f"ssh -i {key_path} -o StrictHostKeyChecking=no {user}@{server}"
        elif password:
            # 使用sshpass和密码（需要安装sshpass）
            return f"sshpass -p '{password}' ssh -o StrictHostKeyChecking=no {user}@{server}"
        else:
            # 假设已配置SSH密钥认证
            return f"ssh -o StrictHostKeyChecking=no {user}@{server}"

    def _generate_nfs_readme_content(self, pvc, path):
        """生成NFS README文件内容"""
        if pvc:
            return f"This is a dynamically provisioned NFS volume for PVC {pvc.namespace}/{pvc.name}\\nCreated by MiniK8s PV Controller\\nCapacity: {pvc.storage}\\nPath: {path}"
        else:
            return f"This is a static created NFS storage at {path}\\nCreated by MiniK8s PV Controller"

    def _configure_nfs_export_remote(self, ssh_cmd_prefix, path):
        """远程配置NFS导出 - 由于已预配置/nfs/pv-storage导出，这里只需验证"""
        try:
            # 检查NFS导出配置
            check_export_cmd = f"{ssh_cmd_prefix} 'showmount -e localhost'"
            result = subprocess.run(
                check_export_cmd, shell=True, capture_output=True, text=True
            )

            if result.returncode == 0:
                print(f"[INFO] NFS exports verified:")
                print(f"[INFO] {result.stdout.strip()}")

                if "/nfs/pv-storage" in result.stdout:
                    print(f"[INFO] /nfs/pv-storage export confirmed")
                    return True
                else:
                    print(f"[WARN] /nfs/pv-storage not found in exports")
                    return False
            else:
                print(f"[WARN] Failed to check NFS exports: {result.stderr}")
                return False

        except Exception as e:
            print(f"[WARN] Failed to verify NFS export: {str(e)}")
            return False

    def _cleanup_orphaned_pvc(self, pvc_key):
        """清理孤立的PVC并解绑相关PV"""
        try:
            print(f"[INFO] Cleaning up orphaned PVC: {pvc_key}")

            # 获取要清理的PVC配置
            pvc_config = self.allocated_pvcs.get(pvc_key)

            # 如果PVC绑定了PV，需要解绑PV
            if hasattr(pvc_config, "volume_name") and pvc_config.volume_name:
                self._unbind_pv_from_pvc(pvc_config.volume_name, pvc_key)

            # 从已分配PVC列表中移除
            del self.allocated_pvcs[pvc_key]
            print(f"[INFO] Removed orphaned PVC {pvc_key} from allocated list")

        except Exception as e:
            print(f"[ERROR] Failed to cleanup orphaned PVC {pvc_key}: {str(e)}")

    def _unbind_pv_from_pvc(self, pv_name, pvc_key):
        """解绑PV与PVC的绑定关系"""
        try:
            print(f"[INFO] Unbinding PV {pv_name} from orphaned PVC {pvc_key}")

            # 更新PV到etcd
            self._unbind_pv_remote(pv_name)

            print(f"[INFO] Successfully unbound PV {pv_name} from PVC {pvc_key}")

        except Exception as e:
            print(f"[ERROR] Failed to unbind PV {pv_name} from PVC {pvc_key}: {str(e)}")

    def _add_allocated_pvc(self, pvc_config):
        """添加PVC到已分配列表"""
        try:
            pvc_key = f"{pvc_config.namespace}/{pvc_config.name}"
            self.allocated_pvcs[pvc_key] = pvc_config
            print(f"[INFO] Added PVC {pvc_key} to allocated list")
        except Exception as e:
            print(f"[ERROR] Failed to add PVC to allocated list: {str(e)}")

    def _remove_allocated_pvc(self, pvc_config):
        """从已分配列表中移除PVC"""
        try:
            pvc_key = f"{pvc_config.namespace}/{pvc_config.name}"
            if pvc_key in self.allocated_pvcs:
                del self.allocated_pvcs[pvc_key]
                print(f"[INFO] Removed PVC {pvc_key} from allocated list")
        except Exception as e:
            print(f"[ERROR] Failed to remove PVC from allocated list: {str(e)}")
