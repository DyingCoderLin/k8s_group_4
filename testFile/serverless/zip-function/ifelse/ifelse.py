from typing import Dict

def handler(event: Dict, context: Dict) -> Dict:
    return {
        "bool_out": 'chat_history' not in context,
        "origin_in": context,
    }