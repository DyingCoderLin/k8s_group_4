#!/usr/bin/env python3

"""
测试静态PV创建功能
"""

import sys
import os
import json
import requests
import time

# 添加项目根目录到 Python 路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pkg.config.uriConfig import URIConfig

def test_static_pv_creation():
    """测试静态PV创建"""
    
    print("=== 测试静态PV创建功能 ===\n")
    
    uri_config = URIConfig()
    base_url = f"http://{uri_config.HOST}:{uri_config.PORT}"
    
    # 测试数据：hostPath类型的PV
    hostpath_pv = {
        "apiVersion": "v1",
        "kind": "PersistentVolume",
        "metadata": {
            "name": "test-hostpath-pv"
        },
        "spec": {
            "capacity": "1Gi",
            "hostPath": {
                "path": "/tmp/test-hostpath-storage"
            }
        },
        "status": "static",
    }
    
    # 测试数据：NFS类型的PV
    nfs_pv = {
        "apiVersion": "v1",
        "kind": "PersistentVolume",
        "metadata": {
            "name": "test-nfs-pv"
        },
        "spec": {
            "capacity": "2Gi",
            "nfs": {
                "server": "10.119.15.190",
                "path": "/nfs/pv-storage/exports/test-nfs-storage"
            }
        },
        "status": "static",
    }
    
    test_cases = [
        ("hostPath PV", hostpath_pv),
        ("NFS PV", nfs_pv)
    ]
    
    for test_name, pv_data in test_cases:
        print(f"--- 测试 {test_name} ---")
        pv_name = pv_data["metadata"]["name"]
        
        try:
            # 1. 创建PV
            print(f"1. 创建PV: {pv_name}")
            create_url = f"{base_url}{uri_config.PV_SPEC_URL.format(name=pv_name)}"
            
            response = requests.post(create_url, json=pv_data)
            
            if response.status_code == 200:
                print(f"   ✓ PV {pv_name} 创建成功")
            else:
                print(f"   ✗ PV {pv_name} 创建失败: {response.status_code} - {response.text}")
                continue
            
            # 2. 获取PV
            print(f"2. 获取PV: {pv_name}")
            get_url = f"{base_url}{uri_config.PV_SPEC_URL.format(name=pv_name)}"
            while(1):
                response = requests.get(get_url)
                time.sleep(1)  # 等待1秒钟，确保PV状态更新
                print(f"   正在获取PV {pv_name} 状态...")
                if response.json().get('status') == 'Available':
                    break
                
            
            if response.status_code == 200:
                pv_info = response.json()
                print(f"   ✓ PV {pv_name} 获取成功")
                print(f"   状态: {pv_info.get('status', 'Unknown')}")
                print(f"   存储类型: {pv_info.get('spec', {}).keys()}")
                
                # 检查关键字段
                spec = pv_info.get('spec', {})
                if 'hostPath' in spec:
                    print(f"   hostPath路径: {spec['hostPath']['path']}")
                elif 'nfs' in spec:
                    print(f"   NFS服务器: {spec['nfs']['server']}")
                    print(f"   NFS路径: {spec['nfs']['path']}")
                    
            else:
                print(f"   ✗ PV {pv_name} 获取失败: {response.status_code} - {response.text}")
            
            # 3. 获取PV状态
            print(f"3. 获取PV状态: {pv_name}")
            status_url = f"{base_url}{uri_config.PV_SPEC_STATUS_URL.format(name=pv_name)}"
            
            response = requests.get(status_url)
            
            if response.status_code == 200:
                status_info = response.json()
                print(f"   ✓ PV {pv_name} 状态获取成功")
                print(f"   状态: {status_info.get('status', 'Unknown')}")
                print(f"   绑定的PVC: {status_info.get('claim_ref', 'None')}")
            else:
                print(f"   ✗ PV {pv_name} 状态获取失败: {response.status_code} - {response.text}")
            
            print()
            
        except Exception as e:
            print(f"   ✗ 测试 {test_name} 时发生异常: {str(e)}")
            print()
    
    # 4. 获取所有PV
    print("--- 测试获取所有PV ---")
    try:
        all_pvs_url = f"{base_url}{uri_config.GLOBAL_PVS_URL}"
        response = requests.get(all_pvs_url)
        
        if response.status_code == 200:
            pvs = response.json()
            print(f"✓ 获取所有PV成功，共 {len(pvs)} 个PV")
            for pv in pvs:
                print(f"   - {pv.get('metadata', {}).get('name', 'Unknown')}: {pv.get('status', 'Unknown')}")
        else:
            print(f"✗ 获取所有PV失败: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"✗ 获取所有PV时发生异常: {str(e)}")
    
    print("\n=== 测试完成 ===")
    
def do_delete(pv_name):
    """删除指定的PV"""
    uri_config = URIConfig()
    base_url = f"http://{uri_config.HOST}:{uri_config.PORT}"
    
    delete_url = f"{base_url}{uri_config.PV_SPEC_URL.format(name=pv_name)}"
    
    try:
        response = requests.delete(delete_url)
        if response.status_code == 200:
            print(f"✓ PV {pv_name} 删除成功")
        else:
            print(f"✗ PV {pv_name} 删除失败: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"✗ 删除PV {pv_name} 时发生异常: {str(e)}")

def list_all_pvs():
    """列出所有PV"""
    print("📋 列出所有PV:")
    
    uri_config = URIConfig()
    base_url = f"http://{uri_config.HOST}:{uri_config.PORT}"
    
    try:
        all_pvs_url = f"{base_url}{uri_config.GLOBAL_PVS_URL}"
        response = requests.get(all_pvs_url)
        
        if response.status_code == 200:
            pvs = response.json()
            if pvs:
                print(f"✅ 找到 {len(pvs)} 个PV:")
                for i, pv in enumerate(pvs, 1):
                    metadata = pv.get('metadata', {})
                    spec = pv.get('spec', {})
                    name = metadata.get('name', 'Unknown')
                    status = pv.get('status', 'Unknown')
                    claim_ref = pv.get('claim_ref', 'None')
                    
                    # 确定存储类型
                    storage_type = "Unknown"
                    storage_info = ""
                    if 'hostPath' in spec:
                        storage_type = "hostPath"
                        storage_info = f"路径: {spec['hostPath'].get('path', 'Unknown')}"
                    elif 'nfs' in spec:
                        storage_type = "NFS"
                        storage_info = f"服务器: {spec['nfs'].get('server', 'Unknown')}, 路径: {spec['nfs'].get('path', 'Unknown')}"
                    
                    print(f"   {i}. PV名称: {name}")
                    print(f"      状态: {status}")
                    print(f"      存储类型: {storage_type}")
                    print(f"      存储信息: {storage_info}")
                    print(f"      绑定PVC: {claim_ref}")
                    print()
                return True
            else:
                print("🔍 没有找到任何PV")
                return True
        else:
            print(f"❌ 获取PV列表失败: {response.status_code} - {response.text}")
            return False
    except Exception as e:
        print(f"❌ 列出PV时发生异常: {str(e)}")
        return False

if __name__ == "__main__":
    # 接收命令行参数，如果有--delete，则删除指定的PV
    if len(sys.argv) > 1 and sys.argv[1] == "--delete":
        if len(sys.argv) < 3:
            print("请提供要删除的PV名称")
            sys.exit(1)
        pv_name = sys.argv[2]
        do_delete(pv_name)
        exit(0)
        
    if len(sys.argv) > 1 and sys.argv[1] == "--list":
        # 列出所有PV
        list_all_pvs()
        exit(0)
        
    else:
        # 运行静态PV创建测试
        print("开始测试静态PV创建功能...")
        test_static_pv_creation()

