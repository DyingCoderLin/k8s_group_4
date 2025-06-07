import subprocess
import logging
import platform
import shutil
import json
import sys
from typing import List, Optional
from confluent_kafka import Consumer, KafkaError
from threading import Thread
from time import sleep


class KubeProxy:
    """Service代理类，负责管理iptables规则和NAT转换"""
    
    def __init__(self, node_name: str = None, kafka_config: dict = None):
        self.logger = logging.getLogger(__name__)
        self.nat_chain = "KUBE-SERVICES"
        self.endpoint_chain_prefix = "KUBE-SVC-"
        
        # 节点信息
        self.node_name = node_name
        
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
            topic = self.kafka_config.SERVICE_PROXY_TOPIC.format(name=self.node_name)
            consumer_config = {
                'bootstrap.servers': self.kafka_config.BOOTSTRAP_SERVER,
                'group.id': f'kubeproxy-{self.node_name}',
                'auto.offset.reset': 'latest',
                'enable.auto.commit': False,
            }
            
            self.consumer = Consumer(consumer_config)
            self.consumer.subscribe([topic])
            self.logger.info(f"KubeProxy已订阅Kafka主题: {topic}")
            
        except Exception as e:
            self.logger.error(f"初始化Kafka消费者失败: {e}")
    
    def start_daemon(self):
        """启动KubeProxy守护进程"""
        if not self.consumer:
            self.logger.warning("未配置Kafka消费者，KubeProxy将以静态模式运行")
            return
            
        self.running = True
        daemon_thread = Thread(target=self._daemon_loop, daemon=True)
        daemon_thread.start()
        self.logger.info(f"KubeProxy守护进程已启动，节点: {self.node_name}")
    
    def stop_daemon(self):
        """停止KubeProxy守护进程"""
        self.running = False
        if self.consumer:
            self.consumer.close()
        self.logger.info("KubeProxy守护进程已停止")
    
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
                self.logger.error(f"KubeProxy守护进程异常: {e}")
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
            
            self.logger.info(f"收到Service {action}消息: {service_name}")
            
            if action == "CREATE" or action == "UPDATE":
                self.create_service_rules(
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
        """设置基础iptables链"""
        if self.is_macos or not self.iptables_available:
            self.logger.info("跳过在非Linux系统上设置iptables链")
            return
            
        try:
            # 创建KUBE-SERVICES链
            self._run_iptables(["-t", "nat", "-N", self.nat_chain], ignore_errors=True)
            
            # 将PREROUTING和OUTPUT流量导向KUBE-SERVICES链
            self._run_iptables([
                "-t", "nat", "-I", "PREROUTING", "-j", self.nat_chain
            ], ignore_errors=True)
            
            self._run_iptables([
                "-t", "nat", "-I", "OUTPUT", "-j", self.nat_chain
            ], ignore_errors=True)
            
            self.logger.info("基础iptables链设置完成")
        except Exception as e:
            self.logger.error(f"设置基础iptables链失败: {e}")
    
    def create_service_rules(self, service_name: str, cluster_ip: str, port: int, 
                           protocol: str, endpoints: List[str], node_port: Optional[int] = None):
        """为Service创建iptables规则"""
        if self.is_macos or not self.iptables_available:
            self.logger.info(f"模拟创建Service {service_name}的iptables规则 (ClusterIP: {cluster_ip}:{port})")
            return
            
        try:
            chain_name = f"{self.endpoint_chain_prefix}{service_name.upper()}"
            
            # 清理可能存在的旧规则
            self.delete_service_rules(service_name, cluster_ip, port, protocol, node_port)
            
            if not endpoints:
                self.logger.warning(f"Service {service_name} 没有可用的端点")
                return
            
            # 创建service专用链
            self._run_iptables(["-t", "nat", "-N", chain_name], ignore_errors=True)
            
            # 添加ClusterIP规则：将发往ClusterIP的流量导向service链
            self._run_iptables([
                "-t", "nat", "-A", self.nat_chain,
                "-d", cluster_ip,
                "-p", protocol.lower(),
                "--dport", str(port),
                "-j", chain_name
            ])
            
            # 如果是NodePort类型，添加NodePort规则
            if node_port:
                self._run_iptables([
                    "-t", "nat", "-A", self.nat_chain,
                    "-p", protocol.lower(),
                    "--dport", str(node_port),
                    "-j", chain_name
                ])
            
            # 为每个端点创建DNAT规则（负载均衡）
            endpoint_count = len(endpoints)
            for i, endpoint in enumerate(endpoints):
                endpoint_ip, endpoint_port = endpoint.split(":")
                
                if i == endpoint_count - 1:
                    # 最后一个端点不需要概率判断
                    self._run_iptables([
                        "-t", "nat", "-A", chain_name,
                        "-p", protocol.lower(),
                        "-j", "DNAT",
                        "--to-destination", endpoint
                    ])
                else:
                    # 使用statistic模块实现负载均衡
                    probability = 1.0 / (endpoint_count - i)
                    self._run_iptables([
                        "-t", "nat", "-A", chain_name,
                        "-p", protocol.lower(),
                        "-m", "statistic",
                        "--mode", "random",
                        "--probability", f"{probability:.6f}",
                        "-j", "DNAT",
                        "--to-destination", endpoint
                    ])
            
            self.logger.info(f"为Service {service_name} 创建了iptables规则")
            
        except Exception as e:
            self.logger.error(f"为Service {service_name} 创建iptables规则失败: {e}")
            raise
    
    def delete_service_rules(self, service_name: str, cluster_ip: str, port: int, 
                           protocol: str, node_port: Optional[int] = None):
        """删除Service的iptables规则"""
        if self.is_macos or not self.iptables_available:
            self.logger.info(f"模拟删除Service {service_name}的iptables规则")
            return
            
        try:
            chain_name = f"{self.endpoint_chain_prefix}{service_name.upper()}"
            
            # 删除主链中指向service链的规则
            self._run_iptables([
                "-t", "nat", "-D", self.nat_chain,
                "-d", cluster_ip,
                "-p", protocol.lower(),
                "--dport", str(port),
                "-j", chain_name
            ], ignore_errors=True)
            
            if node_port:
                self._run_iptables([
                    "-t", "nat", "-D", self.nat_chain,
                    "-p", protocol.lower(),
                    "--dport", str(node_port),
                    "-j", chain_name
                ], ignore_errors=True)
            
            # 清空并删除service专用链
            self._run_iptables(["-t", "nat", "-F", chain_name], ignore_errors=True)
            self._run_iptables(["-t", "nat", "-X", chain_name], ignore_errors=True)
            
            self.logger.info(f"删除了Service {service_name} 的iptables规则")
            
        except Exception as e:
            self.logger.error(f"删除Service {service_name} iptables规则失败: {e}")
    
    def update_service_endpoints(self, service_name: str, cluster_ip: str, port: int,
                               protocol: str, endpoints: List[str], node_port: Optional[int] = None):
        """更新Service的端点"""
        if self.is_macos or not self.iptables_available:
            self.logger.info(f"模拟更新Service {service_name}的端点: {endpoints}")
            return
        
        self.logger.info(f"更新Service {service_name} 的端点: {endpoints}")    
        self.create_service_rules(service_name, cluster_ip, port, protocol, endpoints, node_port)
    
    def _run_iptables(self, args: List[str], ignore_errors: bool = False):
        """执行iptables命令"""
        if self.is_macos or not self.iptables_available:
            # 在不支持iptables的环境中模拟成功
            self.logger.debug(f"模拟iptables命令: iptables {' '.join(args)}")
            return None
            
        cmd = ["iptables"] + args
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            self.logger.debug(f"iptables命令执行成功: {' '.join(cmd)}")
            return result
        except subprocess.CalledProcessError as e:
            if not ignore_errors:
                self.logger.error(f"iptables命令执行失败: {' '.join(cmd)}, 错误: {e.stderr}")
                raise
            else:
                self.logger.debug(f"iptables命令执行失败(忽略): {' '.join(cmd)}, 错误: {e.stderr}")
    
    def cleanup_all_rules(self):
        """清理所有Service相关的iptables规则"""
        if self.is_macos or not self.iptables_available:
            self.logger.info("模拟清理所有Service iptables规则")
            return
            
        try:
            # 清空KUBE-SERVICES链
            self._run_iptables(["-t", "nat", "-F", self.nat_chain], ignore_errors=True)
            
            # 清理所有KUBE-SVC-*链
            result = subprocess.run(
                ["iptables", "-t", "nat", "-L", "-n"], 
                capture_output=True, text=True
            )
            
            for line in result.stdout.split('\n'):
                if self.endpoint_chain_prefix in line:
                    chain_name = line.split()[1] if len(line.split()) > 1 else None
                    if chain_name and chain_name.startswith(self.endpoint_chain_prefix):
                        self._run_iptables(["-t", "nat", "-F", chain_name], ignore_errors=True)
                        self._run_iptables(["-t", "nat", "-X", chain_name], ignore_errors=True)
            
            self.logger.info("清理所有Service iptables规则完成")
            
        except Exception as e:
            self.logger.error(f"清理iptables规则失败: {e}")
    
    def get_service_stats(self, service_name: str) -> dict:
        """获取Service的iptables统计信息"""
        if self.is_macos or not self.iptables_available:
            # 在不支持iptables的环境中返回模拟数据
            return {
                "name": service_name,
                "connections": 0,
                "packets": 0,
                "bytes": 0,
                "note": "在不支持iptables的环境中运行，数据为模拟值"
            }
            
        try:
            chain_name = f"{self.endpoint_chain_prefix}{service_name.upper()}"
            result = subprocess.run(
                ["iptables", "-t", "nat", "-L", chain_name, "-n", "-v"],
                capture_output=True, text=True, check=True
            )
            
            stats = {"rules": [], "total_packets": 0, "total_bytes": 0}
            
            for line in result.stdout.split('\n'):
                if line.strip() and not line.startswith('Chain') and not line.startswith('target'):
                    parts = line.split()
                    if len(parts) >= 2:
                        packets = int(parts[0]) if parts[0].isdigit() else 0
                        bytes_count = int(parts[1]) if parts[1].isdigit() else 0
                        stats["rules"].append({
                            "packets": packets,
                            "bytes": bytes_count,
                            "rule": " ".join(parts[2:])
                        })
                        stats["total_packets"] += packets
                        stats["total_bytes"] += bytes_count
            
            return stats
            
        except subprocess.CalledProcessError:
            return {"error": f"Service {service_name} 统计信息不存在"}
        except Exception as e:
            return {"error": f"获取统计信息失败: {e}"}
    
def main():
    """KubeProxy主函数，在每个节点上启动"""
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
    parser = argparse.ArgumentParser(description='Kubernetes kubeProxy')
    parser.add_argument('--node-name', required=True, help='节点名称')
    parser.add_argument('--kafka-server', help='Kafka服务器地址', 
                       default='10.119.15.182:9092')
    parser.add_argument('--cleanup', action='store_true', help='清理所有iptables规则后退出')
    
    args = parser.parse_args()
    
    # 配置Kafka
    kafka_config = {
        'bootstrap_servers': args.kafka_server
    }
    
    # 创建KubeProxy实例
    service_proxy = KubeProxy(
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
        print(f"\n[INFO]收到退出信号 {signum}，正在关闭KubeProxy...")
        service_proxy.stop_daemon()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    print(f"[INFO]在节点 {args.node_name} 上启动KubeProxy...")
    print(f"[INFO]Kafka服务器: {args.kafka_server}")
    print(f"[INFO]iptables支持: {'否 (模拟模式)' if service_proxy.is_macos or not service_proxy.iptables_available else '是'}")
    
    # 启动守护进程
    service_proxy.start_daemon()
    
    print("[INFO]KubeProxy已启动，按 Ctrl+C 退出")
    
    # 保持主线程运行
    try:
        while True:
            sleep(1)
    except KeyboardInterrupt:
        print("\n[INFO]用户中断，正在关闭KubeProxy...")
        service_proxy.stop_daemon()


if __name__ == "__main__":
    main()
