#!/usr/bin/env python3
"""
测试 Service 创建修复
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from pkg.network.serviceProxy import ServiceProxy
import logging

# 设置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_service_proxy():
    """测试 ServiceProxy 的规则创建"""
    logger.info("开始测试 ServiceProxy...")
    
    # 创建 ServiceProxy 实例
    proxy = ServiceProxy(node_name="test-node")
    
    # 测试参数
    service_name = "test-service"
    cluster_ip = "10.96.0.100"
    port = 80
    protocol = "TCP"
    endpoints = ["192.168.1.10:8080", "192.168.1.11:8080"]
    node_port = 30080
    
    try:
        # 测试创建服务规则
        logger.info("创建服务规则...")
        proxy.create_service_rules(
            service_name=service_name,
            cluster_ip=cluster_ip,
            port=port,
            protocol=protocol,
            endpoints=endpoints,
            node_port=node_port
        )
        logger.info("服务规则创建成功！")
        
        # 测试删除服务规则
        logger.info("删除服务规则...")
        proxy.delete_service_rules(
            service_name=service_name,
            cluster_ip=cluster_ip,
            port=port,
            protocol=protocol,
            node_port=node_port
        )
        logger.info("服务规则删除成功！")
        
        return True
        
    except Exception as e:
        logger.error(f"测试失败: {e}")
        return False

if __name__ == "__main__":
    success = test_service_proxy()
    if success:
        print("✅ ServiceProxy 修复测试通过！")
        sys.exit(0)
    else:
        print("❌ ServiceProxy 修复测试失败！")
        sys.exit(1)
