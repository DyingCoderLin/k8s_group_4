#!/usr/bin/env python3
"""
测试PodConfig的volume处理功能
"""

import sys
import os
import json

# 添加项目根目录到Python路径
sys.path.append('/Users/liang/code/cloud_OS/k8s/k8s_group_4')

from pkg.config.podConfig import PodConfig

def test_volume_parsing():
    """测试volume解析功能"""
    print("="*60)
    print("测试PodConfig的volume处理功能")
    print("="*60)
    
    # 测试数据1：原始格式（列表）
    original_format = {
        "metadata": {
            "name": "test-pod-original",
            "namespace": "default",
            "labels": {"app": "test"}
        },
        "spec": {
            "volumes": [
                {
                    "name": "shared-volume",
                    "hostPath": {
                        "path": "/tmp/k8s-shared-volume",
                        "type": "Directory"
                    }
                }
            ],
            "containers": [
                {
                    "name": "test-container",
                    "image": "ubuntu:latest",
                    "volumeMounts": [
                        {
                            "name": "shared-volume",
                            "mountPath": "/data"
                        }
                    ],
                    "resources": {
                        "requests": {"cpu": 0.5, "memory": 134217728},
                        "limits": {"cpu": 1.0, "memory": 268435456}
                    }
                }
            ]
        }
    }
    
    # 测试数据2：传输格式（字典）- 模拟从Kafka接收的数据
    transmitted_format = {
        "metadata": {
            "name": "ubuntu-simple-writer",
            "namespace": "default",
            "labels": {"app": "ubuntu-simple", "role": "writer"}
        },
        "spec": {
            "volumes": {"shared-volume": "/tmp/k8s-shared-volume"},
            "containers": [
                {
                    "name": "ubuntu-container",
                    "image": "ubuntu:latest",
                    "command": ["sh", "-c"],
                    "args": ["echo 'Hello from writer pod' > /data/writer.txt && sleep 3600"],
                    "resources": {
                        "requests": {"cpu": 0.5, "memory": 134217728},
                        "limits": {"cpu": 1.0, "memory": 268435456}
                    },
                    "volumeMounts": [
                        {
                            "name": "k8s-shared-volume",  # 注意：这里名称不匹配
                            "mountPath": "/data"
                        }
                    ]
                }
            ]
        },
        "cni_name": None,
        "subnet_ip": None,
        "node_name": "node-01",
        "status": "CREATING"
    }
    
    print("\n1. 测试原始格式（列表）的volume处理:")
    print(f"Input volumes: {original_format['spec']['volumes']}")
    try:
        config1 = PodConfig(original_format)
        print(f"✓ 解析成功")
        print(f"  Parsed volumes: {config1.volume}")
        print(f"  Container count: {len(config1.containers)}")
        if config1.containers:
            print(f"  Container volumes: {config1.containers[0].volumes}")
    except Exception as e:
        print(f"✗ 解析失败: {e}")
    
    print("\n2. 测试传输格式（字典）的volume处理:")
    print(f"Input volumes: {transmitted_format['spec']['volumes']}")
    try:
        config2 = PodConfig(transmitted_format)
        print(f"✓ 解析成功")
        print(f"  Parsed volumes: {config2.volume}")
        print(f"  Container count: {len(config2.containers)}")
        if config2.containers:
            print(f"  Container volumes: {config2.containers[0].volumes}")
    except Exception as e:
        print(f"✗ 解析失败: {e}")
    
    print("\n3. 测试to_dict()方法:")
    try:
        result_dict = config2.to_dict()
        print(f"✓ to_dict()成功")
        print(f"  Result: {json.dumps(result_dict, indent=2)}")
    except Exception as e:
        print(f"✗ to_dict()失败: {e}")

if __name__ == "__main__":
    test_volume_parsing()
