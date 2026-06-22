"""
app.py - 文本故事生成 AI 视频的完整 Web 应用后端

前后端分离架构：
  后端 (Flask Python API) → ComfyUI API → 生成图片/视频
  前端 (HTML/JS) → 调用后端 API 展示结果

工作流程：
  1. 用户导入故事文本 → AI 分析生成分镜列表
  2. 用户可编辑分镜内容
  3. 点击"生成图片" → 调用 ComfyUI Text_to_Image 工作流
  4. 点击"生成视频" → 调用 ComfyUI Image_to_Video 工作流
  5. 不满意可"重新生成"
  6. 视频+配音自动合并，全部完成后可合并为完整视频
"""

import json
import os
import sys
import time
import threading
import random
import shutil
import subprocess
import yaml
from openai import OpenAI
from flask import Flask, request, jsonify, send_from_directory, abort
from flask_cors import CORS

# ================= 配置区（从 public_config.yaml 加载） =================
from config_loader import get

CONFIG_FILE = "private_config.yaml"         # 私有 API Key 配置（不纳入公共配置）
INPUT_STORY_FILE = "story.txt"              # 输入故事文件
OUTPUT_DIR = get("output_dir", "storyboard_output")
COMFYUI_OUTPUT_DIR = get("comfyui.output_dir", r"F:\ComfyUI\output")

# ================= 叙事人声音库（用于前端下拉菜单） =================
NARRATOR_VOICES = [
    {"value": "温柔女声", "label": "🎙️ 温柔女声（默认）"},
    {"value": "知性旁白女", "label": "🎙️ 知性旁白女"},
    {"value": "沉稳权威女", "label": "🎙️ 沉稳权威女"},
    {"value": "温暖磁性女", "label": "🎙️ 温暖磁性女"},
    {"value": "清甜推销女", "label": "🎙️ 清甜推销女"},
    {"value": "欢脱元气女", "label": "🎙️ 欢脱元气女"},
    {"value": "嗲甜台湾女", "label": "🎙️ 嗲甜台湾女"},
    {"value": "浪漫风情女", "label": "🎙️ 浪漫风情女"},
    {"value": "豪放可爱女", "label": "🎙️ 豪放可爱女"},
    {"value": "暖心甜美女", "label": "🎙️ 暖心甜美女"},
    {"value": "阳光自然女", "label": "🎙️ 阳光自然女"},
    {"value": "沉稳男声", "label": "🎤 沉稳男声"},
    {"value": "温暖元气男", "label": "🎤 温暖元气男"},
    {"value": "睿智青年男", "label": "🎤 睿智青年男"},
    {"value": "清朗明快男", "label": "🎤 清朗明快男"},
    {"value": "阳光大男孩", "label": "🎤 阳光大男孩"},
]

# AI 模型参数
CHUNK_MAX_LENGTH = get("ai.chunk_max_length", 3000)
AI_TEMPERATURE = get("ai.temperature", 0.3)
AI_MAX_TOKENS = get("ai.max_tokens", 4096)

# 默认图片/视频参数
DEFAULT_IMAGE_WIDTH = get("image.width", 960)
DEFAULT_IMAGE_HEIGHT = get("image.height", 540)
DEFAULT_STEPS = get("image.steps", 8)
DEFAULT_VIDEO_WIDTH = get("video.width", 960)
DEFAULT_VIDEO_HEIGHT = get("video.height", 540)
DEFAULT_FPS = get("video.fps", 16)
DEFAULT_DURATION = get("video.duration", 5)
DEFAULT_SHOTS_COUNT = get("defaults.shots_count", 10)

# 配音时长控制（秒）
DUBBING_MAX_SECONDS = get("video_processing.dubbing_max_seconds", 10)


# ================= 艺术风格预设 =================
ART_STYLES = [
    {"value": "迪士尼风格, 细腻光影, 高品质渲染, 4K", "label": "🎨 迪士尼风格（默认）"},
    # 一、传统美术与绘画流派
    {"value": "Oil painting, impasto, rich colors, brush strokes, 4K", "label": "🖼️ 油画风格"},
    {"value": "Watercolor painting, wet-on-wet, soft edges, transparent, splatter, 4K", "label": "🖼️ 水彩风格"},
    {"value": "Charcoal sketch, line art, cross-hatching, detailed, 4K", "label": "🖼️ 素描/炭笔风格"},
    {"value": "Pastel drawing, soft colors, chalk texture, gentle, 4K", "label": "🖼️ 粉彩/色粉风格"},
    {"value": "Impressionism, visible brush strokes, focus on light and shadow, Monet style, 4K", "label": "🎨 印象派（莫奈风格）"},
    {"value": "Surrealism, dreamlike, bizarre, Salvador Dali style, 4K", "label": "🎨 超现实主义（达利风格）"},
    {"value": "Cubism, geometric shapes, multiple perspectives, Picasso style, 4K", "label": "🎨 立体主义（毕加索风格）"},
    {"value": "Renaissance art, classical, chiaroscuro, religious, mythological, 4K", "label": "🎨 文艺复兴风格"},
    {"value": "Ukiyo-e, Japanese traditional woodblock print, flat colors, bold outlines, 4K", "label": "🎨 浮世绘（日式版画）"},
    {"value": "Traditional Chinese ink painting, sumi-e, negative space, elegant, Zen, 4K", "label": "🎨 中国水墨风格"},
    # 二、3D、数字艺术与潮玩
    {"value": "Art toy, blind box, Pop Mart style, clay material, matte finish, cute, 3D render, 4K", "label": "🧸 盲盒/潮玩风（泡泡玛特）"},
    {"value": "Low poly, minimalist 3D, geometric, flat shading, 4K", "label": "🧊 低多边形（Low Poly）"},
    {"value": "Voxel art, 3D pixel, Minecraft style, isometric, 4K", "label": "🧱 体素艺术（方块风）"},
    {"value": "Claymation, stop motion, plasticine texture, Aardman style, 4K", "label": "🎭 黏土动画风格"},
    {"value": "Unreal Engine 5 render, Octane render, Ray tracing, global illumination, 8k resolution, highly detailed", "label": "🎮 虚幻5/OC渲染（超写实）"},
    {"value": "Concept art, epic composition, matte painting, fantasy environment, Greg Rutkowski style, 4K", "label": "🎬 概念艺术（史诗感）"},
    # 三、摄影与影视写实
    {"value": "Cinematic shot, movie still, dramatic lighting, anamorphic lens, widescreen, color grading, 4K", "label": "🎥 电影剧照风格"},
    {"value": "Macro photography, extreme close-up, depth of field, sharp focus, 4K", "label": "📷 微距摄影"},
    {"value": "Aerial view, drone photography, bird's-eye view, landscape, 4K", "label": "📷 航拍/上帝视角"},
    {"value": "Long exposure photography, light trails, silky water, night, 4K", "label": "📷 长曝光摄影"},
    {"value": "Polaroid, 35mm film, film grain, vintage, retro aesthetic, 4K", "label": "📷 胶片/复古风格"},
    {"value": "Cyberpunk, neon lights, futuristic city, rainy street, blade runner style, high tech low life, 4K", "label": "🌃 赛博朋克"},
    {"value": "Steampunk, Victorian era, brass, gears, steam-powered, goggles, 4K", "label": "⚙️ 蒸汽朋克"},
    # 四、插画与二次元
    {"value": "Anime style, manga, cel shading, Makoto Shinkai style, vibrant colors, 4K", "label": "🇯🇵 日系动漫（新海诚风）"},
    {"value": "Studio Ghibli style, Hayao Miyazaki, whimsical, warm, hand-drawn, 4K", "label": "🇯🇵 吉卜力风格"},
    {"value": "Comic book style, graphic novel, Marvel style, halftone dots, bold ink lines, 4K", "label": "🇺🇸 美漫/漫画风格"},
    {"value": "Children's book illustration, whimsical, soft pastel colors, watercolor, cozy, 4K", "label": "📚 儿童绘本风格"},
    {"value": "Vector art, flat design, minimalist, clean lines, corporate illustration, 4K", "label": "📐 扁平化矢量风格"},
    {"value": "Vintage poster, art nouveau, Alphonse Mucha style, intricate details, floral borders, 4K", "label": "🖼️ 复古海报（慕夏风格）"},
    # 五、现代设计与流行文化
    {"value": "Pop art, Andy Warhol style, high saturation, repeated elements, comic aesthetic, 4K", "label": "🎨 波普艺术"},
    {"value": "Minimalism, less is more, simple geometric shapes, vast negative space, clean, 4K", "label": "⬜ 极简主义"},
    {"value": "Vaporwave, retrowave, glitch art, neon pink and cyan, VHS effect, digital distortion, 4K", "label": "🌴 蒸汽波/故障艺术"},
    {"value": "Memphis design, 80s aesthetic, geometric shapes, squiggles, high contrast colors, 4K", "label": "💎 孟菲斯风格"},
    {"value": "Isometric view, 2.5D, diorama, tiny world, cute, clean background, 4K", "label": "📐 等距视角（2.5D）"},
]

# ================= Flask 初始化 =================
app = Flask(__name__)
CORS(app)

# ================= 全局状态 =================
project_state = {
    "shots": [],
    "art_style": ART_STYLES[0]["value"],
    "generated_images": {},
    "generated_videos": {},
    "merged_videos": {},
    "shot_dubbing": {},
    "story_text": "",
}

state_lock = threading.Lock()



# ================= AI 工具函数 =================

def load_api_key(config_path):
    if not os.path.exists(config_path):
        return None
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
            return config.get("deepseek", {}).get("api")
    except Exception:
        return None


def split_text_into_chunks(text, max_length):
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


def analyze_story_for_storyboard(client, text_chunk, chunk_index, total_chunks, art_style, target_shots=None):
    """调用 DeepSeek AI 分析故事，提取分镜（返回 JSON 数组）"""
    shots_instruction = ""
    print('分镜个数：'+ str(target_shots))
    if target_shots:
        shots_instruction = f"请将此故事拆分为约 {target_shots} 个分镜。根据故事的实际内容复杂度自由拆分，不要刻意压缩分镜数。"

    system_prompt = f"""
你是一个专业的动漫/影视分镜师。你需要分析传入的故事文本，将其拆分为一系列连续的分镜镜头。

{shots_instruction}

【核心规则】
1. 每个分镜应聚焦一个关键场景或动作序列，按故事发展顺序排列，确保覆盖完整故事线。
2. 每个分镜必须包含详细、高质量的英文图片生成提示词（prompt）。
3. **所有分镜的美术风格必须完全统一**，使用以下指定风格：{art_style}
4. 角色在不同分镜中出现的提示词要保持一致（外貌、服装、发型等特征）。
5. 每个分镜的 prompt 要详细描述：场景环境、角色位置与姿态、构图角度、光线氛围、色彩基调。
6. 分镜数量根据故事的实际长度和内容复杂度自由决定。故事越长分镜越多，故事越短分镜越少，不要强行凑数。每个分镜只讲一个关键动作或场景变化，确保配音文本可以完整讲述对应部分的故事。**不要精简或省略故事中的重要内容，要完整呈现故事的全貌**。

请严格输出一个 JSON 数组，不要包含任何额外废话。
数组中的每个对象必须包含以下字段：
1. "shot_index": 分镜序号（从1开始递增）
2. "scene_title": 场景标题（简短中文）
3. "characters": 本镜出现的角色名列表
4. "prompt": 高质量的英文图片生成提示词
5. "description": 场景的中文描述（一两句话说明本镜内容）
6. "dubbing_text": 用于配音的中文旁白文本。请用第三人称叙事的方式，用流畅自然的中文简洁描述本镜中发生的核心动作或对话。此文本将被转换为语音（必须控制在8秒内，约45-55字），所以必须简洁，适合朗读。不要使用列表或提纲形式。确保可以完整讲述本镜对应的核心故事内容。
"""

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

        result_content = response.choices[0].message.content.strip()
        import re
        json_match = re.search(r'\[.*\]', result_content, re.DOTALL)
        if json_match:
            json_str = json_match.group(0)
        else:
            json_str = result_content

        return json.loads(json_str)
    except Exception as e:
        print(f"[错误] AI 分析失败: {e}")
        return []


def optimize_storyboard_prompts(client, all_shots, art_style):
    """对所有分镜的 prompt 进行统一风格优化"""
    if not all_shots:
        return all_shots

    shots_summary = json.dumps(
        [{"shot_index": s["shot_index"], "scene_title": s["scene_title"],
          "characters": s["characters"], "prompt": s["prompt"]}
         for s in all_shots],
        ensure_ascii=False, indent=2
    )

    system_prompt = f"""
你是一个专业的动画/影视美术总监。确保以下所有分镜的图片生成提示词在美术风格和角色外观上保持**高度一致**。

【统一风格】: {art_style}

【角色一致性】: 确保同一角色在不同分镜中外貌描述完全一致。

【质量增强】: 在每个 prompt 末尾添加通用画质修饰词。

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
        import re
        json_match = re.search(r'\[.*\]', result_content, re.DOTALL)
        if json_match:
            optimized_shots = json.loads(json_match.group(0))
            opt_map = {s["shot_index"]: s for s in optimized_shots}
            for shot in all_shots:
                if shot["shot_index"] in opt_map:
                    shot["prompt"] = opt_map[shot["shot_index"]]["prompt"]

        return all_shots
    except Exception:
        return all_shots


def enhance_dubbing_texts(client, all_shots):
    """为所有分镜生成/优化配音文本"""
    if not all_shots:
        return all_shots

    for shot in all_shots:
        if not shot.get("dubbing_text") or len(shot["dubbing_text"]) < 20:
            shot["dubbing_text"] = shot.get("description", shot.get("scene_title", ""))

    return all_shots


# ================= 后端生成任务 =================

def run_generate_image(shot_index, prompt_text, width, height, steps, seed=None):
    """后台线程：调用 text_to_image.py 生成图片"""
    from text_to_image import generate_images
    try:
        if seed is None:
            seed = random.randint(1, 99999999999)
        files = generate_images(prompt_text=prompt_text, seed=seed, width=width, height=height, steps=steps)
        with state_lock:
            if files:
                output_files = []
                for f in files:
                    src = os.path.join(COMFYUI_OUTPUT_DIR, f)
                    new_name = f"shot_{shot_index:02d}_{f}"
                    dst = os.path.join(OUTPUT_DIR, new_name)
                    try:
                        shutil.copy2(src, dst)
                        output_files.append(new_name)
                    except Exception:
                        output_files.append(f)
                project_state["generated_images"][shot_index] = output_files
                if shot_index in project_state["generated_videos"]:
                    del project_state["generated_videos"][shot_index]
                if shot_index in project_state.get("merged_videos", {}):
                    del project_state["merged_videos"][shot_index]
    except Exception as e:
        print(f"[错误] 生成图片失败 (分镜 {shot_index}): {e}")


def run_generate_video(shot_index, image_filename, prompt_text, seed=None):
    """后台线程：调用 image_to_video.py 生成视频（普通模式，每分镜单独用其图片生成）"""
    from image_to_video import generate_video
    try:
        if seed is None:
            seed = random.randint(1, 99999999999)
        image_path = os.path.join(OUTPUT_DIR, image_filename)
        if not os.path.exists(image_path):
            image_path = os.path.join(COMFYUI_OUTPUT_DIR, image_filename)
        with state_lock:
            v_width = project_state.get("video_width", DEFAULT_VIDEO_WIDTH)
            v_height = project_state.get("video_height", DEFAULT_VIDEO_HEIGHT)
            v_fps = project_state.get("fps", DEFAULT_FPS)
        video_files = generate_video(
            image_path=image_path, prompt_text=prompt_text, seed=seed,
            width=v_width, height=v_height, duration=DEFAULT_DURATION, fps=v_fps, enable_turbo=True,
        )
        with state_lock:
            if video_files:
                output_files = []
                for vf in video_files:
                    src = os.path.join(COMFYUI_OUTPUT_DIR, vf)
                    base_name = os.path.basename(vf)
                    new_name = f"shot_{shot_index:02d}_video_{base_name}"
                    dst = os.path.join(OUTPUT_DIR, new_name)
                    try:
                        if os.path.exists(src):
                            shutil.copy2(src, dst)
                            output_files.append(new_name)
                        else:
                            output_files.append(vf)
                    except Exception:
                        output_files.append(vf)
                project_state["generated_videos"][shot_index] = output_files
    except Exception as e:
        print(f"[错误] 生成视频失败 (分镜 {shot_index}): {e}")


def run_generate_video_with_frame_connection(shot_index, image_filename, prompt_text, seed=None):
    """
    视频分镜首尾帧相连模式：生成视频时使用上一个视频的尾帧作为输入图片。
    
    对于第一个分镜（shot_index == 1 或最小分镜号），使用生成的图片生成视频。
    对于后续分镜，先找上一个分镜的视频文件，提取其最后一帧作为本分镜的输入图片，
    然后用该帧图片生成视频，实现画面连续过渡。
    """
    from image_to_video import generate_video
    try:
        if seed is None:
            seed = random.randint(1, 99999999999)

        with state_lock:
            v_width = project_state.get("video_width", DEFAULT_VIDEO_WIDTH)
            v_height = project_state.get("video_height", DEFAULT_VIDEO_HEIGHT)
            v_fps = project_state.get("fps", DEFAULT_FPS)
            shots = project_state["shots"]

        # 获取所有分镜号并排序
        shot_indices = sorted([s["shot_index"] for s in shots])
        if not shot_indices:
            print(f"[错误] 没有分镜数据")
            return

        # 判断当前分镜是否是第一个
        current_idx = shot_indices.index(shot_index) if shot_index in shot_indices else -1
        is_first_shot = (current_idx <= 0)

        if is_first_shot:
            # 第一个分镜：使用 AI 生成的图片作为输入
            image_path = os.path.join(OUTPUT_DIR, image_filename)
            if not os.path.exists(image_path):
                image_path = os.path.join(COMFYUI_OUTPUT_DIR, image_filename)
            print(f"  🎬 分镜 {shot_index}（首镜）：使用原始图片")
        else:
            # 后续分镜：找上一个分镜的视频，提取尾帧作为输入
            prev_shot_index = shot_indices[current_idx - 1]
            with state_lock:
                prev_videos = project_state.get("generated_videos", {}).get(prev_shot_index, [])
            
            if prev_videos:
                prev_video_path = os.path.join(OUTPUT_DIR, prev_videos[0])
                if not os.path.exists(prev_video_path):
                    prev_video_path = os.path.join(COMFYUI_OUTPUT_DIR, prev_videos[0])
                
                # 提取尾帧
                frame_filename = f"shot_{shot_index:02d}_frame_connection.png"
                frame_path = os.path.join(OUTPUT_DIR, frame_filename)
                extracted = extract_video_last_frame(prev_video_path, frame_path)
                if extracted:
                    image_path = frame_path
                    print(f"  🎬 分镜 {shot_index}：使用分镜 {prev_shot_index} 视频尾帧 → {frame_filename}")
                else:
                    # 提取失败，回退到原始图片
                    image_path = os.path.join(OUTPUT_DIR, image_filename)
                    if not os.path.exists(image_path):
                        image_path = os.path.join(COMFYUI_OUTPUT_DIR, image_filename)
                    print(f"  ⚠️ 分镜 {shot_index}：尾帧提取失败，回退到原始图片")
            else:
                # 上一个分镜没有视频，使用原始图片
                image_path = os.path.join(OUTPUT_DIR, image_filename)
                if not os.path.exists(image_path):
                    image_path = os.path.join(COMFYUI_OUTPUT_DIR, image_filename)
                print(f"  ⚠️ 分镜 {shot_index}：上一个分镜无视频，使用原始图片")

        video_files = generate_video(
            image_path=image_path, prompt_text=prompt_text, seed=seed,
            width=v_width, height=v_height, duration=DEFAULT_DURATION, fps=v_fps, enable_turbo=True,
        )
        with state_lock:
            if video_files:
                output_files = []
                for vf in video_files:
                    src = os.path.join(COMFYUI_OUTPUT_DIR, vf)
                    base_name = os.path.basename(vf)
                    new_name = f"shot_{shot_index:02d}_video_{base_name}"
                    dst = os.path.join(OUTPUT_DIR, new_name)
                    try:
                        if os.path.exists(src):
                            shutil.copy2(src, dst)
                            output_files.append(new_name)
                        else:
                            output_files.append(vf)
                    except Exception:
                        output_files.append(vf)
                project_state["generated_videos"][shot_index] = output_files
    except Exception as e:
        print(f"[错误] 生成视频失败 (分镜 {shot_index}): {e}")


# ================= FFmpeg 合并功能 =================

def get_media_duration(media_path):
    """用 ffprobe 获取音视频时长（秒）"""
    try:
        probe_cmd = [
            'ffprobe', '-v', 'error', '-show_entries', 'format=duration',
            '-of', 'default=noprint_wrappers=1:nokey=1', media_path
        ]
        result = subprocess.run(probe_cmd, capture_output=True, text=True)
        return float(result.stdout.strip()) if result.stdout.strip() else 0
    except Exception:
        return 0


def extract_video_last_frame(video_path, output_path):
    """
    从视频中提取最后一帧作为图片。
    
    使用 FFmpeg 定位到视频末尾附近，提取一帧保存为 PNG。
    返回 output_path 成功，None 失败。
    """
    if not os.path.exists(video_path):
        print(f"[错误] 视频文件不存在: {video_path}")
        return None
    try:
        # 先获取视频时长，然后定位到末尾附近
        duration = get_media_duration(video_path)
        if duration <= 0:
            duration = 5  # fallback
        seek_time = max(0, duration - 0.1)
        cmd = [
            'ffmpeg', '-y',
            '-ss', str(seek_time),
            '-i', video_path,
            '-frames:v', '1',
            '-q:v', '2',
            output_path
        ]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        if os.path.exists(output_path):
            print(f"  📸 已提取视频尾帧: {output_path}")
            return output_path
        else:
            print(f"  ⚠️ 提取尾帧失败，输出文件不存在")
    except Exception as e:
        print(f"[错误] 提取视频尾帧失败: {e}")
    return None


def merge_shot_media(shot_index):
    """
    合并单个分镜的视频 + 配音。
    
    核心策略：以音频时长为基准，通过变速（调整视频播放速度）拉长视频到与音频一致，
    而不是从头循环播放。确保画面和声音同步结束，音频不会被截断。
    
    - 如果有视频：计算视频时长与音频时长的比例，用 setpts 放慢视频
    - 如果只有图片：用 -loop 1 + -t 音频时长 静态展示
    - 若视频时长 >= 音频时长：正常合并，以音频 -shortest 截断
    - 若视频时长 < 音频时长：放慢视频到音频时长，重新编码
    
    返回 merged.mp4 文件名，或 None。
    """
    with state_lock:
        images = project_state.get("generated_images", {}).get(shot_index, [])
        videos = project_state.get("generated_videos", {}).get(shot_index, [])
        dubbings = project_state.get("shot_dubbing", {}).get(shot_index, None)

    if not dubbings:
        print(f"  分镜 {shot_index} 没有配音，跳过合并")
        return None

    dubbing_path = os.path.join(OUTPUT_DIR, dubbings)
    if not os.path.exists(dubbing_path):
        print(f"  分镜 {shot_index} 配音文件不存在: {dubbing_path}")
        return None

    output_name = f"shot_{shot_index:02d}_merged.mp4"
    output_path = os.path.join(OUTPUT_DIR, output_name)

    # 获取音频时长
    audio_duration = get_media_duration(dubbing_path)
    if audio_duration <= 0:
        print(f"  分镜 {shot_index} 无法获取音频时长，使用默认 10 秒")
        audio_duration = 10

    try:
        if videos:
            video_path = os.path.join(OUTPUT_DIR, videos[0])
            if not os.path.exists(video_path):
                video_path = os.path.join(COMFYUI_OUTPUT_DIR, videos[0])
            if os.path.exists(video_path):
                video_duration = get_media_duration(video_path)
                print(f"  视频时长: {video_duration:.2f}s, 音频时长: {audio_duration:.2f}s")

                if video_duration >= audio_duration:
                    # 视频够长，直接以音频时长截断
                    cmd = [
                        'ffmpeg', '-y',
                        '-i', video_path,
                        '-i', dubbing_path,
                        '-c:v', 'libx264',
                        '-c:a', 'aac',
                        '-shortest',
                        '-pix_fmt', 'yuv420p',
                        '-map', '0:v:0',
                        '-map', '1:a:0',
                        output_path
                    ]
                else:
                    # 视频不够长：用 setpts 放慢视频到音频时长，重新编码
                    speed_factor = video_duration / audio_duration  # e.g. 5/10 = 0.5
                    setpts_val = f"setpts={1/speed_factor}*PTS"  # e.g. setpts=2*PTS
                    cmd = [
                        'ffmpeg', '-y',
                        '-i', video_path,
                        '-i', dubbing_path,
                        '-map', '0:v:0',
                        '-map', '1:a:0',
                        '-c:v', 'libx264',
                        '-c:a', 'aac',
                        '-pix_fmt', 'yuv420p',
                        '-filter:v', setpts_val,
                        '-shortest',
                        output_path
                    ]
                subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
                print(f"  ✅ 分镜 {shot_index} 视频+配音合并完成（音频 {audio_duration:.1f}s → 视频变速至匹配）: {output_name}")
                return output_name
        if images:
            image_path = os.path.join(OUTPUT_DIR, images[0])
            if not os.path.exists(image_path):
                image_path = os.path.join(COMFYUI_OUTPUT_DIR, images[0])
            if os.path.exists(image_path):
                cmd = [
                    'ffmpeg', '-y',
                    '-loop', '1',
                    '-i', image_path,
                    '-i', dubbing_path,
                    '-c:v', 'libx264',
                    '-tune', 'stillimage',
                    '-c:a', 'aac',
                    '-shortest',
                    '-pix_fmt', 'yuv420p',
                    output_path
                ]
                subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
                print(f"  ✅ 分镜 {shot_index} 图片+配音合并完成（以音频 {audio_duration:.1f}s 为准）: {output_name}")
                return output_name
    except Exception as e:
        print(f"  ❌ 分镜 {shot_index} 合并失败: {e}")
    return None


def merge_all_shots(final_name="Final_AI_Video.mp4"):
    """
    合并所有已合并的分镜视频为一个完整视频。
    如果某个分镜没有 merged_video，尝试临时生成。
    """
    with state_lock:
        shots = project_state["shots"]
        existing_merged = dict(project_state.get("merged_videos", {}))

    concat_list = []
    for shot in shots:
        idx = shot["shot_index"]
        merged_file = existing_merged.get(idx)
        if not merged_file or not os.path.exists(os.path.join(OUTPUT_DIR, merged_file)):
            merged_file = merge_shot_media(idx)
            if merged_file:
                with state_lock:
                    if "merged_videos" not in project_state:
                        project_state["merged_videos"] = {}
                    project_state["merged_videos"][idx] = merged_file
        if merged_file and os.path.exists(os.path.join(OUTPUT_DIR, merged_file)):
            concat_list.append(os.path.join(OUTPUT_DIR, merged_file))

    if not concat_list:
        print("❌ 没有可合并的分镜视频")
        return None

    list_path = os.path.join(OUTPUT_DIR, "concat_list.txt")
    with open(list_path, "w", encoding="utf-8") as f:
        for path in concat_list:
            f.write(f"file '{os.path.abspath(path).replace(os.sep, '/')}'\n")

    output_path = os.path.join(OUTPUT_DIR, final_name)
    try:
        # 使用 -filter_complex concat 重新编码，解决 -c copy 导致各分片编码参数不兼容引发的卡带问题
        # 各分镜视频由 ComfyUI 独立生成，编码参数可能不同（GOP大小、关键帧间隔、码率等），
        # -c copy 直接拼接流会导致播放器在拼接处卡顿（画面冻结、音频继续），
        # 使用 concat 滤镜统一重新编码可确保输出视频流畅播放
        input_args = []
        filter_parts = []
        for i in range(len(concat_list)):
            input_args.extend(['-i', concat_list[i]])
            filter_parts.append(f'[{i}:v:0][{i}:a:0]')
        filter_str = f'{"".join(filter_parts)}concat=n={len(concat_list)}:v=1:a=1[outv][outa]'
        cmd = [
            'ffmpeg', '-y',
            *input_args,
            '-filter_complex', filter_str,
            '-map', '[outv]',
            '-map', '[outa]',
            '-c:v', 'libx264',
            '-preset', 'medium',
            '-crf', '23',
            '-c:a', 'aac',
            '-b:a', '192k',
            '-pix_fmt', 'yuv420p',
            output_path
        ]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        print(f"🎉 最终视频合并完成（使用 concat 滤镜重新编码，确保流畅播放）: {output_path}")
        os.remove(list_path)
        return final_name
    except Exception as e:
        print(f"❌ 最终合并失败: {e}")
        # 如果 concat 滤镜失败，回退到 -c copy 方案
        print("⚠️  尝试回退到 -c copy 方案...")
        try:
            cmd_fallback = [
                'ffmpeg', '-y', '-f', 'concat', '-safe', '0',
                '-i', list_path, '-c', 'copy', output_path
            ]
            subprocess.run(cmd_fallback, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            print(f"🎉 最终视频合并完成（回退方案 -c copy）: {output_path}")
            os.remove(list_path)
            return final_name
        except Exception as e2:
            print(f"❌ 最终合并也失败: {e2}")
            try: os.remove(list_path)
            except: pass
            return None



# ================= Flask API 路由 =================

@app.route('/')
def index():
    return send_from_directory('templates', 'index.html')


@app.route('/api/health')
def health():
    return jsonify({"status": "ok", "message": "故事转视频 API 运行中"})


@app.route('/api/story/analyze', methods=['POST'])
def analyze_story():
    """分析故事，生成分镜列表"""
    data = request.get_json(silent=True) or {}
    story_text = data.get("text", "")
    art_style = data.get("style", "迪士尼风格, 细腻光影, 高品质渲染, 4K")
    target_shots = data.get("shots", None)

    if not story_text:
        if not os.path.exists(INPUT_STORY_FILE):
            return jsonify({"error": f"找不到 {INPUT_STORY_FILE}，请上传故事文本"}), 400
        with open(INPUT_STORY_FILE, "r", encoding="utf-8") as f:
            story_text = f.read()

    api_key = load_api_key(CONFIG_FILE)
    if not api_key:
        return jsonify({"error": "API Key 配置失败"}), 500

    client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")

    chunks = split_text_into_chunks(story_text, CHUNK_MAX_LENGTH)
    all_shots = []
    shot_offset = 0

    for i, chunk in enumerate(chunks, 1):
        if not chunk.strip():
            continue
        shots_per_chunk = None
        if target_shots:
            shots_per_chunk = max(3, target_shots // len(chunks))

        result = analyze_story_for_storyboard(client, chunk, i, len(chunks), art_style, shots_per_chunk)
        if result:
            for shot in result:
                shot["shot_index"] += shot_offset
            shot_offset = result[-1]["shot_index"] if result else shot_offset
            all_shots.extend(result)

    if not all_shots:
        return jsonify({"error": "AI 分析未能生成分镜"}), 500

    all_shots = optimize_storyboard_prompts(client, all_shots, art_style)
    all_shots = enhance_dubbing_texts(client, all_shots)

    with state_lock:
        project_state["shots"] = all_shots
        project_state["art_style"] = art_style
        project_state["story_text"] = story_text
        project_state["generated_images"] = {}
        project_state["generated_videos"] = {}
        project_state["merged_videos"] = {}
        project_state["shot_dubbing"] = {}

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    shots_file = os.path.join(OUTPUT_DIR, "storyboard_shots.json")
    with open(shots_file, "w", encoding="utf-8") as f:
        json.dump(all_shots, f, ensure_ascii=False, indent=2)

    return jsonify({
        "message": f"分析完成，共 {len(all_shots)} 个分镜",
        "shots": all_shots
    })


@app.route('/api/styles', methods=['GET'])
def get_styles():
    """返回所有可用的艺术风格列表"""
    return jsonify({"styles": ART_STYLES})

@app.route('/api/narrator-voices', methods=['GET'])
def get_narrator_voices():
    """返回所有可用的叙事人声音列表"""
    return jsonify({"voices": NARRATOR_VOICES})


@app.route('/api/shots', methods=['GET'])

def get_shots():
    """获取当前分镜列表"""
    with state_lock:
        shots = project_state["shots"]
        images = dict(project_state["generated_images"])
        videos = dict(project_state["generated_videos"])
        merged = dict(project_state.get("merged_videos", {}))
        shot_dubbing = dict(project_state.get("shot_dubbing", {}))

    return jsonify({
        "shots": shots,
        "generated_images": images,
        "generated_videos": videos,
        "generated_dubbings": shot_dubbing,
        "merged_videos": merged,
        "art_style": project_state.get("art_style", ""),
    })


@app.route('/api/shots/update', methods=['POST'])
def update_shot():
    data = request.get_json(silent=True) or {}
    shot_index = data.get("shot_index")
    field = data.get("field")
    value = data.get("value")
    if not shot_index or not field:
        return jsonify({"error": "缺少 shot_index 或 field"}), 400
    with state_lock:
        for shot in project_state["shots"]:
            if shot["shot_index"] == shot_index:
                if field in shot:
                    shot[field] = value
                    return jsonify({"message": f"分镜 {shot_index}.{field} 已更新", "shot": shot})
                else:
                    return jsonify({"error": f"分镜中没有字段 '{field}'"}), 400
    return jsonify({"error": f"未找到分镜 {shot_index}"}), 404


@app.route('/api/generate/image', methods=['POST'])
def generate_image():
    data = request.get_json(silent=True) or {}
    shot_index = data.get("shot_index")
    width = data.get("width", DEFAULT_IMAGE_WIDTH)
    height = data.get("height", DEFAULT_IMAGE_HEIGHT)
    steps = data.get("steps", DEFAULT_STEPS)
    seed = data.get("seed", None)
    if not shot_index:
        return jsonify({"error": "缺少 shot_index"}), 400
    shot = None
    with state_lock:
        for s in project_state["shots"]:
            if s["shot_index"] == shot_index:
                shot = s
                break
    if not shot:
        return jsonify({"error": f"未找到分镜 {shot_index}"}), 404
    prompt_text = shot.get("prompt", "")
    thread = threading.Thread(
        target=run_generate_image,
        args=(shot_index, prompt_text, width, height, steps, seed), daemon=True
    )
    thread.start()
    return jsonify({"message": f"分镜 {shot_index} 图片生成任务已启动", "shot_index": shot_index, "prompt": prompt_text})


@app.route('/api/generate/video', methods=['POST'])
def generate_video():
    data = request.get_json(silent=True) or {}
    shot_index = data.get("shot_index")
    seed = data.get("seed", None)
    if not shot_index:
        return jsonify({"error": "缺少 shot_index"}), 400
    with state_lock:
        shot = next((s for s in project_state["shots"] if s["shot_index"] == shot_index), None)
        use_frame_connection = project_state.get("use_frame_connection", False)
        image_files = project_state["generated_images"].get(shot_index, [])
        
    if not shot:
        return jsonify({"error": f"未找到分镜 {shot_index}"}), 404

    # 首尾帧相连模式：非首镜不需要图片文件（使用上一分镜视频尾帧）
    if not use_frame_connection:
        if shot_index not in project_state["generated_images"]:
            return jsonify({"error": f"分镜 {shot_index} 尚未生成图片"}), 400
        if not image_files:
            return jsonify({"error": f"分镜 {shot_index} 无图片文件"}), 400
        image_filename = image_files[0]
    else:
        image_filename = image_files[0] if image_files else ""

    prompt_text = shot.get("prompt", "")
    # 根据是否启用首尾帧相连模式选择不同的生成函数
    if use_frame_connection:
        thread = threading.Thread(
            target=run_generate_video_with_frame_connection,
            args=(shot_index, image_filename, prompt_text, seed), daemon=True
        )
        mode_msg = "（首尾帧相连模式）"
    else:
        thread = threading.Thread(
            target=run_generate_video,
            args=(shot_index, image_filename, prompt_text, seed), daemon=True
        )
        mode_msg = ""
    thread.start()
    return jsonify({"message": f"分镜 {shot_index} 视频生成任务已启动{mode_msg}", "shot_index": shot_index, "image": image_filename})


@app.route('/api/generate/status', methods=['GET'])
def generation_status():
    with state_lock:
        images = dict(project_state["generated_images"])
        videos = dict(project_state["generated_videos"])
        merged = dict(project_state.get("merged_videos", {}))
        dubbings = dict(project_state.get("shot_dubbing", {}))
    result = {}
    with state_lock:
        for shot in project_state["shots"]:
            idx = shot["shot_index"]
            result[idx] = {
                "has_image": idx in images,
                "has_video": idx in videos,
                "has_dubbing": idx in dubbings,
                "has_merged": idx in merged,
                "image_files": images.get(idx, []),
                "video_files": videos.get(idx, []),
                "dubbing_file": dubbings.get(idx, None),
                "merged_files": [merged[idx]] if idx in merged else [],
            }
    return jsonify(result)


@app.route('/api/outputs/image/<shot_index>/<filename>')
def serve_image(shot_index, filename):
    file_path = os.path.join(OUTPUT_DIR, filename)
    if os.path.exists(file_path):
        return send_from_directory(OUTPUT_DIR, filename)
    if os.path.exists(os.path.join(COMFYUI_OUTPUT_DIR, filename)):
        return send_from_directory(COMFYUI_OUTPUT_DIR, filename)
    abort(404)


@app.route('/api/outputs/video/<path:filename>')
def serve_video(filename):
    if os.path.exists(os.path.join(OUTPUT_DIR, filename)):
        return send_from_directory(OUTPUT_DIR, filename)
    full_comfyui_path = os.path.join(COMFYUI_OUTPUT_DIR, filename)
    if os.path.exists(full_comfyui_path):
        dir_path = os.path.dirname(full_comfyui_path)
        base_name = os.path.basename(full_comfyui_path)
        if dir_path and os.path.exists(dir_path):
            return send_from_directory(dir_path, base_name)
        return send_from_directory(COMFYUI_OUTPUT_DIR, filename)
    abort(404)


# ================= 配音 =================

@app.route('/api/dubbing/shot', methods=['POST'])
def generate_shot_dubbing_api():
    data = request.get_json(silent=True) or {}
    shot_index = data.get("shot_index")
    text = data.get("text", "")
    if not shot_index or not text:
        return jsonify({"error": "缺少 shot_index 或 text"}), 400
    thread = threading.Thread(target=_run_shot_dubbing, args=(shot_index, text), daemon=True)
    thread.start()
    return jsonify({"message": f"分镜 {shot_index} 配音任务已启动"})


def _run_shot_dubbing(shot_index, text):
    from audio_dubbing import generate_shot_dubbing
    try:
        with state_lock:
            narrator_voice = project_state.get("narrator_voice", "温柔女声")
        mp3_file = generate_shot_dubbing(text=text, shot_index=shot_index, narrator_voice=narrator_voice)
        if mp3_file:
            with state_lock:
                if "shot_dubbing" not in project_state:
                    project_state["shot_dubbing"] = {}
                project_state["shot_dubbing"][shot_index] = mp3_file
            print(f"✅ 分镜 {shot_index} 配音完成: {mp3_file}")
        else:
            print(f"❌ 分镜 {shot_index} 配音生成失败")
    except Exception as e:
        print(f"[错误] 分镜 {shot_index} 配音异常: {e}")


@app.route('/api/dubbing/status', methods=['GET'])
def dubbing_status():
    shot_index = request.args.get("shot_index", type=int)
    with state_lock:
        shot_dubbing = project_state.get("shot_dubbing", {})
        if shot_index is not None:
            mp3_file = shot_dubbing.get(shot_index)
            if mp3_file and os.path.exists(os.path.join(OUTPUT_DIR, mp3_file)):
                return jsonify({"status": "done", "file": mp3_file, "shot_index": shot_index})
            return jsonify({"status": "pending", "shot_index": shot_index})
        else:
            result = {}
            for idx, f in shot_dubbing.items():
                if os.path.exists(os.path.join(OUTPUT_DIR, f)):
                    result[int(idx)] = {"status": "done", "file": f}
            return jsonify(result)


# ================= 合并 =================

@app.route('/api/merge/shot', methods=['POST'])
def merge_shot():
    """合并单个分镜的视频+配音"""
    data = request.get_json(silent=True) or {}
    shot_index = data.get("shot_index")
    if not shot_index:
        return jsonify({"error": "缺少 shot_index"}), 400
    thread = threading.Thread(target=_run_merge_shot, args=(shot_index,), daemon=True)
    thread.start()
    return jsonify({"message": f"分镜 {shot_index} 音视频合并任务已启动"})


def _run_merge_shot(shot_index):
    merged = merge_shot_media(shot_index)
    if merged:
        with state_lock:
            if "merged_videos" not in project_state:
                project_state["merged_videos"] = {}
            project_state["merged_videos"][shot_index] = merged
        print(f"✅ 分镜 {shot_index} 合并完成: {merged}")


@app.route('/api/merge/all', methods=['POST'])
def merge_all():
    """合并所有分镜为一个完整视频"""
    thread = threading.Thread(target=_run_merge_all, daemon=True)
    thread.start()
    return jsonify({"message": "全部音视频合并任务已启动"})


def _run_merge_all():
    with state_lock:
        shots = list(project_state["shots"])
        existing_merged = dict(project_state.get("merged_videos", {}))
    for shot in shots:
        idx = shot["shot_index"]
        if idx not in existing_merged:
            merged = merge_shot_media(idx)
            if merged:
                with state_lock:
                    if "merged_videos" not in project_state:
                        project_state["merged_videos"] = {}
                    project_state["merged_videos"][idx] = merged
                existing_merged[idx] = merged
    final = merge_all_shots("Final_AI_Video.mp4")
    if final:
        with state_lock:
            project_state["final_video"] = final
        print(f"🎉 完整 AI 视频生成完成: {final}")


@app.route('/api/merge/status', methods=['GET'])
def merge_status():
    with state_lock:
        merged = dict(project_state.get("merged_videos", {}))
        final = project_state.get("final_video")
        shots = project_state["shots"]
    result = {}
    for shot in shots:
        idx = shot["shot_index"]
        result[str(idx)] = {  # 用字符串键避免 JSON 排序时 int/str 混合类型错误
            "has_merged": idx in merged,
            "merged_file": merged.get(idx, None),
        }
    result["final"] = final if final and os.path.exists(os.path.join(OUTPUT_DIR, final)) else None
    return jsonify(result)


# ================= 一键生成 =================

def _run_batch_generate(story_text, art_style, target_shots=None):
    """
    完整的一键生成流水线。
    分批执行：所有图片 → 所有视频 → 所有配音 → 所有合并 → 最终合并
    """
    print("=" * 50)
    print("🚀 一键生成流水线启动")

    # ---- 始终清空旧的生成状态，避免残留数据导致前端误判全部完成 ----
    with state_lock:
        project_state["generated_images"] = {}
        project_state["generated_videos"] = {}
        project_state["merged_videos"] = {}
        project_state["shot_dubbing"] = {}
        project_state["final_video"] = None

    api_key = load_api_key(CONFIG_FILE)
    if not api_key:
        print("❌ API Key 配置失败")
        return

    client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")

    # ---- 检查是否已有分镜且故事文本未变（已分析过则跳过） ----
    with state_lock:
        existing_shots = list(project_state["shots"])
        existing_story = project_state.get("story_text", "")

    # 如果故事变了，把 existing_shots 清空强制重新分析
    story_changed = (story_text != existing_story)
    if story_changed:
        print(f"📝 故事内容已变更，重新分析分镜")
        with state_lock:
            project_state["shots"] = []
        existing_shots = []

    if existing_shots:
        all_shots = existing_shots
        print(f"✅ 已有 {len(all_shots)} 个分镜（故事未变），跳过分析步骤")
    else:
        # ---- 步骤 1: 分析故事（不分批，全部完成） ----
        print("【步骤 1/5】分析故事...")
        chunks = split_text_into_chunks(story_text, CHUNK_MAX_LENGTH)

        all_shots = []
        shot_offset = 0
        for i, chunk in enumerate(chunks, 1):
            if not chunk.strip():
                continue
            # target_shots 传 None -> AI 根据故事长度自由决定分镜数
            result = analyze_story_for_storyboard(client, chunk, i, len(chunks), art_style, target_shots=None)
            if result:
                for shot in result:
                    shot["shot_index"] += shot_offset
                shot_offset = result[-1]["shot_index"] if result else shot_offset
                all_shots.extend(result)

        if not all_shots:
            print("❌ AI 分析未能生成分镜")
            return

        all_shots = optimize_storyboard_prompts(client, all_shots, art_style)
        all_shots = enhance_dubbing_texts(client, all_shots)

        with state_lock:
            project_state["shots"] = all_shots
            project_state["art_style"] = art_style
            project_state["story_text"] = story_text
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        print(f"✅ 分析完成，共 {len(all_shots)} 个分镜")


    # ---- 步骤 2: 生成所有分镜的图片 ----
    print("\n" + "=" * 50)
    print("【步骤 2/5】生成所有分镜的图片...")
    
    with state_lock:
        use_frame_connection = project_state.get("use_frame_connection", False)

    from text_to_image import generate_images

    for idx, shot_data in enumerate(all_shots, 1):
        si = shot_data["shot_index"]

        # 首尾帧相连模式：只生成第一个分镜的图片，后续分镜使用上一分镜视频尾帧
        if use_frame_connection:
            if idx > 1:
                print(f"  🖼️ 分镜 {si} ({idx}/{len(all_shots)})... ⏭️ 首尾帧相连模式跳过（仅首镜需图片）")
                # 为后续分镜创建占位空列表，以便视频生成步骤能识别
                with state_lock:
                    if si not in project_state["generated_images"]:
                        project_state["generated_images"][si] = []
                continue

        print(f"  🖼️ 分镜 {si} ({idx}/{len(all_shots)})...", end="", flush=True)

        prompt_text = shot_data.get("prompt", "")
        w = project_state.get("image_width", DEFAULT_IMAGE_WIDTH)
        h = project_state.get("image_height", DEFAULT_IMAGE_HEIGHT)
        st = project_state.get("steps", DEFAULT_STEPS)
        seed = random.randint(1, 99999999999)

        files = generate_images(prompt_text=prompt_text, seed=seed, width=w, height=h, steps=st)
        if files:
            output_files = []
            for f in files:
                src = os.path.join(COMFYUI_OUTPUT_DIR, f)
                new_name = f"shot_{si:02d}_{f}"
                dst = os.path.join(OUTPUT_DIR, new_name)
                try:
                    shutil.copy2(src, dst)
                    output_files.append(new_name)
                except Exception:
                    output_files.append(f)
            with state_lock:
                project_state["generated_images"][si] = output_files
            print(f" ✅ {output_files[0]}")
        else:
            print(f" ❌ 失败，跳过")

    # ---- 步骤 3: 生成所有分镜的视频 ----
    print("\n" + "=" * 50)
    print("【步骤 3/5】生成所有分镜的视频...")
    from image_to_video import generate_video

    # use_frame_connection 已在步骤2中获取，这里直接复用
    # 获取所有分镜号并排序
    shot_indices = sorted([s["shot_index"] for s in all_shots])

    for idx, shot_data in enumerate(all_shots, 1):
        si = shot_data["shot_index"]
        image_files = project_state.get("generated_images", {}).get(si, [])
        if not image_files:
            print(f"  🎬 分镜 {si} 无图片，跳过")
            continue
        print(f"  🎬 分镜 {si} ({idx}/{len(all_shots)})...", end="", flush=True)

        prompt_text = shot_data.get("prompt", "")
        image_filename = image_files[0]
        v_width = project_state.get("video_width", DEFAULT_VIDEO_WIDTH)
        v_height = project_state.get("video_height", DEFAULT_VIDEO_HEIGHT)
        v_fps = project_state.get("fps", DEFAULT_FPS)
        v_seed = random.randint(1, 99999999999)

        try:
            if use_frame_connection:
                # 首尾帧相连模式
                current_idx = shot_indices.index(si) if si in shot_indices else -1
                is_first_shot = (current_idx <= 0)

                if is_first_shot:
                    # 第一个分镜：使用原始图片
                    image_path = os.path.join(OUTPUT_DIR, image_filename)
                    print(f"  🎬 分镜 {si}（首镜）：使用原始图片")
                else:
                    # 后续分镜：提取上一个视频的尾帧
                    prev_shot_index = shot_indices[current_idx - 1]
                    prev_videos = project_state.get("generated_videos", {}).get(prev_shot_index, [])
                    if prev_videos:
                        prev_video_path = os.path.join(OUTPUT_DIR, prev_videos[0])
                        frame_filename = f"shot_{si:02d}_frame_connection.png"
                        frame_path = os.path.join(OUTPUT_DIR, frame_filename)
                        extracted = extract_video_last_frame(prev_video_path, frame_path)
                        if extracted:
                            image_path = frame_path
                            print(f"  🎬 分镜 {si}：使用分镜 {prev_shot_index} 视频尾帧")
                        else:
                            image_path = os.path.join(OUTPUT_DIR, image_filename)
                            print(f"  ⚠️ 分镜 {si}：尾帧提取失败，回退到原始图片")
                    else:
                        image_path = os.path.join(OUTPUT_DIR, image_filename)
                        print(f"  ⚠️ 分镜 {si}：上一个分镜无视频，使用原始图片")

                video_files = generate_video(
                    image_path=image_path, prompt_text=prompt_text, seed=v_seed,
                    width=v_width, height=v_height, duration=DEFAULT_DURATION, fps=v_fps, enable_turbo=True,
                )
            else:
                # 普通模式：每个分镜使用其本身的图片
                image_path = os.path.join(OUTPUT_DIR, image_filename)
                video_files = generate_video(
                    image_path=image_path, prompt_text=prompt_text, seed=v_seed,
                    width=v_width, height=v_height, duration=DEFAULT_DURATION, fps=v_fps, enable_turbo=True,
                )

            if video_files:
                vf_output = []
                for vf in video_files:
                    src = os.path.join(COMFYUI_OUTPUT_DIR, vf)
                    base_name = os.path.basename(vf)
                    new_name = f"shot_{si:02d}_video_{base_name}"
                    dst = os.path.join(OUTPUT_DIR, new_name)
                    try:
                        if os.path.exists(src):
                            shutil.copy2(src, dst)
                            vf_output.append(new_name)
                        else:
                            vf_output.append(vf)
                    except Exception:
                        vf_output.append(vf)
                with state_lock:
                    project_state["generated_videos"][si] = vf_output
                print(f" ✅")
            else:
                print(f" ⚠️ 生成失败，继续")
        except Exception as e:
            print(f" ❌ 异常 ({e})，继续")

    # ---- 步骤 4: 生成所有分镜的配音 ----
    print("\n" + "=" * 50)
    print("【步骤 4/5】生成所有分镜的配音...")
    from audio_dubbing import generate_shot_dubbing

    with state_lock:
        narrator_voice = project_state.get("narrator_voice", "温柔女声")

    for idx, shot_data in enumerate(all_shots, 1):
        si = shot_data["shot_index"]
        print(f"  🎙️ 分镜 {si} ({idx}/{len(all_shots)})...", end="", flush=True)

        # 优先使用 dubbing_text
        dubbing_text = shot_data.get("dubbing_text") or shot_data.get("description", "")
        if not dubbing_text:
            print(f" 无配音文字，跳过")
            continue

        try:
            mp3_file = generate_shot_dubbing(text=dubbing_text, shot_index=si, narrator_voice=narrator_voice)
            if mp3_file:
                with state_lock:
                    if "shot_dubbing" not in project_state:
                        project_state["shot_dubbing"] = {}
                    project_state["shot_dubbing"][si] = mp3_file
                print(f" ✅")
            else:
                print(f" ⚠️ 失败，继续")
        except Exception as e:
            print(f" ❌ 异常 ({e})，继续")

    # ---- 步骤 5: 合并每个分镜的音视频 ----
    print("\n" + "=" * 50)
    print("【步骤 5/5】合并所有分镜的音视频...")

    for idx, shot_data in enumerate(all_shots, 1):
        si = shot_data["shot_index"]
        print(f"  🔗 分镜 {si} ({idx}/{len(all_shots)})...", end="", flush=True)

        merged = merge_shot_media(si)
        if merged:
            with state_lock:
                if "merged_videos" not in project_state:
                    project_state["merged_videos"] = {}
                project_state["merged_videos"][si] = merged
            print(f" ✅")
        else:
            print(f" ⚠️ 合并失败（可能缺少配音）")

    # ---- 最终合并：合并全部分镜为完整视频 ----
    print("\n" + "=" * 50)
    print("🎬 最终合并：合成完整视频...")
    final = merge_all_shots("Final_AI_Video.mp4")
    if final:
        with state_lock:
            project_state["final_video"] = final
        print(f"\n🎉🎉🎉 完整 AI 视频生成完成: {final}")
    else:
        print(f"\n❌ 最终合并失败")


@app.route('/api/generate/batch', methods=['POST'])
def batch_generate():
    """一键生成全部：分析→图片→视频→配音→合并→最终合并"""
    data = request.get_json(silent=True) or {}
    story_text = data.get("text", "")
    art_style = data.get("style", project_state.get("art_style", "迪士尼风格, 细腻光影, 高品质渲染, 4K"))
    target_shots = data.get("shots", None)

    if not story_text:
        if not os.path.exists(INPUT_STORY_FILE):
            return jsonify({"error": f"找不到 {INPUT_STORY_FILE}，请上传故事文本"}), 400
        with open(INPUT_STORY_FILE, "r", encoding="utf-8") as f:
            story_text = f.read()

    # 启动后台线程
    thread = threading.Thread(
        target=_run_batch_generate,
        args=(story_text, art_style, target_shots),
        daemon=True
    )
    thread.start()
    return jsonify({"message": "🎬 一键生成任务已启动！将按顺序执行：分析故事 → 生成图片 → 生成视频 → 配音 → 合并 → 最终合成"})


@app.route('/api/generate/batch-status', methods=['GET'])
def batch_status():
    """获取一键生成的当前阶段性状态"""
    with state_lock:
        shots = project_state["shots"]
        images = dict(project_state["generated_images"])
        videos = dict(project_state["generated_videos"])
        dubbings = dict(project_state.get("shot_dubbing", {}))
        merged = dict(project_state.get("merged_videos", {}))
        final = project_state.get("final_video")

    total = len(shots)
    img_done = sum(1 for idx in range(1, total+1) if idx in images)
    vid_done = sum(1 for idx in range(1, total+1) if idx in videos)
    dub_done = sum(1 for idx in range(1, total+1) if idx in dubbings)
    merge_done = sum(1 for idx in range(1, total+1) if idx in merged)

    return jsonify({
        "total_shots": total,
        "images_done": img_done,
        "videos_done": vid_done,
        "dubbings_done": dub_done,
        "merges_done": merge_done,
        "final_ready": final is not None and os.path.exists(os.path.join(OUTPUT_DIR, final)),
        "final_file": final,
    })


# ================= 设置 =================

@app.route('/api/settings', methods=['GET', 'POST'])
def settings():
    if request.method == 'GET':
        with state_lock:
            return jsonify({
                "image_width": project_state.get("image_width", DEFAULT_IMAGE_WIDTH),
                "image_height": project_state.get("image_height", DEFAULT_IMAGE_HEIGHT),
                "steps": project_state.get("steps", DEFAULT_STEPS),
                "video_width": project_state.get("video_width", DEFAULT_VIDEO_WIDTH),
                "video_height": project_state.get("video_height", DEFAULT_VIDEO_HEIGHT),
                "duration": project_state.get("duration", DEFAULT_DURATION),
                "fps": project_state.get("fps", DEFAULT_FPS),
                "style": project_state.get("art_style", ""),
                "shots": project_state.get("shots_count", DEFAULT_SHOTS_COUNT),
                "use_frame_connection": project_state.get("use_frame_connection", False),
                "narrator_voice": project_state.get("narrator_voice", "温柔女声"),
            })
    data = request.get_json(silent=True) or {}
    with state_lock:
        for k, v in data.items():
            sn = {"image_width": "image_width", "image_height": "image_height",
                  "video_width": "video_width", "video_height": "video_height",
                  "duration": "duration", "fps": "fps", "style": "art_style",
                  "steps": "steps", "shots": "shots_count", "use_frame_connection": "use_frame_connection",
                  "narrator_voice": "narrator_voice"}
            if k in sn:
                project_state[sn[k]] = v
    return jsonify({"message": "设置已保存"})


# ================= 启动 =================
if __name__ == "__main__":
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    print("🎬 故事转 AI 视频 Web 应用启动中...")
    print(f"   前端地址: http://127.0.0.1:5000")
    print(f"   API 地址: http://127.0.0.1:5000/api/health")
    print(f"   ComfyUI: {COMFYUI_OUTPUT_DIR}")
    app.run(host="127.0.0.1", port=5000, debug=True, threaded=True)
