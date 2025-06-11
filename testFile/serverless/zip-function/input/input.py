from typing import Dict

def input_handler(event: Dict, context: Dict) -> Dict:
    """
    输入节点handler，验证输入格式是否符合要求

    接受的输入格式：
    1. 生成式任务格式：
       {
           "text": "要生成的文本开头",
           "max_length": 100,
           "temperature": 0.7
       }

    2. 对话式任务格式：
       {
           "text": "用户消息",
           "chat_history": [  # 可选，对话历史
               ["用户消息1", "AI回复1"],
               ["用户消息2", "AI回复2"]
           ]
       }

    返回：
        context
        {"error": "invalid input context"}
    """
    if not isinstance(context.get('text'), str):
        return {
            "error": "invalid input context",
        }

    # 如果是generation格式
    # if 'max_length' in context or 'temperature' in context:
    #     valid = True
    #     if 'max_length' in context and not isinstance(context['max_length'], int):
    #         valid = False
    #     if 'temperature' in context and not isinstance(context['temperature'], (int, float)):
    #         valid = False

    #     if 'chat_history' in context:
    #         valid = False

    #     if valid is False:
    #         return {
    #             "error": "invalid input context",
    #         }

    # # 如果是chat格式
    # if 'chat_history' in context:
    #     chat_history = context['chat_history']
    #     if not isinstance(chat_history, list):
    #         return {
    #             "error": "invalid input context",
    #         }

    return context