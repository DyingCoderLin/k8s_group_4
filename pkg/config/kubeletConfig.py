class KubeletConfig():
    def __init__(self, subnet_ip, overlay_name, apiserver, node_id, kafka_server, kafka_topic):
        self.apiserver = apiserver

        self.node_id = node_id
        self.overlay_name = overlay_name
        self.subnet_ip = subnet_ip

        self.kafka_server = kafka_server
        self.topic = kafka_topic

    def consumer_config(self):
        return {
            'bootstrap.servers': self.kafka_server,
            'group.id': self.node_id,
            'auto.offset.reset': 'latest',
            'enable.auto.commit': False,
        }