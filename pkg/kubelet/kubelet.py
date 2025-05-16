from time import sleep
from confluent_kafka import Consumer, KafkaError
from pkg.config.podConfig import PodConfig
from threading import Thread

class Kubelet():
    def __init__(self, config):
        self.config = config
        self.pods_cache = []

        self.consumer = Consumer(config.consumer_config())
        self.consumer.subscribe([config.topic])
        print(f'[INFO]Subscribe kafka({config.kafka_server}) topic {config.topic}')
        

    def run(self):
        print("enter run")
        while True:
            sleep(5.0)
            self.thread = Thread(target=self.consume_messages)

            for pod in self.pods_cache:
                pod.restart_crash()

    def consume_messages(self):
        while True:
            msg = self.consumer.poll(timeout=1.0)
            print(f'[INFO]Receive an message with key = {msg.key()}')

            if msg is not None:
                if not msg.error():
                    print(f'[INFO]Receive an message with key = {msg.key()}')
                    self.update_pod(msg.key(), json.loads(msg.value().decode('utf-8')))
                else:
                    print(f'[ERROR]Message error')

    def update_pod(self, type, data):
        if type == 'ADD':
            print("receive an ADD message")
            config = PodConfig(data)
            self.pods_cache.append(Pod(config))
        elif type == 'UPDATE':
            config = PodConfig(data)
            for i, pod in enumerate(self.pods_cache):
                if pod.name == config.name:
                    self.pods_cache[i] = Pod(config)
                    return
            print('[WARNING]Pod not found.')
        elif type == 'DELETE':
            config = PodConfig(data)
            for i, pod in enumerate(self.pods_cache):
                if pod.name == config.name:
                    self.pods_cache[i] = Pod(config)
                    return
        elif type == 'GET':
            pass

if __name__ == '__main__':
    print('[INFO]Testing kubelet.')
    import yaml
    from pkg.apiObject.pod import Pod
    from pkg.config.kubeletConfig import KubeletConfig

    kubelet_config = KubeletConfig()
    kubelet = Kubelet(kubelet_config)
    with open('../../testFile/pod-3.yaml', 'r', encoding='utf-8') as file:
        data = yaml.safe_load(file)
    print(f"data = {data}")
    podConfig = PodConfig(data)
    # pod = Pod(podConfig)
    # kubelet.pods_cache.append(pod)

    print('[INFO]start kubelet(infinite retry)')
    kubelet.run()