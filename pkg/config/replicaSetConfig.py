class ReplicaSetConfig():
    def __init__(self, arg_json):
        # --- static information ---
        print(f"[DEBUG]ReplicaSetConfig init: {arg_json}")
        metadata = arg_json.get('metadata', {})
        self.name = metadata.get('name')
        self.namespace = metadata.get('namespace', 'default')
        self.labels = metadata.get('labels', {})
        
        spec = arg_json.get('spec', {})
        self.replica_count = spec.get('replicas', 1)  # 期望的副本数量
        self.selector = spec.get('selector')
        if 'matchLabels' not in self.selector:
            self.selector['matchLabels'] = {}
        # self.template = spec.get('tesmplate')
        
        # --- running information ---
        # 这些信息在一开始被创建的时候不会被赋值，但是需要预先留出
        # print(f"[DEBUG] __init__ received status: {arg_json.get('status')}")
        # print(f"[DEBUG] __init__ received current_replicas: {arg_json.get('current_replicas')}")
        # print(f"[DEBUG] __init__ received pod_instances: {arg_json.get('pod_instances')}")
        self.status = arg_json.get('status', [])
        self.current_replicas = arg_json.get('current_replicas', [])
        self.pod_instances = arg_json.get('pod_instances', [])
        self.hpa_controlled = arg_json.get('hpa_controlled', False)
        # print(f"[DEBUG] __init__ self attribute, status: {self.status}")
        # print(f"[DEBUG] __init__ self attribute, current_replicas: {self.current_replicas}")
        # print(f"[DEBUG] __init__ self attribute, pod_instances: {self.pod_instances}")
        
    # 重命名方法，不要覆盖特殊方法__dict__
    def to_dict(self):
        # print(f"[DEBUG]ReplicaSetConfig to_dict: {self.__dict__}")
        return {
            'metadata': {
                'name': self.name,
                'namespace': self.namespace,
                'labels': self.labels
            },
            'spec': {
                'replicas': self.replica_count,
                'selector': self.selector,
                # 'template': self.template
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
        # self.__dict__.update(state)
        
    def get_selector_app(self):
        """
        获取ReplicaSet的应用标签
        :return: 应用标签
        """
        if self.selector and 'matchLabels' in self.selector:
            return self.selector['matchLabels'].get('app', None)
        return None
    
    def get_selector_env(self):
        """
        获取ReplicaSet的环境标签
        :return: 环境标签
        """
        if self.selector and 'matchLabels' in self.selector:
            return self.selector['matchLabels'].get('env', None)
        return None
    
    # 提供方法，便于管理pod_instances
     # 添加管理pod_instances的实用方法
    def add_pod_group(self, base_pod_name):
        """添加一个新的pod组，以base_pod_name作为基础"""
        # 检查是否已存在同名的pod组
        for group in self.pod_instances:
            if group and group[0] == base_pod_name:
                print(f"[INFO] Pod group '{base_pod_name}' already exists, please check")
                return group  # 已存在该组，直接返回
        # 创建新pod组
        new_group = [base_pod_name]
        self.pod_instances.append(new_group)
        return new_group
        
    def add_pod_replica(self, base_pod_name, replica_name):
        """向指定的pod组添加一个副本"""
        # 查找或创建pod组
        target_group = None
        for group in self.pod_instances:
            if group and group[0] == base_pod_name:
                target_group = group
                break
                
        if not target_group:
            target_group = self.add_pod_group(base_pod_name)
            
        # 添加副本（如果不存在）
        if replica_name not in target_group:
            target_group.append(replica_name)
            self.current_replicas += 1
            
        return target_group
        
    def remove_pod_replica(self, replica_name):
        """移除指定的pod副本"""
        for group in self.pod_instances:
            if replica_name in group:
                # 如果是组的第一个元素（基础pod），则保留
                if group[0] == replica_name and len(group) > 1:
                    continue
                    
                group.remove(replica_name)
                self.current_replicas -= 1
                
                # 如果组为空，移除整个组
                if not group or (len(group) == 1 and group[0] != replica_name):
                    self.pod_instances.remove(group)
                return True
                
        return False
        
    # 计算当前副本总数
    def count_group_replicas(self,base_pod_name):
        """计算指定pod组的副本总数"""
        for group in self.pod_instances:
            if group and group[0] == base_pod_name:
                return len(group)
        print(f"[INFO] Pod group '{base_pod_name}' not found")
        return 0
    
    # 获取所有group
    def get_all_groups(self):
        """获取所有pod组的base pod名称"""
        groups = []
        for group in self.pod_instances:
            if group:
                groups.append(group[0])
        return groups
    