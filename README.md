# 📖 Story to AI Video (故事转 AI 视频)

> 输入故事文本，AI 自动分析生成分镜、图片、视频、多角色配音，最终合成完整叙事视频。

## 🚀 功能概览

| 功能 | 说明 |
|------|------|
| **📝 AI 分析故事** | 调用 DeepSeek AI 自动将故事文本拆分为分镜，生成场景描述、图片提示词、配音文本 |
| **🎨 多样化艺术风格** | 内置 30+ 种艺术风格预设（迪士尼、油画、水墨、赛博朋克、吉卜力、日系动漫等），一键切换 |
| **🖼️ 图片生成** | 调用 ComfyUI (Z-Image-Turbo) 为每个分镜生成高质量图片 |
| **🎬 视频生成** | 调用 ComfyUI (Wan2.2 I2V) 将图片转为动态视频，支持 Turbo 4 步快速生成 |
| **🎙️ 多角色配音** | 基于 CosyVoice 引擎，40+ 种声线，智能按性别/性格/方言匹配角色配音 |
| **🎙️ 叙事人声选择** | 支持在设置中选择叙事人声音色（如中文男声、中文女声、萝莉、御姐等 10+ 种声线） |
| **🔗 视频分镜首尾帧相连** | 可选的帧连贯模式：只生成第一张图片，后续分镜自动提取上一视频的尾帧作为输入，实现画面无缝过渡 |
| **🔗 音视频合并** | 自动对齐配音与视频时长（变速/循环），合并为完整视频 |
| **⚡ 一键生成** | 全流程自动化：分析 → 图片 → 视频 → 配音 → 合并 → 最终合成 |
| **✏️ 分镜编辑** | 支持在 Web 界面直接编辑分镜的提示词、配音文本等 |
| **🔄 重新生成** | 不满意可更换种子重新生成指定分镜的图片/视频 |

### 🎨 内置艺术风格（30+ 种）

| 风格分类 | 包含风格 |
|---------|---------|
| 🎨 **经典绘画** | 迪士尼风格、油画、水彩、素描/炭笔、粉彩、印象派、超现实主义、立体主义、文艺复兴 |
| 🌏 **东方艺术** | 浮世绘（日式版画）、中国水墨风格 |
| 🧸 **数字潮玩** | 盲盒/泡泡玛特、低多边形（Low Poly）、体素艺术（方块风）、黏土动画、虚幻5渲染、概念艺术 |
| 🎥 **摄影影视** | 电影剧照、微距摄影、航拍、长曝光、胶片复古、赛博朋克、蒸汽朋克 |
| 🎌 **二次元插画** | 日系动漫（新海诚风）、吉卜力风格、美漫/漫画、儿童绘本、扁平化矢量、复古海报 |
| 💎 **现代设计** | 波普艺术、极简主义、蒸汽波/故障艺术、孟菲斯风格、等距视角（2.5D） |

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
│   └── index.html          # Web 前端界面（暗色主题）
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

# AI 分析参数
ai:
  chunk_max_length: 3000      # 故事文本分块大小
  temperature: 0.3            # 故事分析 AI 温度
  max_tokens: 4096
  dubbing_temperature: 0.1    # 配音 AI 温度

# 图片参数
image:
  width: 960
  height: 540
  steps: 8

# 视频参数
video:
  width: 960
  height: 540
  fps: 16
  duration: 5

# Turbo 模式（4 步 LoRA 加速）
turbo:
  steps_high: 4
  steps_low: 4
  split_step: 2
  cfg_high: 1.0
  cfg_low: 1.0

# 配音参数
audio_dubbing:
  model_version: "Fun-CosyVoice3-0.5B"

defaults:
  shots_count: 10              # 默认分镜数
```

> 所有配置项见 `public_config.yaml`，修改后需重启应用生效。

## 🛠️ 前置依赖

| 依赖 | 版本要求 | 说明 |
|------|----------|------|
| Python | >= 3.10 | 运行 Flask 后端 |
| FFmpeg | 已安装 | 音视频处理（需在 PATH 中） |
| ComfyUI | 已部署 | AI 图片/视频/配音生成引擎 |
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

Web 界面提供：
- 📝 故事文本输入区
- 🎨 30+ 种艺术风格下拉选择
- ⚙️ 图片/视频参数调节面板（宽高、步数、种子、帧率、时长）
- 📋 分镜列表与状态可视化
- 🔄 单个分镜独立操作（生成图片/视频/配音/合并/重新生成）

### 方法一：一键生成

1. 在文本框中输入或粘贴故事
2. 选择艺术风格（可选，默认迪士尼风格）
3. 点击 **⚡ 一键生成全部**
4. 等待全流程自动完成：分析故事 → 生成图片 → 生成视频 → 配音 → 合并 → 最终合成

### 方法二：分步操作

1. 输入故事 → 选择风格 → 点击 **🔍 分析故事**
2. 编辑分镜的提示词或配音文本（可选）
3. 逐分镜点击操作：
   - 🖼️ **生成图片** → 🎬 **生成视频**
   - 🎙️ **配音** → 🔗 **合并音视频**
4. 不满意可点击 **🔄 重新生成** 更换种子
5. 所有分镜完成后 → 🎬 **生成完整 AI 视频**

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

### 命令行分镜生成

```bash
python storyboard.py --style "吉卜力风格" --shots 8 --width 1024 --height 576
```

## 🎙️ 多角色配音与叙事人声

系统采用 **CosyVoice 引擎** 实现智能配音：

- **自动角色识别** — AI 分析故事中的人物角色，提取对话文本
- **按性别/性格匹配声线** — 男性角色自动匹配男声、女性角色匹配女声，支持方言和性格特征
- **叙事人声选择** — 在 Web 设置面板中可选择叙事人声音色（中文男声、中文女声、萝莉、御姐等 10+ 种声线），该设置会在批量生成配音时自动使用
- **API 扩展** — 可在 `audio_dubbing.py` 的 `NARRATOR_VOICE_MAP` 中自由添加新的叙事人声映射

## 🔗 视频分镜首尾帧相连

这是一个可选的**帧连贯模式**，用于实现分镜之间的画面无缝过渡：

- **开启方式** — 在 Web 界面的「生成参数设置」中勾选「🔗 视频分镜首尾帧相连」复选框
- **工作原理**：
  1. 只生成第一个分镜的图片（后续分镜跳过图片生成步骤）
  2. 使用第一张图片生成第一个分镜的视频
  3. 自动提取第一个视频的最后一帧作为图片
  4. 将提取的尾帧作为第二个分镜的输入图片，生成第二个视频
  5. 依次类推，直到最后一个分镜
- **效果** — 每个分镜的视频都以上一分镜视频的最后一帧作为起点，实现画面内容的连续过渡，避免分镜切换时的画面跳跃
- **不影响现有功能** — 该开关默认关闭，关闭时行为与原有逻辑完全一致

## 🧩 API 接口

| 端点 | 方法 | 说明 |
|------|------|------|
| `/` | GET | Web 前端页面 |
| `/api/health` | GET | 健康检查 |
| `/api/story/analyze` | POST | 分析故事生成分镜（支持指定风格和分镜数） |
| `/api/styles` | GET | 获取所有可用的艺术风格列表 |
| `/api/shots` | GET | 获取分镜列表及生成状态 |
| `/api/shots/update` | POST | 更新单个分镜字段 |
| `/api/generate/image` | POST | 生成指定分镜的图片（可指定宽高、步数、种子） |
| `/api/generate/video` | POST | 生成指定分镜的视频（可指定种子） |
| `/api/generate/status` | GET | 查询所有分镜生成进度 |
| `/api/generate/batch` | POST | 一键生成全部 |
| `/api/generate/batch-status` | GET | 一键生成进度查询 |
| `/api/dubbing/shot` | POST | 为指定分镜生成配音 |
| `/api/dubbing/status` | GET | 配音状态查询 |
| `/api/merge/shot` | POST | 合并单个分镜音视频 |
| `/api/merge/all` | POST | 合并全部分镜为完整视频 |
| `/api/merge/status` | GET | 合并进度查询 |
| `/api/settings` | GET/POST | 读取/保存生成参数 |

## 📜 许可证

MIT License
