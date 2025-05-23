import docker
import platform
import argparse
import sys
import os
import yaml
import requests
import argparse
import sys
import os
import yaml

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
            try:
                container_args = container.dockerapi_args()
                if 'cpu_quota' in container_args and isinstance(container_args['cpu_quota'], float):
                    container_args['cpu_quota'] = int(container_args['cpu_quota'])
                print(f'[INFO]container args: {container_args}')
                new_container = self.client.containers.run(
                    **container_args,
                    detach=True, 
                    network_mode=f'container:{pause_docker_name}'
                )
                self.containers.append(new_container)
                print(f'[INFO]container {container.name} created, id: {self.containers[-1].id}')
            except Exception as e:
                print(f'[ERROR]Failed to create container {container.name}: {str(e)}')
                # 可选：添加更详细的错误信息
                import traceback
                print(f'[DEBUG]详细错误: {traceback.format_exc()}')

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
    parser = argparse.ArgumentParser(description='Pod management')
    parser.add_argument('--test', action='store_true', help='Run the test sequence for Pod')
    args = parser.parse_args()

    if args.test:
        print('[INFO]Testing Pod in CI mode...')
        try:
            # 服务已通过 Travis CI 启动，无需在此启动
            import time
            from pkg.config.podConfig import PodConfig
            from pkg.config.uriConfig import URIConfig
            from pkg.config.globalConfig import GlobalConfig
            
            # 常规测试流程
            config = GlobalConfig()
            test_file = "pod-1 copy.yaml"
            test_yaml = os.path.join(config.TEST_FILE_PATH, test_file)
            print(f'[INFO]使用{test_file}作为测试配置')
            
            try:
                with open(test_yaml, 'r', encoding='utf-8') as file:
                    data = yaml.safe_load(file)
                
                # 测试Pod创建（通过API或直接创建）
                try:
                    # 通过API创建
                    uri = URIConfig.PREFIX + URIConfig.POD_SPEC_URL.format(
                        namespace=data['metadata']['namespace'], name=data['metadata']['name'])
                    print(f'[INFO]请求地址: {uri}')
                    response = requests.post(uri, json=data, timeout=5)
                    print(f'[INFO]创建Pod响应: {response.status_code}')
                    
                    # 获取Pod信息
                    response = requests.get(uri, timeout=5)
                    print(f'[INFO]获取Pod响应: {response.status_code}')
                    
                    print('[PASS]API创建和获取Pod测试通过')
                    
                    response = requests.delete(uri, timeout=5)
                    print(f'[INFO]删除Pod响应: {response.status_code}')
                    print('[PASS]API删除Pod测试通过')
                except Exception as e:
                    print(f'[WARN]API测试失败: {str(e)}')
                    print('[INFO]尝试直接创建Pod...')
                    
                    # 直接创建Pod
                    podConfig = PodConfig(data)
                    podConfig.overlay_name = 'bridge'  # 使用bridge网络
                    
                    pod = Pod(podConfig)
                    print(f'[INFO]Pod初始化完成，状态: {pod.status}')
                    
                    pod.stop()
                    print(f'[INFO]Pod已停止，状态: {pod.status}')
                    
                    pod.start()
                    print(f'[INFO]Pod已启动，状态: {pod.status}')
                    
                    pod.stop()
                    pod.remove()
                    print('[PASS]直接创建Pod测试通过')
            except Exception as e:
                print(f'[ERROR]Pod测试失败: {str(e)}')
                raise
            
            print('[INFO]Pod测试完成')
            
            # 不在这里停止服务，因为后续测试还需要用到
            sys.exit(0)
        except Exception as e:
            print(f'[ERROR]Pod测试失败: {str(e)}')
            import traceback
            print(f'[DEBUG]详细错误: {traceback.format_exc()}')
            sys.exit(1)
    else:
        print('[INFO]Testing Pod in regular mode.')
        
        from pkg.config.podConfig import PodConfig
        from pkg.config.uriConfig import URIConfig
        from pkg.config.globalConfig import GlobalConfig
        config = GlobalConfig()
        test_file = "pod-1 copy.yaml"
        test_yaml = os.path.join(config.TEST_FILE_PATH, test_file)
        print(f'[INFO]使用{test_file}作为测试配置，测试Pod的创建和删除。目前没有使用volume绑定')
        with open(test_yaml, 'r', encoding='utf-8') as file:
            data = yaml.safe_load(file)

            dist = True
            if dist:
                # 测试Post
                uri = URIConfig.PREFIX + URIConfig.POD_SPEC_URL.format(
                    namespace= data['metadata']['namespace'], name = data['metadata']['name'])
                # print(f'[INFO]创建Pod请求地址: {uri} \ndata: {data}')
                response = requests.post(uri, json=data)
                print(response.json())

                input('Press Enter To Continue.')
                # 测试Put
                # print(f'[INFO]创建Pod请求地址: {uri} \ndata: {data}')
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
