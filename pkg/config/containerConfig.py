class ContainerConfig():
    def __init__(self, volumes_map, arg_json):
        self.name = arg_json.get('name')
        self.image = arg_json.get('image')
        self.command = arg_json.get('command', [])
        self.args = arg_json.get('args', [])

        self.port = dict()
        if arg_json.get('port') is not None:
            port = dict()
            for port_json in arg_json.get('port'):
                protocol = port_json.get('protocol', 'tcp').lower()
                port[(f'{port_json.get('containerPort')}/'
                           f'{protocol}')] = port_json.get('hostPort', None)
            self.port['ports'] = port

        # resource只支持cpu和内存的request和limit，不支持ephemeral-storage和nvidia.com/gpu
        self.resources = dict()
        requests = arg_json.get('resources').get('requests')
        if requests:
            if requests.get('cpu'): self.resources['cpu_shares'] = int(requests.get('cpu') * 1024)
            if requests.get('memory'): self.mem_request = requests.get('memory')
        limits = arg_json.get('resources').get('limits')
        if limits:
            if limits.get('cpu'):
                self.resources['cpu_period'] = 100000
                self.resources['cpu_quota'] = limits.get('cpu') * self.resources['cpu_period']
            if limits.get('memory'): self.resources['mem_limit'] = limits.get('memory')

        #volumeMounts部分忽略subPath字段
        self.volumes = dict()
        if arg_json.get('volumeMounts') is not None:
            volumes = dict()
            for volume in arg_json.get('volumeMounts'):
                mode = 'ro' if volume.get('readOnly', False) else 'rw'
                host_path = volumes_map[volume.get('name')]
                bind_path = volume.get('mountPath')

                volumes[host_path] = {'bind': bind_path, 'mode': mode}
            self.volumes['volumes'] = volumes

    def dockerapi_args(self):
        return {
            'image': self.image,
            'name': self.name,
            'command': self.command + self.args,
            **self.volumes,
            **self.port,
            **self.resources
        }