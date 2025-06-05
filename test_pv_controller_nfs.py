#!/usr/bin/env python3
"""
测试PV Controller的NFS存储创建功能
"""
import sys
import os
sys.path.append('/Users/liang/code/cloud_OS/k8s/k8s_group_4')

from pkg.controller.pvController import PVController
from pkg.config.pvcConfig import PVCConfig
from pkg.config.pvConfig import PVConfig
import subprocess

def test_pv_controller_nfs():
    """测试PV Controller的NFS存储创建"""
    print("=== 测试PV Controller NFS存储创建 ===")
    
    # 创建PV Controller实例
    controller = PVController()
    
    # 创建模拟PVC配置
    pvc_data = {
        "apiVersion": "v1",
        "kind": "PersistentVolumeClaim",
        "metadata": {
            "name": "test-nfs-pvc",
            "namespace": "default"
        },
        "spec": {
            "storageClassName": "nfs",
            "storage": "1Gi"
        }
    }
    
    pvc_config = PVCConfig(pvc_data)
    
    # 创建模拟PV配置（NFS类型）
    pv_data = {
        "apiVersion": "v1",
        "kind": "PersistentVolume", 
        "metadata": {
            "name": "test-nfs-pv"
        },
        "spec": {
            "capacity": {
                "storage": "1Gi"
            },
            "nfs": {
                "server": "10.119.15.190",
                "path": "/nfs/pv-storage/test/default/test-nfs-pvc"
            }
        }
    }
    
    pv_config = PVConfig(pv_data)
    
    print(f"测试PVC: {pvc_config.name} (namespace: {pvc_config.namespace})")
    print(f"测试PV: {pv_config.name}")
    print(f"NFS路径: {pv_config.volume_source['server']}:{pv_config.volume_source['path']}")
    
    # 测试NFS存储创建
    try:
        result = controller._provision_storage(pv_config, pvc_config)
        
        if result is None:  # _provision_storage 没有返回值，通过异常判断成功
            print("✅ NFS存储创建成功")
            
            # 验证NFS服务器上是否真的创建了目录
            nfs_server = "10.119.15.190"
            nfs_user = "root"
            nfs_password = "Lin040430"
            test_path = pv_config.volume_source['path']
            
            ssh_cmd = f"sshpass -p '{nfs_password}' ssh -o StrictHostKeyChecking=no {nfs_user}@{nfs_server}"
            verify_cmd = f"{ssh_cmd} 'ls -la {test_path}'"
            
            result = subprocess.run(verify_cmd, shell=True, capture_output=True, text=True)
            
            if result.returncode == 0:
                print("✅ NFS服务器上目录验证成功")
                print(f"目录内容:\n{result.stdout}")
                
                # 清理测试目录
                cleanup_cmd = f"{ssh_cmd} 'rm -rf {test_path}'"
                subprocess.run(cleanup_cmd, shell=True, capture_output=True, text=True)
                print("✅ 测试目录已清理")
                
                return True
            else:
                print("❌ NFS服务器上目录验证失败")
                print(f"错误: {result.stderr}")
                return False
                
    except Exception as e:
        print(f"❌ NFS存储创建失败: {str(e)}")
        return False

def test_static_pv_nfs():
    """测试静态NFS PV创建"""
    print("\n=== 测试静态NFS PV创建 ===")
    
    controller = PVController()
    
    # 创建静态NFS PV配置
    static_pv_data = {
        "apiVersion": "v1",
        "kind": "PersistentVolume",
        "metadata": {
            "name": "static-nfs-pv"
        },
        "spec": {
            "capacity": {
                "storage": "2Gi"
            },
            "nfs": {
                "server": "10.119.15.190", 
                "path": "/nfs/pv-storage/static/static-nfs-pv"
            }
        },
        "status": "static"
    }
    
    print(f"测试静态PV: {static_pv_data['metadata']['name']}")
    print(f"NFS路径: {static_pv_data['spec']['nfs']['server']}:{static_pv_data['spec']['nfs']['path']}")
    
    try:
        # 调用静态PV处理方法
        controller._provision_static_pv(static_pv_data)
        
        # 验证NFS服务器上的目录
        nfs_server = "10.119.15.190"
        nfs_user = "root"
        nfs_password = "Lin040430"
        test_path = static_pv_data['spec']['nfs']['path']
        
        ssh_cmd = f"sshpass -p '{nfs_password}' ssh -o StrictHostKeyChecking=no {nfs_user}@{nfs_server}"
        verify_cmd = f"{ssh_cmd} 'ls -la {test_path}'"
        
        result = subprocess.run(verify_cmd, shell=True, capture_output=True, text=True)
        
        if result.returncode == 0:
            print("✅ 静态NFS PV目录验证成功")
            print(f"目录内容:\n{result.stdout}")
            
            # 清理测试目录
            cleanup_cmd = f"{ssh_cmd} 'rm -rf {test_path}'"
            subprocess.run(cleanup_cmd, shell=True, capture_output=True, text=True)
            print("✅ 测试目录已清理")
            
            return True
        else:
            print("❌ 静态NFS PV目录验证失败")
            print(f"错误: {result.stderr}")
            return False
            
    except Exception as e:
        print(f"❌ 静态NFS PV创建失败: {str(e)}")
        return False

def main():
    """主测试函数"""
    print("PV Controller NFS功能测试开始...")
    print("=" * 50)
    
    tests = [
        test_pv_controller_nfs,
        test_static_pv_nfs
    ]
    
    results = []
    for test in tests:
        try:
            result = test()
            results.append(result)
        except Exception as e:
            print(f"❌ 测试异常: {str(e)}")
            results.append(False)
    
    # 总结
    print("\n" + "=" * 50)
    print("测试结果总结:")
    
    test_names = [
        "PV Controller NFS存储创建",
        "静态NFS PV处理"
    ]
    
    all_passed = True
    for i, (name, result) in enumerate(zip(test_names, results)):
        status = "✅ 通过" if result else "❌ 失败"
        print(f"{i+1}. {name}: {status}")
        if not result:
            all_passed = False
    
    if all_passed:
        print("\n🎉 所有测试通过！PV Controller NFS功能正常。")
        return 0
    else:
        print("\n⚠️ 部分测试失败，请检查PV Controller配置。")
        return 1

if __name__ == "__main__":
    sys.exit(main())
