from transformers import pipeline, AutoModelForCausalLM, AutoTokenizer
import torch
from typing import Dict, List

# 全局变量保持加载状态
_chat_pipe = None
_tokenizer = None  # 需要单独保存tokenizer


def handler(event: Dict, context: Dict) -> Dict:
    global _chat_pipe, _tokenizer

    # 延迟加载模型
    if _chat_pipe is None:
        print("Loading dialogue model...")
        try:
            model = AutoModelForCausalLM.from_pretrained(
                "./DialoGPT-small",
                torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32,
                use_safetensors=False
            )
            _tokenizer = AutoTokenizer.from_pretrained("./DialoGPT-small")
            _tokenizer.pad_token = _tokenizer.eos_token  # 确保pad token设置

            _chat_pipe = pipeline(
                'text-generation',
                model=model,
                tokenizer=_tokenizer,
                device=0 if torch.cuda.is_available() else -1
            )
        except Exception as e:
            return {"error": f"模型加载失败: {str(e)}"}

    # 获取对话历史和新输入
    chat_history: List[str] = context.get('chat_history', [])
    new_input: str = context.get('text', '').strip()

    if not new_input:
        return {"error": "输入文本不能为空"}

    # 组合对话历史 (添加特殊token分隔对话轮次)
    full_input = "\n".join(chat_history + [new_input])

    # 生成回复 (添加更安全的生成参数)
    try:
        response = _chat_pipe(
            full_input,
            max_new_tokens=512,
            pad_token_id=_tokenizer.eos_token_id,
            temperature=0.7,
            do_sample=True,
            truncation=True,
        )[0]

        # 只提取新生成的回复
        new_response = response['generated_text'][len(full_input):].strip()

        # 更新context
        return {
            'response': new_response,
            'chat_history': chat_history + [new_input, new_response],
            'dialogue_model': 'DialoGPT-small',
            'status': 'success'
        }

    except Exception as e:
        return {"error": f"生成回复时出错: {str(e)}"}


if __name__ == "__main__":
    """测试对话 handler 函数的正确性"""
    # 初始化对话
    test_context = {
        'text': 'Hello, how are you?',
        'chat_history': []
    }

    print("=== Testing Dialogue Handler ===")
    print("user:", test_context['text'])

    # 第一次对话
    result = handler({}, test_context)
    if 'error' in result:
        print("Error:", result['error'])
        exit(1)

    print("gpt:", result['response'])

    # 第二次对话（带历史）
    test_context['text'] = 'What can you do?'
    test_context['chat_history'] = result['chat_history']
    result = handler({}, test_context)
    print("gpt:", result['response'])

    # 验证输出
    assert 'response' in result, "生成失败，无response字段"
    assert isinstance(result['response'], str), "生成的回复不是字符串"
    assert len(result['chat_history']) == 4, f"对话历史记录不正确，得到{len(result['chat_history'])}条"

    print("\n=== Test Passed ===")
    print("Final Response:", result['response'])
    print("Dialog History:", result['chat_history'])
    print("Model Used:", result.get('dialogue_model', 'unknown'))