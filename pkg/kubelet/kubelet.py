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
        # self.thread = Thread(target=self.consume_messages)
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
                    try:
                        self.update_pod(msg.key().decode('utf-8'), json.loads(msg.value().decode('utf-8')))
                    except:
                        pass
                    self.consumer.commit(asynchronous=False)
                else:
                    print(f'[ERROR]Message error')

    def update_pod(self, type, data):
        if type == 'ADD':
            print("receive an ADD message")
            config = PodConfig(data)
            print(f'[INFO]Kubelet add pod config: {config}.')
            self.pods_cache.append(Pod(config))
            print('[INFO]Kubelet create pod.')
        elif type == 'UPDATE':
            # update又是在做什么？
            print("receive an UPDATE message")
            config = PodConfig(data)
            # 确保交互正确
            print(f'[INFO]Kubelet update pod config: {config}.')
            # for i, pod in enumerate(self.pods_cache):
            #     if pod.name == config.name:
            #         self.pods_cache[i] = Pod(config)
            #         return
            # print('[WARNING]Pod not found.')
        elif type == 'DELETE':
            print("[INFO]Received a DELETE message")
            # 获取要删除的pod配置
            if isinstance(data, dict):
                pod_name = data.get('name')
                if not pod_name and 'metadata' in data:
                    pod_name = data.get('metadata', {}).get('name')
            else:
                # 尝试从PodConfig中获取
                config = PodConfig(data)
                pod_name = config.name
                
            print(f'[INFO]Kubelet deleting pod: {pod_name}')
            
            # 在本地缓存中查找并删除pod
            pod_found = False
            for i, pod in enumerate(self.pods_cache):
                if pod.name == pod_name:
                    print(f'[INFO]Found pod {pod_name} in cache, stopping and removing...')
                    try:
                        # 先停止pod中的所有容器
                        pod.stop()
                        # 再移除pod中的所有容器
                        pod.remove()
                        # 最后从缓存中删除pod对象
                        self.pods_cache.pop(i)
                        pod_found = True
                        print(f'[INFO]Successfully deleted pod {pod_name}')
                    except Exception as e:
                        print(f'[ERROR]Failed to delete pod {pod_name}: {str(e)}')
                    break
                    
            if not pod_found:
                print(f'[WARNING]Pod {pod_name} not found in kubelet cache')
        elif type == 'GET':
            pass

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