from typing import Dict

def handler(event: Dict, context: Dict) -> Dict:
    return context, 'chat_history' not in context