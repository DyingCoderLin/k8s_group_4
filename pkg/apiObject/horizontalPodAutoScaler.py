class STATUS:
    PENDING = 'PENDING'
    RUNNING = 'RUNNING'
    FAILED = 'FAILED'

class HorizontalPodAutoscaler:
    def __init__(self, config):
        self.config = config
        self.name = config.name
        self.namespace = config.namespace
        self.labels = config.labels
        self.status = STATUS.PENDING
        self.target_kind = config.target_kind  # 目标资源类型
        self.target_name = config.target_name  # 目标资源名称
        self.min_replicas = config.min_replicas
        self.max_replicas = config.max_replicas
        self.metrics = config.metrics  # 指标列表
        self.last_scale_time = None  # 上次缩放时间
        self.cooldown_seconds = config.cooldown_seconds or 60  # 冷却时间，默认60秒
        self.current_replicas = 0  # 当前副本数量
        self.target_replicas = 0  # 计算出的目标副本数量
        self.current_metrics = {}  # 当前指标值