class HorizontalPodAutoscalerConfig:
    def __init__(self, arg_json):
        # --- static information ---
        metadata = arg_json.get('metadata', {})
        self.name = metadata.get('name')
        self.namespace = metadata.get('namespace', 'default')
        
        spec = arg_json.get('spec', {})
        
        # 目标资源
        target_ref = spec.get('scaleTargetRef', {})
        self.target_kind = target_ref.get('kind', 'ReplicaSet')
        self.target_name = target_ref.get('name')
        
        # 副本数量限制
        self.min_replicas = spec.get('minReplicas', 1)
        self.max_replicas = spec.get('maxReplicas', 10)
        # 这个变量表示因为资源受限而导致的当前副本数量
        self.current_replicas = spec.get('currentReplicas', 0)
        
        # 指标验证和处理
        metrics = spec.get('metrics', [])
        self._validate_metrics(metrics)
        self.metrics = metrics
        
        print(f"[DEBUG] HPAConfig init: {self.to_dict()}")
        
    def _validate_metrics(self, metrics):
        """
        验证指标配置是否有效
        - 至少包含一个有效的资源指标(CPU或内存)
        - 不允许有其他类型的资源指标
        """
        if not metrics:
            raise ValueError("HPA配置必须至少包含一个指标")
            
        valid_resources = ["cpu", "memory"]
        found_valid_resource = False
        
        for metric in metrics:
            if metric.get('type') != 'Resource':
                continue
                
            resource = metric.get('resource', {})
            resource_name = resource.get('name', '').lower()
            
            if resource_name not in valid_resources:
                raise ValueError(f"不支持的资源指标类型: {resource_name}，仅支持: {', '.join(valid_resources)}")
                
            # 验证target配置
            target = resource.get('target', {})
            if not target or 'type' not in target:
                raise ValueError(f"资源指标 {resource_name} 必须指定target类型")
                
            if resource_name in valid_resources:
                found_valid_resource = True
                
        if not found_valid_resource:
            raise ValueError("HPA配置必须至少包含一个CPU或内存资源指标")
    
    def to_dict(self):
        """转换为字典格式用于API返回或序列化"""
        return {
            'metadata': {
                'name': self.name,
                'namespace': self.namespace
                # 移除了labels字段
            },
            'spec': {
                'scaleTargetRef': {
                    'apiVersion': 'apps/v1',
                    'kind': self.target_kind,
                    'name': self.target_name
                },
                'minReplicas': self.min_replicas,
                'maxReplicas': self.max_replicas,
                'metrics': self.metrics
            }
        }
    
    # 添加__getstate__和__setstate__以支持pickle序列化/反序列化
    def __getstate__(self):
        """序列化时返回对象的属性字典"""
        return self.__dict__.copy()
        
    def __setstate__(self, state):
        """反序列化时直接恢复对象的属性字典"""
        self.__dict__.update(state)
        
    def __str__(self):
        return f"HPA({self.name}, target={self.target_kind}:{self.target_name}, min={self.min_replicas}, max={self.max_replicas})"