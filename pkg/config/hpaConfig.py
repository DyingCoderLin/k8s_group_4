class HorizontalPodAutoscalerConfig:
    def __init__(self, arg_json):
        # --- static information ---
        metadata = arg_json.get('metadata', {})
        self.name = metadata.get('name')
        self.namespace = metadata.get('namespace', 'default')
        self.labels = metadata.get('labels', {})
        
        spec = arg_json.get('spec', {})
        
        # 目标资源
        target_ref = spec.get('scaleTargetRef', {})
        self.target_kind = target_ref.get('kind', 'ReplicaSet')
        self.target_name = target_ref.get('name')
        
        # 副本数量限制
        self.min_replicas = spec.get('minReplicas', 1)
        self.max_replicas = spec.get('maxReplicas', 10)
        
        # 指标
        self.metrics = spec.get('metrics', [])
        
        # 冷却时间
        self.cooldown_seconds = spec.get('behavior', {}).get('scaleDown', {}).get('stabilizationWindowSeconds', 60)
        
        # --- running information ---
        self.status = None