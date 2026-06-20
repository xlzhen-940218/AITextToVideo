import json
import os
import re
import yaml
from openai import OpenAI

# ================= 配置区 =================
CONFIG_FILE = "private_config.yaml"
INPUT_TEXT_FILE = "story.txt"
OUTPUT_JSON_FILE = "input_queue.json"
CHUNK_MAX_LENGTH = 1500  # 每个文本块的最大字符数，避免单次输出超限


def load_api_key(config_path):
    """从 YAML 配置文件中读取 DeepSeek API Key"""
    if not os.path.exists(config_path):
        print(f"[错误] 找不到配置文件 '{config_path}'。")
        return None
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
            return config.get("deepseek", {}).get("api")
    except Exception as e:
        print(f"[错误] 读取配置文件失败: {e}")
        return None


def split_text_into_chunks(text, max_length):
    """将长文本按段落切分成多个短块"""
    paragraphs = text.split('\n')
    chunks = []
    current_chunk = ""

    for p in paragraphs:
        if len(current_chunk) + len(p) < max_length:
            current_chunk += p + "\n"
        else:
            if current_chunk.strip():
                chunks.append(current_chunk.strip())
            current_chunk = p + "\n"

    if current_chunk.strip():
        chunks.append(current_chunk.strip())

    return chunks


def extract_dialogue_chunk(client, text_chunk, chunk_index, total_chunks):
    """处理单个文本块的提取"""
    # 【核心修改区】强化了顺序约束、禁止合并、禁止概括的指令
    system_prompt = """
    你是一个专业的剧本切分和台词提取助手。你需要将传入的文本**逐字逐段**地切分为连续的语音块，并严格按照原文的**绝对物理顺序**输出。

    【核心红线规则】
    1. **绝对顺序**：必须严格按照原文的阅读顺序提取。旁白、对话、再旁白、再对话，原文是怎样交替的，JSON 数组就必须是怎样交替的。
    2. **严禁合并**：绝对不允许将多段分开的旁白合并成一大段！绝对不允许打乱原文的穿插顺序！
    3. **零概括，零遗漏**：不要对原文进行任何总结、提炼或删减！必须原汁原味地保留所有文本，只做切分。

    请严格输出一个 JSON 数组，不要包含任何额外废话。
    数组中的每个对象必须包含以下五个字段：
    1. "name": 角色姓名。环境描写、动作、心理活动统一归类为"旁白"。
    2. "gender": 性别，只能是 "male" 或 "female"。"旁白"统一设为 "female"。
    3. "personality": 推测角色的性格、声线或情绪特征。两三个词概括（如：沉稳干练、温柔、愤怒）。旁白可写"沉稳客观"。
    4. "language": 语种或方言（如：中文普通话、英语等）。未明确默认填 "中文普通话"。
    5. "text": 具体的原文本内容。

    【期望的顺序示例】（必须像这样交替）：
    [
        {"name": "旁白", "gender": "female", "personality": "客观", "language": "中文普通话", "text": "他缓缓推开那扇破旧的木门。"},
        {"name": "张三", "gender": "male", "personality": "警惕", "language": "中文普通话", "text": "谁在里面？"},
        {"name": "旁白", "gender": "female", "personality": "客观", "language": "中文普通话", "text": "房间里无人回应，只有风穿过窗户的呼啸声。"}
    ]
    """

    print(f"🧠 正在分析第 {chunk_index}/{total_chunks} 部分...")

    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"请提取以下文本：\n\n{text_chunk}"}
            ],
            temperature=0.1,  # 【修改】将 temperature 从 0.3 降到 0.1，降低模型发散思维，使其更严格执行指令
            max_tokens=4000
        )

        if response.choices[0].finish_reason == "length":
            print(f"[警告] 第 {chunk_index} 部分提取被截断，可能遗漏部分台词！建议减小 CHUNK_MAX_LENGTH。")

        result_content = response.choices[0].message.content.strip()

        # 使用正则提取 JSON 数组
        json_match = re.search(r'\[.*\]', result_content, re.DOTALL)
        if json_match:
            json_str = json_match.group(0)
        else:
            json_str = result_content

        parsed_data = json.loads(json_str)
        return parsed_data

    except json.JSONDecodeError as e:
        print(f"[错误] 第 {chunk_index} 部分 JSON 解析失败: {e}")
        return []
    except Exception as e:
        print(f"[错误] 第 {chunk_index} 部分请求失败: {e}")
        return []


if __name__ == "__main__":
    # 1. 读取配置
    api_key = load_api_key(CONFIG_FILE)
    if not api_key:
        print("[错误] 未能成功加载 API Key，程序退出。")
        exit(1)

    # 2. 读取文本
    if not os.path.exists(INPUT_TEXT_FILE):
        print(f"[错误] 找不到 '{INPUT_TEXT_FILE}'，请先创建并填入文本。")
        exit(1)

    with open(INPUT_TEXT_FILE, "r", encoding="utf-8") as f:
        novel_text = f.read()

    # 3. 初始化客户端
    client = OpenAI(
        api_key=api_key,
        base_url="https://api.deepseek.com"
    )

    # 4. 执行提取
    chunks = split_text_into_chunks(novel_text, CHUNK_MAX_LENGTH)
    print(f"📄 长文本已切分为 {len(chunks)} 个处理块。")

    full_extracted_queue = []

    for i, chunk in enumerate(chunks, 1):
        if not chunk.strip():
            continue
        chunk_result = extract_dialogue_chunk(client, chunk, i, len(chunks))
        if chunk_result:
            full_extracted_queue.extend(chunk_result)

    # 5. 保存结果
    if full_extracted_queue:
        with open(OUTPUT_JSON_FILE, "w", encoding="utf-8") as f:
            json.dump(full_extracted_queue, f, ensure_ascii=False, indent=4)
        print(f"✅ 全部提取成功！共生成了 {len(full_extracted_queue)} 条配音队列。")
    else:
        print("❌ 未能提取到任何有效的配音队列。")