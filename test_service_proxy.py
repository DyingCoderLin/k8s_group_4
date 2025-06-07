#!/usr/bin/env python3
"""
测试更新后的ServiceProxy功能
"""

import sys
import os
import json
import logging
import time

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from pkg.network.serviceProxy import ServiceProxy

def setup_logging():
    """设置日志"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

def test_service_proxy_initialization():
    """测试ServiceProxy初始化"""
    print("=" * 50)
    print("测试ServiceProxy初始化")
    print("=" * 50)
    
    # 不带Kafka配置的初始化
    proxy1 = ServiceProxy(node_name="test-node-1")
    print(f"✓ ServiceProxy初始化成功，节点名: {proxy1.node_name}")
    print(f"✓ 是否为macOS: {proxy1.is_macos}")
    print(f"✓ iptables可用: {proxy1.iptables_available}")
    
    # 带Kafka配置的初始化（模拟）
    kafka_config = {
        'bootstrap_servers': 'localhost:9092'
    }
    proxy2 = ServiceProxy(node_name="test-node-2", kafka_config=kafka_config)
    print(f"✓ 带Kafka配置的ServiceProxy初始化成功")
    
    return proxy1

def test_service_creation(proxy):
    """测试Service创建"""
    print("\n" + "=" * 50)
    print("测试Service创建")
    print("=" * 50)
    
    # 测试ClusterIP Service
    service_name = "test-hello-world"
    cluster_ip = "10.96.224.38"
    port = 80
    protocol = "tcp"
    endpoints = ["10.5.53.7:9090", "10.5.53.8:9090"]
    
    print(f"创建Service: {service_name}")
    print(f"ClusterIP: {cluster_ip}:{port}")
    print(f"端点: {endpoints}")
    
    try:
        proxy.create_service_rules(
            service_name=service_name,
            cluster_ip=cluster_ip,
            port=port,
            protocol=protocol,
            endpoints=endpoints
        )
        print("✓ ClusterIP Service创建成功")
    except Exception as e:
        print(f"✗ ClusterIP Service创建失败: {e}")
    
    # 测试NodePort Service
    nodeport_service = "test-nodeport-service"
    node_port = 30080
    
    print(f"\n创建NodePort Service: {nodeport_service}")
    print(f"NodePort: {node_port}")
    
    try:
        proxy.create_service_rules(
            service_name=nodeport_service,
            cluster_ip="10.96.224.39",
            port=80,
            protocol=protocol,
            endpoints=endpoints,
            node_port=node_port
        )
        print("✓ NodePort Service创建成功")
    except Exception as e:
        print(f"✗ NodePort Service创建失败: {e}")

def test_service_stats(proxy):
    """测试Service统计信息"""
    print("\n" + "=" * 50)
    print("测试Service统计信息")
    print("=" * 50)
    
    service_names = ["test-hello-world", "test-nodeport-service"]
    
    for service_name in service_names:
        try:
            stats = proxy.get_service_stats(service_name)
            print(f"✓ Service {service_name} 统计信息:")
            print(f"  服务链: {stats.get('service_chain', 'N/A')}")
            print(f"  端点链数量: {len(stats.get('endpoint_chains', []))}")
            print(f"  总包数: {stats.get('total_packets', 0)}")
            print(f"  总字节数: {stats.get('total_bytes', 0)}")
        except Exception as e:
            print(f"✗ 获取Service {service_name} 统计信息失败: {e}")

def test_service_validation(proxy):
    """测试Service规则验证"""
    print("\n" + "=" * 50)
    print("测试Service规则验证")
    print("=" * 50)
    
    service_names = ["test-hello-world", "test-nodeport-service"]
    
    for service_name in service_names:
        try:
            validation = proxy.validate_service_rules(service_name)
            print(f"✓ Service {service_name} 验证结果:")
            for key, value in validation.items():
                status = "✓" if value else "✗"
                print(f"  {status} {key}: {value}")
        except Exception as e:
            print(f"✗ 验证Service {service_name} 失败: {e}")

def test_chain_management(proxy):
    """测试链管理功能"""
    print("\n" + "=" * 50)
    print("测试链管理功能")
    print("=" * 50)
    
    # 列出所有Service链
    try:
        chains_info = proxy.list_all_service_chains()
        print("✓ Service链信息:")
        print(f"  Service链总数: {chains_info['total_service_chains']}")
        print(f"  Endpoint链总数: {chains_info['total_endpoint_chains']}")
        
        for service_name, info in chains_info['services'].items():
            print(f"  Service {service_name}:")
            print(f"    服务链: {info['service_chain']}")
            print(f"    端点链数量: {info['endpoint_count']}")
    except Exception as e:
        print(f"✗ 获取链信息失败: {e}")
    
    # 获取所有Kubernetes链
    try:
        kube_chains = proxy.get_all_kubernetes_chains()
        print(f"✓ 发现 {len(kube_chains)} 个Kubernetes链:")
        for chain in kube_chains:
            print(f"  - {chain}")
    except Exception as e:
        print(f"✗ 获取Kubernetes链失败: {e}")

def test_endpoint_update(proxy):
    """测试端点更新"""
    print("\n" + "=" * 50)
    print("测试端点更新")
    print("=" * 50)
    
    service_name = "test-hello-world"
    cluster_ip = "10.96.224.38"
    port = 80
    protocol = "tcp"
    
    # 更新端点列表
    new_endpoints = ["10.5.53.7:9090", "10.5.53.9:9090", "10.5.53.10:9090"]
    
    print(f"更新Service {service_name} 的端点")
    print(f"新端点: {new_endpoints}")
    
    try:
        proxy.update_service_endpoints(
            service_name=service_name,
            cluster_ip=cluster_ip,
            port=port,
            protocol=protocol,
            endpoints=new_endpoints
        )
        print("✓ 端点更新成功")
    except Exception as e:
        print(f"✗ 端点更新失败: {e}")

def test_service_cleanup(proxy):
    """测试Service清理"""
    print("\n" + "=" * 50)
    print("测试Service清理")
    print("=" * 50)
    
    service_names = ["test-hello-world", "test-nodeport-service"]
    
    for service_name in service_names:
        try:
            proxy.delete_service_rules(
                service_name=service_name,
                cluster_ip="10.96.224.38",
                port=80,
                protocol="tcp",
                node_port=30080 if "nodeport" in service_name else None
            )
            print(f"✓ Service {service_name} 删除成功")
        except Exception as e:
            print(f"✗ 删除Service {service_name} 失败: {e}")
    
    # 清理所有规则
    try:
        proxy.cleanup_all_rules()
        print("✓ 清理所有规则成功")
    except Exception as e:
        print(f"✗ 清理所有规则失败: {e}")

def main():
    """主测试函数"""
    setup_logging()
    
    print("开始测试更新后的ServiceProxy功能")
    print("注意：在macOS上，iptables操作将被模拟")
    
    try:
        # 初始化ServiceProxy
        proxy = test_service_proxy_initialization()
        
        # 测试Service创建
        test_service_creation(proxy)
        
        # 测试统计信息
        test_service_stats(proxy)
        
        # 测试规则验证
        test_service_validation(proxy)
        
        # 测试链管理
        test_chain_management(proxy)
        
        # 测试端点更新
        test_endpoint_update(proxy)
        
        # 测试清理
        test_service_cleanup(proxy)
        
        print("\n" + "=" * 50)
        print("所有测试完成！")
        print("=" * 50)
        
    except Exception as e:
        print(f"测试过程中出现异常: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
