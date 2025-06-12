import docker
from docker.errors import APIError
import platform
import argparse
import sys
import os
import yaml
import requests
import json
import argparse
import sys
import os
import yaml
from pkg.apiServer.apiClient import ApiClient

class STATUS:
    CREATING = "CREATING"
    STOPPED = "STOPPED"
    RUNNING = "RUNNING"
    KILLED = "KILLED"

class Pod:
    def __init__(self, config, api_client: ApiClient = None, uri_config =None):
        self.status = STATUS.CREATING
        self.config = config
        print(f"[INFO]Pod {config.namespace}:{config.name} init, status: {self.status}")

        if platform.system() == "Windows":
            self.client = docker.DockerClient(
                base_url="npipe:////./pipe/docker_engine", version="1.25", timeout=20
            )
        else:
            self.client = docker.DockerClient(
                base_url="unix://var/run/docker.sock", version="1.25", timeout=5
            )
        self.client.networks.prune()
        self.containers = []

        pause_docker_name = "pause_" + self.config.namespace + "_" + self.config.name
        containers = self.client.containers.list(all=True, filters={"name": pause_docker_name})
        if len(containers) == 0:
            self.containers.append(self.client.containers.run(image = 'busybox', name = pause_docker_name, detach = True,
                               command = ['sh', '-c', 'echo [INFO]pod network init. && sleep 3600'],
                               network = self.config.cni_name, dns = [uri_config.COREDNS_IP]))
        else:
            self.containers.append(containers[0])

        for container in self.config.containers:
            try:
                args = container.dockerapi_args()
                host_config_params = args.pop('host_config', {})

                containers = self.client.containers.list(all=True, filters={"name": args['name']})
                if len(containers) > 0: # Node重启，由于不确定容器状态是否发生改变，统一删除后重建
                    for container in containers: 
                        container.remove(force=True)

                # 启动容器
                self.containers.append(self.client.containers.run(
                    **args,
                    host_config=self.client.create_host_config(**host_config_params),
                    detach=True,
                    network_mode=f'container:{pause_docker_name}'
                ))

            except Exception as e:
                print(f"[ERROR]Failed to create container {container.name}: {str(e)}")
                # 可选：添加更详细的错误信息
                import traceback

                print(f"[DEBUG]详细错误: {traceback.format_exc()}")
        
        # 获取Pod的IP地址
        self.subnet_ip = self._get_pod_ip()
        print(f"[INFO]Pod {self.config.namespace}:{self.config.name} IP地址: {self.subnet_ip}")
        if api_client and uri_config:
            api_client.put(
                uri_config.POD_SPEC_IP_URL.format(
                    namespace=self.config.namespace, name=self.config.name
                ),
                {"subnet_ip": self.subnet_ip},
            )
        
        self.status = STATUS.RUNNING

    def _get_pod_ip(self) -> str:
        """获取Pod的IP地址（从pause容器获取）"""
        try:
            pause_container = self.containers[0]  # pause容器是第一个创建的
            pause_container.reload()  # 确保获取最新状态
            
            # 使用docker inspect获取容器网络信息
            container_info = self.client.api.inspect_container(pause_container.id)
            
            # 获取IP地址
            ip_address = container_info['NetworkSettings']['IPAddress']
            
            # 如果默认网络模式没有IP，尝试从自定义网络获取
            if not ip_address:
                networks = container_info['NetworkSettings']['Networks']
                for network_name, network_config in networks.items():
                    if network_config.get('IPAddress'):
                        ip_address = network_config['IPAddress']
                        break
            
            return ip_address
        except Exception as e:
            print(f"[ERROR]获取Pod IP地址失败: {str(e)}")
            return "0.0.0.0"  # 返回默认IP

    # docker stop + docker rm
    def remove(self):
        self.status = STATUS.KILLED
        for container in self.containers:
            self.client.api.kill(container.id)
            self.client.api.remove_container(container.id)
        print(f"[INFO]Pod {self.config.namespace}:{self.config.name} removed.")

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
            for container in self.containers:
                self.client.api.kill(container.id)
        except APIError as e:
            if not "is not running" in e.explanation:
                raise e
        self.status = STATUS.KILLED

    # docker restart
    def restart(self):
        for container in self.containers:
            self.client.api.restart(container.id)
        self.status = STATUS.RUNNING

    def restart_crash(self):
        if self.status == STATUS.KILLED:
            return
        for container in self.containers:
            container.reload()
            if (
                container.status == "exited"
                and container.attrs["State"]["ExitCode"] != 0
            ):
                print(f"[INFO]restart abnormally exited container {container.name}")
                self.client.api.restart(container.id)

    def refresh_status(self):
        exited_normal, creating = 0, 0
        for container in self.containers:
            container.reload()
            if (
                container.status == "exited"
                and container.attrs["State"]["ExitCode"] == 0
            ):
                exited_normal += 1
            elif container.status == "creating":
                creating += 1

        # STOPPED: 如果全部正常退出，那么Pod处于停止状态
        # CREATING: 如果有正在创建，则处于创建状态
        # RUNNING: 否则有异常退出的容器（根据Pod自动重启的原则处于Running状态）或者都在正常运行
        # KILLED: 无法判断，调用killed的时候手动设置（但是没有考虑这种情况，因为还没有实现kill接口）
        if exited_normal == len(self.containers):
            self.status = STATUS.STOPPED
        elif creating == 0:
            self.status = STATUS.RUNNING
        else:
            self.status = STATUS.CREATING
        return self.status


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Pod management")
    parser.add_argument(
        "--test", action="store_true", help="Run the test sequence for Pod"
    )
    args = parser.parse_args()

    if args.test:
        print("[INFO]Testing Pod in CI mode...")
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
            print(f"[INFO]使用{test_file}作为测试配置")

            try:
                with open(test_yaml, "r", encoding="utf-8") as file:
                    data = yaml.safe_load(file)

                # 测试Pod创建（通过API或直接创建）
                try:
                    # 通过API创建
                    uri = URIConfig.PREFIX + URIConfig.POD_SPEC_URL.format(
                        namespace=data["metadata"]["namespace"],
                        name=data["metadata"]["name"],
                    )
                    print(f"[INFO]请求地址: {uri}")
                    response = requests.post(uri, json=data, timeout=5)
                    print(f"[INFO]创建Pod响应: {response.status_code}")

                    # 获取Pod信息
                    response = requests.get(uri, timeout=5)
                    print(f"[INFO]获取Pod响应: {response.status_code}")

                    print("[PASS]API创建和获取Pod测试通过")

                    response = requests.delete(uri, timeout=5)
                    print(f"[INFO]删除Pod响应: {response.status_code}")
                    print("[PASS]API删除Pod测试通过")
                except Exception as e:
                    print(f"[WARN]API测试失败: {str(e)}")
                    print("[INFO]尝试直接创建Pod...")

                    # 直接创建Pod
                    podConfig = PodConfig(data)
                    podConfig.overlay_name = "bridge"  # 使用bridge网络

                    pod = Pod(podConfig)
                    print(f"[INFO]Pod初始化完成，状态: {pod.status}")

                    pod.stop()
                    print(f"[INFO]Pod已停止，状态: {pod.status}")

                    pod.start()
                    print(f"[INFO]Pod已启动，状态: {pod.status}")

                    pod.stop()
                    pod.remove()
                    print("[PASS]直接创建Pod测试通过")
            except Exception as e:
                print(f"[ERROR]Pod测试失败: {str(e)}")
                raise

            print("[INFO]Pod测试完成")

            # 不在这里停止服务，因为后续测试还需要用到
            sys.exit(0)
        except Exception as e:
            print(f"[ERROR]Pod测试失败: {str(e)}")
            import traceback

            print(f"[DEBUG]详细错误: {traceback.format_exc()}")
            sys.exit(1)
    else:
        print("[INFO]Testing Pod in regular mode.")

        from pkg.config.podConfig import PodConfig
        from pkg.config.uriConfig import URIConfig
        from pkg.config.globalConfig import GlobalConfig

        config = GlobalConfig()
        # test_file = "pod-1 copy.yaml"
        # test_file = "test-pod-server-1.yaml"
        test_file = "test-pod-security-context.yaml"
        test_yaml = os.path.join(config.TEST_FILE_PATH, test_file)
        print(
            f"[INFO]使用{test_file}作为测试配置，测试Pod的创建和删除。目前没有使用volume绑定"
        )
        with open(test_yaml, "r", encoding="utf-8") as file:
            data = yaml.safe_load(file)

            dist = True
            if dist:
                # 测试Post
                uri = URIConfig.PREFIX + URIConfig.POD_SPEC_URL.format(
                    namespace=data["metadata"]["namespace"],
                    name=data["metadata"]["name"],
                )
                # print(f'[INFO]创建Pod请求地址: {uri} \ndata: {data}')
                print(f"[INFO]测试Pod的创建")
                response = requests.post(uri, json=data)
                print(f"[INFO]响应状态码: {response.status_code}")
                try:
                    json_response = response.json()
                    print(f"[INFO]响应数据: {json_response}")
                except json.decoder.JSONDecodeError:
                    print(f"[INFO]响应内容不是有效的JSON: {response.text}")

                input("Press Enter To Continue.")
                # 测试Put
                # print(f'[INFO]创建Pod请求地址: {uri} \ndata: {data}')
                # print(f'[INFO]测试Pod的更新')
                # response = requests.put(uri, json=data)
                # try:
                #     json_response = response.json()
                #     print(f"[INFO]响应数据: {json_response}")
                # except json.decoder.JSONDecodeError:
                #     print(f"[INFO]响应内容不是有效的JSON: {response.text}")

                input("Press Enter To Continue.")
                # 测试Delete
                # print(f'[INFO]创建Pod请求地址: {uri}')
                print(f"[INFO]测试Pod的删除")
                response = requests.delete(uri)
                print(f"[INFO]删除响应状态码: {response.status_code}")
                try:
                    json_response = response.json()
                    print(f"[INFO]删除响应数据: {json_response}")
                except json.decoder.JSONDecodeError:
                    print(f"[INFO]删除响应内容不是有效的JSON: {response.text}")

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
                print(f"[INFO]初始化Pod，status: {pod.status}")
                pod.stop()
                print(f"[INFO]关闭Pod，status: {pod.status}")
                pod.start()
                print(f"[INFO]启动Pod，status: {pod.status}")
                pod.stop()
                print(f"[INFO]关闭Pod，status: {pod.status}")
                pod.remove()
                print(f"[INFO]Pod删除，可以在本地docker desktop查看，容器已经被删除")
