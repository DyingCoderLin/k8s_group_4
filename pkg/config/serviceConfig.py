class ServiceConfig:
    """Service配置类，用于存储Service的配置信息"""
    
    def __init__(self, arg_json):
        # 基本元数据
        metadata = arg_json.get("metadata", {})
        self.name = metadata.get("name")
        self.namespace = metadata.get("namespace", "default")
        self.labels = metadata.get("labels", {})
        
        # Service规格
        spec = arg_json.get("spec", {})
        # 默认为ClusterIP类型
        self.type = spec.get("type", "ClusterIP")  # 支持ClusterIP和NodePort
        self.cluster_ip = spec.get("clusterIP", None)  # 虚拟IP，由系统分配
        self.selector = spec.get("selector", {})  # Pod选择器
        
        # 端口配置 - 只支持一个端口
        ports = spec.get("ports", [])
        if not ports:
            raise ValueError("Service must have at least one port configuration")
        if len(ports) > 1:
            raise ValueError("Only one port configuration is supported")
            
        port_config = ports[0]
        self.port_name = port_config.get("name", "default")
        self.port = int(port_config.get("port", 80))
        self.target_port = int(port_config.get("targetPort", 80))
        self.protocol = port_config.get("protocol", "TCP")
        
        # NodePort特定配置
        self.node_port = port_config.get("nodePort") if self.type == "NodePort" else None
        if self.node_port:
            self.node_port = int(self.node_port)
            self._validate_nodeport()
                
    def to_dict(self):
        """转换为字典格式"""
        return {
            "metadata": {
                "name": self.name,
                "namespace": self.namespace,
                "labels": self.labels,
            },
            "spec": {
                "type": self.type,
                "clusterIP": self.cluster_ip,
                "selector": self.selector,
                "ports": [{
                    "name": self.port_name,
                    "port": self.port,
                    "targetPort": self.target_port,
                    "protocol": self.protocol,
                    "nodePort": self.node_port if self.type == "NodePort" else None
                }]
            }
        }
    
    def get_port_config(self):
        """获取端口配置"""
        return {
            "name": self.port_name,
            "port": self.port,
            "targetPort": self.target_port,
            "protocol": self.protocol,
            "nodePort": self.node_port
        }
    
    def matches_pod(self, pod_labels):
        """检查Pod标签是否匹配Service的选择器"""
        if not self.selector or not pod_labels:
            return False
        print(f"[INFO]ServiceConfig.matches_pod: {self.selector} vs {pod_labels}")
            
        for key, value in self.selector.items():
            if key not in pod_labels or pod_labels[key] != value:
                return False
        return True
    
    def _validate_nodeport(self):
        """验证NodePort端口配置"""
        if self.node_port is None:
            return
            
        # NodePort端口范围验证
        NODEPORT_RANGE_START = 30000
        NODEPORT_RANGE_END = 32767
        
        if not (NODEPORT_RANGE_START <= self.node_port <= NODEPORT_RANGE_END):
            raise ValueError(
                f"NodePort端口 {self.node_port} 必须在范围 "
                f"{NODEPORT_RANGE_START}-{NODEPORT_RANGE_END} 内"
            )
    
    def get_nodeport_config(self):
        """获取NodePort配置信息"""
        if self.type != "NodePort":
            return None
            
        return {
            "nodePort": self.node_port,
            "port": self.port,
            "targetPort": self.target_port,
            "protocol": self.protocol
        }
    
    def is_nodeport_service(self):
        """检查是否为NodePort类型的服务"""
        return self.type == "NodePort"
