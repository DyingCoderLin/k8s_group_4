#!/usr/bin/env python3
"""
测试PV/PVC创建和挂载的完整流程
验证路径分配和存储逻辑
"""

import json
import os
import sys

# 添加项目路径到 Python 路径
sys.path.append('/Users/liang/code/cloud_OS/k8s/k8s_group_4')

from pkg.config.pvConfig import PVConfig
from pkg.config.pvcConfig import PVCConfig
from pkg.config.podConfig import PodConfig
from pkg.kubelet.volumeResolver import VolumeResolver
from pkg.apiServer.apiClient import ApiClient
from pkg.config.uriConfig import URIConfig

def test_pv_creation():
    """测试PV创建和路径分配"""
    print("=== 测试PV创建和路径分配 ===")
    
    # 测试hostPath PV
    hostpath_pv_spec = {
        "apiVersion": "v1",
        "kind": "PersistentVolume",
        "metadata": {
            "name": "test-hostpath-pv"
        },
        "spec": {
            "capacity": {
                "storage": "1Gi"
            },
            "hostPath": {
                "path": "/tmp/minik8s-test/hostpath"
            }
        }
    }
    
    pv_config = PVConfig(hostpath_pv_spec)
    print(f"HostPath PV - Name: {pv_config.name}")
    print(f"HostPath PV - Volume Source: {pv_config.volume_source}")
    print(f"HostPath PV - 存储路径: {pv_config.volume_source['path']}")
    print()
    
    # 测试NFS PV
    nfs_pv_spec = {
        "apiVersion": "v1",
        "kind": "PersistentVolume",
        "metadata": {
            "name": "test-nfs-pv"
        },
        "spec": {
            "capacity": {
                "storage": "2Gi"
            },
            "nfs": {
                "server": "10.119.15.190",
                "path": "/exports/test-nfs"
            }
        }
    }
    
    nfs_pv_config = PVConfig(nfs_pv_spec)
    print(f"NFS PV - Name: {nfs_pv_config.name}")
    print(f"NFS PV - Volume Source: {nfs_pv_config.volume_source}")
    print(f"NFS PV - NFS服务器: {nfs_pv_config.volume_source['server']}")
    print(f"NFS PV - NFS路径: {nfs_pv_config.volume_source['path']}")
    print()

def test_pvc_creation():
    """测试PVC创建"""
    print("=== 测试PVC创建 ===")
    
    pvc_spec = {
        "apiVersion": "v1",
        "kind": "PersistentVolumeClaim",
        "metadata": {
            "name": "test-pvc",
            "namespace": "default"
        },
        "spec": {
            "storageClassName": "hostPath",
            "volumeName": "test-hostpath-pv",
            "resources": {
                "requests": {
                    "storage": "1Gi"
                }
            }
        }
    }
    
    pvc_config = PVCConfig(pvc_spec)
    print(f"PVC - Name: {pvc_config.name}")
    print(f"PVC - Namespace: {pvc_config.namespace}")
    print(f"PVC - Storage Class: {pvc_config.storage_class_name}")
    print(f"PVC - Volume Name: {pvc_config.volume_name}")
    print(f"PVC - Storage: {pvc_config.storage}")
    print()

def test_pod_volume_parsing():
    """测试Pod卷配置解析"""
    print("=== 测试Pod卷配置解析 ===")
    
    pod_spec = {
        "apiVersion": "v1",
        "kind": "Pod",
        "metadata": {
            "name": "test-pod",
            "namespace": "default"
        },
        "spec": {
            "volumes": [
                {
                    "name": "storage-volume",
                    "persistentVolumeClaim": {
                        "claimName": "test-pvc"
                    }
                }
            ],
            "containers": [
                {
                    "name": "test-container",
                    "image": "nginx",
                    "volumeMounts": [
                        {
                            "name": "storage-volume",
                            "mountPath": "/data",
                            "readOnly": False
                        }
                    ],
                    "resources": {
                        "requests": {
                            "cpu": 0.1,
                            "memory": 67108864
                        },
                        "limits": {
                            "cpu": 0.2,
                            "memory": 134217728
                        }
                    }
                }
            ]
        }
    }
    
    pod_config = PodConfig(pod_spec)
    print(f"Pod - Name: {pod_config.name}")
    print(f"Pod - Namespace: {pod_config.namespace}")
    print(f"Pod - Volumes: {pod_config.volume}")
    
    # 检查容器配置
    container = pod_config.containers[0]
    print(f"Container - Name: {container.name}")
    print(f"Container - Volumes: {container.volumes}")
    print()

def test_volume_resolution_flow():
    """测试卷解析流程"""
    print("=== 测试卷解析流程 ===")
    
    # 模拟VolumeResolver解析过程
    print("1. Pod配置中的卷:")
    volume_list = [
        {
            'name': 'storage-volume',
            'type': 'pvc',
            'claimName': 'test-pvc'
        }
    ]
    print(f"   Volume list: {volume_list}")
    
    print("\n2. 模拟PVC查询结果:")
    mock_pvc_response = {
        "metadata": {
            "name": "test-pvc",
            "namespace": "default"
        },
        "status": {
            "volumeName": "test-hostpath-pv"
        }
    }
    print(f"   PVC绑定的PV: {mock_pvc_response['status']['volumeName']}")
    
    print("\n3. 模拟PV查询结果:")
    mock_pv_response = {
        "metadata": {
            "name": "test-hostpath-pv"
        },
        "spec": {
            "hostPath": {
                "path": "/tmp/minik8s-test/hostpath"
            }
        }
    }
    print(f"   PV实际路径: {mock_pv_response['spec']['hostPath']['path']}")
    
    print("\n4. 卷挂载映射:")
    volume_mounts = [
        {
            'name': 'storage-volume',
            'mountPath': '/data',
            'readOnly': False
        }
    ]
    resolved_volumes = {'storage-volume': '/tmp/minik8s-test/hostpath'}
    
    print(f"   容器挂载配置: {volume_mounts}")
    print(f"   解析后的卷路径: {resolved_volumes}")
    
    # 模拟生成Docker卷绑定
    for mount in volume_mounts:
        volume_name = mount['name']
        mount_path = mount['mountPath']
        if volume_name in resolved_volumes:
            host_path = resolved_volumes[volume_name]
            mode = 'ro' if mount['readOnly'] else 'rw'
            volume_bind = f"{host_path}:{mount_path}:{mode}"
            print(f"   Docker卷绑定: {volume_bind}")
    print()

def test_nfs_volume_resolution():
    """测试NFS卷解析流程"""
    print("=== 测试NFS卷解析流程 ===")
    
    print("1. NFS PV配置:")
    nfs_pv_spec = {
        "spec": {
            "nfs": {
                "server": "10.119.15.190",
                "path": "/exports/test-nfs"
            }
        }
    }
    
    nfs_spec = nfs_pv_spec['spec']['nfs']
    server = nfs_spec['server']
    path = nfs_spec['path']
    pv_name = "test-nfs-pv"
    
    print(f"   NFS服务器: {server}")
    print(f"   NFS路径: {path}")
    
    print("\n2. 本地挂载点生成:")
    mount_point = f"/tmp/nfs-mounts/{pv_name}"
    print(f"   本地挂载点: {mount_point}")
    
    print("\n3. 挂载命令:")
    mount_cmd = f"sudo mount -t nfs {server}:{path} {mount_point}"
    print(f"   挂载命令: {mount_cmd}")
    
    print("\n4. 容器卷绑定:")
    container_mount_path = "/data"
    volume_bind = f"{mount_point}:{container_mount_path}:rw"
    print(f"   Docker卷绑定: {volume_bind}")
    
    print("\n5. 数据流:")
    print(f"   容器内路径: {container_mount_path}")
    print(f"   → 本地挂载点: {mount_point}")
    print(f"   → NFS存储: {server}:{path}")
    print()

def test_path_allocation_logic():
    """测试路径分配逻辑"""
    print("=== 测试路径分配逻辑 ===")
    
    # 模拟PV Controller的路径分配
    print("1. HostPath动态分配:")
    pvc_namespace = "default"
    pvc_name = "test-pvc"
    hostpath_storage_path = f"/tmp/minik8s-dynamic/{pvc_namespace}/{pvc_name}"
    print(f"   动态HostPath路径: {hostpath_storage_path}")
    
    print("\n2. NFS动态分配:")
    nfs_server = "10.119.15.190"
    nfs_storage_path = f"/exports/dynamic/{pvc_namespace}/{pvc_name}"
    print(f"   NFS服务器: {nfs_server}")
    print(f"   NFS路径: {nfs_storage_path}")
    
    print("\n3. 指定PV名称的路径分配:")
    specific_pv_name = "my-specific-pv"
    specific_hostpath = f"/tmp/minik8s-specific/{pvc_namespace}/{pvc_name}"
    specific_nfs_path = f"/exports/specific/{pvc_namespace}/{pvc_name}"
    print(f"   指定HostPath路径: {specific_hostpath}")
    print(f"   指定NFS路径: {specific_nfs_path}")
    print()

if __name__ == "__main__":
    print("PV/PVC路径分配和挂载流程测试")
    print("=" * 50)
    
    test_pv_creation()
    test_pvc_creation()
    test_pod_volume_parsing()
    test_volume_resolution_flow()
    test_nfs_volume_resolution()
    test_path_allocation_logic()
    
    print("=" * 50)
    print("测试完成")
