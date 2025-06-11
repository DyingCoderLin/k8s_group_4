import queue

class Node:
    def __init__(self, name, type, function_namespace, function_name):
        self.name = name
        self.type = type #[Foward, IfElse, ExactlyOne] 呵呵呵，我没时间写抽象类再细分几个子类了，所以感觉不优雅
        self.force_valid = (type in ["IfElse", "ExactlyOne"])
        self.function_name = function_name
        self.function_namespace = function_namespace

        self.in_i = []
        self.out_i = []

    def num_input(self):
        return len(self.in_i)

    def num_output(self):
        return len(self.out_i)

    def call(self, inputs, uri_config, debug=False):
        if self.type == "ExactlyOne":
            inputs = [i for i in inputs if i is not None]
            assert len(inputs) == 1, f"Function type '{self.type}' takes only one not-None input."
            final_input = inputs[0]
        else:
            assert len(inputs) == 1, f"Function type '{self.type}' takes only one input."
            final_input = inputs[0]

        if not debug:
            url = uri_config.FUNCTION_SPEC_URL.format(self.function_namspace, self.function_name)
            response = requests.put(url, json=final_input)

            if not response.ok:
                raise ValueError(f'Function call "{self.function_namspace}/{self.function_name} failed: {response.text}"')

            res = response.json()
        else:
            if self.type == "IfElse":
                res = {
                    'bool_out': True,
                    'origin_in': final_input
                }
            else:
                res = final_input

        if "error" in res:
            raise ValueError(f'Error on function {self.function_namespace}:{self.function_names} on DAG node {self.name}: {res["error"]}')

        if self.type == "IfElse":
            bool_out = res["bool_out"]
            invalid_out = [self.out_i[0] if bool_out else self.out_i[1]]
            return res["origin_in"], invalid_out
        else:
            return res, []

class Workflow():
    def __init__(self, config, uri_config):
        self.config = config
        self.uri_config = uri_config

        self.nodes = []
        for i, _ in enumerate(self.config.DAG):
            self.nodes.append(Node(**self.config.node_args(i)))

        for i, node_json in enumerate(self.config.DAG):
            for out_name in node_json['out']:
                in_i, out_i = i, self.config.name_dict[out_name]
                self.nodes[in_i].out_i.append(out_i)
                self.nodes[out_i].in_i.append(in_i)

    def exec(self, context, debug = False):
        q = queue.Queue()
        start = None
        n_input = [0] * len(self.nodes)
        f_output = [None] * len(self.nodes)
        valid = [True] * len(self.nodes)

        try:
            for i, node in enumerate(self.nodes):
                if n_input[i] == node.num_input():
                    q.put(i)
                    if start:
                        raise ValueError('DAG should only have one start node.')
                    start = i

            while not q.empty():
                i = q.get()

                # 收集输入
                valid[i] = valid[i] or self.nodes[i].force_valid
                if valid[i]:
                    node_input = [f_output[j] for j in self.nodes[i].in_i] if i != start else [context]
                    f_output[i], invalid_out = self.nodes[i].call(node_input, self.uri_config, debug)
                    for j in invalid_out:
                        valid[j] = False

                for out_i in self.nodes[i].out_i:
                    n_input[out_i] += 1
                    if not valid[i]:
                        valid[out_i] = False
                    if n_input[out_i] == self.nodes[out_i].num_input():
                        q.put(out_i)

            for i, node in enumerate(self.nodes):
                if node.num_output() == 0:
                    if f_output[i] is None:
                        raise ValueError("DAG path did not reach destination.")
                    return f_output[i]
            raise ValueError("DAG does not have an destination.")
        except Exception as e:
            raise ValueError(f"Workflow {self.config.namespace}:{self.config.name} failed: {str(e)}")

if __name__ == '__main__':
    from pkg.config.uriConfig import URIConfig
    from pkg.config.podConfig import PodConfig
    from pkg.config.globalConfig import GlobalConfig
    import os
    import yaml
    import requests
    config = GlobalConfig()

    functions = ['chat', 'gen', 'ifelse', 'input']
    def upload_function(func):
        yaml_path = os.path.join(config.TEST_FILE_PATH, f'function-{func}.yaml')
        print(f'上传函数{yaml_path}')
        with open(yaml_path, "r", encoding="utf-8") as file:
            data = yaml.safe_load(file)
        file_path = os.path.join(config.TEST_FILE_PATH,
                                 f'serverless/zip-function/{func}.zip')
        with open(file_path, 'rb') as f:
            file_data = f.read()

        files = {'file': (os.path.basename(file_path), file_data)}
        url = URIConfig.PREFIX + URIConfig.FUNCTION_SPEC_URL.format(namespace='default', name=func)
        print(f'[INFO]上传函数 {func} 到 {url}')
        response = requests.post(url, files=files, data=data)
        print(response.json())

    for func in functions:
        upload_function(func)

    yaml_path = os.path.join(config.TEST_FILE_PATH, 'workflow-1.yaml')
    with open(yaml_path, "r", encoding="utf-8") as file:
        data = yaml.safe_load(file)

    print(f'[INFO]测试创建')
    uri = URIConfig.PREFIX + URIConfig.WORKFLOW_SPEC_URL.format(
        namespace=data["metadata"]["namespace"],
        name=data["metadata"]["name"],
    )
    response = requests.post(uri, json=data)
    print(response.json())

    input('Press Enter To Continue.')
    print(f'[INFO]测试执行')
    gen_input = {
        "text": "The future of AI is ",
    }
    response = requests.patch(uri, json=gen_input)
    print(response.json())

    input('Press Enter To Continue.')
    chat_input = {
        "text": "How are you?",
        "chat_history": [ "The future of AI is bright.", "I think AI will change the world."]
    }
    response = requests.patch(uri, json=chat_input)
    print(response.json())