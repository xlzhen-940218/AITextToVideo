import json
import urllib.request
import time
import random
import os
import subprocess

# ================= 配置区 =================
COMFYUI_SERVER = "http://127.0.0.1:8188"
INPUT_JSON_FILE = "input_queue.json"
COMFYUI_OUTPUT_DIR = r"F:\ComfyUI\output"  # 【重要】请修改为你的实际路径

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


# ================= 声音库引擎 =================
def parse_voice_files(file_list, folder_name):
    """解析文件名，提取标签和语种"""
    known_langs = ["英语", "北京话", "四川话", "德语", "韩语", "日语", "陕西话", "天津话", "粤语", "闽南话", "上海话",
                   "印尼话", "东北话"]
    db = []
    for f in file_list:
        basename = f.rsplit('.', 1)[0]
        parts = basename.replace('，', '_').split('_')

        lang = "中文普通话"
        tags = []
        for p in parts:
            if p in known_langs:
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

character_voice_map = {}
used_voices = set()


def assign_voice(name, char_gender, char_personality, char_lang):
    """智能分配：按性别 -> 语种 -> 性格匹配度挑选最高分的配音"""
    if name in character_voice_map:
        return character_voice_map[name]

    pool = MAN_DB if char_gender.lower() in ['man', 'male', '男'] else GIRL_DB

    target_lang = char_lang if char_lang else "中文普通话"
    if target_lang == "中文" or target_lang == "普通话": target_lang = "中文普通话"

    lang_matched = [v for v in pool if target_lang in v['language']]
    if not lang_matched:
        lang_matched = [v for v in pool if "中文普通话" in v['language']]
    if not lang_matched:
        lang_matched = pool

    available = [v for v in lang_matched if v['file'] not in used_voices]
    if not available: available = lang_matched

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
    used_voices.add(chosen_file)
    character_voice_map[name] = chosen_file

    print(f"  🎙️ [{name}] 识别语言: {target_lang}, 人设: {char_personality}")
    print(f"     -> 匹配配音: {os.path.basename(chosen_file)} (契合度得分: {best_score})")

    return chosen_file


# ================= 核心处理逻辑 =================
def split_into_batches(queue):
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
    if current_batch: batches.append(current_batch)
    return batches


def build_workflow_for_batch(batch_data, batch_index):
    unique_chars = {}
    for item in batch_data:
        name = item['name']
        if name not in unique_chars:
            unique_chars[name] = {
                'gender': item.get('gender', 'male'),
                'personality': item.get('personality', ''),
                'language': item.get('language', '中文普通话')
            }

    speaker_letters = ['A', 'B', 'C', 'D']
    name_to_speaker = {name: speaker_letters[i] for i, name in enumerate(unique_chars.keys())}

    dialog_lines = [f"SPEAKER {name_to_speaker[item['name']]}: {item['text']}" for item in batch_data]
    dialog_text = "\n".join(dialog_lines)

    prompt = {
        "10": {
            "class_type": "FL_CosyVoice3_ModelLoader",
            "inputs": {
                "model_version": "Fun-CosyVoice3-0.5B",
                "download_source": "HuggingFace",
                "device": "auto", "force_redownload": False, "force_reload": False
            }
        },
        "20": {
            "class_type": "FL_CosyVoice3_Dialog",
            "inputs": {
                "model": ["10", 0], "dialog_text": dialog_text, "speed": 1.0, "seed": random.randint(1, 99999999)
            }
        },
        "30": {
            "class_type": "SaveAudio",
            "inputs": {
                "audio": ["20", 0], "filename_prefix": f"Dubbing_Part_{batch_index:02d}"
            }
        }
    }

    for i, (name, profile) in enumerate(unique_chars.items()):
        speaker_id = name_to_speaker[name]
        voice_file = assign_voice(name, profile['gender'], profile['personality'], profile['language'])

        load_node_id = str(100 + i)
        crop_node_id = str(200 + i)

        prompt[load_node_id] = {"class_type": "LoadAudio", "inputs": {"audio": voice_file}}
        prompt[crop_node_id] = {"class_type": "FL_CosyVoice3_AudioCrop",
                                "inputs": {"audio": [load_node_id, 0], "start_time": "0:00", "end_time": "0:10"}}
        prompt["20"]["inputs"][f"speaker_{speaker_id}_Audio"] = [crop_node_id, 0]

    # ================= 关键修复逻辑 =================
    # 如果这个批次只有1个角色（只有 A），为了满足节点强制要求，把 A 的音频也喂给 B
    if "speaker_B_Audio" not in prompt["20"]["inputs"]:
        prompt["20"]["inputs"]["speaker_B_Audio"] = prompt["20"]["inputs"]["speaker_A_Audio"]
    # ===============================================

    return prompt


def convert_to_mp3(filename):
    original_path = os.path.join(COMFYUI_OUTPUT_DIR, filename)
    if not os.path.exists(original_path) or not (filename.endswith(".flac") or filename.endswith(".wav")):
        return filename

    mp3_filename = filename.rsplit(".", 1)[0] + ".mp3"
    mp3_path = os.path.join(COMFYUI_OUTPUT_DIR, mp3_filename)

    print(f"\n  ↳ 正在转码 MP3: {mp3_filename} ...", end="", flush=True)
    command = ['ffmpeg', '-i', original_path, '-y', mp3_path]
    try:
        subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        os.remove(original_path)
        print(" 完成! (源文件已清理)")
        return mp3_filename
    except Exception as e:
        print(f" [失败] FFmpeg 异常: {e}")
        return filename


def submit_and_track(prompt):
    data = json.dumps({"prompt": prompt}).encode('utf-8')
    req = urllib.request.Request(f"{COMFYUI_SERVER}/prompt", data=data, headers={'Content-Type': 'application/json'})
    prompt_id = json.loads(urllib.request.urlopen(req).read()).get("prompt_id")

    print(f"\n任务提交成功 (ID: {prompt_id})，正在渲染音频 ", end="")
    while True:
        try:
            history = json.loads(
                urllib.request.urlopen(urllib.request.Request(f"{COMFYUI_SERVER}/history/{prompt_id}")).read())
            if prompt_id in history:
                print(" 渲染完毕!")
                outputs = history[prompt_id].get("outputs", {})
                return [convert_to_mp3(a["filename"]) for n in outputs.values() if "audio" in n for a in n["audio"]]
        except Exception:
            pass
        print(".", end="", flush=True)
        time.sleep(2)


# ================= 【新增】合并音频逻辑 =================
def merge_mp3_files(file_list, output_filename="Final_Merged_Dubbing.mp3"):
    """使用 FFmpeg 无损拼接所有的分段 MP3 文件"""
    if not file_list:
        return None
    if len(file_list) == 1:
        return file_list[0]

    list_file_path = os.path.join(COMFYUI_OUTPUT_DIR, "concat_list.txt")
    final_output_path = os.path.join(COMFYUI_OUTPUT_DIR, output_filename)

    # 1. 创建 ffmpeg 拼接需要的列表文件
    with open(list_file_path, "w", encoding="utf-8") as f:
        for file in file_list:
            f.write(f"file '{file}'\n")

    print(f"\n🎧 正在将 {len(file_list)} 个分段音频合并为最终文件...", end="", flush=True)

    # 2. 调用 FFmpeg 进行拼接 (-c copy 极速无损合并)
    command = ['ffmpeg', '-f', 'concat', '-safe', '0', '-i', 'concat_list.txt', '-c', 'copy', '-y', output_filename]

    try:
        # cwd 设置为目标目录，避免特殊字符路径问题
        subprocess.run(command, cwd=COMFYUI_OUTPUT_DIR, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       check=True)
        os.remove(list_file_path)  # 删除临时列表

        # 3. 合并完成后，清理掉没用的分段文件
        for file in file_list:
            part_path = os.path.join(COMFYUI_OUTPUT_DIR, file)
            if os.path.exists(part_path):
                os.remove(part_path)

        print(" 合并成功!")
        return output_filename
    except Exception as e:
        print(f" [合并失败] FFmpeg 异常: {e}")
        return None


# ================= 主程序 =================
if __name__ == "__main__":
    if not os.path.exists(INPUT_JSON_FILE):
        print(f"[错误] 找不到输入文件 {INPUT_JSON_FILE}")
        exit(1)

    print("正在加载输入队列...")
    with open(INPUT_JSON_FILE, "r", encoding="utf-8") as f:
        full_queue = json.load(f)

    batches = split_into_batches(full_queue)
    print(f"剧本分析完毕，共 {len(full_queue)} 句话，分为 {len(batches)} 个批次生成。\n" + "-" * 40)

    all_generated_files = []
    for index, batch in enumerate(batches, start=1):
        print(f"\n>>> 准备第 [{index}/{len(batches)}] 批次工作流:")
        workflow = build_workflow_for_batch(batch, index)
        files = submit_and_track(workflow)
        all_generated_files.extend(files)

    # 批量生成完毕，开始合并
    if all_generated_files:
        print("\n" + "=" * 40)
        final_mp3 = merge_mp3_files(all_generated_files)

        print("\n🎉 自动配音引擎运行完毕！你的最终剧本音频已生成：")
        print(f" -> 所在目录: {COMFYUI_OUTPUT_DIR}")
        print(f" -> 文件名称: {final_mp3}")