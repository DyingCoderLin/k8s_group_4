#!/usr/bin/env python3
"""
kubectl - Kubernetes 命令行工具
支持 Node、Pod、Service、ReplicaSet、HPA 的管理操作
"""

import argparse
import json
import os
import sys
import yaml

# 导入项目依赖
from pkg.config.uriConfig import URIConfig
from pkg.apiServer.apiClient import ApiClient
from pkg.apiObject.node import Node
from pkg.config.nodeConfig import NodeConfig

from pkg.config.dnsConfig import DNSConfig
from pkg.controller.dnsController import DNSController


class KubectlClient:
    """kubectl 客户端主类"""
    
    def __init__(self):
        """初始化 kubectl 客户端"""
        self.uri_config = URIConfig()
        self.api_client = ApiClient(self.uri_config.HOST, self.uri_config.PORT)
        print(f"Connecting to API server at {self.uri_config.HOST}:{self.uri_config.PORT}")
        self.default_namespace = "default"
        
    def format_table_output(self, headers: list, rows: list) -> str:
        """
        格式化表格输出，模仿 kubectl 的输出格式
        """
        if not rows:
            return ""
        
        # 计算每列的最大宽度
        col_widths = []
        
        # 初始化列宽为表头的长度
        for header in headers:
            col_widths.append(len(str(header)))
        
        # 检查数据行，更新列宽
        for row in rows:
            for i, cell in enumerate(row):
                if i < len(col_widths):
                    col_widths[i] = max(col_widths[i], len(str(cell)))
        
        # 构建输出字符串
        output_lines = []
        
        # 添加表头
        header_parts = []
        for i, header in enumerate(headers):
            if i < len(col_widths):
                header_parts.append(str(header).ljust(col_widths[i]))
        output_lines.append("  ".join(header_parts))
        
        # 添加数据行
        for row in rows:
            row_parts = []
            for i, cell in enumerate(row):
                if i < len(col_widths):
                    row_parts.append(str(cell).ljust(col_widths[i]))
            output_lines.append("  ".join(row_parts))
        
        return "\n".join(output_lines)
    
    # ============= 通用 Apply 命令 =============
    
    def apply_from_file(self, filename: str) -> None:
        """通用的 apply 命令，根据 kind 字段自动识别资源类型并创建"""
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                if filename.endswith('.yaml') or filename.endswith('.yml'):
                    resource_data = yaml.safe_load(f)
                else:
                    resource_data = json.load(f)
            
            # 检查是否为有效的 Kubernetes 资源
            if not isinstance(resource_data, dict):
                print(f"Error: Invalid resource format in '{filename}'")
                return
            
            kind = resource_data.get("kind")
            if not kind:
                print(f"Error: Missing 'kind' field in '{filename}'")
                return
            
            metadata = resource_data.get("metadata", {})
            name = metadata.get("name")
            namespace = metadata.get("namespace", self.default_namespace)
            
            if not name:
                print(f"Error: Missing resource name in '{filename}'")
                return
            
            print(f"Applying {kind} '{name}' in  '{namespace}'...")

            # 根据 kind 字段调用相应的创建方法
            if kind == "Pod":
                self._apply_pod(resource_data, name, namespace)
            elif kind == "Service":
                self._apply_service(resource_data, name, namespace)
            elif kind == "ReplicaSet":
                self._apply_replicaset(resource_data, name, namespace)
            elif kind == "HorizontalPodAutoscaler":
                self._apply_hpa(resource_data, name, namespace)
            elif kind == "Node":
                self._apply_node(resource_data, name)
            elif kind == "DNS":
                self._apply_dns(resource_data, name, namespace)
            elif kind == "Function":
                self._apply_function(resource_data, name, namespace)
            elif kind == "Workflow":
                self._apply_workflow(resource_data, name, namespace)
            else:
                print(f"Error: Unsupported resource kind '{kind}'")
                return
                
        except FileNotFoundError:
            print(f"Error: File '{filename}' not found")
        except yaml.YAMLError as e:
            print(f"Error: Invalid YAML format in '{filename}': {e}")
        except json.JSONDecodeError as e:
            print(f"Error: Invalid JSON format in '{filename}': {e}")
        except Exception as e:
            print(f"Error applying resource from '{filename}': {e}")
    
    def _apply_pod(self, pod_data: dict, name: str, namespace: str) -> None:
        """应用Pod资源"""
        try:
            key = URIConfig.POD_SPEC_URL.format(
                        namespace=namespace,
                        name=name,
                    )
            self.api_client.post(key, pod_data)
            
            print(f"pod/{name} created")
            
        except Exception as e:
            print(f"Error creating pod/{name}: {e}")
    
    def _apply_service(self, service_data: dict, name: str, namespace: str) -> None:
        """应用Service资源"""
        try:
            # 通过 API 创建 Service
            key = self.uri_config.SERVICE_SPEC_URL.format(namespace=namespace, name=name)
            response = self.api_client.post(key, service_data)
            
            if response:
                print(f"service/{name} created")
            else:
                print(f"Error creating service/{name}")
                
        except Exception as e:
            print(f"Error creating service/{name}: {e}")
    
    def _apply_replicaset(self, rs_data: dict, name: str, namespace: str) -> None:
        """应用ReplicaSet资源"""
        try:
            path = self.uri_config.REPLICA_SET_SPEC_URL.format(
                namespace=namespace, name=name
            )
            response = self.api_client.post(path, rs_data)
            
            if response:
                print(f"replicaset.apps/{name} created")
                
        except Exception as e:
            print(f"Error creating replicaset.apps/{name}: {e}")
    
    def _apply_hpa(self, hpa_data: dict, name: str, namespace: str) -> None:
        """应用HPA资源"""
        try:
            # 使用 HorizontalPodAutoscalerConfig 创建配置对象
            path = self.uri_config.HPA_SPEC_URL.format(
                namespace=namespace, name=name
            )

            response = self.api_client.post(path, hpa_data)
            
            # 调用创建方法
            if response:
                print(f"horizontalpodautoscaler.autoscaling/{name} created")
            
        except Exception as e:
            print(f"Error creating horizontalpodautoscaler.autoscaling/{name}: {e}")

    def _apply_function(self, function_data: dict, name: str, namespace: str):
        """应用Function资源"""
        try:
            print(f"Applying function '{name}' in namespace '{namespace}'...")

            # TODO 这里存etcd
            # func_url = self.uri_config.FUNCTION_SPEC_URL.format(
            #     namespace = namespace,
            #     name = name
            # )
            # response = self.api_client.post(func_url, function_data)


            print(f"function_data:\n {function_data}")
            print(f"function_name: {function_data.get('metadata', {}).get('name')}")

            from pkg.config.globalConfig import GlobalConfig
            import requests

            config = GlobalConfig()

            def upload_function(func):
                yaml_path = os.path.join(config.TEST_FILE_PATH, f'function-{func}.yaml')
                print(f'上传函数{yaml_path}')
                with open(yaml_path, "r", encoding="utf-8") as file:
                    data = yaml.safe_load(file)
                file_path = os.path.join(config.TEST_FILE_PATH,
                                        f'serverless/zip-function/{func}.zip')
                with open(file_path, 'rb') as f:
                    file_data = f.read()

                files = {'file': (os.path.basename(file_path), file_data)}
                url = URIConfig.PREFIX + URIConfig.FUNCTION_SPEC_URL.format(namespace='default', name=func)
                print(f'[INFO]上传函数 {func} 到 {url}进行中')
                response = requests.post(url, files=files, data=data)
                print(response.json())

            upload_function(function_data.get('metadata', {}).get('name'))

        except Exception as e:
            print(f"Error creating serverless.function/{name}: {e}")
            
    def _apply_workflow(self, workflow_data: dict, name: str, namespace: str):
        """应用Function资源"""
        try:
            import requests

            print(f"workflow_data: \n{workflow_data}")
            uri = URIConfig.PREFIX + URIConfig.WORKFLOW_SPEC_URL.format(
                namespace=workflow_data["metadata"]["namespace"],
                name=workflow_data["metadata"]["name"],
            )
            response = requests.post(uri, json = workflow_data)
            print(response.json())

            # input('Press Enter To Continue.')
            # print(f'[INFO]测试执行')
            # gen_input = {
            #     "text": "The future of AI is ",
            # }
            # response = requests.patch(uri, json=gen_input)
            # print(response.json())

            # input('Press Enter To Continue.')
            # chat_input = {
            #     "text": "How are you?",
            #     "chat_history": [ "The future of AI is bright.", "I think AI will change the world."]
            # }
            # response = requests.patch(uri, json=chat_input)
            # print(response.json())

        except Exception as e:
            print(f"Error creating serverless.function/{name}: {e}")
    
    def _apply_node(self, node_data: dict, name: str) -> None:
        """应用Node资源（特殊处理）"""
        try:
            # Node 是特殊的，需要在节点上执行
            print(f"Warning: Node resources should be applied on the target node itself")
            print(f"Please run 'kubectl add node {name}' on the target node")
            
            # 这里可以选择直接通过 API 注册节点（如果支持）
            # 使用 NodeConfig 创建配置对象
            node_config = NodeConfig(node_data)
            
            node = Node(node_config, URIConfig)
            # 这会阻塞进程
            print(f"Starting node '{name}', note that this will block the current process...")
            node.run()
            
        except Exception as e:
            print(f"Error creating node/{name}: {e}")
    
    def _apply_dns(self, dns_data: dict, name: str, namespace: str) -> None:
        try:
            dns_controller = DNSController()
            
            dns_url = dns_controller.uri_config.DNS_SPEC_URL.format(namespace = namespace, name = name)
            response = dns_controller.api_client.post(dns_url, dns_data)

            dns_controller.sync_dns_records()
        
        except Exception as e:
            print(f"Error creating dns/{name}: {e}")    
        
    def add_node_from_file(self, filename: str) -> None:
        """专门用于节点加入的命令"""
        try:
            import yaml
            import os
            import subprocess
            import sys
        
            # 检查文件是否存在
            if not os.path.exists(filename):
                print(f"Error: File {filename} not found")
                return
            # 直接读取文件，不使用 StringIO
            with open(filename, 'r', encoding='utf-8') as file:
                try:
                    # 使用 safe_load 而不是 load
                    node_data = yaml.safe_load(file)
                except yaml.YAMLError as e:
                    print(f"Error parsing YAML file: {e}")
                    return
            
            # 验证 Node 数据
            if node_data.get("kind") != "Node":
                print(f"Error: File does not contain a Node resource")
                return
            
            metadata = node_data.get("metadata", {})
            name = metadata.get("name")
            
            if not name:
                print("Error: Node name is required")
                return
            
            # 创建日志目录
            log_dir = "./logs"
            os.makedirs(log_dir, exist_ok=True)
            log_file = os.path.join(log_dir, "node.log")
            
            # 使用subprocess在后台启动node进程，将日志重定向到文件
            cmd = [
                sys.executable, "-m", "pkg.apiObject.node",
                "--node-config", filename,
            ]
            
            print(f"Starting node '{name}' in background...")
            print(f"Node logs will be written to: {log_file}")
            
            with open(log_file, 'a') as f:
                # 在日志文件中记录启动信息
                f.write(f"\n=== Node {name} started at {__import__('datetime').datetime.now()} ===\n")
                f.flush()
                
                # 启动后台进程
                process = subprocess.Popen(
                    cmd,
                    stdout=f,
                    stderr=subprocess.STDOUT,
                    cwd=os.getcwd(),
                    env=dict(os.environ, NODE_LOG_FILE=log_file)
                )
            
            print(f"Node '{name}' started successfully with PID: {process.pid}")
            print(f"Monitor logs with: tail -f {log_file}")
            
        except FileNotFoundError:
            print(f"Error: File '{filename}' not found")
        except Exception as e:
            print(f"Error adding node from file: {e}")
    
    # ============= Node 相关操作 =============
    
    def get_nodes(self) -> None:
        """获取所有 Node 信息"""
        try:
            response = self.api_client.get(self.uri_config.NODES_URL)
            if not response:
                print("No nodes found.")
                return
            
            headers = ["NAME", "STATUS", "SUBNET_IP", "LAST_HEARTBEAT"]
            rows = []
            
            # for node_entry in response:
            #     if isinstance(node_entry, dict) and len(node_entry) == 1:
            #         node_name = list(node_entry.keys())[0]
            #         node_data = node_entry[node_name]
                    
            #         # 提取节点信息
            #         status = node_data.get("status", "Unknown")
            #         roles = node_data.get("roles", ["<none>"])
            #         if isinstance(roles, list):
            #             roles_str = ",".join(roles) if roles else "<none>"
            #         else:
            #             roles_str = str(roles)
                    
            #         version = node_data.get("version", "Unknown")
                    
            #         rows.append([node_name, status, roles_str, version])
            
            for node_entry in response:
                if isinstance(node_entry, NodeConfig):
                    node_name = node_entry.name
                    
                    # 提取节点信息
                    status = node_entry.status or "Unknown"
                    
                    subnet_ip = node_entry.subnet_ip or "<none>"
                    
                    heart_beat = node_entry.heartbeat_time or "<none>"
                    
                    rows.append([node_name, status, subnet_ip,heart_beat])
            
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
            
            if not isinstance(response, NodeConfig) or len(response) != 1:
                print(f"Invalid node data for '{node_name}'")
                return
            
            print(f"Name:                 {response.name or '[]'}")
            print(f"Taints:               {response.taints or '[]'}")
            print("")
            
            print("Subnet IP:")
            if response.subnet_ip:
                print(f"  {response.subnet_ip}")
            else:
                print("  <none>")
            
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
            
            headers = ["NAME", "READY", "STATUS"]
            if all_namespaces:
                headers.insert(0, "NAMESPACE")
            
            rows = []
            
            for pod_entry in response:
                if isinstance(pod_entry, dict) and len(pod_entry) == 1:
                    pod_name = list(pod_entry.keys())[0]
                    pod_data = pod_entry[pod_name]
                    
                    # 提取 Pod 信息
                    # ready_containers = len(pod_data.get("containers", 0))
                    total_containers = len(pod_data.get("spec", {}).get("containers", []))
                    ready = f"{total_containers}/{total_containers}"
                    
                    status = pod_data.get("status", "Unknown")
                    
                    if all_namespaces:
                        pod_namespace = pod_data.get("metadata",{}).get("namespace", "Unknown")
                        rows.append([pod_namespace,pod_name, ready, status])
                    else:
                        rows.append([pod_name, ready, status])
            
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
            print(f"Node:         {response.get('node_name', '<none>')}")
            print(f"Labels:       {response.get('metadata', {}).get('labels', {})}")
            print(f"Status:       {response.get('status', "")}")
            print(f"IP:           {response.get('subnet_ip', '<none>')}")
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
            
            headers = ["NAME", "TYPE", "CLUSTER-IP", "PORT(S)"]
            if all_namespaces:
                headers.insert(1, "NAMESPACE")
            
            rows = []
            
            for svc_entry in response:
                if isinstance(svc_entry, dict) and len(svc_entry) == 1:
                    svc_name = list(svc_entry.keys())[0]
                    svc_data = svc_entry[svc_name]
                    
                    # 提取 Service 信息
                    svc_type = svc_data.get("spec", {}).get("type", "ClusterIP")
                    cluster_ip = svc_data.get("spec", {}).get("clusterIP", "<none>")
                    # external_ip = svc_data.get("spec", {}).get("external_ip", "<none>")
                    
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
                    
                    if all_namespaces:
                        svc_namespace = svc_data.get("metadata", {}).get("namespace", "Unknown")
                        rows.append([svc_name, svc_namespace, svc_type, cluster_ip, ports_str])
                    else:
                        rows.append([svc_name, svc_type, cluster_ip, ports_str])
            
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
            print(f"Selector:          {spec.get('selector', {})}")
            print(f"Type:              {spec.get('type', 'ClusterIP')}")
            print(f"IP:                {spec.get('clusterIP', '<none>')}")
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
            
            headers = ["NAME", "DESIRED", "CURRENT", "READY"]
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
                    
                    if all_namespaces:
                        rs_namespace = rs_data.get("metadata", {}).get("namespace", "Unknown")
                        rows.append([rs_name, rs_namespace, str(desired), str(ready_count), str(ready_count)])
                    else:
                        rows.append([rs_name, str(desired), str(ready_count), str(ready_count)])
            
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
            
            headers = ["NAME", "REFERENCE", "TARGETS", "MINPODS", "MAXPODS", "REPLICAS"]
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
                    
                    if all_namespaces:
                        hpa_namespace = hpa_data.get("metadata", {}).get("namespace", "Unknown")
                        rows.append([hpa_name, hpa_namespace, reference, targets_str, str(min_replicas), str(max_replicas), str(current_replicas)])
                    else:
                        rows.append([hpa_name, reference, targets_str, str(min_replicas), str(max_replicas), str(current_replicas)])
            
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

    # ============= Function 相关操作 =============

    def get_functions(self, namespace: str = None, all_namespaces: bool = False) -> None:
        """获取所有 Function 信息"""
        print("Getting functions...")
        try:
            if all_namespaces:
                response = self.api_client.get(self.uri_config.GLOBAL_FUNCTIONS_URL)
            else:
                ns = namespace or self.default_namespace
                path = self.uri_config.SERVICE_URL.format(namespace=ns)
                response = self.api_client.get(path)
            
            if not response:
                ns_info = "all namespaces" if all_namespaces else (namespace or self.default_namespace)
                print(f"No functions found in {ns_info}.")
                return
            
            from .pkg.config.functionConfig import FunctionConfig

            print(f"Found {len(response)} functions.")
            print(f"{response}")

            headers = ["NAME", "NAMESPACE", "PATH"]
            rows = []

            for func_entry in response:
                # print(f"Node: {func_entry}")
                if isinstance(func_entry, FunctionConfig):
                    name = func_entry.get("metadata").get("name")
                    namespace = func_entry.get("metadata").get("namespace")
                    path = func_entry.get("metadata").get("file_path")

                    rows.append([name, namespace, path])
            
            print(self.format_table_output(headers, rows))

        except Exception as e:
            print(f"Error getting functions: {e}")

    def describe_function(self, function_name: str, namespace: str = None) -> None:
        try:
            ns = namespace or self.default_namespace
            path = self.uri_config.FUNCTION_URL.format(namespace=ns, name=function_name)
            response = self.api_client.get(path)

            if not response:
                print(f"Function '{function_name}' not found in namespace '{ns}'")
                return

            metadata = response.get("metadata", {})
            trigger = response.get('trigger', 'Unknown')

            print(f"Name:         {metadata.get('name', 'Unknown')}")
            print(f"Namespace:    {metadata.get('namespace', 'Unknown')}")
            print(f"Labels:       {metadata.get('labels', {})}")
            print(f"Annotations:  {metadata.get('annotations', {})}")
            print(f"Trigger:      {trigger}")

            # 构建信息
            build = response.get("build", {})
            print(f"File:           {build.get('file', 'Unknown')}")
            print(f"Image:          {build.get('image', 'Unknown')}")

            # 实例信息
            print("Running Pods:")
            running_pods = response.get("running_pods", [])
            if running_pods:
                for i, pod in enumerate(running_pods):
                    print(f"Pod {i}")
                    print(f"    Name:         {pod.get('metadata', {}).get('name', 'Unknown')}")
                    print(f"    Namespace:    {pod.get('metadata', {}).get('namespace', 'Unknown')}")
                    print(f"    Priority:     {pod.get('spec', {}).get('priority', 0)}")
                    print(f"    Node:         {pod.get('spec', {}).get('node_name', '<none>')}")
                    print(f"    Start Time:   {pod.get('status', {}).get('start_time', '<unknown>')}")
                    print(f"    Labels:       {pod.get('metadata', {}).get('labels', {})}")
                    print(f"    Annotations:  {pod.get('metadata', {}).get('annotations', {})}")
                    print(f"    Status:       {pod.get('status', {}).get('phase', 'Unknown')}")
                    print(f"    IP:           {pod.get('status', {}).get('pod_ip', '<none>')}")
                    print("")
            else:
                print("  <none>")

        except Exception as e:
            print(f"Error describing function '{function_name}': {e}")

    def create_function_from_file(self, yaml_name: str, file_path: str) -> None:
        """从文件创建 Function"""
        try:
            with open(yaml_name, 'r') as f:
                if yaml_name.endswith('.yaml') or yaml_name.endswith('.yml'):
                    function_data = yaml.safe_load(f)
                else:
                    function_data = json.load(f)

            # 验证 Function 数据
            if function_data.get("kind") != "Function":
                print(f"Error: File does not contain a Function resource")
                return

            metadata = function_data.get("metadata", {})
            name = metadata.get("name")
            namespace = metadata.get("namespace", self.default_namespace)

            if not name:
                print("Error: Function name is required")
                return

            with open(file_path, 'rb') as f:
                file_data = f.read()
            files = {'file': (os.path.basename(file_path), file_data)}

            # 创建 Function
            path = self.uri_config.FUNCTION_SPEC_URL.format(namespace=namespace, name=name)
            response = self.api_client.post(path, json=function_data, files=files)

            if response:
                print(f"serverless.function/{name} created")
            else:
                print(f"Error creating serverless.function/{name}")

        except FileNotFoundError:
            print(f"Error: File '{yaml_name}' or '{file_path}' not found")
        except Exception as e:
            print(f"Error creating function from file: {e}")

    def delete_function(self, function_name: str, namespace: str = None) -> None:
        """删除 Function"""
        try:
            ns = namespace or self.default_namespace
            path = self.uri_config.FUNCTION_SPEC_URL.format(namespace=ns, name=function_name)
            response = self.api_client.delete(path)

            if response:
                print(f"serverless.function \"{function_name}\" deleted")
            else:
                print(f"Error deleting hserverless.function \"{function_name}\"")

        except Exception as e:
            print(f"Error deleting function '{function_name}': {e}")

def main():
    """主函数 - 解析命令行参数并执行相应操作"""
    parser = argparse.ArgumentParser(description="kubectl - Kubernetes 命令行工具")
    subparsers = parser.add_subparsers(dest="command", help="可用命令")
    
    # 全局参数
    parser.add_argument("--namespace", "-n", default="default", help="指定命名空间")
    parser.add_argument("--all-namespaces", "-A", action="store_true", help="查看所有命名空间")
    
    # get 命令
    get_parser = subparsers.add_parser("get", help="显示一个或多个资源")
    get_parser.add_argument("resource", choices=["nodes", "pods", "services", "svc", "replicasets", "rs", "hpa", "function"],
                           help="资源类型")
    get_parser.add_argument("name", nargs="?", help="资源名称")
    
    # describe 命令  
    describe_parser = subparsers.add_parser("describe", help="显示特定资源的详细信息")
    describe_parser.add_argument("resource", choices=["node", "pod", "service", "svc", "replicaset", "rs", "hpa", "function"],
                                help="资源类型")
    describe_parser.add_argument("name", help="资源名称")
    
    # create 命令
    create_parser = subparsers.add_parser("create", help="从文件或stdin创建资源")
    create_parser.add_argument("-f", "--filename", required=True, help="文件名")
    
    # apply 命令 (新增)
    apply_parser = subparsers.add_parser("apply", help="通过文件名或stdin对资源进行配置")
    apply_parser.add_argument("-f", "--filename", required=True, help="文件名")
    
    # add 命令 (专门用于节点加入)
    add_parser = subparsers.add_parser("add", help="添加节点到集群")
    add_parser.add_argument("resource", choices=["node"], help="资源类型")
    add_parser.add_argument("filename", help="节点配置文件")
    
    # delete 命令
    delete_parser = subparsers.add_parser("delete", help="删除资源")
    delete_parser.add_argument("resource", choices=["pod", "service", "svc", "replicaset", "rs", "hpa", "function"],
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
            elif args.resource in ["function"]:
                print("Fetching functions...")
                kubectl.get_functions(namespace=args.namespace, all_namespaces=args.all_namespaces)
                
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
            elif args.resource in ["function"]:
                kubectl.describe_function(args.name, namespace=args.namespace)
                
        elif args.command == "create":
            # 根据文件内容判断资源类型
            kubectl.apply_from_file(args.filename)  # 使用统一的 apply 方法
            
        elif args.command == "apply":
            # 新的 apply 命令
            kubectl.apply_from_file(args.filename)
            
        elif args.command == "add":
            # 专门用于节点加入
            if args.resource == "node":
                kubectl.add_node_from_file(args.filename)
            
        elif args.command == "delete":
            if args.resource == "pod":
                kubectl.delete_pod(args.name, namespace=args.namespace)
            elif args.resource in ["service", "svc"]:
                kubectl.delete_service(args.name, namespace=args.namespace)
            elif args.resource in ["replicaset", "rs"]:
                kubectl.delete_replicaset(args.name, namespace=args.namespace)
            elif args.resource == "hpa":
                kubectl.delete_hpa(args.name, namespace=args.namespace)
            elif args.resource == "function":
                kubectl.delete_function(args.name, namespace=args.namespace)
                
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