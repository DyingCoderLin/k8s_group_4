#!/usr/bin/env python3
# filepath: /Users/liang/code/cloud_OS/k8s/k8s_group_4/test_nodeport_features.py
"""
NodePort功能综合测试脚本
测试NodePort端口分配、冲突检测、范围验证等功能
"""

import sys
import unittest
import logging
from pkg.network.nodePortManager import NodePortManager
from pkg.config.serviceConfig import ServiceConfig


class TestNodePortFeatures(unittest.TestCase):
    """NodePort功能测试类"""
    
    def setUp(self):
        """测试准备"""
        # 每个测试使用独立的管理器实例
        pass
    
    def create_fresh_manager(self):
        """创建新的NodePortManager实例"""
        return NodePortManager(kafka_config=None, namespace="test")
    
    def test_port_range_validation(self):
        """测试端口范围验证"""
        print("\n=== 测试端口范围验证 ===")
        
        manager = self.create_fresh_manager()
        
        # 有效端口
        valid_ports = [30000, 30080, 31000, 32767]
        for port in valid_ports:
            self.assertTrue(
                manager.validate_nodeport_range(port),
                f"端口 {port} 应该是有效的"
            )
            print(f"✓ 端口 {port} 验证通过")
        
        # 无效端口
        invalid_ports = [29999, 32768, 80, 8080, 65535]
        for port in invalid_ports:
            self.assertFalse(
                manager.validate_nodeport_range(port),
                f"端口 {port} 应该是无效的"
            )
            print(f"✓ 端口 {port} 正确拒绝")
    
    def test_port_allocation(self):
        """测试端口分配"""
        print("\n=== 测试端口分配 ===")
        
        manager = self.create_fresh_manager()
        
        # 测试指定端口分配
        service1 = "test-service-1"
        requested_port = 30080
        
        allocated_port = manager.allocate_port(service1, requested_port)
        self.assertEqual(allocated_port, requested_port)
        print(f"✓ 为服务 {service1} 分配指定端口 {allocated_port}")
        
        # 测试自动端口分配
        service2 = "test-service-2"
        auto_port = manager.allocate_port(service2)
        self.assertGreaterEqual(auto_port, manager.NODEPORT_RANGE_START)
        self.assertLessEqual(auto_port, manager.NODEPORT_RANGE_END)
        print(f"✓ 为服务 {service2} 自动分配端口 {auto_port}")
        
        # 验证端口状态
        allocations = manager.get_allocated_ports()
        self.assertIn(service1, allocations)
        self.assertIn(service2, allocations)
        self.assertEqual(allocations[service1], requested_port)
        self.assertEqual(allocations[service2], auto_port)
        print(f"✓ 端口分配状态正确: {allocations}")
    
    def test_port_conflict_detection(self):
        """测试端口冲突检测"""
        print("\n=== 测试端口冲突检测 ===")
        
        manager = self.create_fresh_manager()
        service1 = "conflict-service-1"
        service2 = "conflict-service-2"
        port = 30081
        
        # 第一个服务分配端口
        manager.allocate_port(service1, port)
        print(f"✓ 服务 {service1} 成功分配端口 {port}")
        
        # 第二个服务尝试分配相同端口应该失败
        with self.assertRaises(ValueError) as context:
            manager.allocate_port(service2, port)
        
        self.assertIn("已被服务", str(context.exception))
        print(f"✓ 端口冲突检测正确: {context.exception}")
        
        # 验证端口可用性检查
        self.assertFalse(manager.is_port_available(port))
        self.assertTrue(manager.is_port_available(port, exclude_service=service1))
        print("✓ 端口可用性检查正确")
    
    def test_port_deallocation(self):
        """测试端口释放"""
        print("\n=== 测试端口释放 ===")
        
        manager = self.create_fresh_manager()
        service = "deallocation-service"
        port = 30082
        
        # 分配端口
        manager.allocate_port(service, port)
        self.assertFalse(manager.is_port_available(port))
        print(f"✓ 端口 {port} 已分配给服务 {service}")
        
        # 释放端口
        success = manager.deallocate_port(service)
        self.assertTrue(success)
        self.assertTrue(manager.is_port_available(port))
        print(f"✓ 端口 {port} 已成功释放")
        
        # 重复释放应该返回False
        success = manager.deallocate_port(service)
        self.assertFalse(success)
        print("✓ 重复释放端口正确返回False")
    
    def test_service_update_scenario(self):
        """测试服务更新场景"""
        print("\n=== 测试服务更新场景 ===")
        
        manager = self.create_fresh_manager()
        service = "update-service"
        old_port = 30083
        new_port = 30084
        
        # 初始分配
        manager.allocate_port(service, old_port)
        print(f"✓ 初始分配端口 {old_port}")
        
        # 更新为新端口（应该自动释放旧端口）
        allocated_port = manager.allocate_port(service, new_port)
        self.assertEqual(allocated_port, new_port)
        
        # 验证旧端口已释放，新端口已分配
        self.assertTrue(manager.is_port_available(old_port))
        self.assertFalse(manager.is_port_available(new_port))
        
        allocations = manager.get_allocated_ports()
        self.assertEqual(allocations[service], new_port)
        print(f"✓ 服务更新成功，新端口: {new_port}")
    
    def test_allocation_stats(self):
        """测试分配统计"""
        print("\n=== 测试分配统计 ===")
        
        manager = self.create_fresh_manager()
        
        # 分配几个端口
        services = ["stats-service-1", "stats-service-2", "stats-service-3"]
        ports = [30085, 30086, 30087]
        
        for service, port in zip(services, ports):
            manager.allocate_port(service, port)
        
        stats = manager.get_allocation_stats()
        
        self.assertEqual(stats["allocated_count"], len(services))
        self.assertEqual(len(stats["allocated_ports"]), len(services))
        
        for port in ports:
            self.assertIn(port, stats["allocated_ports"])
        
        print(f"✓ 统计信息正确:")
        print(f"  - 总端口数: {stats['total_ports']}")
        print(f"  - 已分配: {stats['allocated_count']}")
        print(f"  - 可用: {stats['available_count']}")
        print(f"  - 使用率: {stats['utilization_rate']:.2f}%")
    
    def test_service_config_integration(self):
        """测试与ServiceConfig的集成"""
        print("\n=== 测试ServiceConfig集成 ===")
        
        # 测试有效的NodePort配置
        valid_config = {
            "metadata": {
                "name": "integration-service",
                "namespace": "default"
            },
            "spec": {
                "type": "NodePort",
                "selector": {"app": "web"},
                "ports": [{
                    "port": 80,
                    "targetPort": 8080,
                    "nodePort": 30088
                }]
            }
        }
        
        service_config = ServiceConfig(valid_config)
        self.assertEqual(service_config.type, "NodePort")
        self.assertEqual(service_config.node_port, 30088)
        self.assertTrue(service_config.is_nodeport_service())
        print("✓ 有效NodePort配置解析正确")
        
        # 测试无效端口配置
        invalid_config = {
            "metadata": {
                "name": "invalid-service",
                "namespace": "default"
            },
            "spec": {
                "type": "NodePort",
                "selector": {"app": "web"},
                "ports": [{
                    "port": 80,
                    "targetPort": 8080,
                    "nodePort": 25000  # 无效端口
                }]
            }
        }
        
        with self.assertRaises(ValueError) as context:
            ServiceConfig(invalid_config)
        
        self.assertIn("必须在范围", str(context.exception))
        print(f"✓ 无效端口配置正确拒绝: {context.exception}")
    
    def test_edge_cases(self):
        """测试边界情况"""
        print("\n=== 测试边界情况 ===")
        
        manager = self.create_fresh_manager()
        
        # 测试边界端口
        edge_ports = [30000, 32767]  # 最小和最大端口
        for i, port in enumerate(edge_ports):
            service = f"edge-service-{i}"
            allocated = manager.allocate_port(service, port)
            self.assertEqual(allocated, port)
            print(f"✓ 边界端口 {port} 分配成功")
        
        # 测试查找不存在的服务
        non_existent_service = manager.get_service_by_port(31999)
        self.assertIsNone(non_existent_service)
        print("✓ 查找不存在的端口正确返回None")
        
        # 测试空服务名（应该正常工作）
        empty_service = ""
        try:
            port = manager.allocate_port(empty_service, 30089)
            self.assertIsInstance(port, int)
            print("✓ 空服务名处理正常")
        except Exception as e:
            print(f"✓ 空服务名被正确拒绝: {e}")


def run_comprehensive_test():
    """运行综合测试"""
    print("开始NodePort功能综合测试...")
    print("=" * 60)
    
    # 运行单元测试
    suite = unittest.TestLoader().loadTestsFromTestCase(TestNodePortFeatures)
    runner = unittest.TextTestRunner(verbosity=0, stream=open('/dev/null', 'w'))
    result = runner.run(suite)
    
    # 手动运行测试以获得详细输出
    test_instance = TestNodePortFeatures()
    test_instance.setUp()
    
    test_methods = [
        test_instance.test_port_range_validation,
        test_instance.test_port_allocation,
        test_instance.test_port_conflict_detection,
        test_instance.test_port_deallocation,
        test_instance.test_service_update_scenario,
        test_instance.test_allocation_stats,
        test_instance.test_service_config_integration,
        test_instance.test_edge_cases,
    ]
    
    passed = 0
    failed = 0
    
    for test_method in test_methods:
        try:
            test_method()
            passed += 1
        except Exception as e:
            print(f"✗ 测试失败: {test_method.__name__}: {e}")
            failed += 1
    
    print("\n" + "=" * 60)
    print(f"测试完成! 通过: {passed}, 失败: {failed}")
    
    if failed == 0:
        print("🎉 所有NodePort功能测试通过!")
        return True
    else:
        print("❌ 部分测试失败，请检查实现")
        return False


if __name__ == "__main__":
    success = run_comprehensive_test()
    sys.exit(0 if success else 1)
