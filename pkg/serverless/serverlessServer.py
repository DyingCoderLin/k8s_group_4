import importlib
import json
from flask import Flask, request

class ServerlessServer():
    def __init__(self):
        self.app = Flask(__name__)
        self.app.route('/<function_name>', methods=["POST"])(self.exec)

    def run(self):
        self.app.run(host='0.0.0.0', port=6000, processes=True)

    def exec(self, function_name : str):
        module = importlib.import_module(function_name)
        event = {"method": "http"}
        context = request.get_json()
        return context, 200
        result = module.handler(event, context)
        return json.dumps(result), 200

if __name__ == '__main__':
    ServerlessServer().run()