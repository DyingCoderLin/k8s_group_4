from transformers import pipeline, set_seed
import torch
from typing import Dict

# 全局加载模型，避免重复加载
_gen_pipe = None


def handler(event: Dict, context: Dict) -> Dict:
    global _gen_pipe

    # 延迟加载模型
    if _gen_pipe is None:
        print("Loading generation model...")
        _gen_pipe = pipeline(
            'text-generation',
            model='./GPT-Neo-50m',
            device=0 if torch.cuda.is_available() else -1,
            torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32
        )
        set_seed(42)

    # 从context获取输入
    prompt = context.get('text', '')
    max_length = context.get('max_length', 50)
    temperature = context.get('temperature', 0.7)

    # 生成文本
    generated = _gen_pipe(
        prompt,
        max_length=max_length,
        temperature=temperature,
        do_sample=True,
        truncation=True,
        pad_token_id=50256  # GPT2的EOS token
    )

    # 更新context
    context['generated_text'] = generated[0]['generated_text']
    context['generation_model'] = 'distilgpt2'

    return context


if __name__ == '__main__':
    """测试 handler 函数的正确性"""
    # 测试用例 - 英文生成
    test_context = {
        'text': 'The future of AI is',
        'max_length': 30,
        'temperature': 0.7
    }

    print("=== 开始测试 ===")
    print("输入:", test_context['text'])

    # 调用 handler
    result = handler({}, test_context)

    # 检查输出
    assert 'generated_text' in result, "生成失败，无 generated_text 字段"
    assert isinstance(result['generated_text'], str), "生成的文本不是字符串"
    assert len(result['generated_text']) > len(test_context['text']), "生成文本过短"

    print("=== 测试通过 ===")
    print("生成结果:", result['generated_text'])
    print("使用的模型:", result['generation_model'])