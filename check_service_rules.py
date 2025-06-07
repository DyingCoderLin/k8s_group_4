#!/usr/bin/env python3
"""
检查Service负载均衡规则的脚本
"""

import subprocess
import sys

def check_service_chain_rules():
    """检查KUBE-SVC-HELLO_WORLD_SERVICE链的规则"""
    try:
        print("=== 检查KUBE-SVC-HELLO_WORLD_SERVICE链的规则 ===")
        result = subprocess.run(
            ["iptables", "-t", "nat", "-L", "KUBE-SVC-HELLO_WORLD_SERVICE", "-n", "-v", "--line-numbers"],
            capture_output=True, text=True, check=True
        )
        
        print("Service链规则:")
        print(result.stdout)
        
        # 分析规则
        lines = result.stdout.strip().split('\n')
        rule_count = 0
        for line in lines:
            if line.strip() and not line.startswith('Chain') and not line.startswith('num'):
                rule_count += 1
                print(f"规则 {rule_count}: {line}")
        
        if rule_count == 0:
            print("❌ 警告：Service链中没有负载均衡规则！")
            return False
        else:
            print(f"✅ Service链中有 {rule_count} 条规则")
            return True
            
    except subprocess.CalledProcessError as e:
        print(f"❌ 无法获取Service链规则: {e}")
        return False

def check_endpoint_chains():
    """检查所有KUBE-SEP链"""
    try:
        print("\n=== 检查所有KUBE-SEP端点链 ===")
        
        # 获取所有链
        result = subprocess.run(
            ["iptables", "-t", "nat", "-L", "-n"],
            capture_output=True, text=True, check=True
        )
        
        sep_chains = []
        for line in result.stdout.split('\n'):
            if line.startswith('Chain KUBE-SEP-'):
                chain_name = line.split()[1]
                sep_chains.append(chain_name)
        
        print(f"发现 {len(sep_chains)} 个端点链:")
        
        endpoints = {}
        for chain in sep_chains:
            try:
                chain_result = subprocess.run(
                    ["iptables", "-t", "nat", "-L", chain, "-n"],
                    capture_output=True, text=True, check=True
                )
                
                # 提取DNAT目标
                for line in chain_result.stdout.split('\n'):
                    if 'DNAT' in line and 'to:' in line:
                        parts = line.split()
                        for i, part in enumerate(parts):
                            if part.startswith('to:'):
                                target = part[3:]  # 去掉 'to:' 前缀
                                endpoints[chain] = target
                                print(f"  {chain} -> {target}")
                                break
                        break
            except:
                print(f"  {chain} -> 无法获取规则")
        
        # 统计端点分布
        endpoint_count = {}
        for chain, endpoint in endpoints.items():
            endpoint_count[endpoint] = endpoint_count.get(endpoint, 0) + 1
        
        print(f"\n端点分布统计:")
        for endpoint, count in endpoint_count.items():
            print(f"  {endpoint}: {count} 个链")
            
        return endpoints
        
    except Exception as e:
        print(f"❌ 无法获取端点链信息: {e}")
        return {}

def main():
    print("正在检查hello-world-service的iptables规则...")
    
    # 检查Service链
    service_ok = check_service_chain_rules()
    
    # 检查端点链
    endpoints = check_endpoint_chains()
    
    print("\n=== 诊断结果 ===")
    if not service_ok:
        print("❌ 主要问题：Service链缺少负载均衡规则")
        print("   这会导致流量无法分发到端点")
    
    if len(endpoints) > 3:
        print(f"⚠️  警告：发现 {len(endpoints)} 个端点链，预期只有3个")
        print("   可能存在重复创建的问题")
    
    expected_endpoints = ['10.5.53.6:9090', '10.5.78.2:9090', '10.5.39.2:9090']
    actual_endpoints = set(endpoints.values())
    
    missing = set(expected_endpoints) - actual_endpoints
    extra = actual_endpoints - set(expected_endpoints)
    
    if missing:
        print(f"❌ 缺少端点: {missing}")
    if extra:
        print(f"⚠️  额外端点: {extra}")
    
    if service_ok and len(endpoints) == 3 and not missing and not extra:
        print("✅ 所有规则正常")
    else:
        print("❌ 发现问题，需要修复")

if __name__ == "__main__":
    if sys.platform == "darwin":
        print("在macOS上运行，无法执行iptables命令")
        sys.exit(0)
    
    main()
