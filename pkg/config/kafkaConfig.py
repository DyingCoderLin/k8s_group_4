class KafkaConfig:
    # Kafka 地址
    # BOOTSTRAP_SERVER="10.181.22.193:9092" #mac
    # BOOTSTRAP_SERVER = "localhost:9092"
    BOOTSTRAP_SERVER = "10.119.15.182:9092"  # server

    # -------------------- 资源主题定义 --------------------
    # 与Node的kubelet组件交互
    POD_TOPIC = "api.v1.nodes.{name}"
    # 与scheduler交互
    SCHEDULER_TOPIC = "api.v1.scheduler"
    # service controller与kubeproxy交互
    SERVICE_PROXY_TOPIC = "serviceproxy.{name}"
