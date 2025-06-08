import json
import os
from typing import Dict

import requests
from repo import add, encode
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
        a, b = int(context['a']), int(context['b'])

        result = add(a, b)
        message = f'Hello {encode(result)}!'

        return {
            'result': result,
            'message': message,
        }

    except Exception as e:
        return {
            "error": str(e)
        }