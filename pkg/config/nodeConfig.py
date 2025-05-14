from uuid import uuid1

class NodeConfig():
    def __init__(self, arg_json):
        # --- static information ---
        self.id = uuid1()
        metadata = arg_json.get('metadata')
        self.name = metadata.get('name')
        self.apiserver = metadata.get('ip')

        self.json = arg_json

    def running_init(self, arg_json):
        # --- running information ---
        self.subnet_ip = arg_json.get('subnet_ip')
        self.overlay_name = arg_json.get('overlay_name')
        self.kafka_server = arg_json.get('kafka_server')
        self.kafka_topic = arg_json.get('kafka_topic')

    def kubelet_config_args(self):
        return {
            'subnet_ip': self.subnet_ip,
            'overlay_name': self.overlay_name,
            'apiserver': self.apiserver,
            'node_id': self.id,
            'kafka_server': self.kafka_server,
            'kafka_topic': self.kafka_topic
        }