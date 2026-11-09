# Game audio generation

Sound effects are generated offline with **Stable Audio 3 Small SFX** by Stability AI and committed as ordinary audio files. The three music loops are composed note by note for this project and synthesised in code (`compose_music.py`, `music_synth.py`); no model is involved in them. The game never loads or calls the model; these scripts are optional tooling for regenerating or extending the set.

Powered by Stability AI.

## Provenance and licensing

| Item | Terms | In this repository |
| --- | --- | --- |
| Stable Audio 3 Small SFX weights | [Stability AI Community License](https://stability.ai/license) | Not included; download separately from Hugging Face |
| T5Gemma text encoder (bundled with the weights) | [Gemma Terms of Use](https://ai.google.dev/gemma/terms) | Not included |
| `stable-audio-3` inference library | MIT, © 2026 Stability AI | Not included; cloned into `.tools/` by the setup below |
| Generated audio files | Outputs of the model | Included as game assets |
| Music: `bgm_menu`, `bgm_service`, `bgm_rush` | Composed and synthesised in code for this project; covered by the project's license | Included, with the code that renders them |

Under the Community License, model outputs are excluded from "Derivative Works" and belong to the user who generated them to the extent permitted by law; Gemma's terms likewise claim no rights in outputs. The generated audio is used non-commercially in this open-source project. Its use must still follow Stability AI's Acceptable Use Policy, and the Community License forbids using the outputs to create or improve a foundational generative AI model. Anyone reusing these files should keep this note. Copyright protection for AI-generated audio varies by jurisdiction.

`sound_manifest.json` records the exact prompt and seed of every sound, so each file can be traced back to the generation that produced it. Not every file comes from the model: the new-order, order-expired and bad-review chimes are square-wave notes synthesised in code (`chiptune.py`), because the model rendered those simple cues as noise in three rounds; burger assembly reuses the approved board-placement sound (`pick` is `synth_*` or `reuse` in the manifest).

## Music

`compose_music.py` holds the three pieces as note lists and renders them with `music_synth.py` (band-limited pulse and triangle waves, soft noise drums). It needs only numpy, scipy, soundfile and ffmpeg, not the model environment. Running it writes the three mp3 files and their `index.json` entries.

- `bgm_menu` "午后小馆": C major, 92 BPM, before the round.
- `bgm_service` "厨房进行曲": a march, 112 BPM. Players found the earlier model-made track noisy (heavy drums, shrill highs), odd and repetitive, so the melody stays at or below A5 with a round lead, the drums stay light, and one bar of oom-pah-oom-pah opens each 71 s loop so the melody enters about 2 s after the start.
- `bgm_rush`: the same march in harmonic minor at 132 BPM with a doubled oom-pah and a soft clock tick, for the last 30 s. Its first 8 bars keep the in-round lead and turn it punchier, so the switch does not sound like a new piece. At 58 s it does not loop during a normal 30 s rush.

Each piece is rendered twice and the second pass kept, so echo tails wrap into the start and the loop is seamless; notes are placed on whole samples so both passes match exactly. `index.json` stores each piece's bar length: the client moves from service to rush on the service's next bar line (cut in 60 ms) and starts the rush at full level, because a crossfade swallowed the rush's first beat and left an audible gap.

## Pipeline

1. `generate_sounds.py`: generates raw candidates into `art-candidates/audio-v1/raw/<id>/<seed>.wav` and skips existing files.
2. `process_sounds.py`: de-combs every clip (removes the decoder's faint steady whine at multiples of 172.27 Hz, see `decomb.py`), low-passes at 16 kHz, trims one-shots, matches loudness, and builds `art-candidates/audio-v1/index.html` for listening.
3. `export_sounds.py`: writes the picks to `cocos-kitchen/assets/resources/audio/` with `index.json`; textures loop over their steady span with an equal-power crossfade. Sounds whose pick is `composed` (the music) are rendered by `compose_music.py` instead.

Settled design choices: 8-bit chiptune for UI, orders, serving, result jingles and the composed music; unprocessed realistic effects for cooking, fire and dishes. Chopping plays one knife strike when the chop animation reaches its strike frame (the board flash; 2.5 per second per chef), using strikes cut from the chopping takes and filtered to reject boomy ones. Washing uses a tamed solo loop; two chefs washing together (twice as fast) switches to two different takes panned left and right at 1.5× tempo.

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

游戏的音效用 Stability AI 的 **Stable Audio 3 Small SFX** 在本地离线生成，以普通音频文件提交到仓库。三首音乐是为本项目逐个音符作曲、再用代码合成的（`compose_music.py`、`music_synth.py`），没有用到模型。游戏运行时不会加载或调用这个模型；这里的脚本只是可选工具，用于重新生成或扩充音效。

Powered by Stability AI.

## 来源与许可

| 内容 | 条款 | 仓库中是否包含 |
| --- | --- | --- |
| Stable Audio 3 Small SFX 模型权重 | [Stability AI Community License](https://stability.ai/license) | 不包含，需另行从 Hugging Face 下载 |
| T5Gemma 文本编码器（随权重分发） | [Gemma 使用条款](https://ai.google.dev/gemma/terms) | 不包含 |
| `stable-audio-3` 推理库 | MIT，© 2026 Stability AI | 不包含，按下方步骤克隆到 `.tools/` |
| 生成的音频文件 | 模型输出 | 作为游戏素材包含在仓库中 |
| 音乐：`bgm_menu`、`bgm_service`、`bgm_rush` | 为本项目用代码作曲并合成，适用本项目的许可 | 包含，渲染它们的代码也在仓库中 |

按照 Community License，模型输出不属于“衍生作品”，在法律允许的范围内归生成者所有；Gemma 条款同样不主张对输出的权利。本项目为开源项目，非商业使用这些生成音频。使用时仍须遵守 Stability AI 的可接受使用政策；Community License 也禁止用这些输出创建或改进基础生成式 AI 模型。复用这些文件时请保留本说明。AI 生成音频能否受著作权保护，各地法律规定不同。

`sound_manifest.json` 记录了每个声音的完整提示词和随机种子，每个文件都能追溯到对应的生成。并非所有文件都来自模型：新订单、订单过期、差评三个提示音是用代码合成的方波音符（`chiptune.py`），因为模型连续三轮都把这类简单提示音生成成了噪声；组装汉堡复用了已选的“食材放案板”声音（清单里 `pick` 为 `synth_*` 或 `reuse`）。

## 音乐

`compose_music.py` 以音符列表的形式写好三首曲子，用 `music_synth.py` 合成（抗锯齿的方波和三角波，加上很轻的噪声鼓）。它只需要 numpy、scipy、soundfile 和 ffmpeg，不需要模型环境。运行后会写出三个 mp3 和它们在 `index.json` 里的条目。

- `bgm_menu`《午后小馆》：C 大调，92 BPM，开局前播放。
- `bgm_service`《厨房进行曲》：进行曲，112 BPM。玩家反映之前模型生成的营业音乐太吵（鼓太重、高音尖）、旋律怪、太重复，所以这首的旋律最高不超过 A5，主旋律音色圆润，鼓很轻。每圈约 71 秒，开头先有一小节“嘭嚓嘭嚓”，旋律在开局约 2 秒后才进来。
- `bgm_rush`：同一首进行曲改成和声小调，132 BPM，“嘭嚓”加倍，再加一个很轻的滴答声，用于最后 30 秒。前 8 小节先保持营业中的主旋律音色，再逐渐变得更有冲劲，所以切换时听起来不像换了一首曲子。全长 58 秒，正常速度下 30 秒的冲刺不会循环。

每首曲子都连续渲染两遍、保留第二遍，让回声余音自然接进开头，循环没有接缝；音符都放在整数采样点上，两遍完全一致。`index.json` 记录每首曲子的小节长度：客户端从营业中切到冲刺时，会等营业中音乐走到下一个小节线，用 60 毫秒收掉，冲刺版以正常音量开始。之前用交叉淡化，冲刺版的第一拍被吞掉，能听出中间断了一下。

## 流程

1. `generate_sounds.py`：把原始候选生成到 `art-candidates/audio-v1/raw/<id>/<seed>.wav`，已存在的文件会跳过。
2. `process_sounds.py`：先去除解码器残留的微弱持续高频声（172.27Hz 整数倍的纯音，见 `decomb.py`），再做 16kHz 低通、裁剪短音效首尾、统一响度，最后生成试听页 `art-candidates/audio-v1/index.html`。
3. `export_sounds.py`：把选定的声音写入 `cocos-kitchen/assets/resources/audio/` 并生成 `index.json`。底噪类声音取响度稳定的一段，用等功率交叉淡化接成循环。清单里 `pick` 为 `composed` 的声音（也就是音乐）改由 `compose_music.py` 生成。

已定的设计：界面、订单、出餐、结算乐句和代码作曲的音乐用 8-bit 芯片音；烹饪、火、碗碟用未经复古处理的真实音效。切菜在切菜动画到达落刀帧（案板闪一下）时播一声（每位厨师每秒 2.5 刀），刀声从切菜录音中逐刀切出，并剔除发闷的。洗碗用处理过的单人循环；两人一起洗时速度翻倍，切换为两段不同录音左右分开、1.5 倍速播放。

## 环境（Intel 或 Apple Silicon 的 macOS，CPU 运行）

Intel Mac 装不了推理库固定的 `torch==2.7.1`，`sa3_local.py` 加了两处兼容处理，使固定版本能在 torch 2.2.2 上运行。安装命令见上方英文部分。`SA3_MODEL_DIR` 指向下载好的 `stabilityai/stable-audio-3-small-sfx` 文件夹，默认是 `/Volumes/T7/AI-Models/stable-audio-3-small-sfx`。在 2020 款 Intel i5、16GB 内存上，一个短音效约 8–15 秒，内存峰值约 6GB。
