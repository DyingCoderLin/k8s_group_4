import threading
import logging
from typing import Set, Optional, Dict, List
from confluent_kafka import Producer, Consumer, KafkaError
import json
import time


class NodePortManager:
    """NodePort端口管理器，负责NodePort端口分配、冲突检测和全局协调"""
    
    # NodePort端口范围配置
    NODEPORT_RANGE_START = 30000
    NODEPORT_RANGE_END = 32767
    
    def __init__(self, kafka_config: dict = None, namespace: str = "default"):
        self.logger = logging.getLogger(__name__)
        self.namespace = namespace
        
        # NodePort端口分配状态
        self._allocated_ports: Set[int] = set()  # 已分配的端口
        self._port_to_service: Dict[int, str] = {}  # 端口到服务的映射
        self._service_to_port: Dict[str, int] = {}  # 服务到端口的映射
        self._lock = threading.RLock()  # 线程安全锁
        
        # Kafka配置（用于跨节点协调）
        self.kafka_config = kafka_config
        self.producer = None
        self.consumer = None
        self.running = False
        
        if kafka_config:
            self._init_kafka()
    
    def _init_kafka(self):
        """初始化Kafka生产者和消费者"""
        try:
            # 配置生产者
            producer_config = {
                'bootstrap.servers': self.kafka_config['bootstrap_servers'],
                'acks': 'all',
                'retries': 3
            }
            self.producer = Producer(producer_config)
            
            # 配置消费者
            consumer_config = {
                'bootstrap.servers': self.kafka_config['bootstrap_servers'],
                'group.id': f'nodeport-manager-{self.namespace}',
                'auto.offset.reset': 'latest',
                'enable.auto.commit': False,
                'max.poll.interval.ms': 600000,  # 10分钟
                'session.timeout.ms': 30000,     # 30秒
                'heartbeat.interval.ms': 10000,  # 10秒
                'request.timeout.ms': 60000,     # 60秒
            }
            
            self.consumer = Consumer(consumer_config)
            self.consumer.subscribe([f'nodeport.{self.namespace}'])
            
            self.logger.info("NodePort管理器Kafka客户端初始化成功")
            
        except Exception as e:
            self.logger.error(f"初始化Kafka客户端失败: {e}")
    
    def start_daemon(self):
        """启动NodePort管理器守护进程"""
        if not self.consumer:
            self.logger.warning("未配置Kafka，NodePort管理器将以单机模式运行")
            return
            
        self.running = True
        daemon_thread = threading.Thread(target=self._daemon_loop, daemon=True)
        daemon_thread.start()
        self.logger.info("NodePort管理器守护进程已启动")
    
    def stop_daemon(self):
        """停止NodePort管理器守护进程"""
        self.running = False
        if self.consumer:
            self.consumer.close()
        if self.producer:
            self.producer.flush()
        self.logger.info("NodePort管理器守护进程已停止")
    
    def _daemon_loop(self):
        """守护进程主循环，处理跨节点协调"""
        while self.running:
            try:
                msg = self.consumer.poll(timeout=1.0)
                if msg is not None:
                    if not msg.error():
                        self._handle_port_coordination(msg)
                        self.consumer.commit(asynchronous=False)
                    elif msg.error().code() != KafkaError._PARTITION_EOF:
                        self.logger.error(f"NodePort Kafka消费错误: {msg.error()}")
                
                time.sleep(0.1)
                
            except Exception as e:
                self.logger.error(f"NodePort管理器守护进程异常: {e}")
                time.sleep(1)
    
    def _handle_port_coordination(self, msg):
        """处理端口协调消息"""
        try:
            action = msg.key().decode('utf-8') if msg.key() else "ALLOCATE"
            data = json.loads(msg.value().decode('utf-8'))
            
            service_name = data.get('service_name')
            port = data.get('port')
            
            with self._lock:
                if action == "ALLOCATE":
                    self._allocated_ports.add(port)
                    self._port_to_service[port] = service_name
                    self._service_to_port[service_name] = port
                elif action == "DEALLOCATE":
                    self._allocated_ports.discard(port)
                    self._port_to_service.pop(port, None)
                    self._service_to_port.pop(service_name, None)
            
            self.logger.info(f"处理NodePort协调消息: {action} - {service_name}:{port}")
            
        except Exception as e:
            self.logger.error(f"处理NodePort协调消息失败: {e}")
    
    def validate_nodeport_range(self, port: int) -> bool:
        """验证NodePort端口是否在有效范围内"""
        return self.NODEPORT_RANGE_START <= port <= self.NODEPORT_RANGE_END
    
    def is_port_available(self, port: int, exclude_service: str = None) -> bool:
        """检查端口是否可用"""
        with self._lock:
            if port in self._allocated_ports:
                # 如果端口被当前服务占用，则认为可用（更新场景）
                allocated_service = self._port_to_service.get(port)
                return allocated_service == exclude_service
            return True
    
    def allocate_port(self, service_name: str, requested_port: Optional[int] = None) -> int:
        """
        为服务分配NodePort端口
        
        Args:
            service_name: 服务名称
            requested_port: 请求的特定端口（可选）
            
        Returns:
            分配的端口号
            
        Raises:
            ValueError: 端口验证失败或无可用端口
        """
        with self._lock:
            # 如果服务已经有分配的端口，先释放
            if service_name in self._service_to_port:
                old_port = self._service_to_port[service_name]
                self.deallocate_port(service_name, notify_cluster=False)
                self.logger.info(f"释放服务 {service_name} 的旧端口: {old_port}")
            
            if requested_port is not None:
                # 验证请求的端口
                if not self.validate_nodeport_range(requested_port):
                    raise ValueError(
                        f"NodePort端口 {requested_port} 超出有效范围 "
                        f"({self.NODEPORT_RANGE_START}-{self.NODEPORT_RANGE_END})"
                    )
                
                if not self.is_port_available(requested_port, exclude_service=service_name):
                    allocated_service = self._port_to_service.get(requested_port, "未知服务")
                    raise ValueError(
                        f"NodePort端口 {requested_port} 已被服务 {allocated_service} 占用"
                    )
                
                allocated_port = requested_port
            else:
                # 自动分配端口
                allocated_port = self._find_available_port()
                if allocated_port is None:
                    raise ValueError(
                        f"NodePort端口范围 ({self.NODEPORT_RANGE_START}-{self.NODEPORT_RANGE_END}) "
                        "内没有可用端口"
                    )
            
            # 记录端口分配
            self._allocated_ports.add(allocated_port)
            self._port_to_service[allocated_port] = service_name
            self._service_to_port[service_name] = allocated_port
            
            # 通知集群其他节点
            self._notify_cluster_allocation(service_name, allocated_port)
            
            self.logger.info(f"为服务 {service_name} 分配NodePort端口: {allocated_port}")
            return allocated_port
    
    def deallocate_port(self, service_name: str, notify_cluster: bool = True) -> bool:
        """
        释放服务的NodePort端口
        
        Args:
            service_name: 服务名称
            notify_cluster: 是否通知集群其他节点
            
        Returns:
            是否成功释放端口
        """
        with self._lock:
            if service_name not in self._service_to_port:
                self.logger.warning(f"服务 {service_name} 没有分配的NodePort端口")
                return False
            
            port = self._service_to_port[service_name]
            
            # 释放端口
            self._allocated_ports.discard(port)
            self._port_to_service.pop(port, None)
            self._service_to_port.pop(service_name, None)
            
            # 通知集群其他节点
            if notify_cluster:
                self._notify_cluster_deallocation(service_name, port)
            
            self.logger.info(f"释放服务 {service_name} 的NodePort端口: {port}")
            return True
    
    def _find_available_port(self) -> Optional[int]:
        """查找第一个可用的NodePort端口"""
        for port in range(self.NODEPORT_RANGE_START, self.NODEPORT_RANGE_END + 1):
            if port not in self._allocated_ports:
                return port
        return None
    
    def _notify_cluster_allocation(self, service_name: str, port: int):
        """通知集群其他节点端口分配"""
        if not self.producer:
            return
            
        try:
            message = {
                'service_name': service_name,
                'port': port,
                'timestamp': time.time()
            }
            
            self.producer.produce(
                topic=f'nodeport.{self.namespace}',
                key="ALLOCATE",
                value=json.dumps(message)
            )
            self.producer.flush()
            
        except Exception as e:
            self.logger.error(f"通知集群端口分配失败: {e}")
    
    def _notify_cluster_deallocation(self, service_name: str, port: int):
        """通知集群其他节点端口释放"""
        if not self.producer:
            return
            
        try:
            message = {
                'service_name': service_name,
                'port': port,
                'timestamp': time.time()
            }
            
            self.producer.produce(
                topic=f'nodeport.{self.namespace}',
                key="DEALLOCATE",
                value=json.dumps(message)
            )
            self.producer.flush()
            
        except Exception as e:
            self.logger.error(f"通知集群端口释放失败: {e}")
    
    def get_allocated_ports(self) -> Dict[str, int]:
        """获取所有已分配的端口映射"""
        with self._lock:
            return self._service_to_port.copy()
    
    def get_service_by_port(self, port: int) -> Optional[str]:
        """根据端口获取服务名"""
        with self._lock:
            return self._port_to_service.get(port)
    
    def get_allocation_stats(self) -> Dict:
        """获取端口分配统计信息"""
        with self._lock:
            total_ports = self.NODEPORT_RANGE_END - self.NODEPORT_RANGE_START + 1
            allocated_count = len(self._allocated_ports)
            
            return {
                "total_ports": total_ports,
                "allocated_count": allocated_count,
                "available_count": total_ports - allocated_count,
                "utilization_rate": (allocated_count / total_ports) * 100,
                "allocated_ports": sorted(list(self._allocated_ports)),
                "port_range": f"{self.NODEPORT_RANGE_START}-{self.NODEPORT_RANGE_END}",
                "allocations": self._service_to_port.copy()
            }
    
    def validate_service_nodeport(self, service_name: str, node_port: Optional[int]) -> int:
        """
        验证并处理服务的NodePort配置
        
        Args:
            service_name: 服务名称
            node_port: 配置的NodePort端口（可选）
            
        Returns:
            最终分配的NodePort端口
            
        Raises:
            ValueError: 验证失败
        """
        if node_port is not None:
            # 验证指定的端口
            if not self.validate_nodeport_range(node_port):
                raise ValueError(
                    f"NodePort端口 {node_port} 必须在范围 "
                    f"{self.NODEPORT_RANGE_START}-{self.NODEPORT_RANGE_END} 内"
                )
            
            return self.allocate_port(service_name, node_port)
        else:
            # 自动分配端口
            return self.allocate_port(service_name)
