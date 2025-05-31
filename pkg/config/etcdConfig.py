from pkg.config.podConfig import PodConfig
from pkg.config.nodeConfig import NodeConfig
from pkg.config.replicaSetConfig import ReplicaSetConfig
from pkg.config.hpaConfig import HorizontalPodAutoscalerConfig

class EtcdConfig:
    # Etcd 地址

    # HOST = '10.119.11.171' # 这是哪个
    HOST = '10.119.15.182' # server
    # HOST='10.181.22.193' #mac
    # HOST = 'localhost'
    PORT = '2379'

    # -------------------- 资源键值定义 --------------------
    NODES_KEY = "/api/v1/nodes"
    NODE_SPEC_KEY = "/api/v1/nodes/{name}"
    NODES_VALUE = NodeConfig

    GLOBAL_PODS_KEY = "/api/v1/namespaces/pods"
    PODS_KEY = "/api/v1/namespaces/pods/{namespace}"
    POD_SPEC_KEY = "/api/v1/namespaces/pods/{namespace}/{name}"
    PODS_VALUE = PodConfig

    GLOBAL_REPLICA_SETS_KEY = "/api/v1/namespaces/replicasets"
    REPLICA_SETS_KEY = "/api/v1/namespaces/replicasets/{namespace}"
    REPLICA_SET_SPEC_KEY = "/api/v1/namespaces/replicasets/{namespace}/{name}"
    REPLICA_SETS_VALUE = ReplicaSetConfig
    
    # HPA相关
    GLOBAL_HPA_KEY = "/api/v1/namespaces/hpa"
    HPA_KEY = "/api/v1/namespaces/hpa/{namespace}"
    HPA_SPEC_KEY = "/api/v1/namespaces/hpa/{namespace}/{name}"
    HPA_VALUE = HorizontalPodAutoscalerConfig
