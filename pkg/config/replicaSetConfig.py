class ReplicaSetConfig():
    def __init__(self, arg_json):
        # --- static information ---
        metadata = arg_json.get('metadata', {})
        self.name = metadata.get('name')
        self.namespace = metadata.get('namespace', 'default')
        self.labels = metadata.get('labels', {})
        
        spec = arg_json.get('spec', {})
        self.replica_count = spec.get('replicas', 1)  # 期望的副本数量
        self.selector = spec.get('selector')
        self.template = spec.get('template')
        
        # --- running information ---
        # 这些信息在一开始被创建的时候不会被赋值，但是需要预先留出
        self.status = None
        self.current_replicas = 0  # 当前实际的副本数量
        self.pod_instances = []    # 属于该ReplicaSet的Pod名称列表
        self.hpa_controlled = False  # 是否由HPA控制
        
    # 重命名方法，不要覆盖特殊方法__dict__
    def to_dict(self):
        return {
            'metadata': {
                'name': self.name,
                'namespace': self.namespace,
                'labels': self.labels
            },
            'spec': {
                'replicas': self.replica_count,
                'selector': self.selector,
                'template': self.template
            },
            'status': self.status,
            'current_replicas': self.current_replicas,
            'pod_instances': self.pod_instances,
            'hpa_controlled': self.hpa_controlled
        }
        
    # 添加__getstate__和__setstate__以支持pickle序列化/反序列化
    def __getstate__(self):
        return self.to_dict()
        
    def __setstate__(self, state):
        self.__init__(state)