"""
text_to_image.py - 调用 ComfyUI Text_to_Image (Z-Image-Turbo) 工作流生成图片

参考 main.py 的方式：
  1. 加载并转换 workflow JSON 为 API prompt 格式
  2. 通过 POST /prompt 提交
  3. 通过 GET /history/{prompt_id} 轮询等待完成
  4. 获取生成的图片文件路径

用法：
  python text_to_image.py "一只可爱的猫"                  # 基础用法
  python text_to_image.py "猫" --width 768 --height 768   # 自定义尺寸
  python text_to_image.py "猫" --seed 12345 --steps 4     # 自定义种子和步数
"""

import json
import urllib.request
import time
import os
import sys
import argparse
import random


# ================= 配置区（从 public_config.yaml 加载） =================
from config_loader import get

COMFYUI_SERVER = get("comfyui.server", "http://127.0.0.1:8188")
WORKFLOW_FILE = get("workflows.text_to_image", r"F:\ComfyUI\user\default\workflows\Text_to_Image.json")
COMFYUI_OUTPUT_DIR = get("comfyui.output_dir", r"F:\ComfyUI\output")

# 默认图片参数
DEFAULT_WIDTH = get("image.width", 960)
DEFAULT_HEIGHT = get("image.height", 540)
DEFAULT_STEPS = get("image.steps", 8)


# ================= 工作流转换引擎 =================
def _parse_link_array(arr):
    """解析 ComfyUI 数组格式的 link: [id, origin_id, origin_slot, target_id, target_slot, type]"""
    return {
        "id": arr[0],
        "origin_id": arr[1],
        "origin_slot": arr[2],
        "target_id": arr[3],
        "target_slot": arr[4],
    }


# 已知的 ComfyUI 内置节点中，widget_values 包含的"隐式控件"
# （这些控件不体现在 inputs 列表中，但占用 widget_values 位置）
# 格式：{ class_type: [ (隐式控件前的显式控件名列表) ] }
# 例如 KSampler: seed(input) → control_after_generate(隐含) → steps(input) → ...
IMPLICIT_WIDGET_AFTER_INPUT = {
    "KSampler": {
        "seed": "control_after_generate",
    },
    "KSamplerAdvanced": {
        "seed": "control_after_generate",
    },
}


def workflow_to_prompt(workflow, overrides=None):
    """
    将 ComfyUI workflow JSON 格式转换为 API prompt 格式。

    - 此 workflow 使用 subgraph 结构
    - API prompt 格式：{ node_id: { "class_type": "...", "inputs": { ... } } }
    """
    if overrides is None:
        overrides = {}

    # --- Step 1: 提取所有实际执行节点 ---
    subgraph = workflow["definitions"]["subgraphs"][0]
    internal_nodes = [n for n in subgraph.get("nodes", []) if n["id"] not in (-10, -20)]

    # 顶层节点：排除 MarkdownNote 和 subgraph 代理节点
    external_nodes = [
        n for n in workflow.get("nodes", [])
        if n["type"] not in ("MarkdownNote",) and n["id"] != 57
    ]

    all_nodes = internal_nodes + external_nodes

    # --- Step 2: 构建 link 查找表 ---
    link_map = {}
    for arr in workflow.get("links", []):
        info = _parse_link_array(arr)
        link_map[info["id"]] = info
    for d in subgraph.get("links", []):
        link_map[d["id"]] = {
            "id": d["id"],
            "origin_id": d["origin_id"],
            "origin_slot": d["origin_slot"],
            "target_id": d["target_id"],
            "target_slot": d["target_slot"],
        }

    # --- Step 3: 转换每个节点 ---
    prompt = {}
    for node in all_nodes:
        node_id = str(node["id"])
        node_type = node["type"]

        inputs = {}
        widget_values = node.get("widgets_values", [])
        widget_idx = 0

        implicit_map = IMPLICIT_WIDGET_AFTER_INPUT.get(node_type, {})

        for inp in node.get("inputs", []):
            iname = inp.get("name", "")
            if not iname:
                iname = inp.get("label", "")

            link_id = inp.get("link")
            has_link = (link_id is not None)

            if has_link:
                link_info = link_map.get(link_id)
                if link_info:
                    origin_id = link_info["origin_id"]
                    if origin_id == -10:
                        # 来自子图外部输入 → 用 widget 默认值
                        if widget_idx < len(widget_values):
                            inputs[iname] = widget_values[widget_idx]
                            widget_idx += 1
                        # 检查该 input 后面是否有隐式控件，有则跳过
                        if iname in implicit_map:
                            widget_idx += 1
                    else:
                        # 普通节点间连接
                        inputs[iname] = [str(origin_id), link_info["origin_slot"]]
                else:
                    # link 找不到 → 用 widget 值
                    if widget_idx < len(widget_values):
                        inputs[iname] = widget_values[widget_idx]
                        widget_idx += 1
                    if iname in implicit_map:
                        widget_idx += 1
            else:
                # 独立控件（无 link）
                if widget_idx < len(widget_values):
                    inputs[iname] = widget_values[widget_idx]
                    widget_idx += 1
                if iname in implicit_map:
                    widget_idx += 1

        prompt[node_id] = {
            "class_type": node_type,
            "inputs": inputs,
        }

    # --- Step 4: 修复 SaveImage 的图片输入 ---
    # SaveImage (9) 原本连接 subgraph 代理节点 (57)，
    # 需要改为指向实际的 VAEDecode (8) 输出
    if "9" in prompt and prompt["9"]["class_type"] == "SaveImage":
        for info in link_map.values():
            if info["target_id"] == -20 and info["origin_id"] != -10:
                prompt["9"]["inputs"]["images"] = [str(info["origin_id"]), info["origin_slot"]]
                break

    # --- Step 5: 应用用户覆盖参数 ---
    for nid, override_inputs in overrides.items():
        if nid in prompt:
            prompt[nid]["inputs"].update(override_inputs)

    return prompt


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


def wait_for_completion(prompt_id, poll_interval=2):
    """
    轮询等待 ComfyUI 任务完成。
    返回 outputs dict（节点ID -> 输出信息）。
    """
    print(f"任务已提交 (ID: {prompt_id})，正在渲染图片 ", end="", flush=True)
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


def collect_image_files(outputs):
    """
    从 outputs 中提取所有生成的图片文件路径。
    返回相对于 COMFYUI_OUTPUT_DIR 的文件名列表。
    """
    files = []
    for node_id, node_output in outputs.items():
        if "images" in node_output:
            for img in node_output["images"]:
                files.append(img["filename"])
    return files


def generate_images(
    prompt_text,
    seed=None,
    width=None,
    height=None,
    steps=None,
):
    """
    主函数：加载工作流 → 设置参数 → 提交 → 等待 → 返回图片文件列表。
    """
    # 使用默认值
    if width is None:
        width = DEFAULT_WIDTH
    if height is None:
        height = DEFAULT_HEIGHT
    if steps is None:
        steps = DEFAULT_STEPS

    # 1. 加载 workflow JSON
    if not os.path.exists(WORKFLOW_FILE):
        print(f"[错误] 找不到工作流文件: {WORKFLOW_FILE}")
        return []

    print(f"正在加载工作流: {WORKFLOW_FILE}")
    with open(WORKFLOW_FILE, "r", encoding="utf-8") as f:
        workflow = json.load(f)

    # 2. 构建可覆盖参数
    # 节点 27 = CLIPTextEncode → text
    # 节点 3  = KSampler → seed, steps + 其他参数使用工作流默认值
    # 节点 13 = EmptySD3LatentImage → width, height, batch_size
    overrides = {
        "27": {"text": prompt_text},
    }
    if seed is not None:
        overrides.setdefault("3", {})["seed"] = seed
    if steps is not None:
        overrides.setdefault("3", {})["steps"] = steps
    if width is not None:
        overrides.setdefault("13", {})["width"] = width
    if height is not None:
        overrides.setdefault("13", {})["height"] = height

    # 3. 转换 workflow 为 API prompt
    print(f"提示词: {prompt_text}")
    if width and height:
        print(f"尺寸: {width}x{height}")
    if steps:
        print(f"步数: {steps}")
    if seed:
        print(f"种子: {seed}")

    prompt = workflow_to_prompt(workflow, overrides)

    # 4. 提交
    prompt_id = submit_prompt(prompt)

    # 5. 等待完成
    outputs = wait_for_completion(prompt_id)

    # 6. 收集结果
    image_files = collect_image_files(outputs)

    if image_files:
        print(f"\n✅ 成功生成 {len(image_files)} 张图片:")
        for f in image_files:
            full_path = os.path.join(COMFYUI_OUTPUT_DIR, f)
            print(f"   📁 {full_path}")
    else:
        print("\n⚠️  未找到生成的图片文件")

    return image_files


# ================= 命令行入口 =================
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="调用 ComfyUI Text_to_Image (Z-Image-Turbo) 工作流生成图片",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s "一只可爱的猫"
  %(prog)s "赛博朋克城市夜景" --width 768 --height 768
  %(prog)s "山水画" --seed 42 --steps 4
  %(prog)s "太空站" --width 1024 --height 576 --steps 6 --seed 12345
        """,
    )
    parser.add_argument("prompt", type=str, help="图片描述提示词（必填）")
    parser.add_argument("--width", type=int, default=None, help=f"图片宽度 (默认: {DEFAULT_WIDTH})")
    parser.add_argument("--height", type=int, default=None, help=f"图片高度 (默认: {DEFAULT_HEIGHT})")
    parser.add_argument("--seed", type=int, default=None, help="随机种子 (默认: 随机)")
    parser.add_argument("--steps", type=int, default=None, help=f"采样步数 (默认: {DEFAULT_STEPS})")

    args = parser.parse_args()

    # 如果未提供 seed，随机生成一个
    if args.seed is None:
        args.seed = random.randint(1, 99999999999)

    generate_images(
        prompt_text=args.prompt,
        seed=args.seed,
        width=args.width,
        height=args.height,
        steps=args.steps,
    )
