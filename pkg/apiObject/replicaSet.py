class STATUS:
    PENDING = 'PENDING'
    RUNNING = 'RUNNING'
    FAILED = 'FAILED'

class ReplicaSet:
    def __init__(self, config):
        self.config = config
        self.name = config.name
        self.namespace = config.namespace
        self.labels = config.labels
        self.status = STATUS.PENDING
        self.desired_replicas = config.replica_count
        self.current_replicas = 0
        self.selector = config.selector
        self.pod_template = config.template
        self.pod_instances = []  # 存储属于该ReplicaSet的Pod名称列表
        self.hpa_controlled = False  # 标记是否被HPA控制

    def add_pod(self, pod_name):
        """添加Pod到ReplicaSet"""
        if pod_name not in self.pod_instances:
            self.pod_instances.append(pod_name)
            self.current_replicas = len(self.pod_instances)

    def remove_pod(self, pod_name):
        """从ReplicaSet中移除Pod"""
        if pod_name in self.pod_instances:
            self.pod_instances.remove(pod_name)
            self.current_replicas = len(self.pod_instances)

    def needs_scaling(self):
        """判断是否需要扩缩容"""
        return self.current_replicas != self.desired_replicas

    def scale_up_count(self):
        """需要创建的Pod数量"""
        return max(0, self.desired_replicas - self.current_replicas)

    def scale_down_count(self):
        """需要删除的Pod数量"""
        return max(0, self.current_replicas - self.desired_replicas)

    def scale_up(self):
        """标记需要扩容"""
        self.status = STATUS.PENDING
        return self.scale_up_count()

    def scale_down(self):
        """标记需要缩容"""
        self.status = STATUS.PENDING
        return self.scale_down_count()

    def update_status(self):
        """更新ReplicaSet状态"""
        if self.needs_scaling():
            self.status = STATUS.PENDING
        else:
            self.status = STATUS.RUNNING