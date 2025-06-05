#!/usr/bin/env python3
"""
测试Service iptables规则在多节点间的分发情况
"""

import subprocess
import json
import requests
from pkg.config.globalConfig import GlobalConfig
from pkg.apiServer.apiClient import ApiClient

def check_iptables_rules(service_name=None):
    """检查当前节点的iptables规则"""
    try:
        # 查看所有KUBE-相关的iptables规则
        result = subprocess.run(
            ["iptables", "-t", "nat", "-L", "-n", "-v"],
            capture_output=True, text=True, check=True
        )
        
        print("=== 当前节点的iptables NAT规则 ===")
        lines = result.stdout.split('\n')
        
        kube_rules = []
        for line in lines:
            if 'KUBE-' in line:
                kube_rules.append(line.strip())
        
        if kube_rules:
            print(f"找到 {len(kube_rules)} 条KUBE相关规则:")
            for rule in kube_rules:
                print(f"  {rule}")
        else:
            print("❌ 未找到任何KUBE相关的iptables规则")
            
        # 如果指定了service名称，查找特定Service的规则
        if service_name:
            service_chain = f"KUBE-SVC-{service_name.upper()}"
            service_rules = [rule for rule in kube_rules if service_chain in rule]
            
            print(f"\n=== Service {service_name} 的规则 ===")
            if service_rules:
                for rule in service_rules:
                    print(f"  {rule}")
            else:
                print(f"❌ 未找到Service {service_name} 的iptables规则")
        
        return kube_rules
        
    except subprocess.CalledProcessError as e:
        print(f"❌ 执行iptables命令失败: {e}")
        return []
    except FileNotFoundError:
        print("❌ iptables命令不存在，可能在非Linux系统上运行")
        return []

def check_services_from_api():
    """从API Server获取所有Service信息"""
    try:
        global_config = GlobalConfig()
        api_client = ApiClient(global_config.URI_CONFIG.HOST, global_config.URI_CONFIG.PORT)
        
        # 获取所有Service
        services_url = global_config.URI_CONFIG.GLOBAL_SERVICES_URL
        response = api_client.get(services_url)
        
        print("\n=== API Server中的Service列表 ===")
        if response:
            print(f"找到 {len(response)} 个Service:")
            for service_dict in response:
                service_name = list(service_dict.keys())[0]
                service_info = service_dict[service_name]
                
                print(f"  📋 Service: {service_name}")
                print(f"     ClusterIP: {service_info.get('spec', {}).get('clusterIP', 'N/A')}")
                print(f"     Selector: {service_info.get('spec', {}).get('selector', {})}")
                
                # 检查这个Service是否有对应的iptables规则
                check_iptables_rules(service_name)
        else:
            print("❌ 未找到任何Service")
            
        return response
        
    except Exception as e:
        print(f"❌ 获取Service列表失败: {e}")
        return []

def check_pods_distribution():
    """检查Pod在各节点的分布情况"""
    try:
        global_config = GlobalConfig()
        api_client = ApiClient(global_config.URI_CONFIG.HOST, global_config.URI_CONFIG.PORT)
        
        # 获取所有Pod
        pods_url = global_config.URI_CONFIG.GLOBAL_PODS_URL
        response = api_client.get(pods_url)
        
        print("\n=== Pod分布情况 ===")
        if response:
            node_pods = {}
            for pod_dict in response:
                pod_name = list(pod_dict.keys())[0]
                pod_info = pod_dict[pod_name]
                
                node_name = pod_info.get('node_name', 'unknown')
                if node_name not in node_pods:
                    node_pods[node_name] = []
                node_pods[node_name].append(pod_name)
            
            for node, pods in node_pods.items():
                print(f"  🖥️  节点 {node}: {len(pods)} 个Pod")
                for pod in pods:
                    print(f"     - {pod}")
        else:
            print("❌ 未找到任何Pod")
            
    except Exception as e:
        print(f"❌ 获取Pod分布失败: {e}")

def main():
    """主函数"""
    print("🔍 Service iptables规则分发情况检查")
    print("=" * 50)
    
    # 1. 检查当前节点的iptables规则
    iptables_rules = check_iptables_rules()
    
    # 2. 检查API Server中的Service
    services = check_services_from_api()
    
    # 3. 检查Pod分布
    check_pods_distribution()
    
    # 4. 分析结果
    print("\n=== 分析结果 ===")
    if iptables_rules and services:
        print("✅ 当前节点有Service相关的iptables规则")
        print("💡 这表明ServiceController在此节点运行")
    elif services and not iptables_rules:
        print("⚠️  API Server中有Service，但当前节点没有对应的iptables规则")
        print("💡 这表明当前节点可能无法处理Service流量")
    elif not services:
        print("ℹ️  系统中暂无Service")
    
    print("\n📝 建议:")
    print("1. 如果是多节点环境，需要在每个节点运行ServiceController或实现规则分发")
    print("2. 可以通过 'iptables -t nat -L KUBE-SERVICES -n' 检查Service规则")
    print("3. 确保所有节点都能访问etcd和接收Service更新")

if __name__ == "__main__":
    main()
