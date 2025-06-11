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

    def call(self, inputs: dict, uri_config):
        if self.type == "ExactlyOne":
            inputs = [i in inputs if i is not None]
            assert len(inputs) == 0, f"Function type '{self.type}' takes only one not-None input."
            final_input = inputs[0]
        else:
            assert len(inputs) == 0, f"Function type '{self.type}' takes only one input."
            final_input = inputs[0]

        url = uri_config.FUNCTION_SPEC_URL.format(node.function_namspace, node.function_name)
        response = requests.put(url, json=final_input)

        if not reponse.ok:
            raise ValueError(f'Function call "{node.function_namspace}/{node.function_name} failed: {reponse.text}"')

        res = response.json()
        if "error" in res:
            raise ValueError(f'Error on function {self.function_namespace}:{self.function_names} on DAG node {self.name}: {res["error"]}')

        if self.type == "IfElse":
            bool_out = res["bool_out"]
            invalid_out = [self.out[0] if bool_out else self.out[1]]
            return res["origin_in"], invalid_out
        else:
            return res, []

class Workflow():
    def __init__(self, config, uri_config):
        self.config = config
        self.uri_config = uri_config

        self.nodes = []
        for i, _ in enumerate(self.config.DAG):
            self.nodes.append(Node(**self.confg.node_args(i))

        for i, node_json in enumerate(self.config.DAG):
            for out_name in node_json['out']:
                in_i, out_i = i, self.config.name_dict(out_name)
                self.nodes[in_i].out_i.append(out_i)
                self.nodes[out_i].in_i.append(in_i)

    def run(self, context, debug = False):
        q = queue.Queue()
        n_input = [0] * len(self.nodes)
        f_output = [None] * len(self.nodes)
        valid = [True] * len(self.nodes)

        try:
            for i, node in enumerate(self.nodes):
                if n_input[i] == node.num_input():
                    q.put(i)

            while not q.empty():
                i = q.get()

                # 收集输入
                valid[i] = valid[i] or self.nodes[i].force_valid
                if valid[i]:
                    node_input = [f_output[j] for j in self.nodes[i].in_i]
                    f_output[i], invalid_out = self.nodes[i].call(node_input, self.uri_config)
                    for i in invalid_out:
                        valid[i] = False

                for out_i in self.nodes[i].out:
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
            raise f"Workflow {self.config.namespace}:{self.config.name} failed: {str(e)}"

if __name__ == '__main__':
    def test_function(yaml_path, input_json):
        print('测试函数上传')
        yaml_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '../../testFile/function-1.yaml')
        with open(yaml_path, "r", encoding="utf-8") as file:
            data = yaml.safe_load(file)
        file_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                 '../../testFile/serverless/zip-function/pkgs(文件在第一层).zip')
        with open(file_path, 'rb') as f:
            file_data = f.read()

        files = {'file': (os.path.basename(file_path), file_data)}
        url = URIConfig.PREFIX + URIConfig.FUNCTION_SPEC_URL.format(namespace='default', name='hello')
        response = requests.post(url, files=files, data=data)
        print(response.json())
        input('Press Enter To Continue.')

        print('测试函数调用')
        response = requests.put(url, json=input_json)
        print(response.json())