import datetime
from pkg.apiServer.apiClient import ApiClient
from pkg.config.uriConfig import URIConfig
from pkg.config.hpaConfig import HorizontalPodAutoscalerConfig
from pkg.apiObject.replicaSet import ReplicaSet

class STATUS:
    PENDING = 'PENDING'
    RUNNING = 'RUNNING'
    FAILED = 'FAILED'

class HorizontalPodAutoscaler:
    def __init__(self, config):
        """初始化HPA对象"""
        # 保存原始配置
        self.config = config
        
        # 基本信息
        self.name = config.name
        self.namespace = config.namespace
        self.labels = config.labels
        
        # 目标资源
        self.target_kind = config.target_kind
        self.target_name = config.target_name
        
        # 副本数量限制
        self.min_replicas = config.min_replicas
        self.max_replicas = config.max_replicas
        
        # 指标和调整参数
        self.metrics = config.metrics
        self.cooldown_seconds = config.cooldown_seconds
        
        # 运行时状态
        self.status = getattr(config, 'status', STATUS.PENDING)
        self.current_replicas = getattr(config, 'current_replicas', 0)
        self.target_replicas = getattr(config, 'target_replicas', 0)
        self.current_metrics = getattr(config, 'current_metrics', {})
        
        # 处理last_scale_time (可能是字符串或None)
        self.last_scale_time = None
        if hasattr(config, 'last_scale_time') and config.last_scale_time:
            if isinstance(config.last_scale_time, str):
                try:
                    self.last_scale_time = datetime.datetime.fromisoformat(config.last_scale_time)
                except:
                    pass
            else:
                self.last_scale_time = config.last_scale_time
        
        # API通信
        self.api_client = None
        self.uri_config = None

    def set_api_client(self, api_client, uri_config=None):
        """设置API客户端，用于与API Server通信"""
        self.api_client = api_client
        self.uri_config = uri_config or URIConfig()
        return self

    def _ensure_api_client(self):
        """确保API客户端已初始化"""
        if not self.api_client:
            self.api_client = ApiClient()
            self.uri_config = URIConfig()

    def to_config_dict(self):
        """将HPA转换为配置字典"""
        hpa_dict = {
            'metadata': {
                'name': self.name,
                'namespace': self.namespace,
                'labels': self.labels
            },
            'spec': {
                'scaleTargetRef': {
                    'kind': self.target_kind,
                    'name': self.target_name
                },
                'minReplicas': self.min_replicas,
                'maxReplicas': self.max_replicas,
                'metrics': self.metrics,
                'behavior': {
                    'scaleDown': {
                        'stabilizationWindowSeconds': self.cooldown_seconds
                    }
                }
            },
            'status': self.status,
            'current_replicas': self.current_replicas,
            'target_replicas': self.target_replicas,
            'current_metrics': self.current_metrics
        }
        
        # 处理last_scale_time (转换为ISO格式字符串)
        if self.last_scale_time:
            hpa_dict['last_scale_time'] = self.last_scale_time.isoformat()
        else:
            hpa_dict['last_scale_time'] = None
        
        return hpa_dict

    # API操作方法

    def create(self):
        """创建HPA"""
        self._ensure_api_client()
        
        # 构建API路径
        path = self.uri_config.HPA_SPEC_URL.format(
            namespace=self.namespace, 
            name=self.name
        )
        
        # 发送创建请求
        create_result = self.api_client.post(path, self.to_config_dict())
        if not create_result:
            print(f"[ERROR]Failed to create HPA {self.name}")
            return False
        
        return True

    @staticmethod
    def get(namespace, name, api_client=None, uri_config=None):
        """获取HPA（静态方法）"""
        # 初始化API客户端
        _api_client = api_client or ApiClient()
        _uri_config = uri_config or URIConfig()
        
        # 构建API路径
        path = _uri_config.HPA_SPEC_URL.format(
            namespace=namespace, 
            name=name
        )
        
        # 获取HPA配置
        hpa_config_dict = _api_client.get(path)
        if not hpa_config_dict:
            print(f"[ERROR]HPA {name} not found in namespace {namespace}")
            return None
        
        # 创建HPAConfig
        hpa_config = HorizontalPodAutoscalerConfig(hpa_config_dict)
        
        # 创建HPA并设置API客户端
        hpa = HorizontalPodAutoscaler(hpa_config)
        hpa.set_api_client(_api_client, _uri_config)
        
        return hpa

    @staticmethod
    def list(namespace='default', api_client=None, uri_config=None):
        """列出命名空间下的所有HPA（静态方法）"""
        # 初始化API客户端
        _api_client = api_client or ApiClient()
        _uri_config = uri_config or URIConfig()
        
        # 构建API路径
        path = _uri_config.HPAS_URL.format(namespace=namespace)
        
        # 获取HPA列表
        hpa_list_data = _api_client.get(path)
        if not hpa_list_data:
            return []
        
        # 转换为HPA对象
        hpas = []
        
        if isinstance(hpa_list_data, list):
            for hpa_data in hpa_list_data:
                try:
                    hpa_config = HorizontalPodAutoscalerConfig(hpa_data)
                    hpa = HorizontalPodAutoscaler(hpa_config)
                    hpa.set_api_client(_api_client, _uri_config)
                    hpas.append(hpa)
                except Exception as e:
                    print(f"[ERROR]Failed to parse HPA: {e}")
        elif isinstance(hpa_list_data, dict) and 'items' in hpa_list_data:
            for hpa_data in hpa_list_data['items']:
                try:
                    hpa_config = HorizontalPodAutoscalerConfig(hpa_data)
                    hpa = HorizontalPodAutoscaler(hpa_config)
                    hpa.set_api_client(_api_client, _uri_config)
                    hpas.append(hpa)
                except Exception as e:
                    print(f"[ERROR]Failed to parse HPA: {e}")
        
        return hpas

    def update(self):
        """更新HPA"""
        self._ensure_api_client()
        
        # 构建API路径
        path = self.uri_config.HPA_SPEC_URL.format(
            namespace=self.namespace, 
            name=self.name
        )
        
        # 发送更新请求
        update_result = self.api_client.put(path, self.to_config_dict())
        if not update_result:
            print(f"[ERROR]Failed to update HPA {self.name}")
            return False
        
        return True

    def delete(self):
        """删除HPA"""
        self._ensure_api_client()
        
        # 构建API路径
        path = self.uri_config.HPA_SPEC_URL.format(
            namespace=self.namespace, 
            name=self.name
        )
        
        # 发送删除请求
        delete_result = self.api_client.delete(path)
        if not delete_result:
            print(f"[ERROR]Failed to delete HPA {self.name}")
            return False
        
        print(f"[INFO]HPA {self.name} deleted")
        return True

    def get_target_resource(self):
        """获取目标资源"""
        self._ensure_api_client()
        
        if self.target_kind == 'ReplicaSet':
            return ReplicaSet.get(
                self.namespace, 
                self.target_name,
                self.api_client,
                self.uri_config
            )
        
        return None

    def scale_target(self, target_replicas):
        """调整目标资源的副本数量"""
        # 获取目标资源
        target = self.get_target_resource()
        if not target:
            print(f"[ERROR]Target {self.target_kind} {self.target_name} not found")
            return False
        
        # 检查当前副本数
        if target.current_replicas == target_replicas:
            return True  # 已经是目标数量，无需调整
        
        # 检查冷却期
        if self.last_scale_time and (datetime.datetime.now() - self.last_scale_time).total_seconds() < self.cooldown_seconds:
            print(f"[INFO]In cooldown period, skipping scaling")
            return False  # 冷却期内，不进行调整
        
        # 执行扩缩容
        print(f"[INFO]Scaling {self.target_kind} {self.target_name} from {target.current_replicas} to {target_replicas} replicas")
        scaling_success = target.scale(target_replicas)
        
        if scaling_success:
            # 更新HPA状态
            self.last_scale_time = datetime.datetime.now()
            self.current_replicas = target.current_replicas
            self.target_replicas = target_replicas
            self.update()
            return True
        
        return False