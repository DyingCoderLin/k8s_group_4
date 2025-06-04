from pkg.config.podConfig import PodConfig
from pkg.config.nodeConfig import NodeConfig
from pkg.config.replicaSetConfig import ReplicaSetConfig
from pkg.config.hpaConfig import HorizontalPodAutoscalerConfig
from pkg.config.serviceConfig import ServiceConfig
from pkg.config.pvConfig import PVConfig
from pkg.config.pvcConfig import PVCConfig


class EtcdConfig:
    # Etcd 地址

    # HOST = '10.119.11.171' # 这是哪个
    HOST = "10.119.15.182"  # server
    # HOST='10.181.22.193' #mac
    # HOST = 'localhost'
    PORT = "2379"

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
    
    # Service相关
    GLOBAL_SERVICES_KEY = "/api/v1/namespaces/services"  # 修正为与 uriConfig.py 一致
    SERVICES_KEY = "/api/v1/namespaces/services/{namespace}"  # 修正为与 uriConfig.py 一致
    SERVICE_SPEC_KEY = "/api/v1/namespaces/services/{namespace}/{name}"  # 修正为与 uriConfig.py 一致
    SERVICES_VALUE = ServiceConfig

    # PersistentVolume相关 (集群级别)
    GLOBAL_PVS_KEY = "/api/v1/persistentvolumes"
    PV_SPEC_KEY = "/api/v1/persistentvolumes/{namespace}/{name}"
    PVS_VALUE = PVConfig

    # PersistentVolumeClaim相关 (命名空间级别)
    GLOBAL_PVCS_KEY = "/api/v1/namespaces/persistentvolumeclaims"
    PVCS_KEY = "/api/v1/namespaces/persistentvolumeclaims/{namespace}"
    PVC_SPEC_KEY = "/api/v1/namespaces/persistentvolumeclaims/{namespace}/{name}"
    PVCS_VALUE = PVCConfig
    
    
