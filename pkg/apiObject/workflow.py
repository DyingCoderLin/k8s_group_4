import queue

class Node:
    def __init__(self, type, function_namespace, function_name):
        self.type = type
        self.function_name = function_name
        self.function_namespace = function_namespace

        self.num_input = 0
        self.in_i = []
        self.out_i = []

class Workflow():
    def __init__(self, config, uri_config):
        self.config = config
        self.uri_config = uri_config
        self.nodes = []

    def node_call(self, node: Node, context: dict):
        url = self.uri_config.FUNCTION_SPEC_URL.format(node.function_namspace, node.function_name)
        response = requests.put(url, json=context)
        if reponse.ok:
            return response.json()
        raise ValueError(f'Function call "{node.function_namspace}/{node.function_name} failed."')

    def run(self, context):
        q = queue.Queue()
        n_input = [0] * len(self.nodes)
        f_output = [None] * len(self.nodes)

        try:
            for i, node in enumerate(self.nodes):
                if n_input[i] == node.num_input:
                    f_output[i] = node_call(node, context)
                    q.put(i)

            while not q.empty():
                i = q.get()
                for out_i in self.nodes[i].out:
                    n_input[out_i] += 1
                    if n_input[out_i] == self.nodes[out_i].num_input:
                        q.put(out_i)
        except Exception as e:
            raise f"Workflow {self.config.namespace}/{self.config.name} failed: {str(e)}"

