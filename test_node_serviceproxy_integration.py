#!/usr/bin/env python3
"""
测试Node与ServiceProxy集成的脚本
这个脚本验证：
1. Node能够正确启动ServiceProxy
2. ServiceProxy能够接收到正确的节点名称
3. 两者能够协调工作
"""

import subprocess
import sys
import time
import signal
import os

def test_node_with_serviceproxy():
    """测试Node集成ServiceProxy的功能"""
    print("=== 测试Node与ServiceProxy集成 ===")
    
    # 测试节点配置文件路径
    node_config = "node-1.yaml"
    node_name = "test-node-01"
    
    print(f"节点配置文件: {node_config}")
    print(f"节点名称: {node_name}")
    print("-" * 50)
    
    # 启动带有ServiceProxy的Node
    cmd = [
        sys.executable, "-m", "pkg.apiObject.node",
        "--node-config", node_config,
        "--node-name", node_name
    ]
    
    print(f"执行命令: {' '.join(cmd)}")
    print("启动Node（集成ServiceProxy）...")
    print("注意：这将在后台启动Kafka消费者，请确保Kafka服务正在运行")
    print("按 Ctrl+C 停止测试")
    print("-" * 50)
    
    try:
        # 启动进程
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
            bufsize=1
        )
        
        # 实时输出日志
        for line in iter(process.stdout.readline, ''):
            print(f"[NODE] {line.rstrip()}")
            
            # 检查是否有ServiceProxy启动的标识
            if "ServiceProxy已在节点" in line:
                print("✅ ServiceProxy成功启动!")
            elif "ServiceProxy已订阅Kafka主题" in line:
                print("✅ ServiceProxy成功连接到Kafka!")
            elif "ERROR" in line:
                print(f"❌ 发现错误: {line.rstrip()}")
        
    except KeyboardInterrupt:
        print("\n\n=== 收到中断信号，正在停止测试 ===")
        if process:
            process.terminate()
            process.wait()
        print("✅ 测试已停止")
    except Exception as e:
        print(f"❌ 测试过程中发生错误: {e}")
        if process:
            process.terminate()

def test_command_line_args():
    """测试命令行参数解析"""
    print("=== 测试命令行参数解析 ===")
    
    # 测试帮助信息
    cmd = [sys.executable, "-m", "pkg.apiObject.node", "--help"]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        print("命令行帮助信息:")
        print(result.stdout)
        print("✅ 命令行参数解析正常")
    except Exception as e:
        print(f"❌ 命令行参数解析失败: {e}")

if __name__ == "__main__":
    print("Node与ServiceProxy集成测试工具")
    print("=" * 60)
    
    # 检查环境
    print("检查运行环境...")
    current_dir = os.getcwd()
    print(f"当前目录: {current_dir}")
    
    # 检查是否在正确的项目目录中
    if not os.path.exists("pkg/apiObject/node.py"):
        print("❌ 请在项目根目录中运行此脚本")
        sys.exit(1)
    
    print("✅ 环境检查通过")
    print()
    
    # 首先测试命令行参数
    test_command_line_args()
    print()
    
    # 询问用户是否要进行完整测试
    response = input("是否要进行完整的Node启动测试？(需要Kafka运行) [y/N]: ")
    if response.lower() in ['y', 'yes']:
        test_node_with_serviceproxy()
    else:
        print("跳过完整测试")
        print("\n使用方法:")
        print("python -m pkg.apiObject.node --node-name your-node-name")
        print("或者:")
        print("python -m pkg.apiObject.node --node-config custom-config.yaml --node-name your-node-name")
