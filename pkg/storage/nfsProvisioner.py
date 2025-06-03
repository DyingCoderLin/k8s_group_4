import os
import subprocess
import platform
from pkg.storage.provisioner import BaseProvisioner

class NFSProvisioner(BaseProvisioner):
    """NFS 类型的存储供应器"""
    
    def __init__(self, storage_class_config):
        super().__init__(storage_class_config)
        self.nfs_server = self.parameters.get("server")
        self.nfs_path = self.parameters.get("path", "/nfs/pv-storage")
        
        if not self.nfs_server:
            raise ValueError("NFS server parameter is required")
    
    def provision(self, pvc_config):
        """动态供应 NFS PV"""
        pv_name = self.generate_pv_name(pvc_config)
        
        # 创建 NFS 子目录
        pv_path = f"{self.nfs_path.rstrip('/')}/{pv_name}"
        
        try:
            self._create_nfs_directory(pv_path)
            print(f"[INFO] Created NFS directory: {self.nfs_server}:{pv_path}")
        except Exception as e:
            print(f"[ERROR] Failed to create NFS directory: {e}")
            raise
        
        # 生成 PV 配置
        pv_spec = self.get_default_pv_spec(pvc_config, pv_name)
        pv_spec["spec"]["nfs"] = {
            "server": self.nfs_server,
            "path": pv_path,
            "readOnly": False
        }
        
        return pv_spec
    
    def delete(self, pv_config):
        """删除 NFS PV"""
        volume_source = pv_config.volume_source
        if volume_source["type"] != "nfs":
            raise ValueError("PV is not an NFS volume")
        
        server = volume_source["server"]
        path = volume_source["path"]
        
        if server != self.nfs_server:
            print(f"[WARN] NFS server mismatch: {server} != {self.nfs_server}")
            return
        
        try:
            self._delete_nfs_directory(path)
            print(f"[INFO] Deleted NFS directory: {server}:{path}")
        except Exception as e:
            print(f"[ERROR] Failed to delete NFS directory: {e}")
            raise
    
    def _create_nfs_directory(self, path):
        """在 NFS 服务器上创建目录"""
        # 如果 NFS 服务器是本地，直接创建目录
        if self._is_local_server():
            os.makedirs(path, exist_ok=True)
            return
        
        # 通过 SSH 在远程服务器创建目录
        ssh_user = self.parameters.get("sshUser", "root")
        cmd = [
            "ssh", f"{ssh_user}@{self.nfs_server}",
            f"mkdir -p {path} && chmod 777 {path}"
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise Exception(f"SSH command failed: {result.stderr}")
    
    def _delete_nfs_directory(self, path):
        """删除 NFS 服务器上的目录"""
        # 安全检查：只删除我们管理的路径下的目录
        if not path.startswith(self.nfs_path):
            raise ValueError(f"Path {path} is outside managed NFS path {self.nfs_path}")
        
        # 如果 NFS 服务器是本地，直接删除目录
        if self._is_local_server():
            if os.path.exists(path):
                import shutil
                shutil.rmtree(path)
            return
        
        # 通过 SSH 在远程服务器删除目录
        ssh_user = self.parameters.get("sshUser", "root")
        cmd = [
            "ssh", f"{ssh_user}@{self.nfs_server}",
            f"rm -rf {path}"
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise Exception(f"SSH command failed: {result.stderr}")
    
    def _is_local_server(self):
        """检查 NFS 服务器是否是本地"""
        local_addresses = ["localhost", "127.0.0.1", "::1"]
        
        # 获取本机 IP 地址
        try:
            import socket
            hostname = socket.gethostname()
            local_ip = socket.gethostbyname(hostname)
            local_addresses.append(local_ip)
        except:
            pass
        
        return self.nfs_server in local_addresses
    
    def test_nfs_connectivity(self):
        """测试 NFS 连接性"""
        # 尝试挂载测试
        test_mount_point = "/tmp/nfs-test-mount"
        
        try:
            # 创建测试挂载点
            os.makedirs(test_mount_point, exist_ok=True)
            
            # 尝试挂载
            if platform.system() == "Darwin":  # macOS
                cmd = ["mount", "-t", "nfs", f"{self.nfs_server}:{self.nfs_path}", test_mount_point]
            else:  # Linux
                cmd = ["mount", "-t", "nfs", f"{self.nfs_server}:{self.nfs_path}", test_mount_point]
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode == 0:
                # 卸载测试挂载
                subprocess.run(["umount", test_mount_point], capture_output=True)
                print(f"[INFO] NFS connectivity test passed: {self.nfs_server}:{self.nfs_path}")
                return True
            else:
                print(f"[WARN] NFS connectivity test failed: {result.stderr}")
                return False
                
        except Exception as e:
            print(f"[ERROR] NFS connectivity test error: {e}")
            return False
        finally:
            # 清理测试挂载点
            try:
                os.rmdir(test_mount_point)
            except:
                pass
