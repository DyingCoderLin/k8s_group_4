import json
from time import sleep
from confluent_kafka import Consumer, KafkaError
from threading import Thread

from pkg.apiObject.pod import Pod
from pkg.config.podConfig import PodConfig

class Kubelet():
    def __init__(self, config):
        self.config = config
        self.pods_cache = []

        self.consumer = Consumer(config.consumer_config())
        self.consumer.subscribe([config.topic])
        print(f'[INFO]Subscribe kafka({config.kafka_server}) topic {config.topic}')

    def run(self):
        self.consume_messages()
        self.thread = Thread(target=self.restart_crash)

    def restart_crash(self):
        while True:
            sleep(5.0)

            for pod in self.pods_cache:
                pod.restart_crash()

    def consume_messages(self):
        while True:
            msg = self.consumer.poll(timeout=1.0)

            if msg is not None:
                if not msg.error():
                    print(f'[INFO]Receive an message with key = {msg.key().decode('utf-8')}')
                    # try:
                    self.update_pod(msg.key().decode('utf-8'), json.loads(msg.value().decode('utf-8')))
                    # except Exception as e:
                    #     print(f'[ERROR]Error processing msg: {e}')
                    self.consumer.commit(asynchronous=False)
                else:
                    print(f'[ERROR]Message error')

    def update_pod(self, type, data):
        if type in ['ADD', 'UPDATE', 'DELETE', 'GET']:
            print(f'[INFO]Kubelet {type} pod with data: {data}')
        else:
            print(f'[ERROR]Unknown kubelet operation {type}.')

        if type == 'ADD':
            config = PodConfig(data)
            # 从kubelet缓存的Pod信息检查命名是否冲突
            for pod in self.pods_cache:
                if pod.config.namespace == config.namespace and pod.config.name == config.name:
                    print(f'[ERROR]Pod name "{config.namespace}:{config.name}" already exists')
                    return
            try: # 尝试创建docker，可能出现名称重复、客户端未连接等容器运行时错误
                new_pod = Pod(config)
            except Exception as e:
                print(f'[ERROR]Docker create fail: {e}')
                return

            self.pods_cache.append(new_pod)
            print(f'[INFO]Kubelet create pod "{config.namespace}:{config.name}".')

        elif type == 'UPDATE':
            config = PodConfig(data)
            # lcl: update又是在做什么？
            # wcc: 别急
            for i, pod in enumerate(self.pods_cache):
                if pod.config.namespace == config.namespace and pod.config.name == config.name:
                    try: # 在旧容器删除过程中出现了容器运行时错误
                        self.pods_cache[i].remove()
                        del self.pods_cache[i]
                    except Exception as e:
                        print(f'[ERROR]Docker rm fail: {e}')
                        return
                    try: # 在新容器创建过程中出现容器运行时错误
                        self.pods_cache.append(Pod(config))
                    except Exception as e:
                        print(f'[ERROR]Docker create fail: {e}')
                        return
                    print(f'[INFO]Pod "{config.namespace}:{config.name}" updated.')
                    return
            # 从kubelet的缓存信息中无法找到对应的Pod
            print(f'[WARNING]Pod "{config.namespace}:{config.name}" not found.')

        elif type == 'DELETE':
            namespace, name = data['namespace'], data['name']
            # lcl: delete逻辑完全没有实现，需要实现
            # wcc: 别急
            for i, pod in enumerate(self.pods_cache):
                if pod.config.namespace == namespace and pod.config.name == name:
                    try:  # 在旧容器删除过程中出现了容器运行时错误
                        self.pods_cache[i].remove()
                        del self.pods_cache[i]
                    except Exception as e:
                        print(f'[ERROR]Docker rm fail: {e}')
                        return
                    print(f'[INFO]Pod "{namespace}:{name}" deleted.')
                    return
            # 从kubelet的缓存信息中无法找到对应的Pod
            print(f'[WARNING]Pod "{namespace}:{name}" not found.')

if __name__ == '__main__':
    print('[INFO]Testing kubelet.')
    import yaml
    from pkg.apiObject.pod import Pod
    from pkg.config.kubeletConfig import KubeletConfig
    from pkg.config.globalConfig import GlobalConfig
    import os

    kubelet_config = KubeletConfig()
    kubelet = Kubelet(kubelet_config)
    global_config = GlobalConfig()
    test_yaml = os.path.join(global_config.TEST_FILE_PATH, 'pod-3.yaml')
    
    with open(test_yaml, 'r', encoding='utf-8') as file:
        data = yaml.safe_load(file)
    print(f"data = {data}")
    podConfig = PodConfig(data)
    # pod = Pod(podConfig)
    # kubelet.pods_cache.append(pod)

    print('[INFO]start kubelet(infinite retry)')
    kubelet.run()