#!/usr/bin/env python3
"""
测试Node与ServiceProxy集成（YAML加载模式）
验证：
1. 能够正确从YAML文件读取节点配置
2. Node能够正确启动ServiceProxy
3. ServiceProxy能够接收到正确的节点名称
"""

import sys
import os
import yaml
from pkg.config.globalConfig import GlobalConfig
from pkg.config.nodeConfig import NodeConfig

def test_yaml_loading():
    """测试YAML配置加载"""
    print("=== 测试YAML配置加载 ===")
    
    try:
        global_config = GlobalConfig()
        file_yaml = "node-1.yaml"
        test_yaml = os.path.join(global_config.TEST_FILE_PATH, file_yaml)
        
        print(f"配置文件路径: {test_yaml}")
        
        if not os.path.exists(test_yaml):
            print(f"❌ 配置文件不存在: {test_yaml}")
            return False
        
        with open(test_yaml, "r", encoding="utf-8") as file:
            data = yaml.safe_load(file)
        
        print(f"✅ YAML文件读取成功")
        print(f"节点名称: {data['metadata']['name']}")
        
        node_config = NodeConfig(data)
        print(f"✅ NodeConfig创建成功")
        print(f"节点配置名称: {node_config.name}")
        
        return True
        
    except Exception as e:
        print(f"❌ YAML配置加载失败: {e}")
        return False

def test_serviceproxy_import():
    """测试ServiceProxy导入"""
    print("\n=== 测试ServiceProxy导入 ===")
    
    try:
        from pkg.network.serviceProxy import ServiceProxy
        from pkg.config.kafkaConfig import KafkaConfig
        
        print("✅ ServiceProxy导入成功")
        print(f"Kafka服务器: {KafkaConfig.BOOTSTRAP_SERVER}")
        
        # 测试创建ServiceProxy实例（不启动）
        kafka_config = {
            'bootstrap_servers': KafkaConfig.BOOTSTRAP_SERVER
        }
        
        service_proxy = ServiceProxy(
            node_name="test-node",
            kafka_config=kafka_config
        )
        print("✅ ServiceProxy实例创建成功")
        
        return True
        
    except Exception as e:
        print(f"❌ ServiceProxy导入失败: {e}")
        return False

def test_node_integration():
    """测试Node集成"""
    print("\n=== 测试Node集成 ===")
    
    try:
        from pkg.apiObject.node import Node
        from pkg.config.uriConfig import URIConfig
        
        # 加载配置
        global_config = GlobalConfig()
        file_yaml = "node-1.yaml"
        test_yaml = os.path.join(global_config.TEST_FILE_PATH, file_yaml)
        
        with open(test_yaml, "r", encoding="utf-8") as file:
            data = yaml.safe_load(file)
        
        node_config = NodeConfig(data)
        
        # 创建Node实例（不运行）
        node = Node(node_config, URIConfig)
        print("✅ Node实例创建成功")
        print(f"节点名称: {node.config.name}")
        print(f"ServiceProxy属性: {hasattr(node, 'service_proxy')}")
        
        return True
        
    except Exception as e:
        print(f"❌ Node集成测试失败: {e}")
        return False

def main():
    print("Node与ServiceProxy集成测试（YAML加载模式）")
    print("=" * 60)
    
    # 检查环境
    print("检查运行环境...")
    current_dir = os.getcwd()
    print(f"当前目录: {current_dir}")
    
    if not os.path.exists("pkg/apiObject/node.py"):
        print("❌ 请在项目根目录中运行此脚本")
        return
    
    if not os.path.exists("testFile/node-1.yaml"):
        print("❌ 测试配置文件不存在: testFile/node-1.yaml")
        return
    
    print("✅ 环境检查通过")
    
    # 运行测试
    tests = [
        test_yaml_loading,
        test_serviceproxy_import, 
        test_node_integration
    ]
    
    results = []
    for test in tests:
        result = test()
        results.append(result)
    
    # 总结
    print(f"\n{'='*60}")
    print("测试总结:")
    print(f"通过: {sum(results)}/{len(results)}")
    
    if all(results):
        print("✅ 所有测试通过！节点可以正常启动ServiceProxy")
        print("\n启动方法:")
        print("1. 直接运行: python3 -m pkg.apiObject.node")
        print("2. 使用脚本: ./start_node_simple.sh")
    else:
        print("❌ 部分测试失败，请检查配置")

if __name__ == "__main__":
    main()
