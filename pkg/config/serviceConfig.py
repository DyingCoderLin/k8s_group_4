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
        self.type = spec.get("type", "ClusterIP")  # 支持ClusterIP和NodePort
        self.cluster_ip = spec.get("clusterIP", None)  # 虚拟IP，由系统分配
        self.selector = spec.get("selector", {})  # Pod选择器
        self.ports = spec.get("ports", [])  # 端口配置
        
        # NodePort特定配置
        self.node_port = None
        if self.type == "NodePort":
            for port_config in self.ports:
                if "nodePort" in port_config:
                    self.node_port = port_config["nodePort"]
                    break
        
        # 运行时状态
        self.status = "Pending"  # Pending, Running, Failed
        
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
                "ports": self.ports,
            },
            "status": self.status
        }
    
    def get_port_config(self, target_port=None):
        """获取端口配置"""
        if not self.ports:
            return None
            
        if target_port is None:
            return self.ports[0]  # 返回第一个端口配置
            
        for port_config in self.ports:
            if port_config.get("targetPort") == target_port or port_config.get("port") == target_port:
                return port_config
        return None
    
    def matches_pod(self, pod_labels):
        """检查Pod标签是否匹配Service的选择器"""
        if not self.selector or not pod_labels:
            return False
            
        for key, value in self.selector.items():
            if key not in pod_labels or pod_labels[key] != value:
                return False
        return True
