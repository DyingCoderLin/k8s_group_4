class FunctionConfig:
    def __init__(self, namespace, name, trigger, code_dir):
        self.namespace = namespace
        self.name = name
        self.trigger = trigger
        self.code_dir = code_dir
        self.target_image = None

        self.pod_list = []

    def to_dict(self):
        return {
            "metadata": {
                "name": self.name,
                "namespace": self.namespace,
            },
            "trigger": self.trigger,
            "build":{
                "file": self.code_dir,
                "image": self.target_image
            },
            "running_pods": [pod.to_dict() for pod in self.pod_list]
        }