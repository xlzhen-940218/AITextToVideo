"""
storyboard.py - 用 AI 将故事拆分为分镜，并使用 ComfyUI 生成整套分镜图片

工作流程：
  1. 从 story.txt 读取故事文本
  2. 调用 DeepSeek AI 分析故事，拆分为多个分镜
  3. 每个分镜保持统一的美术风格和角色一致性
  4. 调用 text_to_image.py 的 generate_images() 批量生成所有分镜图片

用法：
  python storyboard.py                                          # 使用默认配置
  python storyboard.py --style "日式动漫风格"                     # 自定义风格
  python storyboard.py --shots 6                                 # 指定分镜数量
  python storyboard.py --width 1024 --height 576                 # 自定义图片尺寸
  python storyboard.py --seed 42                                 # 固定随机种子（保证可复现）
"""

import json
import os
import re
import sys
import argparse
import random
import yaml
from openai import OpenAI

# ================= 配置区 =================
CONFIG_FILE = "private_config.yaml"
INPUT_STORY_FILE = "story.txt"
OUTPUT_DIR = "storyboard_output"  # 分镜图片输出目录

# AI 模型参数
CHUNK_MAX_LENGTH = 2000  # 每块最大字符数（故事过长时拆分处理）
AI_TEMPERATURE = 0.3     # AI 生成温度（较低值确保一致性）
AI_MAX_TOKENS = 4096     # AI 单次最大输出

# 图片生成默认参数
DEFAULT_WIDTH = 1280
DEFAULT_HEIGHT = 720
DEFAULT_STEPS = 8

# ================= 工具函数 =================

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


# ================= AI 分镜分析 =================

def analyze_story_for_storyboard(client, text_chunk, chunk_index, total_chunks, art_style, target_shots=None):
    """
    调用 DeepSeek AI 分析故事文本，提取分镜描述。

    返回 JSON 数组，每个元素包含：
      - shot_index: 分镜序号
      - scene_title: 场景标题
      - characters: 场景中出现的角色列表
      - prompt: 用于文生图的详细英文提示词（包含风格、构图、光线、色彩等）
      - description: 场景的中文描述（辅助理解）
    """
    # 构建 shots 指令
    shots_instruction = ""
    if target_shots:
        shots_instruction = f"请将此故事拆分为约 {target_shots} 个分镜。"

    system_prompt = f"""
    你是一个专业的动漫/影视分镜师。你需要分析传入的故事文本，将其拆分为一系列连续的分镜镜头。

    {shots_instruction}

    【核心规则】
    1. 每个分镜应聚焦一个关键场景或动作序列，按故事发展顺序排列。
    2. 每个分镜必须包含详细、高质量的英文图片生成提示词（prompt）。
    3. **所有分镜的美术风格必须完全统一**，使用以下指定风格：
       风格: {art_style}
    4. 角色在不同分镜中出现的提示词要保持一致（外貌、服装、发型等特征）。
    5. 每个分镜的 prompt 要详细描述：场景环境、角色位置与姿态、构图角度、光线氛围、色彩基调。

    请严格输出一个 JSON 数组，不要包含任何额外废话。
    数组中的每个对象必须包含以下字段：
    1. "shot_index": 分镜序号（从1开始递增）
    2. "scene_title": 场景标题（简短中文，如"小巷入口"、"后台邂逅"）
    3. "characters": 本镜出现的角色名列表，如 ["陈夜", "陈艺"]
    4. "prompt": 高质量的英文图片生成提示词。必须包含风格描述、角色外观、场景、构图、光线、氛围。
    5. "description": 场景的中文描述（一两句话说明本镜内容）

    【输出格式示例】
    [
      {{
        "shot_index": 1,
        "scene_title": "霓虹街景",
        "characters": ["陈夜"],
        "prompt": "cyberpunk city street at night, neon holographic billboards, {art_style}, wide angle view, a young man in dark coat walking through the crowd, cinematic lighting, vibrant purple and blue tones, detailed urban environment, high quality, 8k",
        "description": "陈夜穿过第112层娱乐区的繁华街道，巨型全息广告牌在空中闪烁。"
      }},
      {{
        "shot_index": 2,
        "scene_title": "Livehouse后台",
        "characters": ["陈夜", "陈艺"],
        "prompt": "backstage dressing room of a small livehouse, warm yellow tungsten lights, mirrored makeup table with bulbs, {art_style}, a young female idol in pink sailor-style stage costume sitting before mirror, a man standing at doorway, intimate atmosphere, shallow depth of field, detailed reflections in mirror, high quality, 8k",
        "description": "陈夜走进黑洞Livehouse的后台，看到正在卸妆的地下偶像陈艺。"
      }}
    ]
    """

    print(f"🧠 正在分析第 {chunk_index}/{total_chunks} 部分故事...")

    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"请分析以下故事文本并生成分镜：\n\n{text_chunk}"}
            ],
            temperature=AI_TEMPERATURE,
            max_tokens=AI_MAX_TOKENS
        )

        if response.choices[0].finish_reason == "length":
            print(f"[警告] 第 {chunk_index} 部分分析被截断，结果可能不完整！")

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
        print(f"原始响应:\n{result_content if 'result_content' in dir() else 'N/A'}")
        return []
    except Exception as e:
        print(f"[错误] 第 {chunk_index} 部分请求失败: {e}")
        return []


def generate_style_consolidation_prompt(client, all_shots, art_style):
    """
    可选：再次调用 AI 对所有分镜的 prompt 进行统一风格优化，
    确保角色外观、美术风格的一致性。
    """
    if not all_shots:
        return all_shots

    print("🎨 正在优化统一风格和角色一致性...")

    # 构建当前分镜的摘要
    shots_summary = json.dumps(
        [{"shot_index": s["shot_index"], "scene_title": s["scene_title"],
          "characters": s["characters"], "prompt": s["prompt"]}
         for s in all_shots],
        ensure_ascii=False, indent=2
    )

    system_prompt = f"""
    你是一个专业的动画/影视美术总监。你的任务是确保以下所有分镜的图片生成提示词在美术风格和角色外观上保持**高度一致**。

    【统一风格】: {art_style}

    【角色一致性】: 确保同一个角色在不同分镜中的外貌描述完全一致（发型、服装颜色、体型等）。

    【质量增强】: 在每个 prompt 末尾添加通用的画质修饰词，如 "high quality, detailed, 8k, masterpiece, cinematic lighting"。

    请输出完整的 JSON 数组（保持原有结构不变，只修改 prompt 字段）。
    """

    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"请统一优化以下分镜的提示词：\n\n{shots_summary}"}
            ],
            temperature=0.2,
            max_tokens=AI_MAX_TOKENS
        )

        result_content = response.choices[0].message.content.strip()
        json_match = re.search(r'\[.*\]', result_content, re.DOTALL)
        if json_match:
            json_str = json_match.group(0)
        else:
            json_str = result_content

        optimized_shots = json.loads(json_str)

        # 合并优化后的 prompt 回原始数据
        opt_map = {s["shot_index"]: s for s in optimized_shots}
        for shot in all_shots:
            if shot["shot_index"] in opt_map:
                shot["prompt"] = opt_map[shot["shot_index"]]["prompt"]

        print("✅ 风格统一优化完成!")
        return all_shots

    except Exception as e:
        print(f"[警告] 风格优化失败，使用原始分镜: {e}")
        return all_shots


# ================= 主流程 =================

def generate_storyboard(
    art_style="日式动漫风格，赛博朋克，细腻光影，高饱和霓虹色调",
    target_shots=None,
    width=DEFAULT_WIDTH,
    height=DEFAULT_HEIGHT,
    steps=DEFAULT_STEPS,
    seed=None,
    skip_consolidation=False,
):
    """
    完整的分镜生成流程：

    1. 读取故事文本
    2. AI 分析拆分分镜
    3. 风格统一优化（可选）
    4. 批量生成图片

    返回: (shots_list, generated_files)
      - shots_list: 分镜信息列表
      - generated_files: 生成的图片文件路径列表
    """
    # ========== 1. 加载配置 ==========
    api_key = load_api_key(CONFIG_FILE)
    if not api_key:
        print("[错误] 未能成功加载 API Key，程序退出。")
        return [], []

    client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")

    # ========== 2. 读取故事 ==========
    if not os.path.exists(INPUT_STORY_FILE):
        print(f"[错误] 找不到故事文件 '{INPUT_STORY_FILE}'。")
        return [], []

    with open(INPUT_STORY_FILE, "r", encoding="utf-8") as f:
        story_text = f.read()

    print(f"📖 已读取故事文件: {INPUT_STORY_FILE} ({len(story_text)} 字符)")

    # ========== 3. AI 分析分镜 ==========
    chunks = split_text_into_chunks(story_text, CHUNK_MAX_LENGTH)

    if len(chunks) > 1:
        print(f"📄 故事较长，已切分为 {len(chunks)} 个处理块分别分析。")
    else:
        print("📄 故事较短，一次性分析。")

    all_shots = []
    shot_offset = 0  # 跨块的序号偏移

    for i, chunk in enumerate(chunks, 1):
        if not chunk.strip():
            continue

        # 根据总块数调整目标分镜数
        shots_per_chunk = None
        if target_shots:
            shots_per_chunk = max(2, target_shots // len(chunks))

        chunk_result = analyze_story_for_storyboard(
            client, chunk, i, len(chunks), art_style, shots_per_chunk
        )

        if chunk_result:
            # 调整序号
            for shot in chunk_result:
                shot["shot_index"] += shot_offset
            shot_offset = chunk_result[-1]["shot_index"] if chunk_result else shot_offset
            all_shots.extend(chunk_result)

    if not all_shots:
        print("❌ 未能从故事中提取到任何分镜。")
        return [], []

    print(f"\n✅ AI 分析完成！共生成 {len(all_shots)} 个分镜。")

    # 打印分镜摘要
    for shot in all_shots:
        chars_str = ", ".join(shot.get("characters", []))
        print(f"  📋 分镜 {shot['shot_index']}: {shot['scene_title']} [{chars_str}]")

    # ========== 4. 风格统一优化（可选） ==========
    if not skip_consolidation:
        all_shots = generate_style_consolidation_prompt(client, all_shots, art_style)

    # ========== 5. 保存分镜信息 ==========
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)

    shots_file = os.path.join(OUTPUT_DIR, "storyboard_shots.json")
    with open(shots_file, "w", encoding="utf-8") as f:
        json.dump(all_shots, f, ensure_ascii=False, indent=2)
    print(f"\n💾 分镜信息已保存: {shots_file}")

    # ========== 6. 批量生成图片 ==========
    from text_to_image import generate_images, COMFYUI_OUTPUT_DIR

    generated_files = []
    print(f"\n{'='*50}")
    print(f"🎬 开始批量生成 {len(all_shots)} 个分镜图片...")
    print(f"{'='*50}")

    for idx, shot in enumerate(all_shots):
        prompt_text = shot["prompt"]
        shot_seed = (seed + shot["shot_index"]) if seed else None

        print(f"\n--- 分镜 {shot['shot_index']}/{len(all_shots)}: {shot['scene_title']} ---")

        files = generate_images(
            prompt_text=prompt_text,
            seed=shot_seed,
            width=width,
            height=height,
            steps=steps,
        )

        if files:
            # 重命名文件，加入分镜序号以便识别
            for f in files:
                src_path = os.path.join(COMFYUI_OUTPUT_DIR, f)
                new_name = f"shot_{shot['shot_index']:02d}_{shot['scene_title']}_{f}"
                dst_path = os.path.join(OUTPUT_DIR, new_name)
                try:
                    os.rename(src_path, dst_path)
                    generated_files.append(dst_path)
                    print(f"  ✅ -> {new_name}")
                except Exception:
                    # 如果重命名失败，保留原文件
                    generated_files.append(src_path)
                    print(f"  ✅ {src_path}")

    # 打印最终总结
    print(f"\n{'='*50}")
    print(f"🎉 分镜生成完成！")
    print(f"   总图片: {len(generated_files)} 张")
    print(f"   输出目录: {os.path.abspath(OUTPUT_DIR)}")
    print(f"{'='*50}")

    return all_shots, generated_files


# ================= 命令行入口 =================
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="用 AI 将故事拆分为分镜，并使用 ComfyUI 生成整套分镜图片",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s                                          # 默认风格生成分镜
  %(prog)s --style "吉卜力风格, 温暖治愈, 细腻水彩"    # 自定义风格
  %(prog)s --shots 8                                 # 指定 8 个分镜
  %(prog)s --width 1024 --height 576 --steps 6       # 自定义图片质量
  %(prog)s --seed 42                                  # 固定种子可复现
  %(prog)s --no-consolidate                           # 跳过风格优化步骤
        """,
    )
    parser.add_argument("--style", type=str,
                        default="迪士尼风格",
                        help="统一的美术风格描述 (默认: 日式动漫赛博朋克)")
    parser.add_argument("--shots", type=int, default=None,
                        help="目标分镜数量 (默认: AI 自动决定)")
    parser.add_argument("--width", type=int, default=DEFAULT_WIDTH,
                        help=f"图片宽度 (默认: {DEFAULT_WIDTH})")
    parser.add_argument("--height", type=int, default=DEFAULT_HEIGHT,
                        help=f"图片高度 (默认: {DEFAULT_HEIGHT})")
    parser.add_argument("--steps", type=int, default=DEFAULT_STEPS,
                        help=f"采样步数 (默认: {DEFAULT_STEPS})")
    parser.add_argument("--seed", type=int, default=None,
                        help="随机种子 (默认: 随机，所有分镜使用相同种子链)")
    parser.add_argument("--no-consolidate", action="store_true",
                        help="跳过 AI 风格统一优化步骤")

    args = parser.parse_args()

    # 如果未提供 seed，随机生成一个
    if args.seed is None:
        args.seed = random.randint(1, 99999999)

    print(f"🎬 故事转分镜生成器")
    print(f"   风格: {args.style}")
    print(f"   尺寸: {args.width}x{args.height}")
    print(f"   步数: {args.steps}")
    print(f"   种子: {args.seed}")
    if args.shots:
        print(f"   目标分镜数: {args.shots}")
    if args.no_consolidate:
        print(f"   跳过风格优化: 是")
    print()

    generate_storyboard(
        art_style=args.style,
        target_shots=args.shots,
        width=args.width,
        height=args.height,
        steps=args.steps,
        seed=args.seed,
        skip_consolidation=args.no_consolidate,
    )
