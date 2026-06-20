# 📖 Story to AI Video (故事转 AI 视频)

> 输入故事文本，AI 自动分析生成分镜、图片、视频、多角色配音，最终合成完整叙事视频。

## 🚀 功能概览

| 功能 | 说明 |
|------|------|
| **📝 AI 分析故事** | 调用 DeepSeek AI 自动将故事文本拆分为分镜，生成场景描述、图片提示词、配音文本 |
| **🖼️ 图片生成** | 调用 ComfyUI (Z-Image-Turbo) 为每个分镜生成高质量图片 |
| **🎬 视频生成** | 调用 ComfyUI (Wan2.2 I2V) 将图片转为动态视频 |
| **🎙️ 多角色配音** | 基于 CosyVoice 引擎，智能分配男声/女声/方言声线，给不同角色配音 |
| **🔗 音视频合并** | 自动对齐配音与视频时长（变速/循环），合并为完整视频 |
| **⚡ 一键生成** | 全流程自动化：分析 → 图片 → 视频 → 配音 → 合并 → 最终合成 |

## 🏗️ 系统架构

```
┌─────────────┐     ┌─────────────────────────────────────┐
│  Web 前端    │     │       Flask Python API (app.py)      │
│  (HTML/JS)  │◄───►│                                      │
│             │     │  ┌───────────────────────────────────┐│
│  index.html │     │  │  storyboard.py → 分镜分析         ││
│             │     │  │  text_to_image.py → 图片生成       ││
│             │     │  │  image_to_video.py → 视频生成      ││
│             │     │  │  audio_dubbing.py → 多角色配音     ││
│             │     │  └───────────────────────────────────┘│
└─────────────┘     └──────────┬──────────────────────────┘
                               │ POST /prompt
                               ▼
                    ┌─────────────────────┐
                    │  ComfyUI Server      │
                    │  (http://127.0.0.1:8188) │
                    │                      │
                    │  Text_to_Image.json   │
                    │  Image_to_Video.json  │
                    │  CosyVoice 配音       │
                    └─────────────────────┘
```

## 📁 项目结构

```
AIVideos/
├── app.py                  # Flask Web 应用主入口 + API 路由
├── config_loader.py        # 公共配置加载器 (YAML)
├── public_config.yaml      # 公共配置文件
├── private_config.yaml     # 私有配置 (API Key)
├── story.txt               # 输入故事文件
├── text_to_image.py        # ComfyUI 图片生成模块
├── image_to_video.py       # ComfyUI 视频生成模块
├── audio_dubbing.py        # 多角色配音引擎 (CosyVoice)
├── storyboard.py           # 分镜分析模块
├── chapter_to_json.py      # 批量对话提取工具
├── main.py                 # 纯配音命令行工具 (旧版)
├── templates/
│   └── index.html          # Web 前端界面
└── storyboard_output/      # 输出目录（图片、视频、配音、合成视频）
```

## ⚙️ 配置

### 1. 私有配置 (`private_config.yaml`)

```yaml
deepseek:
  api: "sk-your-deepseek-api-key-here"
```

### 2. 公共配置 (`public_config.yaml`)

```yaml
comfyui:
  server: "http://127.0.0.1:8188"
  output_dir: "F:/ComfyUI/output"
  input_dir: "F:/ComfyUI/input"

workflows:
  text_to_image: "F:/ComfyUI/user/default/workflows/Text_to_Image.json"
  image_to_video: "F:/ComfyUI/user/default/workflows/Image_to_Video.json"

output_dir: "storyboard_output"

image:
  width: 1280
  height: 720
  steps: 8

video:
  width: 640
  height: 320
  fps: 16
  duration: 5
```

> 所有配置项见 `public_config.yaml`，修改后需重启应用生效。

## 🛠️ 前置依赖

| 依赖 | 版本要求 | 说明 |
|------|----------|------|
| Python | >= 3.10 | 运行 Flask 后端 |
| FFmpeg | 已安装 | 音视频处理（需在 PATH 中） |
| ComfyUI | 已部署 | AI 图片/视频生成引擎 |
| DeepSeek API | 有效 Key | 故事分析、配音文本生成 |

### Python 依赖

```bash
pip install flask flask-cors pyyaml openai
```

### ComfyUI 节点需求

- **Text to Image** — Z-Image-Turbo 工作流
- **Image to Video** — Wan2.2 I2V 工作流
- **CosyVoice** — FL_CosyVoice3 系列节点（配音）

## 🔧 使用方法

### 启动 Web 应用

```bash
python app.py
```

访问 `http://127.0.0.1:5000`

### 方法一：一键生成

1. 在文本框中输入或粘贴故事
2. 点击 **⚡ 一键生成全部**
3. 等待全流程自动完成：分析故事 → 生成图片 → 生成视频 → 配音 → 合并 → 最终合成

### 方法二：分步操作

1. 输入故事 → 点击 **🔍 分析故事**
2. 编辑提示词（可选）
3. 逐分镜点击操作：
   - 🖼️ **生成图片** → 🎬 **生成视频**
   - 🎙️ **配音** → 🔗 **合并音视频**
4. 所有分镜完成后 → 🎬 **生成完整 AI 视频**

### 命令行生成图片

```bash
python text_to_image.py "一只可爱的猫在公园里散步" --width 1280 --height 720
```

### 命令行生成视频

```bash
python image_to_video.py --image "shot_01.png" --prompt "a cat walking" --duration 5
```

### 命令行配音（旧版多角色）

```bash
python chapter_to_json.py     # 先提取对话
python main.py                 # 再生成配音
```

## 🧩 API 接口

| 端点 | 方法 | 说明 |
|------|------|------|
| `/` | GET | Web 前端页面 |
| `/api/health` | GET | 健康检查 |
| `/api/story/analyze` | POST | 分析故事生成分镜 |
| `/api/shots` | GET | 获取分镜列表及生成状态 |
| `/api/shots/update` | POST | 更新单个分镜字段 |
| `/api/generate/image` | POST | 生成指定分镜的图片 |
| `/api/generate/video` | POST | 生成指定分镜的视频 |
| `/api/generate/status` | GET | 查询所有分镜生成进度 |
| `/api/generate/batch` | POST | 一键生成全部 |
| `/api/generate/batch-status` | GET | 一键生成进度查询 |
| `/api/dubbing/shot` | POST | 为指定分镜生成配音 |
| `/api/dubbing/status` | GET | 配音状态查询 |
| `/api/merge/shot` | POST | 合并单个分镜音视频 |
| `/api/merge/all` | POST | 合并全部分镜为完整视频 |
| `/api/merge/status` | GET | 合并进度查询 |
| `/api/settings` | GET/POST | 读取/保存生成参数 |

## ⚠️ 常见问题

### 最终合成视频播放时卡顿/画面冻结

各分镜视频由 ComfyUI 独立生成，编码参数可能不同。系统已自动使用 `-filter_complex concat` 统一重新编码解决此问题。如果仍有问题，可以手动重新合成。

### 一键生成提示"全部完成"但实际还在生成

刷新页面后再次点击一键生成即可，系统会检测故事文本是否变化，自动重新执行未完成的步骤。

### 配音生成失败

- 确保 ComfyUI 已安装 CosyVoice 相关节点（FL_CosyVoice3 系列）
- 确保 ComfyUI 的 `input/man/` 和 `input/girls/` 目录下有配音音源文件

### API Key 报错

检查 `private_config.yaml` 中的 `deepseek.api` 配置是否正确。

## 📜 许可证

MIT License
