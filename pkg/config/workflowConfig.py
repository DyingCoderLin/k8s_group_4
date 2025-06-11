class WorkflowConfig:
    def __init__(self, arg_json):
        metadata = arg_json.get("metadata")
        self.name = metadata.get("name")
        self.namespace = metadata.get("namespace", "default")
        self.labels = metadata.get("labels", {})

        self.DAG = arg_json.get("DAG", [])
        self.name_dict = dict()
        for i, node in enumerate(self.DAG):
            if node['name'] in self.name_dict:
                raise ValueError(f'Duplicated DAG node name {node["name"]}')
            self.name_dict[node['name']] = i

    def node_args(self, i):
        node_json = self.DAG[i]
        if node_json['type'] == 'ExactlyOne':
            function_namespace, function_name = None, None
        else:
            function_namespace = node_json['function']['namespace']
            function_name = node_json['function']['name']

        return {
            'name': node_json['name'],
            'type': node_json['type'],
            'function_namespace': function_namespace,
            'function_name': function_name
        }