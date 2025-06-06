#!/usr/bin/env python3
"""
完整的PV/PVC/Pod测试脚本
功能：
1. 创建PVC绑定到静态PV
2. 等待PVC绑定完成
3. 创建Pod使用这两个PVC
4. 检查Pod启动状态和挂载情况
5. 验证数据持久性

命令行参数：
- 无参数: 运行完整测试
- --list [namespace]: 列出指定命名空间的所有PVC (默认: default)
- --delete <pvc_name> [namespace]: 删除指定的PVC (默认命名空间: default)

示例：
  python test_complete_pv_pvc_pod.py                    # 运行完整测试
  python test_complete_pv_pvc_pod.py --list             # 列出default命名空间的PVC
  python test_complete_pv_pvc_pod.py --list kube-system # 列出kube-system命名空间的PVC
  python test_complete_pv_pvc_pod.py --delete pvc-bind-hostpath        # 删除default命名空间的PVC
  python test_complete_pv_pvc_pod.py --delete pvc-bind-nfs default     # 删除指定命名空间的PVC
"""

import sys
import os
import json
import requests
import time
import yaml
import subprocess

# 添加项目根目录到 Python 路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pkg.config.uriConfig import URIConfig
from pkg.apiObject.pod import Pod
from pkg.config.podConfig import PodConfig

class PVCPodTester:
    def __init__(self):
        self.uri_config = URIConfig()
        self.base_url = f"http://{self.uri_config.HOST}:{self.uri_config.PORT}"
        self.namespace = "default"
        
    def load_yaml_file(self, file_path):
        """加载YAML文件"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        except Exception as e:
            print(f"❌ 加载YAML文件失败 {file_path}: {str(e)}")
            return None
    
    def create_pvc(self, pvc_name, pvc_data):
        """创建PVC"""
        print(f"📦 创建PVC: {pvc_name}")
        
        try:
            create_url = f"{self.base_url}{self.uri_config.PVC_SPEC_URL.format(namespace=self.namespace, name=pvc_name)}"
            response = requests.post(create_url, json=pvc_data)
            
            if response.status_code == 200:
                print(f"   ✅ PVC {pvc_name} 创建成功")
                return True
            else:
                print(f"   ❌ PVC {pvc_name} 创建失败: {response.status_code} - {response.text}")
                return False
        except Exception as e:
            print(f"   ❌ 创建PVC异常: {str(e)}")
            return False
    
    def wait_for_pvc_bound(self, pvc_name, timeout=60):
        """等待PVC绑定完成"""
        print(f"⏳ 等待PVC {pvc_name} 绑定...")
        
        get_url = f"{self.base_url}{self.uri_config.PVC_SPEC_STATUS_URL.format(namespace=self.namespace, name=pvc_name)}"
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            try:
                response = requests.get(get_url)
                if response.status_code == 200:
                    pvc_info = response.json()
                    status = pvc_info.get('status', 'Unknown')
                    bound_pv = pvc_info.get('volume_name', 'None')
                    
                    print(f"   📊 PVC {pvc_name} 状态: {status}, 绑定PV: {bound_pv}")
                    
                    if status == 'Bound':
                        print(f"   ✅ PVC {pvc_name} 已成功绑定到PV: {bound_pv}")
                        return True
                    elif status == 'Failed':
                        print(f"   ❌ PVC {pvc_name} 绑定失败")
                        return False
                        
                time.sleep(2)
            except Exception as e:
                print(f"   ⚠️ 检查PVC状态异常: {str(e)}")
                time.sleep(2)
        
        print(f"   ⏰ PVC {pvc_name} 绑定超时")
        return False
    
    def get_pvc_info(self, pvc_name):
        """获取PVC详细信息"""
        try:
            get_url = f"{self.base_url}{self.uri_config.PVC_SPEC_URL.format(namespace=self.namespace, name=pvc_name)}"
            response = requests.get(get_url)
            
            if response.status_code == 200:
                return response.json()
            else:
                print(f"   ❌ 获取PVC {pvc_name} 信息失败: {response.status_code}")
                return None
        except Exception as e:
            print(f"   ❌ 获取PVC信息异常: {str(e)}")
            return None
    
    def create_pod_direct(self, pod_data):
        """使用Pod类直接创建Pod"""
        print(f"🚀 创建Pod: {pod_data['metadata']['name']}")
        
        try:
            # 使用PodConfig和Pod类创建
            pod_config = PodConfig(pod_data)
            print(f"   📋 Pod配置: {json.dumps(pod_config.to_dict(), indent=2)}")
            pod = Pod(pod_config)
            
            print(f"   ✅ Pod {pod_config.name} 创建成功")
            print(f"   📍 Pod 容器数量: {len(pod.containers)}")
            if pod.containers:
                main_container = self.get_main_container(pod)
                if main_container:
                    print(f"   📍 主容器 ID: {main_container.id[:12]}...")
                else:
                    print(f"   📍 主容器 ID: {pod.containers[0].id[:12]}...")
            print(f"   📊 Pod 状态: {pod.status}")
            print(f"   🌐 Pod IP: {pod.subnet_ip}")
            
            return pod
            
        except Exception as e:
            print(f"   ❌ 创建Pod异常: {str(e)}")
            import traceback
            print(f"   🔍 错误详情: {traceback.format_exc()}")
            return None
    
    def get_main_container(self, pod):
        """获取主容器（非pause容器）"""
        if not hasattr(pod, 'containers') or not pod.containers:
            return None
            
        # 查找非pause容器
        for container in pod.containers:
            # 获取容器名称信息
            cmd = f"docker inspect {container.id} --format '{{{{.Name}}}}'"
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            
            if result.returncode == 0:
                container_name = result.stdout.strip()
                print(f"   🔍 检查容器: {container.id[:12]} - {container_name}")
                
                # 如果容器名不包含pause，则认为是主容器
                if 'pause' not in container_name.lower():
                    print(f"   ✅ 找到主容器: {container.id[:12]}")
                    return container
                    
        # 如果没找到非pause容器，返回第一个容器
        print(f"   ⚠️ 未找到非pause容器，使用第一个容器")
        return pod.containers[0] if pod.containers else None

    def check_pod_status(self, pod):
        """检查Pod状态"""
        print(f"🔍 检查Pod状态...")
        
        try:
            main_container = self.get_main_container(pod)
            if main_container:
                # 检查容器是否在运行
                cmd = f"docker ps --filter id={main_container.id} --format 'table {{{{.ID}}}}\\t{{{{.Image}}}}\\t{{{{.Status}}}}'"
                result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
                
                if result.returncode == 0 and main_container.id in result.stdout:
                    print(f"   ✅ Pod主容器正在运行")
                    print(f"   📊 容器信息: {result.stdout.strip()}")
                    return True
                else:
                    print(f"   ❌ Pod主容器未运行")
                    return False
            else:
                print(f"   ❌ Pod没有容器ID")
                return False
                
        except Exception as e:
            print(f"   ❌ 检查Pod状态异常: {str(e)}")
            return False
    
    def check_volume_mounts(self, pod):
        """检查Pod的卷挂载情况"""
        print(f"💾 检查卷挂载情况...")
        
        try:
            main_container = self.get_main_container(pod)
            if not main_container:
                print(f"   ❌ Pod没有主容器信息")
                return False
            
            # 首先检查Docker容器的卷挂载信息
            print(f"   🔍 检查Docker容器卷挂载:")
            inspect_cmd = f"docker inspect {main_container.id}"
            inspect_result = subprocess.run(inspect_cmd, shell=True, capture_output=True, text=True)
            
            if inspect_result.returncode == 0:
                import json
                try:
                    container_info = json.loads(inspect_result.stdout)[0]
                    mounts = container_info.get('Mounts', [])
                    print(f"      📋 容器挂载信息:")
                    for mount in mounts:
                        source = mount.get('Source', 'Unknown')
                        destination = mount.get('Destination', 'Unknown')
                        mount_type = mount.get('Type', 'Unknown')
                        rw = mount.get('RW', False)
                        print(f"         📁 {mount_type}: {source} -> {destination} (RW: {rw})")
                except json.JSONDecodeError:
                    print(f"      ❌ 无法解析容器信息")
            
            # 检查容器内的挂载点
            mount_checks = [
                ("/hostpath-data", "hostPath存储"),
                ("/nfs-data", "NFS存储")
            ]
            
            all_mounted = True
            
            for mount_path, mount_type in mount_checks:
                cmd = f"docker exec {main_container.id} ls -la {mount_path}"
                result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
                
                if result.returncode == 0:
                    print(f"   ✅ {mount_type} 挂载成功: {mount_path}")
                    print(f"      内容: {result.stdout.strip()}")
                else:
                    print(f"   ❌ {mount_type} 挂载失败: {mount_path}")
                    print(f"      错误: {result.stderr.strip()}")
                    all_mounted = False
            
            return all_mounted
            
        except Exception as e:
            print(f"   ❌ 检查卷挂载异常: {str(e)}")
            return False
    
    def test_data_persistence(self, pod):
        """测试数据持久性"""
        print(f"💽 测试数据持久性...")
        
        try:
            main_container = self.get_main_container(pod)
            if not main_container:
                print(f"   ❌ Pod没有主容器信息")
                return False
            
            print(f"   🔍 使用主容器 {main_container.id[:12]} 进行测试")
            
            # 首先检查目录是否存在和权限
            check_commands = [
                ("ls -la /", "检查根目录"),
                ("ls -la /hostpath-data", "检查hostPath目录"),
                ("ls -la /nfs-data", "检查NFS目录"),
                ("whoami", "检查当前用户"),
                ("id", "检查用户权限"),
                ("pwd", "检查当前工作目录")
            ]
            
            print("   📋 首先检查容器环境:")
            for cmd, description in check_commands:
                docker_cmd = f"docker exec {main_container.id} {cmd}"
                result = subprocess.run(docker_cmd, shell=True, capture_output=True, text=True)
                
                print(f"      🔍 {description}: {cmd}")
                if result.returncode == 0:
                    print(f"         ✅ 成功: {result.stdout.strip()}")
                else:
                    print(f"         ❌ 失败: {result.stderr.strip()}")
            
            # 分步测试写入操作，更好地诊断问题
            test_commands = [
                # 第一步：测试目录权限
                ("ls -ld /hostpath-data", "检查hostPath目录权限"),
                ("ls -ld /nfs-data", "检查NFS目录权限"),
                
                # 第二步：尝试创建文件
                ("touch /hostpath-data/test.txt", "hostPath创建文件"),
                ("touch /nfs-data/test.txt", "NFS创建文件"),
                
                # 第三步：检查文件是否创建成功
                ("ls -la /hostpath-data/test.txt", "检查hostPath文件"),
                ("ls -la /nfs-data/test.txt", "检查NFS文件"),
                
                # 第四步：尝试写入内容
                ("echo 'hostPath test data' > /hostpath-data/test.txt", "hostPath存储写入"),
                ("echo 'NFS test data' > /nfs-data/test.txt", "NFS存储写入"),
                
                # 第五步：验证写入
                ("cat /hostpath-data/test.txt", "hostPath存储读取"),
                ("cat /nfs-data/test.txt", "NFS存储读取"),
                
                # 第六步：检查磁盘空间
                ("df -h /hostpath-data", "检查hostPath磁盘空间"),
                ("df -h /nfs-data", "检查NFS磁盘空间")
            ]
            
            print("   📝 执行数据持久性测试:")
            all_success = True
            
            for cmd, description in test_commands:
                docker_cmd = f"docker exec {main_container.id} bash -c '{cmd}'"
                result = subprocess.run(docker_cmd, shell=True, capture_output=True, text=True)
                
                print(f"      🔍 {description}: {cmd}")
                if result.returncode == 0:
                    print(f"         ✅ 成功")
                    if "读取" in description:
                        print(f"         📄 内容: {result.stdout.strip()}")
                else:
                    print(f"         ❌ 失败")
                    print(f"         🔴 错误输出: {result.stderr.strip()}")
                    print(f"         🔵 标准输出: {result.stdout.strip()}")
                    
                    # 如果是写入失败，尝试更详细的权限检查
                    if "写入" in description:
                        dir_path = "/hostpath-data" if "hostPath" in description else "/nfs-data"
                        
                        # 详细的权限诊断
                        print(f"         🔍 开始详细诊断 {dir_path} 写入问题:")
                        
                        # 1. 检查目录权限
                        perm_cmd = f"docker exec {main_container.id} ls -ld {dir_path}"
                        perm_result = subprocess.run(perm_cmd, shell=True, capture_output=True, text=True)
                        print(f"         📁 目录权限: {perm_result.stdout.strip()}")
                        
                        # 2. 检查目录所有者
                        owner_cmd = f"docker exec {main_container.id} stat -c '%U:%G' {dir_path}"
                        owner_result = subprocess.run(owner_cmd, shell=True, capture_output=True, text=True)
                        print(f"         👤 目录所有者: {owner_result.stdout.strip()}")
                        
                        # 3. 检查当前用户
                        user_cmd = f"docker exec {main_container.id} whoami"
                        user_result = subprocess.run(user_cmd, shell=True, capture_output=True, text=True)
                        print(f"         👤 当前用户: {user_result.stdout.strip()}")
                        
                        # 4. 检查用户ID
                        id_cmd = f"docker exec {main_container.id} id"
                        id_result = subprocess.run(id_cmd, shell=True, capture_output=True, text=True)
                        print(f"         🆔 用户ID: {id_result.stdout.strip()}")
                        
                        # 5. 尝试不同的写入方式
                        print(f"         🧪 尝试不同的写入方式:")
                        
                        # 尝试使用tee命令
                        tee_cmd = f"docker exec {main_container.id} bash -c 'echo \"test with tee\" | tee {dir_path}/test_tee.txt'"
                        tee_result = subprocess.run(tee_cmd, shell=True, capture_output=True, text=True)
                        if tee_result.returncode == 0:
                            print(f"            ✅ tee命令写入成功")
                        else:
                            print(f"            ❌ tee命令失败: {tee_result.stderr.strip()}")
                        
                        # 尝试使用dd命令
                        dd_cmd = f"docker exec {main_container.id} bash -c 'echo \"test with dd\" | dd of={dir_path}/test_dd.txt 2>/dev/null'"
                        dd_result = subprocess.run(dd_cmd, shell=True, capture_output=True, text=True)
                        if dd_result.returncode == 0:
                            print(f"            ✅ dd命令写入成功")
                        else:
                            print(f"            ❌ dd命令失败")
                        
                        # 尝试使用cat重定向
                        cat_cmd = f"docker exec {main_container.id} bash -c 'cat > {dir_path}/test_cat.txt << EOF\ntest with cat\nEOF'"
                        cat_result = subprocess.run(cat_cmd, shell=True, capture_output=True, text=True)
                        if cat_result.returncode == 0:
                            print(f"            ✅ cat重定向写入成功")
                        else:
                            print(f"            ❌ cat重定向失败: {cat_result.stderr.strip()}")
                        
                        # 6. 检查文件系统类型
                        fs_cmd = f"docker exec {main_container.id} df -T {dir_path}"
                        fs_result = subprocess.run(fs_cmd, shell=True, capture_output=True, text=True)
                        print(f"         💾 文件系统类型: {fs_result.stdout.strip()}")
                        
                        # 7. 检查挂载选项
                        mount_cmd = f"docker exec {main_container.id} mount | grep {dir_path}"
                        mount_result = subprocess.run(mount_cmd, shell=True, capture_output=True, text=True)
                        if mount_result.stdout.strip():
                            print(f"         🔗 挂载信息: {mount_result.stdout.strip()}")
                        else:
                            print(f"         🔗 未找到特定挂载信息，检查所有挂载:")
                            all_mount_cmd = f"docker exec {main_container.id} mount"
                            all_mount_result = subprocess.run(all_mount_cmd, shell=True, capture_output=True, text=True)
                            print(f"            {all_mount_result.stdout.strip()}")
                    
                    all_success = False
            
            # 最后再次检查文件是否存在
            print("   🔍 最终文件检查:")
            final_checks = [
                ("ls -la /hostpath-data/", "hostPath目录内容"),
                ("ls -la /nfs-data/", "NFS目录内容")
            ]
            
            for cmd, description in final_checks:
                docker_cmd = f"docker exec {main_container.id} {cmd}"
                result = subprocess.run(docker_cmd, shell=True, capture_output=True, text=True)
                print(f"      📁 {description}:")
                print(f"         {result.stdout.strip()}")
            
            return all_success
            
        except Exception as e:
            print(f"   ❌ 测试数据持久性异常: {str(e)}")
            import traceback
            print(f"   🔍 异常详情: {traceback.format_exc()}")
            return False
    
    def verify_nfs_remote_data(self):
        """验证NFS服务器上的数据"""
        print(f"🌐 验证NFS服务器上的数据...")
        
        try:
            nfs_server = "10.119.15.190"
            nfs_user = "root"
            nfs_password = "Lin040430"
            nfs_test_path = "/nfs/pv-storage/exports/test-nfs-storage"
            
            ssh_cmd = f"sshpass -p '{nfs_password}' ssh -o StrictHostKeyChecking=no {nfs_user}@{nfs_server}"
            
            # 检查测试文件是否存在
            check_cmd = f"{ssh_cmd} 'ls -la {nfs_test_path}/test.txt'"
            result = subprocess.run(check_cmd, shell=True, capture_output=True, text=True)
            
            if result.returncode == 0:
                print(f"   ✅ NFS服务器上的测试文件存在")
                
                # 读取文件内容
                read_cmd = f"{ssh_cmd} 'cat {nfs_test_path}/test.txt'"
                result = subprocess.run(read_cmd, shell=True, capture_output=True, text=True)
                
                if result.returncode == 0:
                    print(f"   ✅ NFS文件内容: {result.stdout.strip()}")
                    return True
                else:
                    print(f"   ❌ 读取NFS文件失败")
                    return False
            else:
                print(f"   ❌ NFS服务器上的测试文件不存在")
                return False
                
        except Exception as e:
            print(f"   ❌ 验证NFS数据异常: {str(e)}")
            return False
    
    def cleanup_pod(self, pod):
        """清理Pod"""
        print(f"🧹 清理Pod...")
        
        try:
            if pod and hasattr(pod, 'remove'):
                pod.remove()
                print(f"   ✅ Pod清理成功")
            else:
                print(f"   ⚠️ Pod对象无效，跳过清理")
        except Exception as e:
            print(f"   ⚠️ Pod清理异常: {str(e)}")
    
    def cleanup_pvc(self, pvc_name):
        """清理PVC"""
        print(f"🧹 清理PVC: {pvc_name}")
        
        try:
            delete_url = f"{self.base_url}{self.uri_config.PVC_SPEC_URL.format(namespace=self.namespace, name=pvc_name)}"
            response = requests.delete(delete_url)
            
            if response.status_code == 200:
                print(f"   ✅ PVC {pvc_name} 删除成功")
            else:
                print(f"   ⚠️ PVC {pvc_name} 删除失败: {response.status_code}")
        except Exception as e:
            print(f"   ⚠️ 删除PVC异常: {str(e)}")
    
    def delete_pvc(self, pvc_name, namespace=None):
        """删除指定的PVC"""
        if namespace is None:
            namespace = self.namespace
            
        print(f"🗑️ 删除PVC: {namespace}/{pvc_name}")
        
        try:
            delete_url = f"{self.base_url}{self.uri_config.PVC_SPEC_URL.format(namespace=namespace, name=pvc_name)}"
            response = requests.delete(delete_url)
            
            if response.status_code == 200:
                print(f"✅ PVC {namespace}/{pvc_name} 删除成功")
                return True
            else:
                print(f"❌ PVC {namespace}/{pvc_name} 删除失败: {response.status_code} - {response.text}")
                return False
        except Exception as e:
            print(f"❌ 删除PVC {namespace}/{pvc_name} 时发生异常: {str(e)}")
            return False
    
    def list_all_pvcs(self, namespace=None):
        """列出所有PVC"""
        if namespace is None:
            namespace = self.namespace
            
        print(f"📋 列出命名空间 {namespace} 中的所有PVC:")
        
        try:
            # 获取指定命名空间的所有PVC
            list_url = f"{self.base_url}{self.uri_config.GLOBAL_PVCS_URL.format(namespace=namespace)}"
            response = requests.get(list_url)
            
            if response.status_code == 200:
                pvcs = response.json()
                if pvcs:
                    print(f"✅ 找到 {len(pvcs)} 个PVC:")
                    for i, pvc in enumerate(pvcs, 1):
                        pvc_name = pvc.get('metadata', {}).get('name', 'Unknown')
                        pvc_status = pvc.get('status', 'Unknown')
                        volume_name = pvc.get('volume_name', 'None')
                        storage_class = pvc.get('storage_class_name', 'Unknown')
                        
                        print(f"   {i}. 📦 {pvc_name}")
                        print(f"      状态: {pvc_status}")
                        print(f"      绑定PV: {volume_name}")
                        print(f"      存储类型: {storage_class}")
                        print()
                    return True
                else:
                    print("🔍 没有找到任何PVC")
                    return True
            else:
                print(f"❌ 获取PVC列表失败: {response.status_code} - {response.text}")
                return False
        except Exception as e:
            print(f"❌ 列出PVC时发生异常: {str(e)}")
            return False
    
    def run_complete_test(self):
        """运行完整测试"""
        print("🎯 开始完整的PV/PVC/Pod测试")
        print("=" * 60)
        
        # 测试文件路径
        testfile_dir = "/Users/liang/code/cloud_OS/k8s/k8s_group_4/testFile"
        pvc_files = {
            "pvc-bind-hostpath": f"{testfile_dir}/pvc-bind-hostpath-pv.yaml",
            "pvc-bind-nfs": f"{testfile_dir}/pvc-bind-nfs-pv.yaml"
        }
        pod_file = f"{testfile_dir}/pod-with-dual-pvcs.yaml"
        
        created_pvcs = []
        pod = None
        
        try:
            # 1. 创建PVC
            print("\n📦 步骤1: 创建PVC")
            for pvc_name, pvc_file in pvc_files.items():
                pvc_data = self.load_yaml_file(pvc_file)
                if pvc_data and self.create_pvc(pvc_name, pvc_data):
                    created_pvcs.append(pvc_name)
            
            if len(created_pvcs) != 2:
                print("❌ PVC创建失败，终止测试")
                return False
            
            # 2. 等待PVC绑定
            print("\n⏳ 步骤2: 等待PVC绑定")
            all_bound = True
            for pvc_name in created_pvcs:
                if not self.wait_for_pvc_bound(pvc_name):
                    all_bound = False
            
            if not all_bound:
                print("❌ PVC绑定失败，终止测试")
                return False
            
            # 3. 显示PVC信息
            print("\n📊 步骤3: PVC绑定信息")
            finish_binding = True
            while 1:
                for pvc_name in created_pvcs:
                    pvc_info = self.get_pvc_info(pvc_name)
                    if not pvc_info.get('status') == 'Bound':
                        finish_binding = False
                if finish_binding:
                    print("✅ 所有PVC已成功绑定")
                    break
                time.sleep(2)
                print("等待PVC绑定状态更新...")
            
            for pvc_name in created_pvcs:
                pvc_info = self.get_pvc_info(pvc_name)
                if pvc_info:
                    print(f"   📝 {pvc_name}:")
                    print(f"      状态: {pvc_info.get('status', 'Unknown')}")
                    print(f"      绑定PV: {pvc_info.get('volume_name', 'None')}")
                    print(f"      存储类型: {pvc_info.get('storage_class_name', 'Unknown')}")
            
            # 4. 创建Pod
            print("\n🚀 步骤4: 创建Pod")
            pod_data = self.load_yaml_file(pod_file)
            if not pod_data:
                print("❌ 加载Pod YAML失败")
                return False
            
            pod = self.create_pod_direct(pod_data)
            if not pod:
                print("❌ Pod创建失败")
                return False
            
            # 等待Pod启动
            print("⏳ 等待Pod启动...")
            time.sleep(10)
            
            # # 5. 检查Pod状态
            # print("\n🔍 步骤5: 检查Pod状态")
            # if not self.check_pod_status(pod):
            #     print("❌ Pod状态检查失败")
            #     return False
            
            # 6. 检查卷挂载
            print("\n💾 步骤6: 检查卷挂载")
            if not self.check_volume_mounts(pod):
                print("❌ 卷挂载检查失败")
                return False
            
            # 7. 测试数据持久性
            print("\n💽 步骤7: 测试数据持久性")
            if not self.test_data_persistence(pod):
                print("❌ 数据持久性测试失败")
                return False
            
            # 8. 验证NFS远程数据
            print("\n🌐 步骤8: 验证NFS远程数据")
            if not self.verify_nfs_remote_data():
                print("⚠️ NFS远程数据验证失败（但不影响整体测试）")
            
            print("\n🎉 所有测试通过！")
            return True
            
        except Exception as e:
            print(f"\n❌ 测试过程中发生异常: {str(e)}")
            return False
            
        finally:
            # 用户确认后清理资源
            print("\n" + "="*60)
            print("🧹 测试完成，准备清理资源")
            print(f"📦 将要清理的资源:")
            if pod:
                print(f"   - Pod: {pod_data.get('metadata', {}).get('name', 'unknown')}")
            for pvc_name in created_pvcs:
                print(f"   - PVC: {pvc_name}")
            
            print("\n⚠️  注意: 清理后所有测试数据将被删除")
            input("🔄 按 Enter 键开始清理资源...")
            
            print("\n🧹 开始清理资源...")
            if pod:
                self.cleanup_pod(pod)
            
            for pvc_name in created_pvcs:
                self.cleanup_pvc(pvc_name)
            
            print("✨ 清理完成，测试结束")

def main():
    """主函数"""
    # 检查命令行参数
    if len(sys.argv) > 1:
        command = sys.argv[1]
        
        if command == "--delete":
            if len(sys.argv) < 3:
                print("❌ 请提供要删除的PVC名称")
                print("用法: python test_complete_pv_pvc_pod.py --delete <pvc_name> [namespace]")
                print("示例: python test_complete_pv_pvc_pod.py --delete pvc-bind-hostpath")
                print("示例: python test_complete_pv_pvc_pod.py --delete pvc-bind-nfs default")
                sys.exit(1)
            
            pvc_name = sys.argv[2]
            namespace = sys.argv[3] if len(sys.argv) > 3 else "default"
            
            tester = PVCPodTester()
            success = tester.delete_pvc(pvc_name, namespace)
            
            if success:
                print(f"\n✅ PVC {namespace}/{pvc_name} 删除成功！")
                return 0
            else:
                print(f"\n❌ PVC {namespace}/{pvc_name} 删除失败！")
                return 1
                
        elif command == "--list":
            namespace = sys.argv[2] if len(sys.argv) > 2 else "default"
            
            tester = PVCPodTester()
            success = tester.list_all_pvcs(namespace)
            
            if success:
                print(f"\n✅ PVC列表获取成功！")
                return 0
            else:
                print(f"\n❌ PVC列表获取失败！")
                return 1
            
        elif command == "--clean":
            # 添加清理功能的实现
            print("🧹 清理功能暂未实现")
            return 0
            
                
        else:
            print("❌ 未知的命令参数")
            print("用法:")
            print("  python test_complete_pv_pvc_pod.py               # 运行完整测试")
            print("  python test_complete_pv_pvc_pod.py --list [namespace]  # 列出PVC")
            print("  python test_complete_pv_pvc_pod.py --delete <pvc_name> [namespace]  # 删除PVC")
            sys.exit(1)
    else:
        # 运行完整测试
        print("开始完整的PV/PVC/Pod测试...")
        tester = PVCPodTester()
        success = tester.run_complete_test()
        
        if success:
            print("\n✅ 完整测试成功！")
            return 0
        else:
            print("\n❌ 测试失败！")
            return 1

if __name__ == "__main__":
    sys.exit(main())
