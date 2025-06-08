#!/usr/bin/env python3
"""
Pod Volume Mount Test Script
测试Pod volume挂载功能的脚本
"""

import os
import time
import subprocess
import sys
import json
from pathlib import Path

def run_command(cmd, description=""):
    """运行shell命令并返回结果"""
    print(f"\n{'='*60}")
    print(f"执行: {description}")
    print(f"命令: {cmd}")
    print(f"{'='*60}")
    
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
        if result.stdout:
            print("输出:")
            print(result.stdout)
        if result.stderr:
            print("错误:")
            print(result.stderr)
        return result.returncode == 0, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        print("命令执行超时!")
        return False, "", "Timeout"
    except Exception as e:
        print(f"命令执行异常: {e}")
        return False, "", str(e)

def check_volume_directory():
    """检查volume挂载目录"""
    volume_path = "/tmp/minik8s-volume-test"
    print(f"\n检查volume目录: {volume_path}")
    
    if os.path.exists(volume_path):
        print(f"✓ Volume目录已存在: {volume_path}")
        files = os.listdir(volume_path)
        if files:
            print(f"目录中的文件: {files}")
            for file in files:
                file_path = os.path.join(volume_path, file)
                if os.path.isfile(file_path):
                    try:
                        with open(file_path, 'r') as f:
                            content = f.read()
                            print(f"\n文件 {file} 内容:")
                            print(content[:500] + "..." if len(content) > 500 else content)
                    except Exception as e:
                        print(f"读取文件 {file} 失败: {e}")
        else:
            print("目录为空")
    else:
        print(f"✗ Volume目录不存在: {volume_path}")
        print("创建volume目录...")
        os.makedirs(volume_path, exist_ok=True)
        print(f"✓ 已创建volume目录: {volume_path}")

def test_pod_creation():
    """测试Pod创建"""
    print("\n" + "="*80)
    print("开始测试Pod Volume挂载功能")
    print("="*80)
    
    # 检查volume目录
    check_volume_directory()
    
    # 获取当前脚本目录
    script_dir = Path(__file__).parent
    
    # Pod配置文件路径
    pod1_file = script_dir / "testFile" / "test-pod-volume-pod1.yaml"
    pod2_file = script_dir / "testFile" / "test-pod-volume-pod2.yaml"
    
    # 检查文件是否存在
    if not pod1_file.exists():
        print(f"✗ Pod1配置文件不存在: {pod1_file}")
        return False
    if not pod2_file.exists():
        print(f"✗ Pod2配置文件不存在: {pod2_file}")
        return False
    
    print(f"✓ 找到Pod配置文件:")
    print(f"  Pod1: {pod1_file}")
    print(f"  Pod2: {pod2_file}")
    
    # 清理可能存在的旧Pod
    print("\n清理旧的Pod...")
    run_command("python3 master.py delete pod ubuntu-volume-pod1 2>/dev/null || true", "删除Pod1")
    run_command("python3 master.py delete pod ubuntu-volume-pod2 2>/dev/null || true", "删除Pod2")
    time.sleep(5)
    
    # 创建Pod1
    success1, _, _ = run_command(f"python3 master.py create -f {pod1_file}", "创建Pod1 (ubuntu-volume-pod1)")
    if not success1:
        print("✗ Pod1创建失败!")
        return False
    
    # 等待一段时间再创建Pod2
    print("\n等待10秒后创建Pod2...")
    time.sleep(10)
    
    # 创建Pod2
    success2, _, _ = run_command(f"python3 master.py create -f {pod2_file}", "创建Pod2 (ubuntu-volume-pod2)")
    if not success2:
        print("✗ Pod2创建失败!")
        return False
    
    print("\n✓ 两个Pod都已创建成功!")
    return True

def monitor_pods():
    """监控Pod状态和volume内容"""
    print("\n" + "="*80)
    print("监控Pod状态和Volume内容")
    print("="*80)
    
    for i in range(10):  # 监控10次，每次间隔30秒
        print(f"\n{'='*40} 第{i+1}次检查 {'='*40}")
        
        # 检查Pod状态
        run_command("python3 master.py get pods", "获取Pod状态")
        
        # 检查volume目录内容
        check_volume_directory()
        
        if i < 9:  # 最后一次不需要等待
            print(f"\n等待30秒后进行下一次检查...")
            time.sleep(30)

def cleanup_test():
    """清理测试资源"""
    print("\n" + "="*80)
    print("清理测试资源")
    print("="*80)
    
    # 删除Pod
    run_command("python3 master.py delete pod ubuntu-volume-pod1", "删除Pod1")
    run_command("python3 master.py delete pod ubuntu-volume-pod2", "删除Pod2")
    
    # 询问是否删除volume目录
    volume_path = "/tmp/minik8s-volume-test"
    if os.path.exists(volume_path):
        response = input(f"\n是否删除volume目录 {volume_path}? (y/N): ")
        if response.lower() == 'y':
            try:
                import shutil
                shutil.rmtree(volume_path)
                print(f"✓ 已删除volume目录: {volume_path}")
            except Exception as e:
                print(f"✗ 删除volume目录失败: {e}")
        else:
            print(f"保留volume目录: {volume_path}")

def main():
    """主函数"""
    if len(sys.argv) > 1:
        action = sys.argv[1]
        if action == "create":
            test_pod_creation()
        elif action == "monitor":
            monitor_pods()
        elif action == "cleanup":
            cleanup_test()
        elif action == "check":
            check_volume_directory()
        else:
            print(f"未知操作: {action}")
            print("支持的操作: create, monitor, cleanup, check")
    else:
        # 完整测试流程
        print("开始完整的Pod Volume挂载测试流程...")
        
        # 1. 创建Pod
        if test_pod_creation():
            # 2. 监控Pod和volume
            monitor_pods()
            
            # 3. 询问是否清理
            response = input("\n测试完成，是否清理资源? (Y/n): ")
            if response.lower() != 'n':
                cleanup_test()
        else:
            print("✗ Pod创建失败，测试终止")

if __name__ == "__main__":
    main()
