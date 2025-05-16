class KafkaConfig:
    # Kafka 地址
    # BOOTSTRAP_SERVER = "47.103.11.77:9092"
    BOOTSTRAP_SERVER="10.181.22.193:9092" #mac
    # BOOTSTRAP_SERVER = "localhost:9092"

    # -------------------- 资源主题定义 --------------------
    # 与Node的kubelet组件交互
    POD_TOPIC = "api.v1.nodes.{name}"