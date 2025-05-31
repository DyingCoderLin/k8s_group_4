from uuid import uuid1


class NodeConfig:
    def __init__(self, arg_json):
        # --- static information ---
        self.id = str(uuid1())
        metadata = arg_json.get("metadata")
        self.name = metadata.get("name")
        self.apiserver = metadata.get("ip")

        spec = arg_json.get("spec")
        self.subnet_ip = spec.get("podCIDR")
        self.taints = spec.get("taints")
        self.json = arg_json

        self.status = None
        self.kafka_server = None
        self.kafka_topic = None

    def kubelet_config_args(self):
        return {
            "subnet_ip": self.subnet_ip,
            "apiserver": self.apiserver,
            "node_id": self.id,
        }
