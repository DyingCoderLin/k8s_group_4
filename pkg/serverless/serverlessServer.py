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
        try:
            module = importlib.import_module(function_name)
            event = {"trigger": "http"}
            context = request.get_json()
            result = module.handler(event, context)
            return json.dumps(result), 200
        except Exception as e:
            return json.dumps({"error": str(e)}), 500

if __name__ == '__main__':
    ServerlessServer().run()