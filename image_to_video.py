"""
image_to_video.py - 调用 ComfyUI Image_to_Video (Wan2.2) 工作流，将图片转为视频

流程：
  1. 将输入图片上传到 ComfyUI 的 input 目录
  2. 构建 Wan2.2 I2V 工作流 API prompt
  3. 提交到 ComfyUI 渲染
  4. 返回生成的视频文件路径

用法（作为模块调用）：
  from image_to_video import generate_video
  video_files = generate_video(
      image_path="F:/ComfyUI/output/shot_01_scene.png",
      prompt="a cat walking in the park",
      seed=42,
      duration=5
  )
"""

import json
import urllib.request
import urllib.parse
import time
import os
import sys
import random
import shutil

# ================= 配置区（从 public_config.yaml 加载） =================
from config_loader import get

COMFYUI_SERVER = get("comfyui.server", "http://127.0.0.1:8188")
WORKFLOW_FILE = get("workflows.image_to_video", r"F:\ComfyUI\user\default\workflows\Image_to_Video.json")
COMFYUI_INPUT_DIR = get("comfyui.input_dir", r"F:\ComfyUI\input")
COMFYUI_OUTPUT_DIR = get("comfyui.output_dir", r"F:\ComfyUI\output")

# 模型参数（从 public_config.yaml 加载）
DEFAULT_CLIP = get("image_to_video_model.clip", "umt5_xxl_fp8_e4m3fn_scaled.safetensors")
DEFAULT_VAE = get("image_to_video_model.vae", "wan_2.1_vae.safetensors")
DEFAULT_HIGH_NOISE_UNET = get("image_to_video_model.high_noise_unet", "wan2.2_i2v_high_noise_14B_fp8_scaled.safetensors")
DEFAULT_LOW_NOISE_UNET = get("image_to_video_model.low_noise_unet", "wan2.2_i2v_low_noise_14B_fp8_scaled.safetensors")
DEFAULT_HIGH_NOISE_LORA = get("image_to_video_model.high_noise_lora", "wan2.2_i2v_lightx2v_4steps_lora_v1_high_noise.safetensors")
DEFAULT_LOW_NOISE_LORA = get("image_to_video_model.low_noise_lora", "wan2.2_i2v_lightx2v_4steps_lora_v1_low_noise.safetensors")

# 默认视频参数
DEFAULT_WIDTH = get("video.width", 960)
DEFAULT_HEIGHT = get("video.height", 540)

DEFAULT_FPS = get("video.fps", 16)
DEFAULT_DURATION = get("video.duration", 5)

# Turbo 模式参数
TURBO_STEPS_HIGH = get("turbo.steps_high", 4)
TURBO_STEPS_LOW = get("turbo.steps_low", 4)
TURBO_SPLIT_STEP = get("turbo.split_step", 2)
TURBO_CFG_HIGH = get("turbo.cfg_high", 1.0)
TURBO_CFG_LOW = get("turbo.cfg_low", 1.0)

# 非 Turbo 模式参数
DEFAULT_STEPS_HIGH = get("non_turbo.steps_high", 20)
DEFAULT_STEPS_LOW = get("non_turbo.steps_low", 4)
DEFAULT_SPLIT_STEP = get("non_turbo.split_step", 10)
DEFAULT_CFG_HIGH = get("non_turbo.cfg_high", 3.5)
DEFAULT_CFG_LOW = get("non_turbo.cfg_low", 1.0)

DEFAULT_SHIFT = get("shift", 5.0)
SAVEVIDEO_PREFIX = get("image_to_video_model.savevideo_prefix", "video/Wan2.2_i2v")



# ================= 图片上传 =================

def upload_image_to_comfyui(local_image_path):
    """
    将图片上传到 ComfyUI 的 input 目录。
    如果图片已在 input 目录中，直接返回文件名。
    否则复制过去。
    
    返回: (filename, success)
    """
    if not os.path.exists(local_image_path):
        print(f"[错误] 找不到图片文件: {local_image_path}")
        return None, False

    filename = os.path.basename(local_image_path)
    target_path = os.path.join(COMFYUI_INPUT_DIR, filename)

    try:
        if os.path.abspath(local_image_path) != os.path.abspath(target_path):
            shutil.copy2(local_image_path, target_path)
            print(f"📤 已上传图片到 ComfyUI: {target_path}")
        else:
            print(f"📤 图片已在 ComfyUI input 目录: {filename}")

        return filename, True
    except Exception as e:
        print(f"[错误] 上传图片失败: {e}")
        return None, False


# ================= 工作流构建 =================

def build_i2v_prompt(
    image_filename,
    prompt_text,
    negative_prompt="色调艳丽，过曝，静态，细节模糊不清，字幕，风格，作品，画作，画面，静止，整体发灰，最差质量，低质量，JPEG压缩残留，丑陋的，残缺的，多余的手指，画得不好的手部，画得不好的脸部，畸形的，毁容的，形态畸形的肢体，手指融合，静止不动的画面，杂乱的背景，三条腿，背景人很多，倒着走",
    seed=None,
    width=DEFAULT_WIDTH,
    height=DEFAULT_HEIGHT,
    duration=5,
    fps=DEFAULT_FPS,
    enable_turbo=True,  # 工作流默认 turbo 模式已启用
    # 模型参数（使用默认值）
    clip_name=DEFAULT_CLIP,
    vae_name=DEFAULT_VAE,
    high_noise_unet=DEFAULT_HIGH_NOISE_UNET,
    low_noise_unet=DEFAULT_LOW_NOISE_UNET,
    high_noise_lora=DEFAULT_HIGH_NOISE_LORA,
    low_noise_lora=DEFAULT_LOW_NOISE_LORA,
):
    """
    构建 Wan2.2 Image-to-Video 的 API prompt。
    
    这是双阶段采样架构：
      Stage 1 (High Noise): 用高噪声模型采样，保留噪声
      Stage 2 (Low Noise): 用低噪声模型从 Stage 1 的 latent 继续采样
    
    返回: prompt dict (ComfyUI API 格式)
    """
    if seed is None:
        seed = random.randint(1, 99999999999)

    # 计算帧数: duration * fps + 1
    length = int(duration * fps + 1)

    prompt = {}

    # --- 图片加载 ---
    prompt["97"] = {
        "class_type": "LoadImage",
        "inputs": {"image": image_filename}
    }

    # --- 模型加载 ---
    prompt["84"] = {
        "class_type": "CLIPLoader",
        "inputs": {
            "clip_name": clip_name,
            "type": "wan",
            "device": "default"
        }
    }

    prompt["90"] = {
        "class_type": "VAELoader",
        "inputs": {"vae_name": vae_name}
    }

    # UNET Loaders (高噪声 + 低噪声)
    prompt["95"] = {
        "class_type": "UNETLoader",
        "inputs": {
            "unet_name": high_noise_unet,
            "weight_dtype": "default"
        }
    }

    prompt["96"] = {
        "class_type": "UNETLoader",
        "inputs": {
            "unet_name": low_noise_unet,
            "weight_dtype": "default"
        }
    }

    # --- 文本编码 ---
    prompt["93"] = {
        "class_type": "CLIPTextEncode",
        "inputs": {
            "clip": ["84", 0],
            "text": prompt_text
        }
    }

    prompt["89"] = {
        "class_type": "CLIPTextEncode",
        "inputs": {
            "clip": ["84", 0],
            "text": negative_prompt
        }
    }

    # --- WanImageToVideo (核心 I2V 节点) ---
    prompt["98"] = {
        "class_type": "WanImageToVideo",
        "inputs": {
            "positive": ["93", 0],
            "negative": ["89", 0],
            "vae": ["90", 0],
            "start_image": ["97", 0],
            "width": width,
            "height": height,
            "length": length,
            "batch_size": 1
        }
    }

    # --- 根据 enable_turbo 选择参数 ---
    if enable_turbo:
        # 工作流默认启用 Turbo: LoRA + 4步采样
        # 高噪声分支: UNET(95) -> LoRA(101) -> ModelSamplingSD3(104)
        prompt["101"] = {
            "class_type": "LoraLoaderModelOnly",
            "inputs": {
                "model": ["95", 0],
                "lora_name": high_noise_lora,
                "strength_model": 1.0
            }
        }
        prompt["104"] = {
            "class_type": "ModelSamplingSD3",
            "inputs": {
                "model": ["101", 0],
                "shift": DEFAULT_SHIFT
            }
        }

        # 低噪声分支: UNET(96) -> LoRA(102) -> ModelSamplingSD3(103)
        prompt["102"] = {
            "class_type": "LoraLoaderModelOnly",
            "inputs": {
                "model": ["96", 0],
                "lora_name": low_noise_lora,
                "strength_model": 1.0
            }
        }
        prompt["103"] = {
            "class_type": "ModelSamplingSD3",
            "inputs": {
                "model": ["102", 0],
                "shift": DEFAULT_SHIFT
            }
        }

        steps_high = TURBO_STEPS_HIGH
        steps_low = TURBO_STEPS_LOW
        split_step = TURBO_SPLIT_STEP
        cfg_high = TURBO_CFG_HIGH
        cfg_low = TURBO_CFG_LOW
    else:
        # 非 Turbo: 直连 UNET -> ModelSamplingSD3
        prompt["104"] = {
            "class_type": "ModelSamplingSD3",
            "inputs": {
                "model": ["95", 0],
                "shift": DEFAULT_SHIFT
            }
        }
        prompt["103"] = {
            "class_type": "ModelSamplingSD3",
            "inputs": {
                "model": ["96", 0],
                "shift": DEFAULT_SHIFT
            }
        }

        steps_high = DEFAULT_STEPS_HIGH
        steps_low = DEFAULT_STEPS_LOW
        split_step = DEFAULT_SPLIT_STEP
        cfg_high = DEFAULT_CFG_HIGH
        cfg_low = DEFAULT_CFG_LOW

    # --- KSamplerAdvanced (Stage 1: 高噪声) ---
    # 对应工作流节点 86: start=0, end=split_step, return_with_leftover_noise="enable"
    prompt["86"] = {
        "class_type": "KSamplerAdvanced",
        "inputs": {
            "model": ["104", 0],
            "positive": ["98", 0],
            "negative": ["98", 1],
            "latent_image": ["98", 2],
            "add_noise": "enable",
            "noise_seed": seed,
            "steps": steps_high,
            "cfg": cfg_high,
            "sampler_name": "euler",
            "scheduler": "simple",
            "start_at_step": 0,
            "end_at_step": split_step,
            "return_with_leftover_noise": "enable"
        }
    }

    # --- KSamplerAdvanced (Stage 2: 低噪声) ---
    # 对应工作流节点 85: start=split_step, end=steps_high, return_with_leftover_noise="disable"
    prompt["85"] = {
        "class_type": "KSamplerAdvanced",
        "inputs": {
            "model": ["103", 0],
            "positive": ["98", 0],
            "negative": ["98", 1],
            "latent_image": ["86", 0],
            "add_noise": "disable",
            "noise_seed": 0,
            "steps": steps_low,
            "cfg": cfg_low,
            "sampler_name": "euler",
            "scheduler": "simple",
            "start_at_step": split_step,
            "end_at_step": steps_high,
            "return_with_leftover_noise": "disable"
        }
    }

    # --- VAE Decode ---
    prompt["87"] = {
        "class_type": "VAEDecode",
        "inputs": {
            "samples": ["85", 0],
            "vae": ["90", 0]
        }
    }

    # --- 视频合成 ---
    prompt["94"] = {
        "class_type": "CreateVideo",
        "inputs": {
            "images": ["87", 0],
            "fps": fps,
            "bit_depth": 8
        }
    }

    # --- 视频输出 ---
    prompt["108"] = {
        "class_type": "SaveVideo",
        "inputs": {
            "video": ["94", 0],
            "filename_prefix": SAVEVIDEO_PREFIX,
            "format": "auto",
            "codec": "auto"
        }
    }

    return prompt


# ================= API 交互 =================

def submit_prompt(prompt):
    """提交 prompt 到 ComfyUI API，返回 prompt_id"""
    data = json.dumps({"prompt": prompt}).encode("utf-8")
    req = urllib.request.Request(
        f"{COMFYUI_SERVER}/prompt",
        data=data,
        headers={"Content-Type": "application/json"},
    )
    response = json.loads(urllib.request.urlopen(req).read())
    prompt_id = response.get("prompt_id")
    if not prompt_id:
        raise RuntimeError(f"提交失败: {response}")
    return prompt_id


def wait_for_completion(prompt_id, poll_interval=3):
    """
    轮询等待 ComfyUI 任务完成。
    返回 outputs dict。
    """
    print(f"任务已提交 (ID: {prompt_id})，正在渲染视频 ", end="", flush=True)
    while True:
        try:
            url = f"{COMFYUI_SERVER}/history/{prompt_id}"
            req = urllib.request.Request(url)
            history = json.loads(urllib.request.urlopen(req).read())

            if prompt_id in history:
                print(" 渲染完成!")
                outputs = history[prompt_id].get("outputs", {})
                return outputs
        except Exception:
            pass
        print(".", end="", flush=True)
        time.sleep(poll_interval)


def collect_video_files(outputs):
    """
    从 outputs 中提取生成的视频文件。
    
    SaveVideo 使用 filename_prefix="video/Wan2.2_i2v"，
    因此视频实际保存在 output/video/ 子目录下。
    
    ComfyUI API 历史返回格式有多种情况：
    1. {"filename": "Wan2.2_i2v_00001.mp4", "subfolder": "video", "type": "output"}
    2. {"filename": "video/Wan2.2_i2v_00001.mp4", "subfolder": "", "type": "output"}
    
    本函数兼容多种格式，最终返回相对于 COMFYUI_OUTPUT_DIR 的路径。
    同时也回退检查文件系统，确保能找到已生成的文件。
    """
    files = []
    
    # 打印原始 outputs 用于调试
    print(f"[debug] outputs keys: {list(outputs.keys())}")
    for node_id, node_output in outputs.items():
        print(f"[debug] node {node_id} keys: {list(node_output.keys())}")
    
    for node_id, node_output in outputs.items():
        # 检查 "videos"、"video"、"images" 多种可能的 key
        for key in ("videos", "video", "images", "gifs"):
            if key in node_output:
                items = node_output[key]
                for v in items:
                    filename = v.get("filename", "")
                    subfolder = v.get("subfolder", "")
                    if subfolder:
                        # 格式1: filename 不含路径，subfolder 有值
                        combined = f"{subfolder}/{filename}"
                    elif "/" in filename or "\\" in filename:
                        # 格式2: filename 已经包含子目录
                        combined = filename
                    else:
                        # 兜底: 根据我们的 prefix 加 video/ 子目录
                        combined = f"video/{filename}"
                    if combined not in files:
                        files.append(combined)
    
    # 如果还是没找到文件，尝试直接扫描 output/video/ 目录
    if not files:
        video_dir = os.path.join(COMFYUI_OUTPUT_DIR, "video")
        if os.path.exists(video_dir):
            existing = [f for f in os.listdir(video_dir) if f.endswith(".mp4")]
            if existing:
                print(f"[回退扫描] 在 {video_dir} 发现视频文件: {existing}")
                files = [f"video/{f}" for f in existing]
    
    return files


# ================= 主函数 =================

def generate_video(
    image_path,
    prompt_text,
    seed=None,
    width=DEFAULT_WIDTH,
    height=DEFAULT_HEIGHT,
    duration=5,
    fps=DEFAULT_FPS,
    enable_turbo=True,
):
    """
    主函数：上传图片 → 构建 I2V 工作流 → 提交 → 等待 → 返回视频文件列表。
    
    参数:
      image_path: 输入图片路径（可以是任何位置，会自动上传到 ComfyUI）
      prompt_text: 视频描述提示词
      seed: 随机种子
      width/height: 视频尺寸（默认 640x320 匹配工作流）
      duration: 视频时长（秒）
      fps: 帧率
      enable_turbo: 是否启用 4-step LoRA 加速（默认启用，匹配工作流）
    
    返回: 视频文件路径列表（相对于 COMFYUI_OUTPUT_DIR，如 "video/Wan2.2_i2v_00001.mp4"）
    """
    # 1. 上传图片到 ComfyUI
    image_filename, success = upload_image_to_comfyui(image_path)
    if not success:
        print("[错误] 图片上传失败!")
        return []

    # 2. 构建 prompt
    print(f"提示词: {prompt_text}")
    print(f"尺寸: {width}x{height}, 时长: {duration}s, FPS: {fps}")
    if seed:
        print(f"种子: {seed}")
    print(f"Turbo 模式: {'启用' if enable_turbo else '关闭'}")

    prompt = build_i2v_prompt(
        image_filename=image_filename,
        prompt_text=prompt_text,
        seed=seed,
        width=width,
        height=height,
        duration=duration,
        fps=fps,
        enable_turbo=enable_turbo,
    )

    # 3. 提交
    prompt_id = submit_prompt(prompt)

    # 4. 等待完成
    outputs = wait_for_completion(prompt_id)

    # 5. 收集结果
    video_files = collect_video_files(outputs)

    if video_files:
        print(f"\n✅ 成功生成 {len(video_files)} 个视频:")
        for f in video_files:
            full_path = os.path.join(COMFYUI_OUTPUT_DIR, f)
            print(f"   📁 {full_path}")
    else:
        print("\n⚠️  未找到生成的视频文件")

    return video_files


# ================= 命令行入口 =================
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="调用 ComfyUI Image_to_Video (Wan2.2) 工作流生成视频",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s --image "F:/ComfyUI/output/shot_01.png" --prompt "a cat walking"
  %(prog)s --image "test.png" --prompt "sunset beach" --width 640 --height 320 --duration 5
  %(prog)s --image "test.png" --prompt "dance" --no-turbo
        """,
    )
    parser.add_argument("--image", required=True, help="输入图片路径")
    parser.add_argument("--prompt", required=True, help="视频描述提示词")
    parser.add_argument("--width", type=int, default=DEFAULT_WIDTH, help=f"视频宽度 (默认: {DEFAULT_WIDTH})")
    parser.add_argument("--height", type=int, default=DEFAULT_HEIGHT, help=f"视频高度 (默认: {DEFAULT_HEIGHT})")
    parser.add_argument("--seed", type=int, default=None, help="随机种子")
    parser.add_argument("--duration", type=float, default=5, help="视频时长秒 (默认: 5)")
    parser.add_argument("--fps", type=int, default=DEFAULT_FPS, help=f"帧率 (默认: {DEFAULT_FPS})")
    parser.add_argument("--no-turbo", action="store_true", help="关闭 4-step LoRA 加速")

    args = parser.parse_args()

    if args.seed is None:
        args.seed = random.randint(1, 99999999999)

    generate_video(
        image_path=args.image,
        prompt_text=args.prompt,
        seed=args.seed,
        width=args.width,
        height=args.height,
        duration=args.duration,
        fps=args.fps,
        enable_turbo=not args.no_turbo,
    )
