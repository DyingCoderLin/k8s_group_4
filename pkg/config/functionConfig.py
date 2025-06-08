class FunctionConfig:
    def __init__(self, namespace, name, code_dir):
        self.namespace = namespace
        self.name = name
        self.code_dir = code_dir
        self.target_image = None

        self.pod_list = []