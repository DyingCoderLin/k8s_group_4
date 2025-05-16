from pkg.config.containerConfig import ContainerConfig

class PodConfig():
    def __init__(self, arg_json):
        # --- static information ---
        metadata = arg_json.get('metadata')
        self.name = metadata.get('name')
        self.namespace = metadata.get('namespace', 'default')

        spec = arg_json.get('spec')
        volumes = spec.get('volumes', [])
        containers = spec.get('containers', [])
        self.volume, self.containers = dict(), []

        # 目前只支持hostPath，并且忽略type字段
        for volume in volumes:
            self.volume[volume.get('name')] = volume.get('hostPath').get('path')

        for container in containers:
            self.containers.append(ContainerConfig(self.volume, container))

        # --- running information ---
        self.overlay_name = None
        self.subnet_ip = None
        self.node_id = None
        self.status = None