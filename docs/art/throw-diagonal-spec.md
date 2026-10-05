# Diagonal throw bodies — art brief

While a chef aims or releases a throw, the body turns to the aim. The four straight views already exist (front, back, left, right: the knifeless chop poses in `chefs-v2`). This brief covers the four diagonals. Until they are delivered, diagonal throws use the nearest straight view with the arm raised or lowered.

## Frames (16)

| | down-right | down-left | up-left | up-right |
|---|---|---|---|---|
| Player (brown hair, white shirt, blue overalls) | wind-up, release | wind-up, release | wind-up, release | wind-up, release |
| Jeff (tracked robot, chef hat, red scarf) | wind-up, release | wind-up, release | wind-up, release | wind-up, release |

"Down" faces the viewer (three-quarter front), "up" faces away (three-quarter back). Down-left and up-left may mirror their right-hand frames only if the lighting is repainted from the top left; do not deliver a plain flip.

- **Wind-up**: the throwing hand raised behind or beside the head, item about to leave. Matches `chop_0` of the straight views.
- **Release**: the arm extended toward the aim, slightly forward. Matches `chop_1` (straight) of the side views.
- The held item is not painted: the game draws it at the fist. Leave the hand open enough to hold it.

## Format

- One PNG per frame, 68×88, RGBA, transparent background, 1 art pixel = 1 game pixel (64 px per tile).
- Feet on the line y = 83 (PNG top-left origin), body centred on x = 34, the same height and proportions as the straight views.
- Same style as `chefs-v2`: painterly pixel art lit from the top left, a 1-pixel near-black outline, no anti-aliased edge against transparency.
- File names: `<chef>_<diagonal>_<phase>.png`, with `chef` = `player` | `jeff`, `diagonal` = `down_right` | `down_left` | `up_left` | `up_right`, `phase` = `windup` | `release`. Example: `jeff_up_left_release.png`.
- Optional fist overlay drawn over the held item: `<same name>_hand.png` (68×88, only the fingers).
- `grips.json`: for every frame, the fist centre and the arm direction, e.g. `{"player_down_right_release": {"grip": [50, 52], "arm_deg": -20}}` (`arm_deg` counter-clockwise from pointing right).

Reference sheets of the existing straight poses with the feet line and centre marked: `python3 scripts/art/throw_diagonals.py --reference <folder>`.

## Importing

`python3 scripts/art/throw_diagonals.py <folder>` checks the files (all 16 present, canvas size, feet line, grips) and writes `cocos-kitchen/assets/resources/art/throw-diagonal-v1`. Rebuild the web client; the game then uses a diagonal body whenever the aim is within 22.5° of a diagonal, for both chefs.

---

## 中文说明

# 斜向投掷身体 · 美术需求

厨师瞄准或投出时，身体会转向瞄准方向。四个正方向（正面、背面、左、右）已有：即 `chefs-v2` 里无刀的切菜姿势。本需求补四个斜向。交付前，斜向投掷暂用最近的正方向身体，配合手臂上扬或下压。

## 帧（16 张）

| | 右下 | 左下 | 左上 | 右上 |
|---|---|---|---|---|
| 玩家（棕发、白衬衫、蓝背带裤） | 蓄力、出手 | 蓄力、出手 | 蓄力、出手 | 蓄力、出手 |
| Jeff（履带机器人、厨师帽、红领巾） | 蓄力、出手 | 蓄力、出手 | 蓄力、出手 | 蓄力、出手 |

“下”为面向镜头的四分之三正面，“上”为背向镜头的四分之三背面。左向可以参考右向镜像起稿，但需按左上方光源重画明暗，不要直接翻转交付。

- **蓄力**：投掷手举到头后或头侧，物品即将出手；对应正方向的 `chop_0`。
- **出手**：手臂伸向瞄准方向、略向前；对应侧身的 `chop_1`（平伸）。
- 手中物品不用画，游戏会画在拳头位置；手部留出握持的空间。

## 格式

- 每帧一张 PNG，68×88，RGBA 透明底，1 美术像素 = 1 游戏像素（每格 64 像素）。
- 脚底在 y = 83（以 PNG 左上角为原点），身体中心 x = 34，身高与比例同正方向。
- 画风同 `chefs-v2`：左上光源的绘画感像素画，1 像素近黑描边，边缘对透明底不做抗锯齿。
- 文件名：`<角色>_<斜向>_<阶段>.png`；角色 `player` | `jeff`，斜向 `down_right` | `down_left` | `up_left` | `up_right`，阶段 `windup` | `release`。例：`jeff_up_left_release.png`。
- 可选的手指叠层（盖在物品上）：`<同名>_hand.png`（68×88，只画手指）。
- `grips.json`：每帧的拳头中心和手臂方向，例如 `{"player_down_right_release": {"grip": [50, 52], "arm_deg": -20}}`（`arm_deg` 以指向右方为 0，逆时针为正）。

现有正方向姿势的参考图（标出脚底线和中线）：`python3 scripts/art/throw_diagonals.py --reference <文件夹>`。

## 导入

`python3 scripts/art/throw_diagonals.py <文件夹>` 会检查文件（16 张齐全、画布尺寸、脚底线、握点），并写入 `cocos-kitchen/assets/resources/art/throw-diagonal-v1`。重新构建网页后，瞄准方向在斜向 ±22.5° 内时，两位厨师都会使用斜向身体。
