#!/usr/bin/env python3
# filepath: /Users/liang/code/cloud_OS/k8s/k8s_group_4/nodeport_cli.py
"""
NodePort管理命令行工具
用于查看、分配和管理NodePort端口
"""

import sys
import argparse
import json
import logging
from typing import Optional
from pkg.network.nodePortManager import NodePortManager
from pkg.config.kafkaConfig import KafkaConfig


def setup_logging(verbose: bool = False):
    """设置日志"""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[logging.StreamHandler(sys.stdout)]
    )


def create_nodeport_manager(kafka_server: Optional[str] = None) -> NodePortManager:
    """创建NodePort管理器"""
    kafka_config = None
    if kafka_server:
        kafka_config = {
            'bootstrap_servers': kafka_server
        }
    
    return NodePortManager(kafka_config=kafka_config, namespace="default")


def cmd_stats(args):
    """显示NodePort统计信息"""
    manager = create_nodeport_manager(args.kafka_server)
    stats = manager.get_allocation_stats()
    
    print("=== NodePort端口分配统计 ===")
    print(f"端口范围: {stats['port_range']}")
    print(f"总端口数: {stats['total_ports']}")
    print(f"已分配: {stats['allocated_count']}")
    print(f"可用: {stats['available_count']}")
    print(f"使用率: {stats['utilization_rate']:.2f}%")
    
    if stats['allocated_ports']:
        print(f"\n已分配端口: {', '.join(map(str, stats['allocated_ports']))}")
        
        print("\n端口分配详情:")
        for service_name, port in stats['allocations'].items():
            print(f"  {service_name}: {port}")
    else:
        print("\n当前没有已分配的端口")


def cmd_allocate(args):
    """分配NodePort端口"""
    manager = create_nodeport_manager(args.kafka_server)
    
    try:
        allocated_port = manager.allocate_port(args.service_name, args.port)
        print(f"成功为服务 '{args.service_name}' 分配NodePort端口: {allocated_port}")
    except ValueError as e:
        print(f"分配失败: {e}")
        sys.exit(1)


def cmd_deallocate(args):
    """释放NodePort端口"""
    manager = create_nodeport_manager(args.kafka_server)
    
    if manager.deallocate_port(args.service_name):
        print(f"成功释放服务 '{args.service_name}' 的NodePort端口")
    else:
        print(f"服务 '{args.service_name}' 没有分配的NodePort端口")


def cmd_validate(args):
    """验证端口是否可用"""
    manager = create_nodeport_manager(args.kafka_server)
    
    # 验证端口范围
    if not manager.validate_nodeport_range(args.port):
        print(f"端口 {args.port} 不在有效范围内 ({NodePortManager.NODEPORT_RANGE_START}-{NodePortManager.NODEPORT_RANGE_END})")
        sys.exit(1)
    
    # 检查端口可用性
    if manager.is_port_available(args.port, args.exclude_service):
        print(f"端口 {args.port} 可用")
    else:
        allocated_service = manager.get_service_by_port(args.port)
        print(f"端口 {args.port} 已被服务 '{allocated_service}' 占用")
        sys.exit(1)


def cmd_list(args):
    """列出所有分配的端口"""
    manager = create_nodeport_manager(args.kafka_server)
    allocations = manager.get_allocated_ports()
    
    if not allocations:
        print("当前没有已分配的NodePort端口")
        return
    
    print("=== NodePort端口分配列表 ===")
    print(f"{'服务名':<30} {'端口':<8}")
    print("-" * 40)
    
    for service_name, port in sorted(allocations.items()):
        print(f"{service_name:<30} {port:<8}")


def cmd_find_service(args):
    """根据端口查找服务"""
    manager = create_nodeport_manager(args.kafka_server)
    service_name = manager.get_service_by_port(args.port)
    
    if service_name:
        print(f"端口 {args.port} 被服务 '{service_name}' 占用")
    else:
        print(f"端口 {args.port} 未被分配")


def cmd_daemon(args):
    """启动NodePort管理器守护进程"""
    print(f"启动NodePort管理器守护进程...")
    print(f"Kafka服务器: {args.kafka_server}")
    print(f"命名空间: default")
    
    manager = create_nodeport_manager(args.kafka_server)
    manager.start_daemon()
    
    print("NodePort管理器守护进程已启动，按 Ctrl+C 退出")
    
    try:
        import time
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n正在停止NodePort管理器守护进程...")
        manager.stop_daemon()
        print("NodePort管理器守护进程已停止")


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='NodePort端口管理命令行工具')
    parser.add_argument('--kafka-server', help='Kafka服务器地址', default='10.119.15.182:9092')
    parser.add_argument('--verbose', '-v', action='store_true', help='详细输出')
    
    subparsers = parser.add_subparsers(dest='command', help='可用命令')
    
    # stats命令
    stats_parser = subparsers.add_parser('stats', help='显示NodePort统计信息')
    
    # allocate命令
    allocate_parser = subparsers.add_parser('allocate', help='分配NodePort端口')
    allocate_parser.add_argument('service_name', help='服务名称')
    allocate_parser.add_argument('--port', type=int, help='指定端口（可选，不指定则自动分配）')
    
    # deallocate命令
    deallocate_parser = subparsers.add_parser('deallocate', help='释放NodePort端口')
    deallocate_parser.add_argument('service_name', help='服务名称')
    
    # validate命令
    validate_parser = subparsers.add_parser('validate', help='验证端口是否可用')
    validate_parser.add_argument('port', type=int, help='要验证的端口')
    validate_parser.add_argument('--exclude-service', help='排除的服务名（用于更新场景）')
    
    # list命令
    list_parser = subparsers.add_parser('list', help='列出所有分配的端口')
    
    # find-service命令
    find_parser = subparsers.add_parser('find-service', help='根据端口查找服务')
    find_parser.add_argument('port', type=int, help='端口号')
    
    # daemon命令
    daemon_parser = subparsers.add_parser('daemon', help='启动NodePort管理器守护进程')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    setup_logging(args.verbose)
    
    # 执行对应的命令
    command_handlers = {
        'stats': cmd_stats,
        'allocate': cmd_allocate,
        'deallocate': cmd_deallocate,
        'validate': cmd_validate,
        'list': cmd_list,
        'find-service': cmd_find_service,
        'daemon': cmd_daemon,
    }
    
    handler = command_handlers.get(args.command)
    if handler:
        try:
            handler(args)
        except Exception as e:
            print(f"命令执行失败: {e}")
            if args.verbose:
                import traceback
                traceback.print_exc()
            sys.exit(1)
    else:
        print(f"未知命令: {args.command}")
        sys.exit(1)


if __name__ == "__main__":
    main()
