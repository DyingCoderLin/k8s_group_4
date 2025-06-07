import subprocess
import logging
import platform
import shutil
import json
import sys
import random
import string
from typing import List, Optional, Dict, Set
from confluent_kafka import Consumer, KafkaError
from threading import Thread
from time import sleep


class ServiceProxy:
    """Service代理类，负责管理iptables规则和NAT转换"""
    
    def __init__(self, node_name: str = None, kafka_config: dict = None):
        self.logger = logging.getLogger(__name__)
        
        # Kubernetes iptables链名称
        self.nat_chain = "KUBE-SERVICES"
        self.mark_chain = "KUBE-MARK-MASQ"
        self.postrouting_chain = "KUBE-POSTROUTING"
        self.service_chain_prefix = "KUBE-SVC-"
        self.endpoint_chain_prefix = "KUBE-SEP-"
        
        # 节点信息
        self.node_name = node_name
        
        # Service 和 Endpoint 链映射
        self.service_chains: Dict[str, str] = {}  # service_name -> chain_name
        self.endpoint_chains: Dict[str, List[str]] = {}  # service_name -> [endpoint_chain_names]
        
        # Kafka配置（用于接收ServiceController的规则更新）
        self.kafka_config = kafka_config
        self.consumer = None
        self.running = False
        
        # 检查是否在macOS上运行
        self.is_macos = platform.system() == "Darwin"
        # 检查iptables是否可用
        self.iptables_available = not self.is_macos and shutil.which('iptables') is not None
        
        if self.is_macos:
            self.logger.warning("在macOS上运行，iptables功能将被模拟")
        elif not self.iptables_available:
            self.logger.warning("iptables命令不可用，网络代理功能将被禁用")
        else:
            self.setup_base_chains()
            
        # 如果提供了Kafka配置，初始化消费者
        if self.kafka_config and self.node_name:
            self._init_kafka_consumer()
    
    def _init_kafka_consumer(self):
        """初始化Kafka消费者"""
        try:
            topic = f"serviceproxy.{self.node_name}"
            consumer_config = {
                'bootstrap.servers': self.kafka_config['bootstrap_servers'],
                'group.id': f'serviceproxy-{self.node_name}',
                'auto.offset.reset': 'latest',
                'enable.auto.commit': False,
            }
            
            self.consumer = Consumer(consumer_config)
            self.consumer.subscribe([topic])
            self.logger.info(f"ServiceProxy已订阅Kafka主题: {topic}")
            
        except Exception as e:
            self.logger.error(f"初始化Kafka消费者失败: {e}")
    
    def start_daemon(self):
        """启动ServiceProxy守护进程"""
        if not self.consumer:
            self.logger.warning("未配置Kafka消费者，ServiceProxy将以静态模式运行")
            return
            
        self.running = True
        daemon_thread = Thread(target=self._daemon_loop, daemon=True)
        daemon_thread.start()
        self.logger.info(f"ServiceProxy守护进程已启动，节点: {self.node_name}")
    
    def stop_daemon(self):
        """停止ServiceProxy守护进程"""
        self.running = False
        if self.consumer:
            self.consumer.close()
        self.logger.info("ServiceProxy守护进程已停止")
    
    def _daemon_loop(self):
        """守护进程主循环"""
        while self.running:
            try:
                msg = self.consumer.poll(timeout=1.0)
                if msg is not None:
                    if not msg.error():
                        self._handle_service_update(msg)
                        self.consumer.commit(asynchronous=False)
                    elif msg.error().code() != KafkaError._PARTITION_EOF:
                        self.logger.error(f"Kafka消费错误: {msg.error()}")
                
                sleep(0.1)  # 防止CPU占用过高
                
            except Exception as e:
                self.logger.error(f"ServiceProxy守护进程异常: {e}")
                sleep(1)
    
    def _handle_service_update(self, msg):
        """处理Service更新消息"""
        try:
            action = msg.key().decode('utf-8') if msg.key() else "UPDATE"
            data = json.loads(msg.value().decode('utf-8'))
            
            service_name = data.get('service_name')
            cluster_ip = data.get('cluster_ip')
            port = data.get('port')
            protocol = data.get('protocol', 'tcp')
            endpoints = data.get('endpoints', [])
            node_port = data.get('node_port')
            
            print(f"endpoints:{endpoints}")
            
            self.logger.info(f"收到Service {action}消息: {service_name}")
            
            if action == "CREATE":
                self.create_service_rules(
                    service_name, cluster_ip, port, protocol, endpoints, node_port
                )
            elif action == "UPDATE":
                # 使用智能增量更新
                self.update_service_endpoints(
                    service_name, cluster_ip, port, protocol, endpoints, node_port
                )
            elif action == "DELETE":
                self.delete_service_rules(
                    service_name, cluster_ip, port, protocol, node_port
                )
            else:
                self.logger.warning(f"未知的Service操作: {action}")
                
        except Exception as e:
            self.logger.error(f"处理Service更新消息失败: {e}")
    
    def setup_base_chains(self):
        """设置基础iptables链（按照Kubernetes标准）"""
        if self.is_macos or not self.iptables_available:
            self.logger.info("跳过在非Linux系统上设置iptables链")
            return
            
        try:
            # 1. 创建基础链（如果不存在）
            self._run_iptables(["-t", "nat", "-N", self.mark_chain], ignore_errors=True)
            self._run_iptables(["-t", "nat", "-N", self.postrouting_chain], ignore_errors=True)
            self._run_iptables(["-t", "nat", "-N", self.nat_chain], ignore_errors=True)
            
            # 2. 检查并设置基础链规则（避免重复）
            # KUBE-MARK-MASQ：用于标记需要SNAT的流量
            if not self._chain_has_mark_rule(self.mark_chain):
                # 清空链并添加正确的规则
                self._run_iptables(["-t", "nat", "-F", self.mark_chain])
                self._run_iptables([
                    "-t", "nat", "-A", self.mark_chain, 
                    "-j", "MARK", "--set-xmark", "0x4000/0x4000"
                ])
                self.logger.info(f"设置了 {self.mark_chain} 链的标记规则")
            
            # KUBE-POSTROUTING：处理被标记的流量
            if not self._chain_has_masquerade_rule(self.postrouting_chain):
                # 清空链并添加正确的规则
                self._run_iptables(["-t", "nat", "-F", self.postrouting_chain])
                self._run_iptables([
                    "-t", "nat", "-A", self.postrouting_chain,
                    "-m", "mark", "--mark", "0x4000/0x4000",
                    "-j", "MASQUERADE",
                    "-m", "comment", "--comment", "kubernetes service traffic requiring SNAT"
                ])
                self.logger.info(f"设置了 {self.postrouting_chain} 链的MASQUERADE规则")
            
            # 3. 设置主链跳转（检查是否已存在）
            if not self._rule_exists("PREROUTING", self.nat_chain):
                self._run_iptables([
                    "-t", "nat", "-I", "PREROUTING", "1", 
                    "-j", self.nat_chain,
                    "-m", "comment", "--comment", "kubernetes service portals"
                ])
                self.logger.info(f"添加了PREROUTING -> {self.nat_chain} 跳转规则")
            
            if not self._rule_exists("OUTPUT", self.nat_chain):
                self._run_iptables([
                    "-t", "nat", "-I", "OUTPUT", "1", 
                    "-j", self.nat_chain,
                    "-m", "comment", "--comment", "kubernetes service portals" 
                ])
                self.logger.info(f"添加了OUTPUT -> {self.nat_chain} 跳转规则")
            
            if not self._rule_exists("POSTROUTING", self.postrouting_chain):
                self._run_iptables([
                    "-t", "nat", "-I", "POSTROUTING", "1", 
                    "-j", self.postrouting_chain,
                    "-m", "comment", "--comment", "kubernetes postrouting rules"
                ])
                self.logger.info(f"添加了POSTROUTING -> {self.postrouting_chain} 跳转规则")
            
            self.logger.info("基础iptables链设置完成")
        except Exception as e:
            self.logger.error(f"设置基础iptables链失败: {e}")
            raise
    
    def create_service_rules(self, service_name: str, cluster_ip: str, port: int, 
                           protocol: str, endpoints: List[str], node_port: Optional[int] = None):
        """为Service创建iptables规则（按照Kubernetes标准）"""
        if self.is_macos or not self.iptables_available:
            self.logger.info(f"模拟创建Service {service_name}的iptables规则 (ClusterIP: {cluster_ip}:{port})")
            return
            
        try:
            # 1. 清理可能存在的旧规则
            self.delete_service_rules(service_name, cluster_ip, port, protocol, node_port)
            
            if not endpoints:
                self.logger.warning(f"Service {service_name} 没有可用的端点")
                return
            print(f"创建Service {service_name} 的iptables规则，端点: {endpoints}")
            
            # 2. 生成Service链名（使用一致的命名规则）
            service_chain = f"{self.service_chain_prefix}{service_name.upper().replace('-', '_')}"
            
            # 3. 创建Service专用链
            self._run_iptables(["-t", "nat", "-N", service_chain], ignore_errors=True)
            
            # 4. 为Service创建Endpoint链
            endpoint_chains = []
            
            for i, endpoint in enumerate(endpoints):
                # 生成随机的Endpoint链名
                sep_hash = self._generate_chain_hash()
                endpoint_chain = f"{self.endpoint_chain_prefix}{sep_hash}"
                endpoint_chains.append(endpoint_chain)
                
                # 创建Endpoint链
                self._run_iptables(["-t", "nat", "-N", endpoint_chain], ignore_errors=True)
                
                # 解析endpoint
                endpoint_ip, endpoint_port = endpoint.split(":")
                
                # 添加DNAT规则到Endpoint链
                self._run_iptables([
                    "-t", "nat", "-A", endpoint_chain,
                    "-p", protocol.lower(),
                    "-j", "DNAT",
                    "--to-destination", endpoint
                ])
                
                # 添加源地址标记规则（防止Pod访问自身Service）
                self._run_iptables([
                    "-t", "nat", "-A", endpoint_chain,
                    "-s", f"{endpoint_ip}/32",
                    "-j", self.mark_chain
                ])
            
            # 5. 在Service链中添加负载均衡规则（倒序添加）
            self._setup_load_balancing(service_chain, endpoint_chains, protocol)
            
            # 6. 添加ClusterIP入口规则（在KUBE-SERVICES链开头插入）
            # 先添加标记规则
            self._run_iptables([
                "-t", "nat", "-I", self.nat_chain, "1",
                "-d", f"{cluster_ip}/32",
                "-p", protocol.lower(),
                "-m", protocol.lower(), "--dport", str(port),
                "-j", self.mark_chain,
                "-m", "comment", "--comment", f"{service_name}: cluster IP"
            ])
            
            # 再添加跳转规则
            self._run_iptables([
                "-t", "nat", "-I", self.nat_chain, "2", 
                "-d", f"{cluster_ip}/32",
                "-p", protocol.lower(),
                "-m", protocol.lower(), "--dport", str(port),
                "-j", service_chain,
                "-m", "comment", "--comment", f"{service_name}: cluster IP"
            ])
            
            # 7. 如果是NodePort类型，添加NodePort规则
            if node_port:
                # NodePort标记规则
                self._run_iptables([
                    "-t", "nat", "-I", self.nat_chain, "1",
                    "-p", protocol.lower(),
                    "-m", protocol.lower(), "--dport", str(node_port),
                    "-j", self.mark_chain,
                    "-m", "comment", "--comment", f"{service_name}: nodePort"
                ])
                
                # NodePort跳转规则
                self._run_iptables([
                    "-t", "nat", "-I", self.nat_chain, "2",
                    "-p", protocol.lower(),
                    "-m", protocol.lower(), "--dport", str(node_port),
                    "-j", service_chain,
                    "-m", "comment", "--comment", f"{service_name}: nodePort"
                ])
                
                self.logger.info(f"为Service {service_name} 添加NodePort规则，端口: {node_port}")
            
            # 8. 更新映射
            self.service_chains[service_name] = service_chain
            self.endpoint_chains[service_name] = endpoint_chains
            
            self.logger.info(f"为Service {service_name} 创建了iptables规则，端点数: {len(endpoints)}")
            
        except Exception as e:
            self.logger.error(f"为Service {service_name} 创建iptables规则失败: {e}")
            raise
    
    def delete_service_rules(self, service_name: str, cluster_ip: str, port: int, 
                           protocol: str, node_port: Optional[int] = None):
        """删除Service的iptables规则（按照Kubernetes标准）"""
        if self.is_macos or not self.iptables_available:
            self.logger.info(f"模拟删除Service {service_name}的iptables规则")
            return
            
        try:
            # 生成Service链名（确保与创建时一致）
            service_chain = f"{self.service_chain_prefix}{service_name.upper().replace('-', '_')}"
            
            # 1. 删除KUBE-SERVICES链中的入口规则（可能有多条重复规则）
            # 删除ClusterIP标记规则
            while True:
                result = self._run_iptables([
                    "-t", "nat", "-D", self.nat_chain,
                    "-d", f"{cluster_ip}/32",
                    "-p", protocol.lower(),
                    "-m", protocol.lower(), "--dport", str(port),
                    "-j", self.mark_chain,
                    "-m", "comment", "--comment", f"{service_name}: cluster IP"
                ], ignore_errors=True)
                if not result:
                    break
            
            # 删除ClusterIP跳转规则
            while True:
                result = self._run_iptables([
                    "-t", "nat", "-D", self.nat_chain,
                    "-d", f"{cluster_ip}/32",
                    "-p", protocol.lower(),
                    "-m", protocol.lower(), "--dport", str(port),
                    "-j", service_chain,
                    "-m", "comment", "--comment", f"{service_name}: cluster IP"
                ], ignore_errors=True)
                if not result:
                    break
            
            # 2. 如果是NodePort，删除NodePort规则
            if node_port:
                # 删除NodePort标记规则
                while True:
                    result = self._run_iptables([
                        "-t", "nat", "-D", self.nat_chain,
                        "-p", protocol.lower(),
                        "-m", protocol.lower(), "--dport", str(node_port),
                        "-j", self.mark_chain,
                        "-m", "comment", "--comment", f"{service_name}: nodePort"
                    ], ignore_errors=True)
                    if not result:
                        break
                
                # 删除NodePort跳转规则
                while True:
                    result = self._run_iptables([
                        "-t", "nat", "-D", self.nat_chain,
                        "-p", protocol.lower(),
                        "-m", protocol.lower(), "--dport", str(node_port),
                        "-j", service_chain,
                        "-m", "comment", "--comment", f"{service_name}: nodePort"
                    ], ignore_errors=True)
                    if not result:
                        break
                
                self.logger.info(f"删除了Service {service_name} 的NodePort规则")
            
            # 3. 清理Service和Endpoint链
            self._cleanup_service_chains(service_name)
            
            self.logger.info(f"删除了Service {service_name} 的所有iptables规则")
            
        except Exception as e:
            self.logger.error(f"删除Service {service_name} iptables规则失败: {e}")
    
    def update_service_endpoints(self, service_name: str, cluster_ip: str, port: int,
                               protocol: str, endpoints: List[str], node_port: Optional[int] = None):
        """智能更新Service的端点（支持增量更新）"""
        if self.is_macos or not self.iptables_available:
            self.logger.info(f"模拟更新Service {service_name}的端点: {endpoints}")
            return
        
        try:
            # 如果Service不存在，直接创建
            if service_name not in self.service_chains:
                self.logger.info(f"Service {service_name} 不存在，创建新的Service规则")
                self.create_service_rules(service_name, cluster_ip, port, protocol, endpoints, node_port)
                return
            
            # 获取当前的端点信息
            current_endpoints = set()
            if service_name in self.endpoint_chains:
                # 通过iptables规则反推当前端点
                for endpoint_chain in self.endpoint_chains[service_name]:
                    try:
                        result = subprocess.run(
                            ["iptables", "-t", "nat", "-L", endpoint_chain, "-n"],
                            capture_output=True, text=True, check=True
                        )
                        
                        for line in result.stdout.split('\n'):
                            if 'DNAT' in line and 'to:' in line:
                                # 提取目标地址
                                parts = line.split()
                                for i, part in enumerate(parts):
                                    if part == 'to:' and i + 1 < len(parts):
                                        current_endpoints.add(parts[i + 1])
                                        break
                    except:
                        continue
            
            # 计算需要添加和删除的端点
            new_endpoints = set(endpoints)
            endpoints_to_add = new_endpoints - current_endpoints
            endpoints_to_remove = current_endpoints - new_endpoints
            
            self.logger.info(f"Service {service_name} 端点更新: "
                           f"添加 {len(endpoints_to_add)} 个, 删除 {len(endpoints_to_remove)} 个")
            print(f"添加的端点: {endpoints_to_add}")
            print(f"删除的端点: {endpoints_to_remove}")
            
            # 如果变化较大，直接重建（超过一半的端点变化）
            if (len(endpoints_to_add) + len(endpoints_to_remove)) > len(current_endpoints) / 2:
                self.logger.info(f"Service {service_name} 端点变化较大，重建所有规则")
                self.create_service_rules(service_name, cluster_ip, port, protocol, endpoints, node_port)
                return
            
            # 增量更新
            service_chain = self.service_chains[service_name]
            
            # 删除不需要的端点
            for endpoint_to_remove in endpoints_to_remove:
                self._remove_endpoint_from_service(service_name, endpoint_to_remove, protocol)
            
            # 添加新的端点
            for endpoint_to_add in endpoints_to_add:
                self._add_endpoint_to_service(service_name, service_chain, endpoint_to_add, protocol)
            
            # 如果有变化，重新设置负载均衡
            if endpoints_to_add or endpoints_to_remove:
                self._rebuild_load_balancing(service_name, service_chain, endpoints, protocol)
            
            self.logger.info(f"Service {service_name} 端点更新完成")
            
        except Exception as e:
            self.logger.error(f"更新Service {service_name} 端点失败: {e}")
            # 失败时回退到完全重建
            self.logger.info(f"回退到完全重建Service {service_name}")
            self.create_service_rules(service_name, cluster_ip, port, protocol, endpoints, node_port)
    
    def _add_endpoint_to_service(self, service_name: str, service_chain: str, endpoint: str, protocol: str):
        """向Service添加新的端点"""
        try:
            # 创建新的Endpoint链
            sep_hash = self._generate_chain_hash()
            endpoint_chain = f"{self.endpoint_chain_prefix}{sep_hash}"
            
            self._run_iptables(["-t", "nat", "-N", endpoint_chain], ignore_errors=True)
            
            # 解析endpoint
            endpoint_ip, endpoint_port = endpoint.split(":")
            
            # 添加DNAT规则
            self._run_iptables([
                "-t", "nat", "-A", endpoint_chain,
                "-p", protocol.lower(),
                "-j", "DNAT",
                "--to-destination", endpoint
            ])
            
            # 添加源地址标记规则
            self._run_iptables([
                "-t", "nat", "-A", endpoint_chain,
                "-s", f"{endpoint_ip}/32",
                "-j", self.mark_chain
            ])
            
            # 更新映射
            if service_name not in self.endpoint_chains:
                self.endpoint_chains[service_name] = []
            self.endpoint_chains[service_name].append(endpoint_chain)
            
            self.logger.debug(f"为Service {service_name} 添加端点 {endpoint}")
            
        except Exception as e:
            self.logger.error(f"添加端点失败: {e}")
            raise
    
    def _remove_endpoint_from_service(self, service_name: str, endpoint: str, protocol: str):
        """从Service移除端点"""
        try:
            if service_name not in self.endpoint_chains:
                return
            
            # 找到对应的端点链
            endpoint_chain_to_remove = None
            for endpoint_chain in self.endpoint_chains[service_name]:
                try:
                    result = subprocess.run(
                        ["iptables", "-t", "nat", "-L", endpoint_chain, "-n"],
                        capture_output=True, text=True, check=True
                    )
                    
                    if f"to:{endpoint}" in result.stdout:
                        endpoint_chain_to_remove = endpoint_chain
                        break
                except:
                    continue
            
            if endpoint_chain_to_remove:
                # 清理链
                self._run_iptables(["-t", "nat", "-F", endpoint_chain_to_remove], ignore_errors=True)
                self._run_iptables(["-t", "nat", "-X", endpoint_chain_to_remove], ignore_errors=True)
                
                # 更新映射
                self.endpoint_chains[service_name].remove(endpoint_chain_to_remove)
                
                self.logger.debug(f"从Service {service_name} 移除端点 {endpoint}")
            
        except Exception as e:
            self.logger.error(f"移除端点失败: {e}")
    
    def _rebuild_load_balancing(self, service_name: str, service_chain: str, endpoints: List[str], protocol: str):
        """重建Service链的负载均衡规则"""
        try:
            # 清空Service链
            self._run_iptables(["-t", "nat", "-F", service_chain], ignore_errors=True)
            
            # 获取当前的端点链
            if service_name in self.endpoint_chains:
                endpoint_chains = self.endpoint_chains[service_name]
                self._setup_load_balancing(service_chain, endpoint_chains, protocol)
                
        except Exception as e:
            self.logger.error(f"重建负载均衡失败: {e}")
            raise
    
    def list_all_service_chains(self) -> Dict[str, Dict]:
        """列出所有Service相关的链信息"""
        result = {
            "services": {},
            "total_service_chains": len(self.service_chains),
            "total_endpoint_chains": sum(len(chains) for chains in self.endpoint_chains.values())
        }
        
        for service_name in self.service_chains:
            service_info = {
                "service_chain": self.service_chains[service_name],
                "endpoint_chains": self.endpoint_chains.get(service_name, []),
                "endpoint_count": len(self.endpoint_chains.get(service_name, []))
            }
            
            # 如果可以访问iptables，获取规则统计
            if not self.is_macos and self.iptables_available:
                try:
                    stats = self.get_service_stats(service_name)
                    service_info["stats"] = stats
                except:
                    service_info["stats"] = {"error": "无法获取统计信息"}
            
            result["services"][service_name] = service_info
        
        return result
    
    def validate_service_rules(self, service_name: str) -> Dict[str, bool]:
        """验证Service的iptables规则是否完整"""
        if self.is_macos or not self.iptables_available:
            return {"validated": False, "reason": "iptables不可用"}
        
        validation = {
            "service_chain_exists": False,
            "endpoint_chains_exist": True,
            "main_chain_rules_exist": False,
            "load_balancing_rules_exist": False
        }
        
        try:
            # 检查Service链是否存在
            if service_name in self.service_chains:
                service_chain = self.service_chains[service_name]
                result = subprocess.run(
                    ["iptables", "-t", "nat", "-L", service_chain, "-n"],
                    capture_output=True, text=True
                )
                validation["service_chain_exists"] = result.returncode == 0
                
                # 检查负载均衡规则
                if validation["service_chain_exists"]:
                    validation["load_balancing_rules_exist"] = len(result.stdout.split('\n')) > 3
            
            # 检查Endpoint链
            if service_name in self.endpoint_chains:
                for endpoint_chain in self.endpoint_chains[service_name]:
                    result = subprocess.run(
                        ["iptables", "-t", "nat", "-L", endpoint_chain, "-n"],
                        capture_output=True, text=True
                    )
                    if result.returncode != 0:
                        validation["endpoint_chains_exist"] = False
                        break
            
            # 检查主链规则
            result = subprocess.run(
                ["iptables", "-t", "nat", "-L", self.nat_chain, "-n"],
                capture_output=True, text=True
            )
            if result.returncode == 0:
                validation["main_chain_rules_exist"] = service_name.upper() in result.stdout
            
        except Exception as e:
            validation["error"] = str(e)
        
        return validation
    
    def get_all_kubernetes_chains(self) -> List[str]:
        """获取所有Kubernetes相关的iptables链"""
        chains = []
        
        if self.is_macos or not self.iptables_available:
            return chains
        
        try:
            result = subprocess.run(
                ["iptables", "-t", "nat", "-L", "-n"],
                capture_output=True, text=True, check=True
            )
            
            for line in result.stdout.split('\n'):
                if line.startswith('Chain '):
                    parts = line.split()
                    if len(parts) >= 2:
                        chain_name = parts[1]
                        if (chain_name.startswith('KUBE-') or 
                            chain_name in [self.nat_chain, self.mark_chain, self.postrouting_chain]):
                            chains.append(chain_name)
        
        except Exception as e:
            self.logger.error(f"获取Kubernetes链列表失败: {e}")
        
        return chains
    
    def get_service_stats(self, service_name: str) -> dict:
        """获取Service的iptables统计信息"""
        if self.is_macos or not self.iptables_available:
            # 在不支持iptables的环境中返回模拟数据
            return {
                "service_name": service_name,
                "service_chain": f"{self.service_chain_prefix}{service_name.upper().replace('-', '_')}",
                "endpoint_chains": [],
                "total_packets": 0,
                "total_bytes": 0,
                "note": "在不支持iptables的环境中运行，数据为模拟值"
            }
            
        try:
            stats = {
                "service_name": service_name,
                "service_chain": None,
                "endpoint_chains": [],
                "total_packets": 0,
                "total_bytes": 0
            }
            
            # 获取Service链统计
            if service_name in self.service_chains:
                service_chain = self.service_chains[service_name]
                stats["service_chain"] = service_chain
                
                try:
                    result = subprocess.run(
                        ["iptables", "-t", "nat", "-L", service_chain, "-n", "-v"],
                        capture_output=True, text=True, check=True
                    )
                    
                    for line in result.stdout.split('\n'):
                        if line.strip() and not line.startswith('Chain') and not line.startswith('target'):
                            parts = line.split()
                            if len(parts) >= 2 and parts[0].isdigit():
                                packets = int(parts[0])
                                bytes_count = int(parts[1])
                                stats["total_packets"] += packets
                                stats["total_bytes"] += bytes_count
                except:
                    pass
            
            # 获取Endpoint链统计
            if service_name in self.endpoint_chains:
                for endpoint_chain in self.endpoint_chains[service_name]:
                    endpoint_stat = {"chain": endpoint_chain, "packets": 0, "bytes": 0}
                    
                    try:
                        result = subprocess.run(
                            ["iptables", "-t", "nat", "-L", endpoint_chain, "-n", "-v"],
                            capture_output=True, text=True, check=True
                        )
                        
                        for line in result.stdout.split('\n'):
                            if line.strip() and not line.startswith('Chain') and not line.startswith('target'):
                                parts = line.split()
                                if len(parts) >= 2 and parts[0].isdigit():
                                    endpoint_stat["packets"] += int(parts[0])
                                    endpoint_stat["bytes"] += int(parts[1])
                    except:
                        pass
                    
                    stats["endpoint_chains"].append(endpoint_stat)
            
            return stats
            
        except Exception as e:
            return {"error": f"获取Service {service_name} 统计信息失败: {e}"}
    
    def cleanup_all_rules(self):
        """清理所有Kubernetes相关的iptables规则"""
        if self.is_macos or not self.iptables_available:
            self.logger.info("模拟清理所有iptables规则")
            return
        
        try:
            # 1. 获取所有Kubernetes链
            kube_chains = self.get_all_kubernetes_chains()
            
            # 2. 清理主链中的跳转规则
            self._cleanup_base_chains()
            
            # 3. 清理所有Service相关的链
            for service_name in list(self.service_chains.keys()):
                self._cleanup_service_chains(service_name)
            
            # 4. 清理基础链
            for chain in [self.mark_chain, self.postrouting_chain, self.nat_chain]:
                self._run_iptables(["-t", "nat", "-F", chain], ignore_errors=True)
                self._run_iptables(["-t", "nat", "-X", chain], ignore_errors=True)
            
            # 5. 清理任何残留的Kubernetes链
            for chain in kube_chains:
                if chain.startswith(('KUBE-SVC-', 'KUBE-SEP-')):
                    self._run_iptables(["-t", "nat", "-F", chain], ignore_errors=True)
                    self._run_iptables(["-t", "nat", "-X", chain], ignore_errors=True)
            
            # 6. 清空映射
            self.service_chains.clear()
            self.endpoint_chains.clear()
            
            self.logger.info("所有Kubernetes iptables规则已清理")
            
        except Exception as e:
            self.logger.error(f"清理所有规则失败: {e}")

    def reset_and_reinit_base_chains(self):
        """重置并重新初始化基础链（用于故障恢复）"""
        if self.is_macos or not self.iptables_available:
            self.logger.info("跳过在非Linux系统上重置iptables链")
            return
        
        try:
            self.logger.info("开始重置Kubernetes基础链...")
            
            # 1. 完全清理现有基础链
            self._cleanup_base_chains()
            
            # 2. 重新设置基础链
            self.setup_base_chains()
            
            self.logger.info("基础链重置完成")
            
        except Exception as e:
            self.logger.error(f"重置基础链失败: {e}")
            raise

    def _run_iptables(self, args: List[str], ignore_errors: bool = False):
        """执行iptables命令"""
        if self.is_macos or not self.iptables_available:
            # 在不支持iptables的环境中记录命令但不执行
            cmd_str = " ".join(["iptables"] + args)
            self.logger.debug(f"模拟执行: {cmd_str}")
            return True
            
        try:
            result = subprocess.run(
                ["iptables"] + args,
                capture_output=True,
                text=True,
                check=not ignore_errors
            )
            
            if result.returncode != 0 and not ignore_errors:
                self.logger.error(f"iptables命令失败: {' '.join(['iptables'] + args)}")
                self.logger.error(f"错误输出: {result.stderr}")
                raise subprocess.CalledProcessError(result.returncode, args)
                
            return result.returncode == 0
            
        except subprocess.CalledProcessError as e:
            if not ignore_errors:
                self.logger.error(f"iptables命令执行失败: {e}")
                raise
            return False
        except Exception as e:
            self.logger.error(f"执行iptables命令时出现异常: {e}")
            if not ignore_errors:
                raise
            return False
    
    def _generate_chain_hash(self) -> str:
        """生成随机链哈希"""
        return ''.join(random.choices(string.ascii_uppercase + string.digits, k=10))
    
    def _cleanup_service_chains(self, service_name: str):
        """清理Service相关的所有链"""
        # 清理Service链
        if service_name in self.service_chains:
            service_chain = self.service_chains[service_name]
            self._run_iptables(["-t", "nat", "-F", service_chain], ignore_errors=True)
            self._run_iptables(["-t", "nat", "-X", service_chain], ignore_errors=True)
            del self.service_chains[service_name]
        
        # 清理Endpoint链
        if service_name in self.endpoint_chains:
            for endpoint_chain in self.endpoint_chains[service_name]:
                self._run_iptables(["-t", "nat", "-F", endpoint_chain], ignore_errors=True)
                self._run_iptables(["-t", "nat", "-X", endpoint_chain], ignore_errors=True)
            del self.endpoint_chains[service_name]
    
    def _setup_load_balancing(self, service_chain: str, endpoint_chains: List[str], protocol: str):
        """在Service链中设置负载均衡规则（正确的Kubernetes Round-Robin算法）"""
        endpoint_count = len(endpoint_chains)
        
        if endpoint_count == 0:
            self.logger.warning(f"Service链 {service_chain} 没有可用的端点")
            return
        
        if endpoint_count == 1:
            # 只有一个端点，直接跳转
            self._run_iptables([
                "-t", "nat", "-A", service_chain,
                "-j", endpoint_chains[0],
                "-m", "comment", "--comment", "single endpoint"
            ])
            self.logger.info(f"单端点Service，直接跳转到 {endpoint_chains[0]}")
            return
        
        # 多端点场景：实现正确的均匀负载均衡
        # Kubernetes标准算法：每个端点获得相等的流量分配
        
        self.logger.info(f"开始为Service链 {service_chain} 设置 {endpoint_count} 个端点的负载均衡规则")
        
        for i in range(endpoint_count):
            endpoint_chain = endpoint_chains[i]
            
            if i == endpoint_count - 1:
                # 最后一个端点：无条件跳转（处理所有剩余流量）
                self._run_iptables([
                    "-t", "nat", "-A", service_chain,
                    "-j", endpoint_chain,
                    "-m", "comment", "--comment", f"fallback to endpoint {i+1}/{endpoint_count}"
                ])
                self.logger.debug(f"端点 {i+1}/{endpoint_count}: 默认处理剩余流量 -> {endpoint_chain}")
            else:
                # 前面的端点：使用正确的概率跳转
                # 关键修复：每个端点在剩余流量中的概率
                remaining_endpoints = endpoint_count - i
                probability = 1.0 / remaining_endpoints
                
                self._run_iptables([
                    "-t", "nat", "-A", service_chain,
                    "-m", "statistic",
                    "--mode", "random", 
                    "--probability", f"{probability:.6f}",
                    "-j", endpoint_chain,
                    "-m", "comment", "--comment", f"endpoint {i+1}/{endpoint_count} ({probability:.1%})"
                ])
                
                # 详细的负载均衡分析日志
                actual_share = probability
                for j in range(i):
                    prev_remaining = endpoint_count - j
                    prev_prob = 1.0 / prev_remaining
                    actual_share *= (1 - prev_prob)
                
                self.logger.debug(f"端点 {i+1}/{endpoint_count}: 规则概率={probability:.2%}, 实际分配≈{actual_share:.2%} -> {endpoint_chain}")
        
        # 验证负载均衡配置
        self._log_load_balancing_summary(endpoint_count)
        self.logger.info(f"✅ Service链 {service_chain} 负载均衡规则设置完成")

    def _log_load_balancing_summary(self, endpoint_count: int):
        """输出负载均衡配置摘要"""
        self.logger.info("📊 负载均衡分配摘要:")
        
        cumulative_prob = 1.0
        for i in range(endpoint_count):
            if i == endpoint_count - 1:
                # 最后一个端点获得所有剩余流量
                actual_share = cumulative_prob
                self.logger.info(f"   端点 {i+1}: {actual_share:.1%} (默认)")
            else:
                remaining = endpoint_count - i
                rule_prob = 1.0 / remaining
                actual_share = cumulative_prob * rule_prob
                cumulative_prob *= (1 - rule_prob)
                self.logger.info(f"   端点 {i+1}: {actual_share:.1%} (规则概率: {rule_prob:.1%})")
        
        # 理论验证：每个端点应该得到大约 1/endpoint_count 的流量
        expected_share = 1.0 / endpoint_count
        self.logger.info(f"   📋 理论均分: 每个端点应获得 {expected_share:.1%} 流量")

    def _cleanup_base_chains(self):
        """完全清理基础链规则（仅在需要重置时使用）"""
        try:
            self.logger.info("开始完全清理Kubernetes基础链规则...")
            
            # 1. 删除主链中的跳转规则
            while self._rule_exists("PREROUTING", self.nat_chain):
                self._run_iptables([
                    "-t", "nat", "-D", "PREROUTING", 
                    "-j", self.nat_chain,
                    "-m", "comment", "--comment", "kubernetes service portals"
                ], ignore_errors=True)
            
            while self._rule_exists("OUTPUT", self.nat_chain):
                self._run_iptables([
                    "-t", "nat", "-D", "OUTPUT", 
                    "-j", self.nat_chain,
                    "-m", "comment", "--comment", "kubernetes service portals" 
                ], ignore_errors=True)
            
            while self._rule_exists("POSTROUTING", self.postrouting_chain):
                self._run_iptables([
                    "-t", "nat", "-D", "POSTROUTING", 
                    "-j", self.postrouting_chain,
                    "-m", "comment", "--comment", "kubernetes postrouting rules"
                ], ignore_errors=True)
            
            # 2. 清空并删除基础链
            for chain in [self.mark_chain, self.postrouting_chain, self.nat_chain]:
                self._run_iptables(["-t", "nat", "-F", chain], ignore_errors=True)
                self._run_iptables(["-t", "nat", "-X", chain], ignore_errors=True)
            
            self.logger.info("基础链规则清理完成")
                
        except Exception as e:
            self.logger.warning(f"清理基础链时出现异常: {e}")

    def _rule_exists(self, chain: str, target_chain: str) -> bool:
        """检查指定链中是否存在跳转到目标链的规则"""
        try:
            result = subprocess.run(
                ["iptables", "-t", "nat", "-L", chain, "-n", "--line-numbers"],
                capture_output=True, text=True, check=True
            )
            # 更精确的匹配：查找 "-j target_chain" 或者 "target" 列包含目标链
            lines = result.stdout.split('\n')
            for line in lines:
                if f" {target_chain} " in line or line.strip().endswith(f" {target_chain}"):
                    return True
            return False
        except:
            return False
        
    def _chain_has_mark_rule(self, chain_name: str) -> bool:
        """检查链中是否已有正确的MARK规则"""
        try:
            result = subprocess.run(
                ["iptables", "-t", "nat", "-L", chain_name, "-n"],
                capture_output=True, text=True, check=True
            )
            # 检查是否有 MARK 规则和正确的标记值
            return "MARK" in result.stdout and "0x4000/0x4000" in result.stdout
        except:
            return False
    
    def _chain_has_masquerade_rule(self, chain_name: str) -> bool:
        """检查链中是否已有正确的MASQUERADE规则"""
        try:
            result = subprocess.run(
                ["iptables", "-t", "nat", "-L", chain_name, "-n"],
                capture_output=True, text=True, check=True
            )
            # 检查是否有 MASQUERADE 规则和正确的标记匹配
            return "MASQUERADE" in result.stdout and "0x4000/0x4000" in result.stdout
        except:
            return False

def main():
    """ServiceProxy主函数，在每个节点上启动"""
    import argparse
    import signal
    import os
    from pkg.config.globalConfig import GlobalConfig
    
    # 设置日志
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout),
        ]
    )
    
    # 解析命令行参数
    parser = argparse.ArgumentParser(description='Kubernetes ServiceProxy - kube-proxy替代')
    parser.add_argument('--node-name', required=True, help='节点名称')
    parser.add_argument('--kafka-server', help='Kafka服务器地址', 
                       default='10.119.15.182:9092')
    parser.add_argument('--cleanup', action='store_true', help='清理所有iptables规则后退出')
    
    args = parser.parse_args()
    
    # 配置Kafka
    kafka_config = {
        'bootstrap_servers': args.kafka_server
    }
    
    # 创建ServiceProxy实例
    service_proxy = ServiceProxy(
        node_name=args.node_name,
        kafka_config=kafka_config
    )
    
    # 如果是清理模式
    if args.cleanup:
        print(f"[INFO]清理节点 {args.node_name} 的所有Service iptables规则...")
        service_proxy.cleanup_all_rules()
        print("[INFO]清理完成")
        return
    
    # 设置信号处理
    def signal_handler(signum, frame):
        print(f"\n[INFO]收到退出信号 {signum}，正在关闭ServiceProxy...")
        service_proxy.stop_daemon()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    print(f"[INFO]在节点 {args.node_name} 上启动ServiceProxy...")
    print(f"[INFO]Kafka服务器: {args.kafka_server}")
    print(f"[INFO]iptables支持: {'否 (模拟模式)' if service_proxy.is_macos or not service_proxy.iptables_available else '是'}")
    
    # 启动守护进程
    service_proxy.start_daemon()
    
    print("[INFO]ServiceProxy已启动，按 Ctrl+C 退出")
    
    # 保持主线程运行
    try:
        while True:
            sleep(1)
    except KeyboardInterrupt:
        print("\n[INFO]用户中断，正在关闭ServiceProxy...")
        service_proxy.stop_daemon()


if __name__ == "__main__":
    main()
