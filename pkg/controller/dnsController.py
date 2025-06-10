import logging
import json
import subprocess
import threading
import time
from typing import Dict
from pkg.config.dnsConfig import DNSConfig
from pkg.apiObject.dns import DNS
from pkg.apiServer.apiClient import ApiClient
from pkg.config.uriConfig import URIConfig

class DNSController:
    """DNSController 类，负责管理 DNS 资源并生成 Nginx 配置文件"""
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        
        self.api_client = None
        self.uri_config = None
        self.set_api_client()
        
        self.dns_objects = {}  # {namespace/name: DNS}
        self.nginx_conf_path = "\conf\nginx.conf"
        self.running = False
        self.sync_interval = 10  # 同步间隔（秒）
        
        print("DNSController 初始化完成")

    def set_api_client(self, api_client = None, uri_config = None):
        """设置API客户端，用于与API Server通信"""
        self.api_client = api_client or ApiClient()
        self.uri_config = uri_config or URIConfig()
        return self

    def _ensure_api_client(self):
        """确保 API 客户端已初始化"""
        if not self.api_client:
            self.api_client = ApiClient()
            self.uri_config = URIConfig()

    def start(self):
        """启动 DNSController，监听 DNS 资源并启动同步循环"""
        if self.running:
            # print("DNSController 已经在运行")
            print("DNSController 已经在运行")
            return
        self.running = True

        print("[INFO] 开始 DNS 同步循环")
        threading.Thread(target=self._sync_loop, daemon=True).start()

    def stop(self):
        """停止 DNSController"""
        self.running = False
        # self.dns_objects.clear()
        # self._update_nginx_config()  # 清空 Nginx 配置
        print("DNSController 已停止")

    def _get_all_services(self):
        """从API Server获取所有Service"""
        print(f"[DEBUG]获取Service列表: ")
        try:
            # 获取指定namespace的Service
            services_url = self.uri_config.GLOBAL_SERVICES_URL
            response = self.api_client.get(services_url)
            
            print(f"[DEBUG]获取Service列表: {response}")
            
            if response:
                return response
            return []
            
        except Exception as e:
            print(f"获取Service列表失败: {e}")
            return []
    
    def _sync_loop(self):
        """定期同步 DNS 记录"""
        while self.running:
            try:
                self.sync_dns_records()
                time.sleep(self.sync_interval)

            except Exception as e:
                self.logger.error(f"DNS 同步失败: {e}")
                time.sleep(self.sync_interval)

    def sync_dns_records(self):
        """同步所有 DNS 记录"""
        print("[INFO] 开始同步 sync_dns_records")
        try:
            dns_url = self.uri_config.DNS_URL.format(namespace = "default")
            response = self.api_client.get(dns_url)
            print(f"[INFO] 找到 {len(response)} 个 DNS 资源")
            # print(f"[INFO]获取 DNS 资源: {response}")

            if not response:
                print("[INFO] 没有找到 DNS 资源")
                return

            current_dns = set()
            for dns_data in response:
                try:
                    dns_config = DNSConfig(dns_data)
                    key = f"{dns_config.namespace}/{dns_config.name}"
                    print(f"处理 DNS 资源 namespace/name: {key}")
                    print(f"{dns_data}")

                    current_dns.add(key)
                    self.dns_objects[key] = DNS(dns_config)

                    # if key in self.dns_objects:
                    #     self.dns_objects[key].update_dns_records()
                    # else:
                    #     self.dns_objects[key] = DNS(dns_config)

                except Exception as e:
                    print(f"处理 DNS {key} 失败: {e}")

            # 清理不存在的 DNS 资源
            for key in list(self.dns_objects.keys()):
                if key not in current_dns:
                    print(f"删除 DNS 资源: {key}")
                    del self.dns_objects[key]

            # for key, dns in self.dns_objects.items():
            #     print(f"{dns.to_dict()}")

            self._update_nginx_config()
            print("DNS 记录同步完成")
        except Exception as e:
            self.logger.error(f"DNS 记录同步失败: {e}")

    def _update_nginx_config(self):
        """更新 Nginx 配置文件并重载"""
        try:
            config_content = self._generate_nginx_config()
            nginx_conf = os.path.join(config.CONFIG_FILE_PATH, "nginx.conf")

            with open(nginx_conf, "w") as f:
                f.write(config_content)

            # nginx-configmap.yaml
            configmap_lines = []
            configmap_lines.append(f"apiVersion: v1")
            configmap_lines.append(f"kind: ConfigMap")
            configmap_lines.append(f"metadata:")
            configmap_lines.append(f"    name: nginx-config")
            configmap_lines.append(f"    namespace: default")
            configmap_lines.append(f"data:")
            configmap_lines.append(f"    nginx.conf: |")
            for line in config_content.splitlines():
                configmap_lines.append(f"        {line}")
            
            configmap_content = "\n".join(configmap_lines)
            configmap_file = os.path.join(config.CONFIG_FILE_PATH, "nginx-configmap.yaml")
            with open(configmap_file, "w") as f:
                f.write(configmap_content)

            # # 重载 Nginx
            # result = subprocess.run(["nginx", "-s", "reload"], capture_output=True, text=True)
            # if result.returncode == 0:
            #     print("Nginx 配置更新并重载成功")
            #     return True
            # else:
            #     self.logger.error(f"Nginx 重载失败: {result.stderr}")
            #     return False

        except Exception as e:
            self.logger.error(f"更新 Nginx 配置失败: {e}")
            return False
        
    def _generate_nginx_config(self) -> str:
        """生成 Nginx 配置文件内容"""
        config_lines = []
        config_lines.append(f"events {{")
        config_lines.append(f"    worker_connections 1024;")
        config_lines.append(f"}}")
        
        config_lines.append(f"http {{")
        config_lines.append(f"    include mime.types;")
        config_lines.append(f"    default_type application/octet-stream;")

        for key, dns in self.dns_objects.items():
            print(f"生成 Nginx 配置: {key}\n{dns.to_dict()}")
            
            config_lines.append(f"    server {{")
            config_lines.append(f"        listen 80;")
            config_lines.append(f"        server_name {dns.config.host};")
            config_lines.append(f"")

            for path in dns.config.paths:
                dns_key = f"{dns.config.host}{path.get("path")}"
                if(dns.dns_records.get(dns_key)):
                    service_name, cluster_ip, ports = dns.dns_records[dns_key]
                    print(f"DNS 解析成功: {dns_key} -> ({service_name}, {cluster_ip}, {ports})")
                    
                    config_lines.append(f"        location {path.get('path')} {{")
                    config_lines.append(f"            proxy_pass http://{cluster_ip}:{ports[0]["port"]};")
                    config_lines.append(f"            proxy_set_header Host $host;")
                    config_lines.append(f"        }}")
            config_lines.append(f"    }}")

            # print(f"{config_lines}")
        config_lines.append(f"}}")

        return "\n".join(config_lines)
        # return config_lines

    def get_stats(self) -> Dict:
        """获取 DNSController 统计信息"""
        return {
            "total_dns": len(self.dns_objects),
            "dns_objects": [
                {"key": key, "stats": dns.get_stats()}
                for key, dns in self.dns_objects.items()
            ]
        }

# 测试 DNS 类
if __name__ == "__main__":
    try:
        import yaml
        import os
        from pkg.config.globalConfig import GlobalConfig
        import requests

        dns_controller = DNSController()

        config = GlobalConfig()

        # service_file = "test-dns-service.yaml"
        # service_yaml = os.path.join(config.TEST_FILE_PATH, service_file)
        
        # print(f"[INFO]测试 SERVICE 配置文件路径: {service_yaml}")
        
        # with open(service_yaml, "r", encoding="utf-8") as file:
        #     service_data = yaml.safe_load(file)

        #     namespace = service_data["metadata"]["namespace"]
        #     name = service_data["metadata"]["name"]

        #     # 通过 API 创建 Service
        #     key = dns_controller.uri_config.SERVICE_SPEC_URL.format(namespace=namespace, name=name)
        #     response = dns_controller.api_client.post(key, service_data)
        #     if response:
        #         print(f"[INFO]测试 Service 配置: {namespace}/{name}\n")
        #     else:
        #         print(f"Error creating service/{name}\n")
        
        dns_file = "test-dns-cloud.yaml"
        dns_yaml = os.path.join(config.TEST_FILE_PATH, dns_file)

        print(f"[INFO]测试 DNS 配置文件路径: {dns_yaml}")

        with open(dns_yaml, "r", encoding="utf-8") as file:
            data = yaml.safe_load(file)

            namespace = data["metadata"]["namespace"]
            name = data["metadata"]["name"]


            dns_url = dns_controller.uri_config.DNS_SPEC_URL.format(namespace = namespace, name = name)
            response = dns_controller.api_client.post(dns_url, data)

            print(f"[INFO]测试 DNS 配置: {namespace}/{name}\n")

         # 启动 DNSController
        dns_controller.start()

        # 保持主线程运行
        print("[INFO] DNSController 正在运行，按 Ctrl+C 退出")
        try:
            while True:
                time.sleep(1)  # 主线程保持运行
        except KeyboardInterrupt:
            print("[INFO] 收到终止信号，停止 DNSController")
            dns_controller.stop()

    except Exception as e:
        print(f"[ERROR]测试 DNS 失败: {e}")

