"""
audio_dubbing.py - 多角色配音引擎

整合流程：
  1. 用 DeepSeek AI 从故事文本中提取对话/旁白（复用 chapter_to_json.py 逻辑）
  2. 智能分配配音角色（复用 main.py 逻辑）
  3. 分批调用 ComfyUI CosyVoice 生成音频
  4. 合并所有分段为最终音频文件

用法：
  from audio_dubbing import generate_dubbing
  mp3_file = generate_dubbing(story_text="...")


注意：请确保在 ComfyUI 中已安装 CosyVoice 相关节点。
"""

import json
import urllib.request
import time
import random
import os
import subprocess
import re
import sys
import yaml
from openai import OpenAI

# ================= 配置区（从 public_config.yaml 加载） =================
from config_loader import get

CONFIG_FILE = "private_config.yaml"
COMFYUI_SERVER = get("comfyui.server", "http://127.0.0.1:8188")
COMFYUI_OUTPUT_DIR = get("comfyui.output_dir", r"F:\ComfyUI\output")
OUTPUT_DIR = get("output_dir", "storyboard_output")

# AI 对话提取参数（使用公共配置）
CHUNK_MAX_LENGTH = get("ai.dubbing_chunk_max_length", 1500)
AI_TEMPERATURE = get("ai.dubbing_temperature", 0.1)
AI_MAX_TOKENS = get("ai.dubbing_max_tokens", 4000)
AI_API_BASE_URL = get("ai.api_base_url", "https://api.deepseek.com")

# 配音模型参数
DUBBING_MODEL_VERSION = get("audio_dubbing.model_version", "Fun-CosyVoice3-0.5B")
DUBBING_DOWNLOAD_SOURCE = get("audio_dubbing.download_source", "HuggingFace")
DUBBING_DEVICE = get("audio_dubbing.device", "auto")
VOICE_DIR_MAN = get("audio_dubbing.voice_dir_man", "man")
VOICE_DIR_GIRLS = get("audio_dubbing.voice_dir_girls", "girls")


# ================= 声音库 =================
RAW_MAN_FILES = [
    "Aiden_美式男孩_英语.wav", "Chinese (Mandarin)_Gentle_Youth_清亮干净、温暖柔和、节奏舒缓、治愈、亲切、邻家感.mp3",
    "Chinese (Mandarin)_Reliable_Executive_低沉厚实、磁性强、节奏从容、条理清晰、成熟、权威、可靠.mp3",
    "Dylan_胡同少年_北京话.wav",
    "English_expressive_narrator_清亮有张力、节奏起伏明显、表现力强、生动、戏剧化、感染力_英语.mp3",
    "Eric_成都大哥_四川话.wav",
    "Ethan_清朗明快男.wav", "hunyin_6_清亮有朝气、干脆利落、节奏明快、自信、意气风发.mp3", "kabuleshen_v2_实力歌手男.mp3",
    "Kai_磁性男声.wav", "Lenn_德国青年_德语.wav", "longanchong_激情推销男.mp3", "longanlang_清爽利落男.mp3",
    "longanyang_阳光大男孩.mp3",
    "longcheng_v2_智慧青年男.mp3", "longgaoseng_得道高僧音.mp3", "longhan_v2_温暖痴情男.mp3",
    "longhouge_经典猴哥_尖锐男声.mp3",
    "longlaotie_v2_东北直率男_东北话.mp3", "longnan_v2_睿智青年男.mp3", "longshao_v2_积极向上男.mp3",
    "longshu_v2_沉稳青年男.mp3",
    "longshuo_v3_博才干练男.mp3", "longxiu_v2_博才说书男.mp3", "longyichen_洒脱活力男.mp3",
    "longyingcui_严肃催收男.mp3",
    "longyingxun_年轻青涩男.mp3", "longze_v2_温暖元气男.mp3", "longzhe_v2_呆板大暖男.mp3",
    "loongjihun_v3_韩语男_韩语.wav",
    "loongluca_v3_英式英文男_英语.wav", "loongyuuma_v3_日语男_日语.wav", "Marcus_陕北汉子_陕西话.wav",
    "Moon_呆板大暖男.wav",
    "Neil_新闻主播（沉稳男声）.wav", "Nofish_南方口音男.wav", "Peter_天津捧哏_天津话.wav", "Rocky_幽默港仔_粤语.wav",
    "Roy_闽南哥仔_闽南话.wav", "Ryan_美剧张力男_英语.wav"
]

RAW_GIRL_FILES = [
    "Cantonese_ProfessionalHost（F)_清晰明亮、吐字标准、节奏紧凑有力、专业、冷静、权威_粤语.mp3", "Chelsie_乖巧，柔弱.wav",
    "Cherry_阳光自然女.wav", "Elias_学术讲师女.wav", "Jada_爽利带劲女_上海话.wav", "Jennifer_美式英文女_英语.wav",
    "Kiki_甜美_粤语.wav",
    "longanhuan_欢脱元气女.mp3", "longanling_思维灵动女.mp3", "longanmin_甜美闽南女_闽南话.mp3",
    "longanpei_青少年教师女.mp3",
    "longanping_高亢直播女.mp3", "longanrou_温柔闺蜜女.mp3", "longantai_v3_嗲甜台湾女.mp3", "longbaizhi_睿气旁白女.mp3",
    "longdaiyu_嗲嗲娇率才女音.mp3", "longgangmei_TVB港剧国语女.mp3", "longhua_v3_元气甜美女.mp3",
    "longjiayi_v2_知性粤语女_粤语.mp3",
    "longjixin_尖锐毒舌心机女.mp3", "longmiao_v3_抑扬顿挫女.mp3", "longqiang_v3_浪漫风情女.mp3",
    "longwanjun_细腻柔声女.mp3",
    "longxian_v3_豪放可爱女.mp3", "longxiaochun_知性积极女.mp3", "longxiaoxia_v2_沉稳权威女.mp3",
    "longyingbing_尖锐强势女.mp3",
    "longyingda_开朗高音女.mp3", "longyingjing_低调冷静女.mp3", "longyingtian_温柔甜美女.mp3",
    "longyingxiao_清甜推销女.mp3",
    "longyingyan_义正严辞女.mp3", "longyue_v2_温暖磁性女.mp3", "loongbella_v2_精准干练女.mp3",
    "loongcally_v3_美式英文女_英语.wav",
    "loongindah_v3_印尼话.wav", "loongkyong_v3_韩语女_韩语.wav", "loongyuuna_v3_日语女_日语.wav", "Maia_温柔女声.wav",
    "Mia_乖巧女声_英语.wav", "Ono Anna_日式漫画音_日语.wav", "Seren_磁性低音.wav", "Sohee_温柔欧尼_韩语.wav",
    "Stella_嗲声少女.wav",
    "Sunny_甜飒川妹_四川话.wav", "Vivian_暴躁大姐大.wav"
]

KNOWN_LANGS = ["英语", "北京话", "四川话", "德语", "韩语", "日语", "陕西话", "天津话", "粤语", "闽南话", "上海话", "印尼话", "东北话"]


def parse_voice_files(file_list, folder_name):
    """解析文件名，提取标签和语种"""
    db = []
    for f in file_list:
        basename = f.rsplit('.', 1)[0]
        parts = basename.replace('，', '_').split('_')
        lang = "中文普通话"
        tags = []
        for p in parts:
            if p in KNOWN_LANGS:
                lang = p
            else:
                tags.append(p)
        db.append({
            "file": f"{folder_name}/{f}",
            "language": lang,
            "tags": " ".join(tags)
        })
    return db


MAN_DB = parse_voice_files(RAW_MAN_FILES, "man")
GIRL_DB = parse_voice_files(RAW_GIRL_FILES, "girls")

# 配音分配缓存（避免同一角色重复分配不同声线）
_character_voice_map = {}
_used_voices = set()


def reset_voice_cache():
    """重置配音分配缓存"""
    _character_voice_map.clear()
    _used_voices.clear()


def assign_voice(name, char_gender, char_personality, char_lang):
    """智能分配：按性别 -> 语种 -> 性格匹配度挑选最高分的配音"""
    if name in _character_voice_map:
        return _character_voice_map[name]

    pool = MAN_DB if char_gender.lower() in ['man', 'male', '男'] else GIRL_DB

    target_lang = char_lang if char_lang else "中文普通话"
    if target_lang == "中文" or target_lang == "普通话":
        target_lang = "中文普通话"

    lang_matched = [v for v in pool if target_lang in v['language']]
    if not lang_matched:
        lang_matched = [v for v in pool if "中文普通话" in v['language']]
    if not lang_matched:
        lang_matched = pool

    available = [v for v in lang_matched if v['file'] not in _used_voices]
    if not available:
        available = lang_matched

    best_voice = None
    best_score = -1
    ignore_chars = ['男', '女', '声', '音', '的', '、', '，', '（', '）', ' ']

    for v in available:
        score = 0
        for char in char_personality:
            if char in v['tags'] and char not in ignore_chars:
                score += 1
        if score > best_score:
            best_score = score
            best_voice = v

    if best_score == 0 or not best_voice:
        best_voice = random.choice(available)

    chosen_file = best_voice['file']
    _used_voices.add(chosen_file)
    _character_voice_map[name] = chosen_file

    print(f"  🎙️ [{name}] 语言: {target_lang}, 人设: {char_personality}")
    print(f"     -> 匹配配音: {os.path.basename(chosen_file)} (得分: {best_score})")
    return chosen_file


# ================= 加载 API Key =================

def load_api_key(config_path):
    if not os.path.exists(config_path):
        return None
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
            return config.get("deepseek", {}).get("api")
    except Exception:
        return None


# ================= AI 对话提取 =================

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


def extract_dialogue_chunk(client, text_chunk, chunk_index, total_chunks):
    """处理单个文本块的对话提取"""
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
            temperature=AI_TEMPERATURE,
            max_tokens=AI_MAX_TOKENS
        )
        if response.choices[0].finish_reason == "length":
            print(f"[警告] 第 {chunk_index} 部分提取被截断，可能遗漏部分台词！")

        result_content = response.choices[0].message.content.strip()
        json_match = re.search(r'\[.*\]', result_content, re.DOTALL)
        json_str = json_match.group(0) if json_match else result_content
        return json.loads(json_str)
    except json.JSONDecodeError as e:
        print(f"[错误] 第 {chunk_index} 部分 JSON 解析失败: {e}")
        return []
    except Exception as e:
        print(f"[错误] 第 {chunk_index} 部分请求失败: {e}")
        return []


# ================= CosyVoice 音频生成（复用 main.py 逻辑） =================

def split_into_batches(queue):
    """按角色分批，每批最多4个不同角色（CosyVoice 的 Speaker 限制 A/B/C/D）"""
    batches, current_batch, current_characters = [], [], set()
    for item in queue:
        name = item['name']
        if name not in current_characters and len(current_characters) >= 4:
            batches.append(current_batch)
            current_batch = [item]
            current_characters = {name}
        else:
            current_batch.append(item)
            current_characters.add(name)
    if current_batch:
        batches.append(current_batch)
    return batches


def clean_text_for_tts(text):
    """
    清理文本以避免 CosyVoice 产生爆音/疙瘩声：
    - 去除多余空白和换行
    - 确保句子以标点结尾
    - 压缩连续空白
    - 在开头加入语气词「嗯，」让TTS平稳启动，避免首个字突兀
    """
    # 替换换行符为空格（避免换行导致疙瘩声）
    text = text.replace('\n', ' ').replace('\r', ' ').replace('\t', ' ')
    # 压缩连续空白
    text = re.sub(r' +', ' ', text)
    # 去除首尾空白
    text = text.strip()
    # 确保以句号/问号/感叹号/省略号结尾，没有则补句号
    if text and text[-1] not in ('。', '？', '！', '…', '.', '?', '!', '，', ','):
        text += '。'
    return text


def build_workflow_for_batch(batch_data, batch_index):
    """构建 CosyVoice API prompt"""
    unique_chars = {}
    for item in batch_data:
        name = item['name']
        if name not in unique_chars:
            unique_chars[name] = {
                'gender': item.get('gender', 'female'),
                'personality': item.get('personality', ''),
                'language': item.get('language', '中文普通话')
            }

    speaker_letters = ['A', 'B', 'C', 'D']
    name_to_speaker = {name: speaker_letters[i] for i, name in enumerate(unique_chars.keys())}

    # 清理每句文本，消除换行符导致的疙瘩声
    dialog_lines = []
    for item in batch_data:
        clean_text = clean_text_for_tts(item['text'])
        dialog_lines.append(f"SPEAKER {name_to_speaker[item['name']]}: {clean_text}")
    dialog_text = "\n".join(dialog_lines)

    prompt = {
        "10": {
            "class_type": "FL_CosyVoice3_ModelLoader",
            "inputs": {
                "model_version": DUBBING_MODEL_VERSION,
                "download_source": DUBBING_DOWNLOAD_SOURCE,
                "device": DUBBING_DEVICE,
                "force_redownload": False,
                "force_reload": False
            }
        },

        "20": {
            "class_type": "FL_CosyVoice3_Dialog",
            "inputs": {
                "model": ["10", 0],
                "dialog_text": dialog_text,
                "speed": 1.0,
                "seed": random.randint(1, 99999999)
            }
        },
        "30": {
            "class_type": "SaveAudio",
            "inputs": {
                "audio": ["20", 0],
                "filename_prefix": f"Dubbing_Part_{batch_index:02d}"
            }
        }
    }

    for i, (name, profile) in enumerate(unique_chars.items()):
        speaker_id = name_to_speaker[name]
        voice_file = assign_voice(name, profile['gender'], profile['personality'], profile['language'])
        load_node_id = str(100 + i)
        crop_node_id = str(200 + i)
        prompt[load_node_id] = {"class_type": "LoadAudio", "inputs": {"audio": voice_file}}
        prompt[crop_node_id] = {
            "class_type": "FL_CosyVoice3_AudioCrop",
            "inputs": {"audio": [load_node_id, 0], "start_time": "0:01", "end_time": "0:10"}
        }
        prompt["20"]["inputs"][f"speaker_{speaker_id}_Audio"] = [crop_node_id, 0]

    # 如果只有1个角色，用 A 也填 B
    if "speaker_B_Audio" not in prompt["20"]["inputs"]:
        prompt["20"]["inputs"]["speaker_B_Audio"] = prompt["20"]["inputs"]["speaker_A_Audio"]

    return prompt


def submit_prompt(prompt):
    """提交 prompt 到 ComfyUI API"""
    data = json.dumps({"prompt": prompt}).encode('utf-8')
    req = urllib.request.Request(
        f"{COMFYUI_SERVER}/prompt",
        data=data,
        headers={'Content-Type': 'application/json'}
    )
    prompt_id = json.loads(urllib.request.urlopen(req).read()).get("prompt_id")
    if not prompt_id:
        raise RuntimeError("提交失败")
    return prompt_id


def wait_for_completion(prompt_id, poll_interval=3):
    """轮询等待 ComfyUI 任务完成"""
    print(f"任务已提交 (ID: {prompt_id})，正在渲染音频 ", end="", flush=True)
    while True:
        try:
            url = f"{COMFYUI_SERVER}/history/{prompt_id}"
            history = json.loads(urllib.request.urlopen(urllib.request.Request(url)).read())
            if prompt_id in history:
                print(" 渲染完毕!")
                return history[prompt_id].get("outputs", {})
        except Exception:
            pass
        print(".", end="", flush=True)
        time.sleep(poll_interval)


def collect_audio_files(outputs):
    """从 outputs 中提取音频文件"""
    files = []
    for node_id, node_output in outputs.items():
        if "audio" in node_output:
            for a in node_output["audio"]:
                files.append(a["filename"])
    return files


def convert_to_mp3(filename):
    """将 flac/wav 转码为 mp3，同时裁剪开头 0.3 秒的静音/噪声"""
    original_path = os.path.join(COMFYUI_OUTPUT_DIR, filename)
    if not os.path.exists(original_path) or not (filename.endswith(".flac") or filename.endswith(".wav")):
        return filename
    mp3_filename = filename.rsplit(".", 1)[0] + ".mp3"
    mp3_path = os.path.join(COMFYUI_OUTPUT_DIR, mp3_filename)
    print(f"  ↳ 正在转码 MP3: {mp3_filename} ...", end="", flush=True)
    # 用 atrim 裁剪开头 0.3 秒噪声，同时转码为 mp3
    command = ['ffmpeg', '-i', original_path, '-af', 'atrim=start=0.1', '-y', mp3_path]
    try:
        subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        os.remove(original_path)
        print(" 完成!")
        return mp3_filename
    except Exception as e:
        print(f" [失败] {e}")
        return filename


def merge_mp3_files(file_list, output_filename="Final_Dubbing.mp3"):
    """使用 FFmpeg 无损拼接所有分段 MP3"""
    if not file_list:
        return None
    if len(file_list) == 1:
        return file_list[0]

    list_file_path = os.path.join(COMFYUI_OUTPUT_DIR, "concat_list.txt")
    final_output_path = os.path.join(COMFYUI_OUTPUT_DIR, output_filename)

    with open(list_file_path, "w", encoding="utf-8") as f:
        for file in file_list:
            f.write(f"file '{file}'\n")

    print(f"\n🎧 正在将 {len(file_list)} 个分段音频合并...", end="", flush=True)
    command = ['ffmpeg', '-f', 'concat', '-safe', '0', '-i', 'concat_list.txt', '-c', 'copy', '-y', output_filename]
    try:
        subprocess.run(command, cwd=COMFYUI_OUTPUT_DIR, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        os.remove(list_file_path)
        for file in file_list:
            part_path = os.path.join(COMFYUI_OUTPUT_DIR, file)
            if os.path.exists(part_path):
                os.remove(part_path)
        print(" 合并成功!")
        return output_filename
    except Exception as e:
        print(f" [失败] {e}")
        return None


# ================= 主函数 =================

def generate_dubbing(story_text=None, story_file="story.txt"):
    """
    主流程：
      1. 读取故事文本
      2. AI 提取对话/旁白队列
      3. 分批配音（每批最多4角色）
      4. 合并音频
      5. 拷贝到故事目录

    返回: 最终 mp3 文件路径（相对于 COMFYUI_OUTPUT_DIR），或 None
    """
    # 1. 读取故事
    if not story_text:
        if not os.path.exists(story_file):
            print(f"[错误] 找不到故事文件: {story_file}")
            return None
        with open(story_file, "r", encoding="utf-8") as f:
            story_text = f.read()
        print(f"📖 已读取故事文件: {story_file} ({len(story_text)} 字符)")

    # 2. 加载 API Key
    api_key = load_api_key(CONFIG_FILE)
    if not api_key:
        print("[错误] 未能加载 API Key")
        return None

    client = OpenAI(api_key=api_key, base_url=AI_API_BASE_URL)


    # 3. 提取对话
    reset_voice_cache()
    chunks = split_text_into_chunks(story_text, CHUNK_MAX_LENGTH)
    print(f"📄 文本已切分为 {len(chunks)} 个处理块。")

    full_queue = []
    for i, chunk in enumerate(chunks, 1):
        if not chunk.strip():
            continue
        chunk_result = extract_dialogue_chunk(client, chunk, i, len(chunks))
        if chunk_result:
            full_queue.extend(chunk_result)

    if not full_queue:
        print("❌ 未能提取到任何对话/旁白")
        return None

    print(f"✅ 共提取 {len(full_queue)} 条配音项\n")

    # 4. 分批生成
    batches = split_into_batches(full_queue)
    print(f"分 {len(batches)} 个批次进行配音生成。\n" + "-" * 40)

    all_generated_files = []
    for index, batch in enumerate(batches, start=1):
        print(f"\n>>> 第 [{index}/{len(batches)}] 批:")
        workflow = build_workflow_for_batch(batch, index)
        outputs = wait_for_completion(submit_prompt(workflow))
        files = [convert_to_mp3(f) for f in collect_audio_files(outputs)]
        all_generated_files.extend(files)

    # 5. 合并
    if not all_generated_files:
        print("❌ 未生成任何音频文件")
        return None

    print("\n" + "=" * 40)
    final_mp3 = merge_mp3_files(all_generated_files, "Final_Dubbing.mp3")

    if final_mp3:
        # 6. 拷贝到故事目录
        src_path = os.path.join(COMFYUI_OUTPUT_DIR, final_mp3)
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        dst_path = os.path.join(OUTPUT_DIR, final_mp3)
        try:
            import shutil
            shutil.copy2(src_path, dst_path)
            print(f"\n🎉 配音音频已拷贝到: {dst_path}")
        except Exception as e:
            print(f"\n⚠️ 拷贝到故事目录失败: {e}")

        print(f"\n🎉 最终配音音频: {os.path.join(COMFYUI_OUTPUT_DIR, final_mp3)}")
        return final_mp3
    else:
        print("❌ 音频合并失败")
        return None


def generate_shot_dubbing(text, shot_index, narrator_voice_note="旁白"):
    """
    为单个分镜生成配音。
    只需要一个讲述人（旁白）角色，把分镜描述念出来。
    
    参数:
        text: 要朗读的文本（分镜的 description 或 prompt）
        shot_index: 分镜序号（用于文件名）
        narrator_voice_note: 旁白角色标签，用于筛选声线
        
    返回: mp3 文件名（相对于 COMFYUI_OUTPUT_DIR），或 None
    """
    if not text or not text.strip():
        print(f"[错误] 分镜 {shot_index} 没有配音文本")
        return None
    
    # 清理文本
    clean_text = clean_text_for_tts(text)
    print(f"\n🎙️ 正在为分镜 {shot_index} 生成配音...")
    print(f"   文本: {clean_text[:80]}...")
    
    # 分配旁白声线
    narrator_file = assign_voice("旁白", "female", narrator_voice_note, "中文普通话")
    
    # 构建单角色 prompt
    dialog_text = f"SPEAKER A: {clean_text}"
    
    prompt = {
        "10": {
            "class_type": "FL_CosyVoice3_ModelLoader",
            "inputs": {
                "model_version": DUBBING_MODEL_VERSION,
                "download_source": DUBBING_DOWNLOAD_SOURCE,
                "device": DUBBING_DEVICE,
                "force_redownload": False,
                "force_reload": False
            }
        },
        "20": {
            "class_type": "FL_CosyVoice3_Dialog",
            "inputs": {
                "model": ["10", 0],
                "dialog_text": dialog_text,
                "speed": 1.0,
                "seed": random.randint(1, 99999999),
                "speaker_A_Audio": None,  # 下面会填入
                "speaker_B_Audio": None,
            }
        },
        "30": {
            "class_type": "SaveAudio",
            "inputs": {
                "audio": ["20", 0],
                "filename_prefix": f"Shot_Dubbing_{shot_index:02d}"
            }
        }
    }

    
    # 加载旁白音频
    prompt["100"] = {"class_type": "LoadAudio", "inputs": {"audio": narrator_file}}
    prompt["200"] = {
        "class_type": "FL_CosyVoice3_AudioCrop",
        "inputs": {"audio": ["100", 0], "start_time": "0:01", "end_time": "0:10"}
    }
    prompt["20"]["inputs"]["speaker_A_Audio"] = ["200", 0]
    prompt["20"]["inputs"]["speaker_B_Audio"] = ["200", 0]  # 填同样的避免校验失败
    
    # 提交并等待
    try:
        outputs = wait_for_completion(submit_prompt(prompt))
        files = [convert_to_mp3(f) for f in collect_audio_files(outputs)]
        
        if files:
            # 拷贝到故事目录
            os.makedirs(OUTPUT_DIR, exist_ok=True)
            shot_mp3_name = f"shot_{shot_index:02d}_dubbing.mp3"
            src = os.path.join(COMFYUI_OUTPUT_DIR, files[0])
            dst = os.path.join(OUTPUT_DIR, shot_mp3_name)
            import shutil
            shutil.copy2(src, dst)
            print(f"    ✅ 分镜 {shot_index} 配音完成: {shot_mp3_name}")
            return shot_mp3_name
        else:
            print(f"    ❌ 分镜 {shot_index} 配音生成无文件")
            return None
    except Exception as e:
        print(f"    ❌ 分镜 {shot_index} 配音失败: {e}")
        return None


# ================= 命令行入口 =================
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="多角色配音引擎")
    parser.add_argument("story", nargs="?", help="故事文件路径（默认 story.txt）")
    args = parser.parse_args()

    generate_dubbing(story_file=args.story or "story.txt")
