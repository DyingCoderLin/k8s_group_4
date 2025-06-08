import importlib
from flask import Flask, request

class ServerlessServer():
    def __init__(self):
        self.app = Flask(__name__)
        self.app.route(config.GLOBAL_PODS_URL, methods=["POST"])(self.exec)

    def run(self):
        self.app.run(host='0.0.0.0', port=5000, processes=True)

    def exec(module_name: str, function_name: str):
        module = importlib.import_module(module_name)
        event = {"method": "http"}
        context = request.form.to_dict()
        result = eval("module.{}".format(function_name))(event, context)
        return result, 200

if __name__ == '__main__':
    ServerlessServer().run()