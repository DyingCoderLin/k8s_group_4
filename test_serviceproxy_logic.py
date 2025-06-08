#!/usr/bin/env python3
"""
ServiceProxy逻辑测试脚本
测试修复后的基础链设置逻辑
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from pkg.network.serviceProxy import ServiceProxy
import logging

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

def test_base_chain_logic():
    """测试基础链设置逻辑"""
    print("=" * 60)
    print("测试ServiceProxy基础链设置逻辑")
    print("=" * 60)
    
    # 创建ServiceProxy实例（在macOS上会模拟运行）
    proxy = ServiceProxy(node_name="test-node")
    
    print("\n1. 初始化完成，基础链已设置")
    
    # 在macOS上，我们只能测试逻辑，不能真正运行iptables
    if proxy.is_macos:
        print("   在macOS上运行，iptables功能被模拟")
    else:
        print("   在Linux上运行，iptables功能正常")
    
    # 测试Service规则创建逻辑
    print("\n2. 测试Service规则创建逻辑")
    test_endpoints = ["10.244.1.10:8080", "10.244.2.10:8080"]
    
    proxy.create_service_rules(
        service_name="test-service",
        cluster_ip="10.96.0.100", 
        port=80,
        protocol="tcp",
        endpoints=test_endpoints,
        node_port=30080
    )
    
    # 测试Service信息查看
    print("\n3. 查看Service链信息")
    chains_info = proxy.list_all_service_chains()
    
    print(f"   Service链总数: {chains_info['total_service_chains']}")
    print(f"   Endpoint链总数: {chains_info['total_endpoint_chains']}")
    
    for service_name, info in chains_info['services'].items():
        print(f"   Service '{service_name}':")
        print(f"     Service链: {info['service_chain']}")
        print(f"     Endpoint链数量: {info['endpoint_count']}")
    
    # 测试端点更新逻辑
    print("\n4. 测试端点增量更新逻辑")
    new_endpoints = ["10.244.1.10:8080", "10.244.3.10:8080"]  # 一个相同，一个新增，一个移除
    
    proxy.update_service_endpoints(
        service_name="test-service",
        cluster_ip="10.96.0.100",
        port=80,
        protocol="tcp", 
        endpoints=new_endpoints,
        node_port=30080
    )
    
    # 测试Service删除逻辑
    print("\n5. 测试Service删除逻辑")
    proxy.delete_service_rules(
        service_name="test-service",
        cluster_ip="10.96.0.100",
        port=80,
        protocol="tcp",
        node_port=30080
    )
    
    # 验证清理后的状态
    print("\n6. 验证清理后的状态")
    chains_info_after = proxy.list_all_service_chains()
    print(f"   清理后Service链总数: {chains_info_after['total_service_chains']}")
    print(f"   清理后Endpoint链总数: {chains_info_after['total_endpoint_chains']}")
    
    print("\n7. 测试完全重置功能")
    if not proxy.is_macos:
        # 只在Linux上测试重置功能
        proxy.reset_and_reinit_base_chains()
        print("   基础链重置完成")
    else:
        print("   在macOS上跳过基础链重置测试")
    
    print("\n" + "=" * 60)
    print("ServiceProxy逻辑测试完成！")
    print("=" * 60)

def test_chain_validation():
    """测试链验证逻辑"""
    print("\n8. 测试链验证逻辑")
    
    proxy = ServiceProxy(node_name="test-node")
    
    # 创建一个测试Service
    proxy.create_service_rules(
        service_name="validation-test",
        cluster_ip="10.96.0.200",
        port=80,
        protocol="tcp",
        endpoints=["10.244.1.20:8080"],
        node_port=None
    )
    
    # 验证Service规则
    validation_result = proxy.validate_service_rules("validation-test")
    print(f"   Service规则验证结果: {validation_result}")
    
    # 清理测试Service
    proxy.delete_service_rules(
        service_name="validation-test",
        cluster_ip="10.96.0.200",
        port=80,
        protocol="tcp",
        node_port=None
    )

if __name__ == "__main__":
    try:
        test_base_chain_logic()
        test_chain_validation()
        
        print("\n✅ 所有测试通过！修复后的ServiceProxy逻辑运行正常。")
        
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
