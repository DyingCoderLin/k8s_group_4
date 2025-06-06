#!/usr/bin/env python3
"""
kubectl - Kubernetes 命令行工具
支持 Node、Pod、Service、ReplicaSet、HPA 的管理操作
"""

import argparse
import json
import sys
import yaml
from typing import Dict, List, Optional, Any
from datetime import datetime

# 导入项目依赖
from pkg.config.uriConfig import URIConfig
from pkg.apiServer.apiClient import ApiClient
from pkg.apiObject.pod import Pod
from pkg.apiObject.service import Service
from pkg.apiObject.replicaSet import ReplicaSet
from pkg.apiObject.hpa import HorizontalPodAutoscaler
from pkg.config.podConfig import PodConfig
from pkg.config.serviceConfig import ServiceConfig
from pkg.config.replicaSetConfig import ReplicaSetConfig
from pkg.config.hpaConfig import HorizontalPodAutoscalerConfig


class KubectlClient:
    """kubectl 客户端主类"""
    
    def __init__(self):
        """初始化 kubectl 客户端"""
        self.uri_config = URIConfig()
        self.api_client = ApiClient(self.uri_config.HOST, self.uri_config.PORT)
        self.default_namespace = "default"
        
    def format_table_output(self, headers: List[str], rows: List[List[str]]) -> str:
        """格式化表格输出"""
        if not rows:
            return f"No resources found in {self.default_namespace} namespace."
        
        # 计算每列的最大宽度
        col_widths = [len(header) for header in headers]
        for row in rows:
            for i, cell in enumerate(row):
                if i < len(col_widths):
                    col_widths[i] = max(col_widths[i], len(str(cell)))
        
        # 构建表格
        output_lines = []
        
        # 表头
        header_line = "  ".join(header.ljust(col_widths[i]) for i, header in enumerate(headers))
        output_lines.append(header_line)
        
        # 数据行
        for row in rows:
            row_line = "  ".join(str(cell).ljust(col_widths[i]) for i, cell in enumerate(row))
            output_lines.append(row_line)
        
        return "\n".join(output_lines)
    
    def format_age(self, creation_time: str) -> str:
        """格式化资源年龄"""
        try:
            if not creation_time:
                return "<unknown>"
                
            # 尝试解析时间戳
            if isinstance(creation_time, str):
                try:
                    create_dt = datetime.fromisoformat(creation_time.replace('Z', '+00:00'))
                except ValueError:
                    # 尝试其他格式
                    create_dt = datetime.strptime(creation_time, "%Y-%m-%d %H:%M:%S")
            else:
                return "<unknown>"
                
            now = datetime.now(create_dt.tzinfo) if create_dt.tzinfo else datetime.now()
            delta = now - create_dt
            
            days = delta.days
            hours, remainder = divmod(delta.seconds, 3600)
            minutes, seconds = divmod(remainder, 60)
            
            if days > 0:
                return f"{days}d"
            elif hours > 0:
                return f"{hours}h"
            elif minutes > 0:
                return f"{minutes}m"
            else:
                return f"{seconds}s"
        except Exception:
            return "<unknown>"

    # ============= Node 相关操作 =============
    
    def get_nodes(self) -> None:
        """获取所有 Node 信息"""
        try:
            response = self.api_client.get(self.uri_config.NODES_URL)
            if not response:
                print("No nodes found.")
                return
            
            headers = ["NAME", "STATUS", "ROLES", "AGE", "VERSION"]
            rows = []
            
            for node_entry in response:
                if isinstance(node_entry, dict) and len(node_entry) == 1:
                    node_name = list(node_entry.keys())[0]
                    node_data = node_entry[node_name]
                    
                    # 提取节点信息
                    status = node_data.get("status", "Unknown")
                    roles = node_data.get("roles", ["<none>"])
                    if isinstance(roles, list):
                        roles_str = ",".join(roles) if roles else "<none>"
                    else:
                        roles_str = str(roles)
                    
                    age = self.format_age(node_data.get("creation_time", ""))
                    version = node_data.get("version", "Unknown")
                    
                    rows.append([node_name, status, roles_str, age, version])
            
            print(self.format_table_output(headers, rows))
            
        except Exception as e:
            print(f"Error getting nodes: {e}")

    def describe_node(self, node_name: str) -> None:
        """描述特定 Node 的详细信息"""
        try:
            path = self.uri_config.NODE_SPEC_URL.format(name=node_name)
            response = self.api_client.get(path)
            
            if not response:
                print(f"Node '{node_name}' not found")
                return
            
            print(f"Name:                 {response.get('name', 'Unknown')}")
            print(f"Roles:                {','.join(response.get('roles', ['<none>']))}")
            print(f"Labels:               {response.get('labels', {})}")
            print(f"Annotations:          {response.get('annotations', {})}")
            print(f"CreationTimestamp:    {response.get('creation_time', 'Unknown')}")
            print(f"Taints:               {response.get('taints', '<none>')}")
            print("")
            print("Conditions:")
            conditions = response.get("conditions", [])
            if conditions:
                for condition in conditions:
                    print(f"  Type:    {condition.get('type', 'Unknown')}")
                    print(f"  Status:  {condition.get('status', 'Unknown')}")
                    print(f"  Reason:  {condition.get('reason', 'Unknown')}")
                    print(f"  Message: {condition.get('message', 'Unknown')}")
                    print("")
            else:
                print("  <none>")
            
            print("Addresses:")
            addresses = response.get("addresses", [])
            if addresses:
                for addr in addresses:
                    print(f"  {addr.get('type', 'Unknown')}: {addr.get('address', 'Unknown')}")
            else:
                print("  <none>")
            
            print("")
            print("System Info:")
            system_info = response.get("system_info", {})
            for key, value in system_info.items():
                print(f"  {key}: {value}")
            
        except Exception as e:
            print(f"Error describing node '{node_name}': {e}")

    # ============= Pod 相关操作 =============
    
    def get_pods(self, namespace: str = None, all_namespaces: bool = False) -> None:
        """获取 Pod 列表"""
        try:
            if all_namespaces:
                response = self.api_client.get(self.uri_config.GLOBAL_PODS_URL)
            else:
                ns = namespace or self.default_namespace
                path = self.uri_config.PODS_URL.format(namespace=ns)
                response = self.api_client.get(path)
            
            if not response:
                ns_info = "all namespaces" if all_namespaces else (namespace or self.default_namespace)
                print(f"No pods found in {ns_info}.")
                return
            
            headers = ["NAME", "READY", "STATUS", "RESTARTS", "AGE"]
            if all_namespaces:
                headers.insert(1, "NAMESPACE")
            
            rows = []
            
            for pod_entry in response:
                if isinstance(pod_entry, dict) and len(pod_entry) == 1:
                    pod_name = list(pod_entry.keys())[0]
                    pod_data = pod_entry[pod_name]
                    
                    # 提取 Pod 信息
                    ready_containers = pod_data.get("ready_containers", 0)
                    total_containers = len(pod_data.get("spec", {}).get("containers", []))
                    ready = f"{ready_containers}/{total_containers}"
                    
                    status = pod_data.get("status", "Unknown")
                    restarts = pod_data.get("restart_count", 0)
                    age = self.format_age(pod_data.get("creation_time", ""))
                    
                    if all_namespaces:
                        pod_namespace = pod_data.get("namespace", "Unknown")
                        rows.append([pod_name, pod_namespace, ready, status, str(restarts), age])
                    else:
                        rows.append([pod_name, ready, status, str(restarts), age])
            
            print(self.format_table_output(headers, rows))
            
        except Exception as e:
            print(f"Error getting pods: {e}")

    def describe_pod(self, pod_name: str, namespace: str = None) -> None:
        """描述特定 Pod 的详细信息"""
        try:
            ns = namespace or self.default_namespace
            path = self.uri_config.POD_SPEC_URL.format(namespace=ns, name=pod_name)
            response = self.api_client.get(path)
            
            if not response:
                print(f"Pod '{pod_name}' not found in namespace '{ns}'")
                return
            
            print(f"Name:         {response.get('metadata', {}).get('name', 'Unknown')}")
            print(f"Namespace:    {response.get('metadata', {}).get('namespace', 'Unknown')}")
            print(f"Priority:     {response.get('spec', {}).get('priority', 0)}")
            print(f"Node:         {response.get('spec', {}).get('node_name', '<none>')}")
            print(f"Start Time:   {response.get('status', {}).get('start_time', '<unknown>')}")
            print(f"Labels:       {response.get('metadata', {}).get('labels', {})}")
            print(f"Annotations:  {response.get('metadata', {}).get('annotations', {})}")
            print(f"Status:       {response.get('status', {}).get('phase', 'Unknown')}")
            print(f"IP:           {response.get('status', {}).get('pod_ip', '<none>')}")
            print("")
            
            # 容器信息
            print("Containers:")
            containers = response.get("spec", {}).get("containers", [])
            for container in containers:
                print(f"  {container.get('name', 'Unknown')}:")
                print(f"    Container ID:  {container.get('container_id', '<none>')}")
                print(f"    Image:         {container.get('image', 'Unknown')}")
                print(f"    Image ID:      {container.get('image_id', '<none>')}")
                print(f"    Port:          {container.get('ports', [])}")
                print(f"    State:         {container.get('state', 'Unknown')}")
                print(f"    Ready:         {container.get('ready', False)}")
                print(f"    Restart Count: {container.get('restart_count', 0)}")
                print("")
            
            # 条件信息
            print("Conditions:")
            conditions = response.get("status", {}).get("conditions", [])
            if conditions:
                for condition in conditions:
                    print(f"  Type:               {condition.get('type', 'Unknown')}")
                    print(f"  Status:             {condition.get('status', 'Unknown')}")
                    print(f"  Last Probe Time:    {condition.get('last_probe_time', '<unknown>')}")
                    print(f"  Last Transition Time: {condition.get('last_transition_time', '<unknown>')}")
                    print("")
            else:
                print("  <none>")
            
        except Exception as e:
            print(f"Error describing pod '{pod_name}': {e}")

    def create_pod_from_file(self, filename: str) -> None:
        """从文件创建 Pod"""
        try:
            with open(filename, 'r') as f:
                if filename.endswith('.yaml') or filename.endswith('.yml'):
                    pod_data = yaml.safe_load(f)
                else:
                    pod_data = json.load(f)
            
            # 验证 Pod 数据
            if pod_data.get("kind") != "Pod":
                print(f"Error: File does not contain a Pod resource")
                return
            
            metadata = pod_data.get("metadata", {})
            name = metadata.get("name")
            namespace = metadata.get("namespace", self.default_namespace)
            
            if not name:
                print("Error: Pod name is required")
                return
            
            # 创建 Pod
            path = self.uri_config.POD_SPEC_URL.format(namespace=namespace, name=name)
            response = self.api_client.post(path, pod_data)
            
            if response:
                print(f"pod/{name} created")
            else:
                print(f"Error creating pod/{name}")
                
        except FileNotFoundError:
            print(f"Error: File '{filename}' not found")
        except Exception as e:
            print(f"Error creating pod from file: {e}")

    def delete_pod(self, pod_name: str, namespace: str = None) -> None:
        """删除 Pod"""
        try:
            ns = namespace or self.default_namespace
            path = self.uri_config.POD_SPEC_URL.format(namespace=ns, name=pod_name)
            response = self.api_client.delete(path)
            
            if response:
                print(f"pod \"{pod_name}\" deleted")
            else:
                print(f"Error deleting pod \"{pod_name}\"")
                
        except Exception as e:
            print(f"Error deleting pod '{pod_name}': {e}")

    # ============= Service 相关操作 =============
    
    def get_services(self, namespace: str = None, all_namespaces: bool = False) -> None:
        """获取 Service 列表"""
        try:
            if all_namespaces:
                response = self.api_client.get(self.uri_config.GLOBAL_SERVICES_URL)
            else:
                ns = namespace or self.default_namespace
                path = self.uri_config.SERVICE_URL.format(namespace=ns)
                response = self.api_client.get(path)
            
            if not response:
                ns_info = "all namespaces" if all_namespaces else (namespace or self.default_namespace)
                print(f"No services found in {ns_info}.")
                return
            
            headers = ["NAME", "TYPE", "CLUSTER-IP", "EXTERNAL-IP", "PORT(S)", "AGE"]
            if all_namespaces:
                headers.insert(1, "NAMESPACE")
            
            rows = []
            
            for svc_entry in response:
                if isinstance(svc_entry, dict) and len(svc_entry) == 1:
                    svc_name = list(svc_entry.keys())[0]
                    svc_data = svc_entry[svc_name]
                    
                    # 提取 Service 信息
                    svc_type = svc_data.get("spec", {}).get("type", "ClusterIP")
                    cluster_ip = svc_data.get("spec", {}).get("cluster_ip", "<none>")
                    external_ip = svc_data.get("spec", {}).get("external_ip", "<none>")
                    
                    # 端口信息
                    ports = svc_data.get("spec", {}).get("ports", [])
                    port_strs = []
                    for port in ports:
                        port_str = str(port.get("port", ""))
                        if "target_port" in port:
                            port_str += f":{port['target_port']}"
                        if "protocol" in port:
                            port_str += f"/{port['protocol']}"
                        port_strs.append(port_str)
                    ports_str = ",".join(port_strs) if port_strs else "<none>"
                    
                    age = self.format_age(svc_data.get("metadata", {}).get("creation_time", ""))
                    
                    if all_namespaces:
                        svc_namespace = svc_data.get("metadata", {}).get("namespace", "Unknown")
                        rows.append([svc_name, svc_namespace, svc_type, cluster_ip, external_ip, ports_str, age])
                    else:
                        rows.append([svc_name, svc_type, cluster_ip, external_ip, ports_str, age])
            
            print(self.format_table_output(headers, rows))
            
        except Exception as e:
            print(f"Error getting services: {e}")

    def describe_service(self, service_name: str, namespace: str = None) -> None:
        """描述特定 Service 的详细信息"""
        try:
            ns = namespace or self.default_namespace
            path = self.uri_config.SERVICE_SPEC_URL.format(namespace=ns, name=service_name)
            response = self.api_client.get(path)
            
            if not response:
                print(f"Service '{service_name}' not found in namespace '{ns}'")
                return
            
            metadata = response.get("metadata", {})
            spec = response.get("spec", {})
            
            print(f"Name:              {metadata.get('name', 'Unknown')}")
            print(f"Namespace:         {metadata.get('namespace', 'Unknown')}")
            print(f"Labels:            {metadata.get('labels', {})}")
            print(f"Annotations:       {metadata.get('annotations', {})}")
            print(f"Selector:          {spec.get('selector', {})}")
            print(f"Type:              {spec.get('type', 'ClusterIP')}")
            print(f"IP Family Policy:  {spec.get('ip_family_policy', 'SingleStack')}")
            print(f"IP Families:       {spec.get('ip_families', ['IPv4'])}")
            print(f"IP:                {spec.get('cluster_ip', '<none>')}")
            print(f"IPs:               {spec.get('cluster_ips', [])}")
            print(f"Port:              {spec.get('ports', [])}")
            print("")
            
            # 端点信息
            print("Endpoints:")
            endpoints = response.get("endpoints", [])
            if endpoints:
                for endpoint in endpoints:
                    print(f"  {endpoint}")
            else:
                print("  <none>")
            
            print("")
            print("Session Affinity:  None")
            
        except Exception as e:
            print(f"Error describing service '{service_name}': {e}")

    def create_service_from_file(self, filename: str) -> None:
        """从文件创建 Service"""
        try:
            with open(filename, 'r') as f:
                if filename.endswith('.yaml') or filename.endswith('.yml'):
                    svc_data = yaml.safe_load(f)
                else:
                    svc_data = json.load(f)
            
            # 验证 Service 数据
            if svc_data.get("kind") != "Service":
                print(f"Error: File does not contain a Service resource")
                return
            
            metadata = svc_data.get("metadata", {})
            name = metadata.get("name")
            namespace = metadata.get("namespace", self.default_namespace)
            
            if not name:
                print("Error: Service name is required")
                return
            
            # 创建 Service
            path = self.uri_config.SERVICE_SPEC_URL.format(namespace=namespace, name=name)
            response = self.api_client.post(path, svc_data)
            
            if response:
                print(f"service/{name} created")
            else:
                print(f"Error creating service/{name}")
                
        except FileNotFoundError:
            print(f"Error: File '{filename}' not found")
        except Exception as e:
            print(f"Error creating service from file: {e}")

    def delete_service(self, service_name: str, namespace: str = None) -> None:
        """删除 Service"""
        try:
            ns = namespace or self.default_namespace
            path = self.uri_config.SERVICE_SPEC_URL.format(namespace=ns, name=service_name)
            response = self.api_client.delete(path)
            
            if response:
                print(f"service \"{service_name}\" deleted")
            else:
                print(f"Error deleting service \"{service_name}\"")
                
        except Exception as e:
            print(f"Error deleting service '{service_name}': {e}")

    # ============= ReplicaSet 相关操作 =============
    
    def get_replicasets(self, namespace: str = None, all_namespaces: bool = False) -> None:
        """获取 ReplicaSet 列表"""
        try:
            if all_namespaces:
                response = self.api_client.get(self.uri_config.GLOBAL_REPLICA_SETS_URL)
            else:
                ns = namespace or self.default_namespace
                path = self.uri_config.REPLICA_SETS_URL.format(namespace=ns)
                response = self.api_client.get(path)
            
            if not response:
                ns_info = "all namespaces" if all_namespaces else (namespace or self.default_namespace)
                print(f"No replicasets found in {ns_info}.")
                return
            
            headers = ["NAME", "DESIRED", "CURRENT", "READY", "AGE"]
            if all_namespaces:
                headers.insert(1, "NAMESPACE")
            
            rows = []
            
            for rs_entry in response:
                if isinstance(rs_entry, dict) and len(rs_entry) == 1:
                    rs_name = list(rs_entry.keys())[0]
                    rs_data = rs_entry[rs_name]
                    
                    # 提取 ReplicaSet 信息
                    desired = rs_data.get("spec", {}).get("replicas", 0)
                    current_replicas = rs_data.get("current_replicas", 0)
                    
                    # 计算 ready 数量
                    ready_count = 0
                    if isinstance(current_replicas, list):
                        ready_count = sum(current_replicas)
                    elif isinstance(current_replicas, int):
                        ready_count = current_replicas
                    
                    age = self.format_age(rs_data.get("metadata", {}).get("creation_time", ""))
                    
                    if all_namespaces:
                        rs_namespace = rs_data.get("metadata", {}).get("namespace", "Unknown")
                        rows.append([rs_name, rs_namespace, str(desired), str(ready_count), str(ready_count), age])
                    else:
                        rows.append([rs_name, str(desired), str(ready_count), str(ready_count), age])
            
            print(self.format_table_output(headers, rows))
            
        except Exception as e:
            print(f"Error getting replicasets: {e}")

    def describe_replicaset(self, rs_name: str, namespace: str = None) -> None:
        """描述特定 ReplicaSet 的详细信息"""
        try:
            ns = namespace or self.default_namespace
            path = self.uri_config.REPLICA_SET_SPEC_URL.format(namespace=ns, name=rs_name)
            response = self.api_client.get(path)
            
            if not response:
                print(f"ReplicaSet '{rs_name}' not found in namespace '{ns}'")
                return
            
            metadata = response.get("metadata", {})
            spec = response.get("spec", {})
            
            print(f"Name:         {metadata.get('name', 'Unknown')}")
            print(f"Namespace:    {metadata.get('namespace', 'Unknown')}")
            print(f"Selector:     {spec.get('selector', {})}")
            print(f"Labels:       {metadata.get('labels', {})}")
            print(f"Annotations:  {metadata.get('annotations', {})}")
            print(f"Replicas:     {spec.get('replicas', 0)} current / {spec.get('replicas', 0)} desired")
            print("")
            
            # Pod 模板信息
            template = spec.get("template", {})
            if template:
                print("Pod Template:")
                print(f"  Labels:     {template.get('metadata', {}).get('labels', {})}")
                print("  Containers:")
                containers = template.get("spec", {}).get("containers", [])
                for container in containers:
                    print(f"   {container.get('name', 'Unknown')}:")
                    print(f"    Image:      {container.get('image', 'Unknown')}")
                    print(f"    Port:       {container.get('ports', [])}")
                    print(f"    Resources:  {container.get('resources', {})}")
            
            print("")
            
            # Pod 实例信息
            pod_instances = response.get("pod_instances", [])
            if pod_instances:
                print("Pod Instances:")
                for group in pod_instances:
                    if isinstance(group, list):
                        print(f"  Group: {group}")
                    else:
                        print(f"  Pod: {group}")
            else:
                print("Pod Instances: <none>")
            
            print("")
            
            # HPA 控制信息
            hpa_controlled = response.get("hpa_controlled", False)
            print(f"Controlled by HPA: {hpa_controlled}")
            
        except Exception as e:
            print(f"Error describing replicaset '{rs_name}': {e}")

    def create_replicaset_from_file(self, filename: str) -> None:
        """从文件创建 ReplicaSet"""
        try:
            with open(filename, 'r') as f:
                if filename.endswith('.yaml') or filename.endswith('.yml'):
                    rs_data = yaml.safe_load(f)
                else:
                    rs_data = json.load(f)
            
            # 验证 ReplicaSet 数据
            if rs_data.get("kind") != "ReplicaSet":
                print(f"Error: File does not contain a ReplicaSet resource")
                return
            
            metadata = rs_data.get("metadata", {})
            name = metadata.get("name")
            namespace = metadata.get("namespace", self.default_namespace)
            
            if not name:
                print("Error: ReplicaSet name is required")
                return
            
            # 创建 ReplicaSet
            path = self.uri_config.REPLICA_SET_SPEC_URL.format(namespace=namespace, name=name)
            response = self.api_client.post(path, rs_data)
            
            if response:
                print(f"replicaset.apps/{name} created")
            else:
                print(f"Error creating replicaset.apps/{name}")
                
        except FileNotFoundError:
            print(f"Error: File '{filename}' not found")
        except Exception as e:
            print(f"Error creating replicaset from file: {e}")

    def delete_replicaset(self, rs_name: str, namespace: str = None) -> None:
        """删除 ReplicaSet"""
        try:
            ns = namespace or self.default_namespace
            path = self.uri_config.REPLICA_SET_SPEC_URL.format(namespace=ns, name=rs_name)
            response = self.api_client.delete(path)
            
            if response:
                print(f"replicaset.apps \"{rs_name}\" deleted")
            else:
                print(f"Error deleting replicaset.apps \"{rs_name}\"")
                
        except Exception as e:
            print(f"Error deleting replicaset '{rs_name}': {e}")

    def scale_replicaset(self, rs_name: str, replicas: int, namespace: str = None) -> None:
        """扩缩容 ReplicaSet"""
        try:
            ns = namespace or self.default_namespace
            
            # 先获取当前 ReplicaSet
            path = self.uri_config.REPLICA_SET_SPEC_URL.format(namespace=ns, name=rs_name)
            current_rs = self.api_client.get(path)
            
            if not current_rs:
                print(f"ReplicaSet '{rs_name}' not found in namespace '{ns}'")
                return
            
            # 更新副本数
            current_rs["spec"]["replicas"] = replicas
            
            # 发送更新请求
            response = self.api_client.put(path, current_rs)
            
            if response:
                print(f"replicaset.apps/{rs_name} scaled")
            else:
                print(f"Error scaling replicaset.apps/{rs_name}")
                
        except Exception as e:
            print(f"Error scaling replicaset '{rs_name}': {e}")

    # ============= HPA 相关操作 =============
    
    def get_hpa(self, namespace: str = None, all_namespaces: bool = False) -> None:
        """获取 HPA 列表"""
        try:
            if all_namespaces:
                response = self.api_client.get(self.uri_config.GLOBAL_HPA_URL)
            else:
                ns = namespace or self.default_namespace
                path = self.uri_config.HPA_URL.format(namespace=ns)
                response = self.api_client.get(path)
            
            if not response:
                ns_info = "all namespaces" if all_namespaces else (namespace or self.default_namespace)
                print(f"No hpa found in {ns_info}.")
                return
            
            headers = ["NAME", "REFERENCE", "TARGETS", "MINPODS", "MAXPODS", "REPLICAS", "AGE"]
            if all_namespaces:
                headers.insert(1, "NAMESPACE")
            
            rows = []
            
            for hpa_entry in response:
                if isinstance(hpa_entry, dict) and len(hpa_entry) == 1:
                    hpa_name = list(hpa_entry.keys())[0]
                    hpa_data = hpa_entry[hpa_name]
                    
                    # 提取 HPA 信息
                    spec = hpa_data.get("spec", {})
                    target_ref = spec.get("scaleTargetRef", {})
                    reference = f"{target_ref.get('kind', 'Unknown')}/{target_ref.get('name', 'Unknown')}"
                    
                    # 指标信息
                    metrics = spec.get("metrics", [])
                    targets = []
                    for metric in metrics:
                        if metric.get("type") == "Resource":
                            resource = metric.get("resource", {})
                            targets.append(f"{resource.get('name', 'unknown')}: {resource.get('target', {}).get('averageUtilization', 'unknown')}%")
                    targets_str = ", ".join(targets) if targets else "<unknown>"
                    
                    min_replicas = spec.get("minReplicas", 1)
                    max_replicas = spec.get("maxReplicas", 10)
                    current_replicas = hpa_data.get("current_replicas", 0)
                    
                    age = self.format_age(hpa_data.get("metadata", {}).get("creation_time", ""))
                    
                    if all_namespaces:
                        hpa_namespace = hpa_data.get("metadata", {}).get("namespace", "Unknown")
                        rows.append([hpa_name, hpa_namespace, reference, targets_str, str(min_replicas), str(max_replicas), str(current_replicas), age])
                    else:
                        rows.append([hpa_name, reference, targets_str, str(min_replicas), str(max_replicas), str(current_replicas), age])
            
            print(self.format_table_output(headers, rows))
            
        except Exception as e:
            print(f"Error getting hpa: {e}")

    def describe_hpa(self, hpa_name: str, namespace: str = None) -> None:
        """描述特定 HPA 的详细信息"""
        try:
            ns = namespace or self.default_namespace
            path = self.uri_config.HPA_SPEC_URL.format(namespace=ns, name=hpa_name)
            response = self.api_client.get(path)
            
            if not response:
                print(f"HPA '{hpa_name}' not found in namespace '{ns}'")
                return
            
            metadata = response.get("metadata", {})
            spec = response.get("spec", {})
            
            print(f"Name:         {metadata.get('name', 'Unknown')}")
            print(f"Namespace:    {metadata.get('namespace', 'Unknown')}")
            print(f"Labels:       {metadata.get('labels', {})}")
            print(f"Annotations:  {metadata.get('annotations', {})}")
            
            # 目标引用
            target_ref = spec.get("scaleTargetRef", {})
            print(f"CreationTimestamp:  {metadata.get('creation_time', '<unknown>')}")
            print(f"Reference:          {target_ref.get('kind', 'Unknown')}/{target_ref.get('name', 'Unknown')}")
            
            # 指标信息
            print("Metrics:")
            metrics = spec.get("metrics", [])
            if metrics:
                for i, metric in enumerate(metrics):
                    if metric.get("type") == "Resource":
                        resource = metric.get("resource", {})
                        print(f"  [{i}] Resource:")
                        print(f"      Name:               {resource.get('name', 'Unknown')}")
                        target = resource.get("target", {})
                        if "averageUtilization" in target:
                            print(f"      Target Utilization: {target['averageUtilization']}%")
                        if "averageValue" in target:
                            print(f"      Target Value:       {target['averageValue']}")
            else:
                print("  <none>")
            
            print(f"Min replicas:       {spec.get('minReplicas', 1)}")
            print(f"Max replicas:       {spec.get('maxReplicas', 10)}")
            print(f"Current replicas:   {response.get('current_replicas', 0)}")
            print(f"Status:             {response.get('status', 'Unknown')}")
            
            # 最后扩缩容时间
            last_scale_time = response.get("last_scale_time")
            if last_scale_time:
                print(f"Last Scale Time:    {last_scale_time}")
            else:
                print("Last Scale Time:    <none>")
            
        except Exception as e:
            print(f"Error describing hpa '{hpa_name}': {e}")

    def create_hpa_from_file(self, filename: str) -> None:
        """从文件创建 HPA"""
        try:
            with open(filename, 'r') as f:
                if filename.endswith('.yaml') or filename.endswith('.yml'):
                    hpa_data = yaml.safe_load(f)
                else:
                    hpa_data = json.load(f)
            
            # 验证 HPA 数据
            if hpa_data.get("kind") != "HorizontalPodAutoscaler":
                print(f"Error: File does not contain a HorizontalPodAutoscaler resource")
                return
            
            metadata = hpa_data.get("metadata", {})
            name = metadata.get("name")
            namespace = metadata.get("namespace", self.default_namespace)
            
            if not name:
                print("Error: HPA name is required")
                return
            
            # 创建 HPA
            path = self.uri_config.HPA_SPEC_URL.format(namespace=namespace, name=name)
            response = self.api_client.post(path, hpa_data)
            
            if response:
                print(f"horizontalpodautoscaler.autoscaling/{name} created")
            else:
                print(f"Error creating horizontalpodautoscaler.autoscaling/{name}")
                
        except FileNotFoundError:
            print(f"Error: File '{filename}' not found")
        except Exception as e:
            print(f"Error creating hpa from file: {e}")

    def delete_hpa(self, hpa_name: str, namespace: str = None) -> None:
        """删除 HPA"""
        try:
            ns = namespace or self.default_namespace
            path = self.uri_config.HPA_SPEC_URL.format(namespace=ns, name=hpa_name)
            response = self.api_client.delete(path)
            
            if response:
                print(f"horizontalpodautoscaler.autoscaling \"{hpa_name}\" deleted")
            else:
                print(f"Error deleting horizontalpodautoscaler.autoscaling \"{hpa_name}\"")
                
        except Exception as e:
            print(f"Error deleting hpa '{hpa_name}': {e}")


def main():
    """主函数 - 解析命令行参数并执行相应操作"""
    parser = argparse.ArgumentParser(description="kubectl - Kubernetes 命令行工具")
    subparsers = parser.add_subparsers(dest="command", help="可用命令")
    
    # 全局参数
    parser.add_argument("--namespace", "-n", default="default", help="指定命名空间")
    parser.add_argument("--all-namespaces", "-A", action="store_true", help="查看所有命名空间")
    
    # get 命令
    get_parser = subparsers.add_parser("get", help="显示一个或多个资源")
    get_parser.add_argument("resource", choices=["nodes", "pods", "services", "svc", "replicasets", "rs", "hpa"], 
                           help="资源类型")
    get_parser.add_argument("name", nargs="?", help="资源名称")
    
    # describe 命令  
    describe_parser = subparsers.add_parser("describe", help="显示特定资源的详细信息")
    describe_parser.add_argument("resource", choices=["node", "pod", "service", "svc", "replicaset", "rs", "hpa"], 
                                help="资源类型")
    describe_parser.add_argument("name", help="资源名称")
    
    # create 命令
    create_parser = subparsers.add_parser("create", help="从文件或stdin创建资源")
    create_parser.add_argument("-f", "--filename", required=True, help="文件名")
    
    # delete 命令
    delete_parser = subparsers.add_parser("delete", help="删除资源")
    delete_parser.add_argument("resource", choices=["pod", "service", "svc", "replicaset", "rs", "hpa"], 
                              help="资源类型")
    delete_parser.add_argument("name", help="资源名称")
    
    # scale 命令 (仅针对 ReplicaSet)
    scale_parser = subparsers.add_parser("scale", help="扩缩容资源")
    scale_parser.add_argument("resource", choices=["replicaset", "rs"], help="资源类型")
    scale_parser.add_argument("name", help="资源名称")
    scale_parser.add_argument("--replicas", type=int, required=True, help="目标副本数")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    # 创建客户端
    kubectl = KubectlClient()
    if args.namespace:
        kubectl.default_namespace = args.namespace
    
    try:
        # 执行命令
        if args.command == "get":
            if args.resource in ["nodes"]:
                kubectl.get_nodes()
            elif args.resource in ["pods"]:
                kubectl.get_pods(namespace=args.namespace, all_namespaces=args.all_namespaces)
            elif args.resource in ["services", "svc"]:
                kubectl.get_services(namespace=args.namespace, all_namespaces=args.all_namespaces)
            elif args.resource in ["replicasets", "rs"]:
                kubectl.get_replicasets(namespace=args.namespace, all_namespaces=args.all_namespaces)
            elif args.resource in ["hpa"]:
                kubectl.get_hpa(namespace=args.namespace, all_namespaces=args.all_namespaces)
                
        elif args.command == "describe":
            if args.resource == "node":
                kubectl.describe_node(args.name)
            elif args.resource == "pod":
                kubectl.describe_pod(args.name, namespace=args.namespace)
            elif args.resource in ["service", "svc"]:
                kubectl.describe_service(args.name, namespace=args.namespace)
            elif args.resource in ["replicaset", "rs"]:
                kubectl.describe_replicaset(args.name, namespace=args.namespace)
            elif args.resource == "hpa":
                kubectl.describe_hpa(args.name, namespace=args.namespace)
                
        elif args.command == "create":
            # 根据文件内容判断资源类型
            kubectl.create_pod_from_file(args.filename)  # 这里简化处理，实际应该解析文件判断类型
            
        elif args.command == "delete":
            if args.resource == "pod":
                kubectl.delete_pod(args.name, namespace=args.namespace)
            elif args.resource in ["service", "svc"]:
                kubectl.delete_service(args.name, namespace=args.namespace)
            elif args.resource in ["replicaset", "rs"]:
                kubectl.delete_replicaset(args.name, namespace=args.namespace)
            elif args.resource == "hpa":
                kubectl.delete_hpa(args.name, namespace=args.namespace)
                
        elif args.command == "scale":
            if args.resource in ["replicaset", "rs"]:
                kubectl.scale_replicaset(args.name, args.replicas, namespace=args.namespace)
                
    except KeyboardInterrupt:
        print("\nOperation cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
