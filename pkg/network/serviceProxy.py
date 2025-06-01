import subprocess
import logging
import platform
import shutil
from typing import List, Optional


class ServiceProxy:
    """Service代理类，负责管理iptables规则和NAT转换"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.nat_chain = "KUBE-SERVICES"
        self.endpoint_chain_prefix = "KUBE-SVC-"
        
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
                        "-j", "DNAT",
                        "--to-destination", endpoint
                    ])
                else:
                    # 使用statistic模块实现负载均衡
                    probability = 1.0 / (endpoint_count - i)
                    self._run_iptables([
                        "-t", "nat", "-A", chain_name,
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
