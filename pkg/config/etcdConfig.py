class EtcdConfig:
    # Etcd 地址
    HOST = '10.119.11.171'
    PORT = '2379'

    # -------------------- 资源键值定义 --------------------
    NODES_KEY = "/api/v1/nodes"
    NODES_VALUE = "List[NodeConfig]"

    PODS_KEY = "/api/v1/namespaces/<namespace>/pods"
    PODS_VALUE = "List[PodConfig]"
