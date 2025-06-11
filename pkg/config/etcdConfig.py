from pkg.config.podConfig import PodConfig
from pkg.config.nodeConfig import NodeConfig
from pkg.config.replicaSetConfig import ReplicaSetConfig
from pkg.config.hpaConfig import HorizontalPodAutoscalerConfig
from pkg.config.serviceConfig import ServiceConfig
from pkg.config.functionConfig import FunctionConfig
from pkg.config.workflowConfig import WorkflowConfig

class EtcdConfig:
    # Etcd 地址

    # HOST = "10.119.15.182"  # server
    # HOST='10.181.22.193' #mac
    HOST = 'localhost'
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

    # Function相关
    GLOBAL_FUNCTION_KEY = "/api/v1/namespaces/functions"
    FUNCTION_KEY = "/api/v1/namespaces/functions/{namespace}"
    FUNCTION_SPEC_KEY = "/api/v1/namespaces/functions/{namespace}/{name}"
    FUNCTION_VALUE = FunctionConfig

    # Workflow相关
    GLOBAL_WORKFLOW_KEY = "/api/v1/namespaces/workflows"
    WORKFLOW_KEY = "/api/v1/namespaces/workflows/{namespace}"
    WORKFLOW_SPEC_KEY = "/api/v1/namespaces/workflows/{namespace}/{name}"
    WORKFLOW_VALUE = WorkflowConfig

    RESET_PREFIX = [NODES_KEY, GLOBAL_PODS_KEY, GLOBAL_REPLICA_SETS_KEY, GLOBAL_HPA_KEY, GLOBAL_SERVICES_KEY, GLOBAL_FUNCTION_KEY, GLOBAL_WORKFLOW_KEY]
