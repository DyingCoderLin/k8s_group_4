class EtcdConfig:
    # Etcd 地址

    # HOST = '10.119.11.171'
    # HOST = '10.119.15.182'
    HOST = 'localhost'

    PORT = '2379'

    # -------------------- 资源键值定义 --------------------
    NODES_KEY = "/api/v1/nodes"
    NODES_VALUE = "List[NodeConfig]"

    PODS_KEY = "/api/v1/namespaces/<namespace>/pods"
    PODS_VALUE = "List[PodConfig]"
    
    # HPA相关
    HPA_KEY = "/api/v1/namespaces/<namespace>/hpa"
    HPA_VALUE = "List[HorizontalPodAutoscalerConfig]"
