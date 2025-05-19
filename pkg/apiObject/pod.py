import docker
import platform

class STATUS():
    STOPPED = 'STOPPED'
    RUNNING = 'RUNNING'
    KILLED = 'KILLED'

class Pod():
    def __init__(self, config):
        self.config = config
        self.status = STATUS.RUNNING
        print(f'[INFO]Pod {config.namespace}:{config.name} init, status: {self.status}')
        
        if platform.system() == "Windows":
            self.client = docker.DockerClient(
                base_url='npipe:////./pipe/docker_engine',
                version='1.25',
                timeout=5
            )
        else:
            self.client = docker.DockerClient(
                base_url='unix://var/run/docker.sock',
                version='1.25',
                timeout=5
            )
        # print(f'[INFO]enter docker client, base_url: {self.client.base_url}')
        print(f"config: {self.config}")
        self.client.networks.prune()
        print(f"labels: {self.config.labels}")

        # --- 不使用overlay网络 ---
        # self.network = self.client.networks.create(name = 'network_' + self.config.namespace, driver='bridge')
        # self.containers = [self.client.containers.run(image = 'busybox', name = 'pause', detach = True,
        #                            command = ['sh', '-c', 'echo [INFO]pod network init. && sleep 3600'],
        #                            network = self.network.name)]

        # --- 使用overlay网络 ---
        pause_docker_name = "pause_" + self.config.namespace + "_" + self.config.name
        self.containers = [self.client.containers.run(image = 'busybox', name = pause_docker_name, detach = True,
                                   command = ['sh', '-c', 'echo [INFO]pod network init. && sleep 3600'],
                                   network = self.config.overlay_name)]
        print(f'[INFO]Pod init, pause container: {self.containers[0].name}')
        print(f"container num: {len(self.config.containers)}")
        for container in self.config.containers:
            print(f'[INFO]Pod init, container: {container.name}')
            self.containers.append(self.client.containers.run(**container.dockerapi_args(),
            detach = True, network_mode = f'container:{pause_docker_name}'))
            print(f'[INFO]container {container.name} created, id: {self.containers[-1].id}')

    # docker stop + docker rm
    def remove(self):
        for container in self.containers:
            self.client.api.stop(container.id)
            self.client.api.remove_container(container.id)
        print(f'[INFO]Pod {self.config.namespace}:{self.config.name} removed.')

    # docker start
    def start(self):
        for container in self.containers:
            self.client.api.start(container.id)
        self.status = STATUS.RUNNING

    # docker stop, 可以在10s内优雅地停止
    def stop(self):
        for container in self.containers:
            self.client.api.stop(container.id)
        self.status = STATUS.STOPPED

    # docker kill, 立即终止
    def kill(self):
        try:
            self.client.api.kill(container.id)
        except APIError as e:
            if not "is not running" in e.explanation:
                raise e
        self.status = STATUS.KILLED

    def restart_crash(self):
        for container in self.containers:
            container.reload()
            if container.status == 'exited' and container.attrs['State']['ExitCode'] != 0:
                print(f'[INFO]restart abnormally exited container {container.name}')
                self.client.api.restart(container.id)

    # docker restart
    def restart(self):
        for container in self.containers:
            self.client.api.restart(container.id)
        self.status = STATUS.RUNNING

if __name__ == '__main__':
    print('[INFO]Testing Pod.')
    
    import yaml
    import requests
    from pkg.config.podConfig import PodConfig
    from pkg.config.uriConfig import URIConfig
    from pkg.config.globalConfig import GlobalConfig
    import os
    config = GlobalConfig()

    def load_yaml(test_file : str):
        test_yaml = os.path.join(config.TEST_FILE_PATH, test_file)
        with open(test_yaml, 'r', encoding='utf-8') as file:
            data = yaml.safe_load(file)
        return data

    print(f'[INFO]使用pod-1.yaml和pod-1-2.yaml，测试Pod的创建、更新和删除。')
    data = load_yaml("pod-1.yaml")

    dist = True
    if dist:
        # 测试Post
        uri = URIConfig.PREFIX + URIConfig.POD_SPEC_URL.format(
            namespace= data['metadata']['namespace'], name = data['metadata']['name'])
        print(f'[INFO]创建Pod请求地址: {uri} \ndata: {data}')
        response = requests.post(uri, json=data)
        print(response.json())

        input('Press Enter To Continue.')
        # 测试Put
        data = load_yaml("pod-1-2.yaml")
        print(f'[INFO]创建Pod请求地址: {uri} \ndata: {data}')
        response = requests.put(uri, json=data)
        print(response.json())

        input('Press Enter To Continue.')
        # 测试Delete
        print(f'[INFO]创建Pod请求地址: {uri}')
        response = requests.delete(uri)
        print(response)

        # 测试pod的获取
        # uri = URIConfig.PREFIX + URIConfig.POD_SPEC_URL.format(
        #     namespace= data['metadata']['namespace'], name = data['metadata']['name'])
        # print(f'[INFO]请求地址: {uri}')
        # response = requests.get(uri)
        # print(f'[INFO]获取pod的返回值: {response}')
        # response_config = PodConfig(response.json())
        # print(f"pod.label.app: {response_config.get_app_label()},pod.label.env: {response_config.get_env_label()}")
    else:
        podConfig = PodConfig(data)
        pod = Pod(podConfig)
        print(f'[INFO]初始化Pod，status: {pod.status}')
        pod.stop()
        print(f'[INFO]关闭Pod，status: {pod.status}')
        pod.start()
        print(f'[INFO]启动Pod，status: {pod.status}')
        pod.stop()
        print(f'[INFO]关闭Pod，status: {pod.status}')
        pod.remove()
        print(f'[INFO]Pod删除，可以在本地docker desktop查看，容器已经被删除')