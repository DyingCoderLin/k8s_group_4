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
    
    def __init__(self, api_client: ApiClient = None, uri_config: URIConfig = None):
        self.api_client = api_client
        self.uri_config = uri_config if uri_config else URIConfig()
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
                
            pvc_data = pvc_response
            bound_pv_name = pvc_data.get('status', {}).get('volumeName')
            
            if not bound_pv_name:
                print(f"[ERROR] PVC {pvc_name} is not bound to any PV")
                return None
                
            # 获取PV信息
            pv_url = self.uri_config.PV_SPEC_URL.format(name=bound_pv_name)
            pv_response = self.api_client.get(pv_url)
            
            if not pv_response:
                print(f"[ERROR] PV {bound_pv_name} not found")
                return None
                
            pv_data = pv_response
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
        
        参数:
            nfs_spec: PV中的NFS规格
            pv_name: PV名称，用于创建唯一的挂载点
            
        返回:
            本地挂载路径，挂载失败则返回None
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
            
            # 挂载NFS
            if platform.system() == "Linux":
                mount_cmd = ["sudo", "mount", "-t", "nfs", f"{server}:{path}", mount_point]
                result = subprocess.run(mount_cmd, capture_output=True, text=True)
                
                if result.returncode == 0:
                    self.mounted_nfs_volumes[mount_point] = {"server": server, "path": path}
                    print(f"[INFO] Successfully mounted NFS volume: {server}:{path} to {mount_point}")
                    return mount_point
                else:
                    print(f"[ERROR] Failed to mount NFS volume: {result.stderr}")
                    return None
            elif platform.system() == "Darwin":
                # macOS
                mount_cmd = ["mount", "-t", "nfs", f"{server}:{path}", mount_point]
                result = subprocess.run(mount_cmd, capture_output=True, text=True)
                
                if result.returncode == 0:
                    self.mounted_nfs_volumes[mount_point] = {"server": server, "path": path}
                    print(f"[INFO] Successfully mounted NFS volume: {server}:{path} to {mount_point}")
                    return mount_point
                else:
                    print(f"[ERROR] Failed to mount NFS volume: {result.stderr}")
                    return None
            else:
                print(f"[ERROR] NFS mounting not implemented for platform: {platform.system()}")
                # 在不支持的平台上，我们仍然返回挂载点以便Pod可以继续运行
                # 但实际上不会挂载
                return mount_point
                
        except Exception as e:
            print(f"[ERROR] Failed to mount NFS volume: {str(e)}")
            return None
            
    def cleanup_volumes(self, pod_volumes: List[Dict]) -> None:
        """
        清理Pod使用的卷资源
        
        参数:
            pod_volumes: 卷配置列表
        """
        for volume_name, mount_path in pod_volumes.items():
            # 仅清理NFS挂载
            if mount_path in self.mounted_nfs_volumes:
                try:
                    if platform.system() in ["Linux", "Darwin"]:
                        unmount_cmd = ["sudo", "umount", mount_path]
                        subprocess.run(unmount_cmd, capture_output=True, text=True)
                        print(f"[INFO] Unmounted NFS volume at {mount_path}")
                        
                    # 从跟踪列表中移除
                    del self.mounted_nfs_volumes[mount_path]
                    
                except Exception as e:
                    print(f"[ERROR] Failed to unmount volume {volume_name} at {mount_path}: {str(e)}")
