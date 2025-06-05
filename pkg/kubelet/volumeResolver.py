#!/usr/bin/env python3
import os
import subprocess
import platform
import json
from pkg.apiServer.apiClient import ApiClient
from pkg.config.uriConfig import URIConfig
from typing import Dict, Optional, List


class VolumeResolver:
    """
    Volume resolver，用于处理PVC到实际路径的解析
    支持hostPath和NFS两种存储类型
    """
    
    def __init__(self):
        self.api_client = ApiClient()
        self.uri_config = URIConfig()
        self.mounted_nfs_volumes = {}  # 跟踪已挂载的NFS卷
    
    def resolve_volumes(self, pod_volumes: List[Dict], namespace: str) -> Dict[str, str]:
        """
        解析Pod卷配置到实际挂载路径
        只支持PVC类型的卷
        
        参数:
            pod_volumes: 卷配置列表
            namespace: Pod命名空间
            
        返回:
            卷名到实际挂载路径的映射字典
        """
        resolved_volumes = {}
        
        for volume in pod_volumes:
            volume_name = volume.get('name')
            volume_type = volume.get('type')
            
            if volume_type == 'pvc':
                # PVC卷 - 通过API解析到实际存储路径
                pvc_name = volume.get('claimName')
                if pvc_name:
                    mount_path = self._resolve_pvc(pvc_name, namespace)
                    if mount_path:
                        resolved_volumes[volume_name] = mount_path
                        print(f"[INFO] Resolved PVC {pvc_name} to {mount_path}")
                    else:
                        print(f"[ERROR] Failed to resolve PVC {pvc_name} in namespace {namespace}")
                else:
                    print(f"[ERROR] PVC volume {volume_name} missing claimName")
            else:
                # 不支持的卷类型
                print(f"[WARN] Unsupported volume type '{volume_type}' for volume '{volume_name}', only PVC is supported")
                        
        return resolved_volumes
    
    def _resolve_pvc(self, pvc_name: str, namespace: str) -> Optional[str]:
        """
        解析PVC到实际挂载路径
        
        参数:
            pvc_name: PVC名称
            namespace: PVC命名空间
            
        返回:
            实际挂载路径，解析失败则返回None
        """
        if not self.api_client:
            print("[ERROR] No API client available for PVC resolution")
            return None
            
        try:
            # 获取PVC信息
            pvc_url = self.uri_config.PVC_SPEC_URL.format(namespace=namespace, name=pvc_name)
            pvc_response = self.api_client.get(pvc_url)
            
            if not pvc_response:
                print(f"[ERROR] PVC {pvc_name} not found in namespace {namespace}")
                return None
            
            # 检查响应类型，如果是字符串则可能是错误消息
            if isinstance(pvc_response, str):
                print(f"[ERROR] API returned string response for PVC {pvc_name}: {pvc_response}")
                return None
                
            pvc_data = pvc_response
            print(f"[DEBUG] PVC data type: {type(pvc_data)}")
            
            # 确保pvc_data是字典类型
            if not isinstance(pvc_data, dict):
                print(f"[ERROR] Expected dict for PVC data, got {type(pvc_data)}: {pvc_data}")
                return None
                
            # print(f"pvc_data: {json.dumps(pvc_data, indent=2)}")
            bound_pv_name = pvc_data.get('spec', {}).get('volumeName')
            
            if not bound_pv_name:
                print(f"[ERROR] PVC {pvc_name} is not bound to any PV")
                return None
                
            # 获取PV信息
            pv_url = self.uri_config.PV_SPEC_URL.format(name=bound_pv_name)
            pv_response = self.api_client.get(pv_url)
            
            if not pv_response:
                print(f"[ERROR] PV {bound_pv_name} not found")
                return None
            
            # 检查PV响应类型
            if isinstance(pv_response, str):
                print(f"[ERROR] API returned string response for PV {bound_pv_name}: {pv_response}")
                return None
                
            pv_data = pv_response
            print(f"[DEBUG] PV data type: {type(pv_data)}")
            
            # 确保pv_data是字典类型
            if not isinstance(pv_data, dict):
                print(f"[ERROR] Expected dict for PV data, got {type(pv_data)}: {pv_data}")
                return None
                
            # print(f"pv_data: {json.dumps(pv_data, indent=2)}")
            pv_spec = pv_data.get('spec', {})
            
            # 处理不同的PV类型
            if 'hostPath' in pv_spec:
                path = pv_spec['hostPath']['path']
                print(f"[INFO] Resolved PVC {pvc_name} to hostPath: {path}")
                return path
                
            elif 'nfs' in pv_spec:
                print(f"[INFO] Mounting NFS volume for PV {bound_pv_name}")
                return self._mount_nfs_volume(pv_spec['nfs'], bound_pv_name)
                
            else:
                print(f"[ERROR] Unsupported PV type for {bound_pv_name}")
                return None
                
        except Exception as e:
            print(f"[ERROR] Failed to resolve PVC {pvc_name}: {str(e)}")
            return None
    
    def _mount_nfs_volume(self, nfs_spec: Dict, pv_name: str) -> Optional[str]:
        """
        挂载NFS卷并返回本地挂载路径
        对于无法直接挂载的情况（如macOS），使用SSH创建本地镜像目录
        
        参数:
            nfs_spec: PV中的NFS规格
            pv_name: PV名称，用于创建唯一的挂载点
            
        返回:
            本地挂载路径，解析失败则返回None
        """
        server = nfs_spec.get('server')
        path = nfs_spec.get('path')
        
        if not server or not path:
            print(f"[ERROR] Invalid NFS specification: {nfs_spec}")
            return None
            
        # 创建唯一的挂载点
        mount_point = f"/tmp/nfs-mounts/{pv_name}"
        
        # 检查是否已挂载
        if mount_point in self.mounted_nfs_volumes:
            return mount_point
            
        try:
            # 创建挂载目录
            os.makedirs(mount_point, exist_ok=True)
            
            # 首先尝试传统的NFS挂载
            mount_success = False
            
            if platform.system() == "Linux":
                mount_cmd = ["sudo", "mount", "-t", "nfs", f"{server}:{path}", mount_point]
                result = subprocess.run(mount_cmd, capture_output=True, text=True)
                
                if result.returncode == 0:
                    self.mounted_nfs_volumes[mount_point] = {"server": server, "path": path, "type": "native"}
                    print(f"[INFO] Successfully mounted NFS volume: {server}:{path} to {mount_point}")
                    mount_success = True
                else:
                    print(f"[WARN] Native NFS mount failed: {result.stderr}")
                    
            elif platform.system() == "Darwin":
                # macOS - 尝试原生挂载，如果失败则使用SSH方式
                mount_cmd = ["mount", "-t", "nfs", f"{server}:{path}", mount_point]
                result = subprocess.run(mount_cmd, capture_output=True, text=True)
                
                if result.returncode == 0:
                    self.mounted_nfs_volumes[mount_point] = {"server": server, "path": path, "type": "native"}
                    print(f"[INFO] Successfully mounted NFS volume: {server}:{path} to {mount_point}")
                    mount_success = True
                else:
                    print(f"[WARN] Native NFS mount failed: {result.stderr}")
            
            # 如果原生挂载失败，使用SSH镜像方式
            if not mount_success:
                print(f"[INFO] Attempting SSH-based NFS access for {server}:{path}")
                if self._setup_ssh_nfs_mirror(server, path, mount_point):
                    self.mounted_nfs_volumes[mount_point] = {"server": server, "path": path, "type": "ssh_mirror"}
                    print(f"[INFO] Successfully set up SSH mirror for NFS volume: {server}:{path} to {mount_point}")
                    mount_success = True
            
            if mount_success:
                return mount_point
            else:
                print(f"[ERROR] Failed to mount NFS volume using all available methods")
                return None
                
        except Exception as e:
            print(f"[ERROR] Failed to mount NFS volume: {str(e)}")
            return None
    
    def _setup_ssh_nfs_mirror(self, server: str, remote_path: str, local_path: str) -> bool:
        """
        通过SSH创建NFS的本地镜像目录
        用于无法直接挂载NFS的环境（如macOS开发环境）
        """
        try:
            # NFS服务器访问配置
            nfs_user = "root"
            nfs_password = "Lin040430"
            
            print(f"[INFO] Setting up SSH mirror for {server}:{remote_path}")
            
            # 构建SSH命令前缀
            ssh_cmd_prefix = f"sshpass -p '{nfs_password}' ssh -o StrictHostKeyChecking=no {nfs_user}@{server}"
            
            # 1. 验证远程目录存在
            check_cmd = f"{ssh_cmd_prefix} 'test -d {remote_path} && echo \"exists\" || echo \"missing\"'"
            result = subprocess.run(check_cmd, shell=True, capture_output=True, text=True)
            
            if result.returncode != 0 or "missing" in result.stdout:
                print(f"[ERROR] Remote NFS directory {remote_path} does not exist")
                return False
            
            print(f"[INFO] Verified remote directory {remote_path} exists")
            
            # 2. 创建本地镜像目录
            os.makedirs(local_path, exist_ok=True)
            
            # 3. 创建一个标识文件表明这是SSH镜像
            mirror_info = f"SSH Mirror for {server}:{remote_path}\nCreated: {subprocess.run(['date'], capture_output=True, text=True).stdout.strip()}"
            with open(os.path.join(local_path, ".ssh_mirror_info"), "w") as f:
                f.write(mirror_info)
            
            print(f"[INFO] Created SSH mirror directory at {local_path}")
            print(f"[INFO] Note: This is a local mirror, data persistence depends on SSH sync")
            
            return True
            
        except Exception as e:
            print(f"[ERROR] Failed to setup SSH NFS mirror: {str(e)}")
            return False
            
    def get_container_volume_mounts(self, volume_mounts: List[Dict], resolved_volumes: Dict[str, str]) -> List[str]:
        """
        根据容器的卷挂载配置和已解析的卷路径，生成Docker容器的挂载参数
        
        参数:
            volume_mounts: 容器的卷挂载配置列表
            resolved_volumes: 已解析的卷名到实际路径映射
            
        返回:
            Docker volume绑定参数列表
        """
        volume_binds = []
        
        for mount in volume_mounts:
            volume_name = mount.get('name')
            mount_path = mount.get('mountPath')
            read_only = mount.get('readOnly', False)
            
            if volume_name in resolved_volumes:
                host_path = resolved_volumes[volume_name]
                mode = 'ro' if read_only else 'rw'
                
                # 确保主机路径存在
                if not os.path.exists(host_path):
                    try:
                        os.makedirs(host_path, exist_ok=True)
                        print(f"[INFO] Created host directory: {host_path}")
                    except Exception as e:
                        print(f"[WARN] Failed to create host directory {host_path}: {str(e)}")
                
                # 创建Docker卷绑定字符串
                volume_bind = f"{host_path}:{mount_path}:{mode}"
                volume_binds.append(volume_bind)
                print(f"[INFO] Volume bind: {volume_bind}")
            else:
                print(f"[ERROR] Volume {volume_name} not found in resolved volumes")
        
        return volume_binds

    def cleanup_volumes(self) -> None:
        """
        清理挂载的卷资源
        主要清理NFS挂载点
        """
        for mount_path in list(self.mounted_nfs_volumes.keys()):
            try:
                mount_info = self.mounted_nfs_volumes[mount_path]
                mount_type = mount_info.get("type", "native")
                
                if mount_type == "native":
                    # 原生挂载 - 需要umount
                    if platform.system() in ["Linux", "Darwin"]:
                        unmount_cmd = ["sudo", "umount", mount_path]
                        result = subprocess.run(unmount_cmd, capture_output=True, text=True)
                        if result.returncode == 0:
                            print(f"[INFO] Unmounted NFS volume at {mount_path}")
                        else:
                            print(f"[WARN] Failed to unmount {mount_path}: {result.stderr}")
                elif mount_type == "ssh_mirror":
                    # SSH镜像 - 只需要清理本地目录
                    print(f"[INFO] Cleaning up SSH mirror at {mount_path}")
                        
                # 从跟踪列表中移除
                del self.mounted_nfs_volumes[mount_path]
                
                # 尝试删除挂载目录
                try:
                    if os.path.exists(mount_path):
                        # 对于SSH镜像，可能包含一些文件，先清理
                        import shutil
                        shutil.rmtree(mount_path)
                        print(f"[INFO] Removed mount directory: {mount_path}")
                except OSError as e:
                    print(f"[WARN] Failed to remove mount directory {mount_path}: {str(e)}")
                    
            except Exception as e:
                print(f"[ERROR] Failed to cleanup volume at {mount_path}: {str(e)}")
