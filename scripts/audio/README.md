# Game audio generation

Music and sound effects are generated offline with **Stable Audio 3 Small SFX** by Stability AI and committed as ordinary audio files. The game never loads or calls the model; these scripts are optional tooling for regenerating or extending the set.

Powered by Stability AI.

## Provenance and licensing

| Item | Terms | In this repository |
| --- | --- | --- |
| Stable Audio 3 Small SFX weights | [Stability AI Community License](https://stability.ai/license) | Not included; download separately from Hugging Face |
| T5Gemma text encoder (bundled with the weights) | [Gemma Terms of Use](https://ai.google.dev/gemma/terms) | Not included |
| `stable-audio-3` inference library | MIT, © 2026 Stability AI | Not included; cloned into `.tools/` by the setup below |
| Generated audio files | Outputs of the model | Included as game assets |

Under the Community License, model outputs are excluded from "Derivative Works" and belong to the user who generated them to the extent permitted by law; Gemma's terms likewise claim no rights in outputs. The generated audio is used non-commercially in this open-source project. Its use must still follow Stability AI's Acceptable Use Policy, and the Community License forbids using the outputs to create or improve a foundational generative AI model. Anyone reusing these files should keep this note. Copyright protection for AI-generated audio varies by jurisdiction.

`sound_manifest.json` records the exact prompt and seed of every sound, so each file can be traced back to the generation that produced it. Not every file comes from the model: the new-order, order-expired and bad-review chimes are square-wave notes synthesised in code (`chiptune.py`), because the model rendered those simple cues as noise in three rounds; burger assembly reuses the approved board-placement sound (`pick` is `synth_*` or `reuse` in the manifest).

## Pipeline

1. `generate_sounds.py`: generates raw candidates into `art-candidates/audio-v1/raw/<id>/<seed>.wav` and skips existing files.
2. `process_sounds.py`: de-combs every clip (removes the decoder's faint steady whine at multiples of 172.27 Hz, see `decomb.py`), low-passes at 16 kHz, trims one-shots, matches loudness, and builds `art-candidates/audio-v1/index.html` for listening.
3. `export_sounds.py`: writes the picks to `cocos-kitchen/assets/resources/audio/` with `index.json`; music loops at the point where the piece best repeats its opening, and textures loop over their steady span with an equal-power crossfade.

Settled design choices: 8-bit chiptune for UI, orders, serving, result jingles and music; unprocessed realistic effects for cooking, fire and dishes. Chopping plays one knife strike when the chop animation reaches its strike frame (the board flash; 2.5 per second per chef), using strikes cut from the chopping takes and filtered to reject boomy ones. Washing uses a tamed solo loop; two chefs washing together (twice as fast) switches to two different takes panned left and right at 1.5× tempo.

## Setup (Intel or Apple Silicon macOS, CPU)

Intel Macs cannot install the library's pinned `torch==2.7.1`; `sa3_local.py` adds two small compatibility shims so the pinned commit runs on torch 2.2.2.

```bash
git clone https://github.com/Stability-AI/stable-audio-3.git .tools/stable-audio-3
git -C .tools/stable-audio-3 checkout 779434a908193105335fd8d833418603625b2859
uv venv -p 3.12 .tools/audio-venv
VIRTUAL_ENV=.tools/audio-venv uv pip install "torch==2.2.2" "torchaudio==2.2.2" "numpy<2" "transformers>=4.53,<5" einops einops-exts safetensors tqdm huggingface-hub soundfile packaging scipy
VIRTUAL_ENV=.tools/audio-venv uv pip install --no-deps -e .tools/stable-audio-3
```

Point `SA3_MODEL_DIR` at the downloaded `stabilityai/stable-audio-3-small-sfx` folder (default `/Volumes/T7/AI-Models/stable-audio-3-small-sfx`). On a 2020 Intel i5 with 16 GB, a short effect takes about 8–15 s and peak memory is about 6 GB.

---

## 中文说明

# 游戏音频生成

游戏的音乐和音效用 Stability AI 的 **Stable Audio 3 Small SFX** 在本地离线生成，以普通音频文件提交到仓库。游戏运行时不会加载或调用这个模型；这里的脚本只是可选工具，用于重新生成或扩充音效。

Powered by Stability AI.

## 来源与许可

| 内容 | 条款 | 仓库中是否包含 |
| --- | --- | --- |
| Stable Audio 3 Small SFX 模型权重 | [Stability AI Community License](https://stability.ai/license) | 不包含，需另行从 Hugging Face 下载 |
| T5Gemma 文本编码器（随权重分发） | [Gemma 使用条款](https://ai.google.dev/gemma/terms) | 不包含 |
| `stable-audio-3` 推理库 | MIT，© 2026 Stability AI | 不包含，按下方步骤克隆到 `.tools/` |
| 生成的音频文件 | 模型输出 | 作为游戏素材包含在仓库中 |

按照 Community License，模型输出不属于“衍生作品”，在法律允许的范围内归生成者所有；Gemma 条款同样不主张对输出的权利。本项目为开源项目，非商业使用这些生成音频。使用时仍须遵守 Stability AI 的可接受使用政策；Community License 也禁止用这些输出创建或改进基础生成式 AI 模型。复用这些文件时请保留本说明。AI 生成音频能否受著作权保护，各地法律规定不同。

`sound_manifest.json` 记录了每个声音的完整提示词和随机种子，每个文件都能追溯到对应的生成。并非所有文件都来自模型：新订单、订单过期、差评三个提示音是用代码合成的方波音符（`chiptune.py`），因为模型连续三轮都把这类简单提示音生成成了噪声；组装汉堡复用了已选的“食材放案板”声音（清单里 `pick` 为 `synth_*` 或 `reuse`）。

## 流程

1. `generate_sounds.py`：把原始候选生成到 `art-candidates/audio-v1/raw/<id>/<seed>.wav`，已存在的文件会跳过。
2. `process_sounds.py`：先去除解码器残留的微弱持续高频声（172.27Hz 整数倍的纯音，见 `decomb.py`），再做 16kHz 低通、裁剪短音效首尾、统一响度，最后生成试听页 `art-candidates/audio-v1/index.html`。
3. `export_sounds.py`：把选定的声音写入 `cocos-kitchen/assets/resources/audio/` 并生成 `index.json`。音乐在最接近开头重复的位置循环，底噪类声音取响度稳定的一段，用等功率交叉淡化接成循环。

已定的设计：界面、订单、出餐、结算乐句和音乐用 8-bit 芯片音；烹饪、火、碗碟用未经复古处理的真实音效。切菜在切菜动画到达落刀帧（案板闪一下）时播一声（每位厨师每秒 2.5 刀），刀声从切菜录音中逐刀切出，并剔除发闷的。洗碗用处理过的单人循环；两人一起洗时速度翻倍，切换为两段不同录音左右分开、1.5 倍速播放。

## 环境（Intel 或 Apple Silicon 的 macOS，CPU 运行）

Intel Mac 装不了推理库固定的 `torch==2.7.1`，`sa3_local.py` 加了两处兼容处理，使固定版本能在 torch 2.2.2 上运行。安装命令见上方英文部分。`SA3_MODEL_DIR` 指向下载好的 `stabilityai/stable-audio-3-small-sfx` 文件夹，默认是 `/Volumes/T7/AI-Models/stable-audio-3-small-sfx`。在 2020 款 Intel i5、16GB 内存上，一个短音效约 8–15 秒，内存峰值约 6GB。
