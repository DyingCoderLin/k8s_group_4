import json
import os
from typing import Dict

import requests
from repo import use_api
from datetime import datetime

def handler(event: Dict, context: Dict) -> Dict:
    """
    AWS Lambda 函数示例，调用外部API并返回处理结果

    参数:
        event (dict): 触发事件的数据 (如API Gateway请求)
        context (dict): 运行时上下文信息

    返回:
        dict: 包含状态码和数据的响应
    """
    try:
        # 1. 从event中获取输入参数 (示例：API Gateway的查询参数)
        query_params = event.get('queryStringParameters', {})
        user_id = query_params.get('user_id', 'default')

        # 2. 使用外部库 (requests) 调用API
        response = use_api()

        # 3. 处理数据
        data = {
            "request_time": datetime.now().isoformat(),
            "user_id": user_id,
            "api_data": response.json(),
            "environment_var": os.getenv("STAGE", "dev")  # 从环境变量读取
        }

        # 4. 返回标准API Gateway响应格式
        return {
            "statusCode": 200,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps(data)
        }

    except Exception as e:
        return {
            "statusCode": 500,
            "body": json.dumps({"error": str(e)})
        }

if __name__ == "__main__":
    test_event = {
        "queryStringParameters": {
            "user_id": "test123"
        }
    }
    print(handler(test_event, {}))