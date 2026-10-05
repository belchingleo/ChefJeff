# Art integration guide

ChefJeff uses a fixed pixel-art camera with directional chefs, modular cabinets/walls, ingredient layers and action effects. Cocos loads local atlases from `cocos-kitchen/assets/resources/art/`; `LevelOneArt.ts` handles resources and `KitchenClient.ts` composes the scene.

## Geometry and layering

`KitchenGeometry.ts` centralizes world-to-screen projection and surface anchors. Map `presentation.station_views` separates the cabinet run axis and device asset axis from the chef's operation side. Align boards, plates, ingredients, selection outlines and effects to the same visible work surface.

Keep logical footprints and access points in map data. Scale assets proportionally using alpha bounds; avoid stretching a cabinet or moving a character to compensate for a misplaced tool. Cabinets, chefs and ground objects share depth ordering. Directional hand/tool layers must agree with whether the chef stands in front of, behind or beside the counter.

## Characters and cooking

The human chef has brown hair, a white shirt and blue overalls. Jeff is a compact tracked robot with a chef hat and red scarf. Preserve each character's height and proportions across directions. Chopping uses directional poses, a separate knife and light impact feedback; standing position follows the workstation's reachable side. Downstrokes may naturally pass behind a back-facing body while raised swings stay readable.

Throws reuse the painted chop arms (knifeless frames): frame 0 raised is the wind-up, 1 straight, 2 forward-down and 3 forward-up are the release. `KitchenGeometry.throwPose` picks the body view and arm for any aim angle; side views take 120° so diagonals lean the arm instead of turning to the front or back. The held item sits in the pose's painted hand (`grip`, a few pixels along `arm_deg`), behind the body for back views, with the pose's fist overlay on top. No angle is rotated freely, so pixels stay crisp. When the optional pack `art/throw-diagonal-v1` is present (`throw/<player|jeff>/<diagonal>/<windup|release>`, see [the brief](throw-diagonal-spec.md)), aims within 22.5° of a diagonal use those painted bodies instead, with the item behind the body for the up diagonals.

Prepared tomatoes use slices and lettuce uses leaves, shared between preparation and plated layers. Burger layers have a fixed order independent of ingredient-addition order. Missing ingredients remain hidden. Art does not decide recipe legality.

A frying pan's handle points at the chef: on a stove or counter toward the station's operation side (`facing`), in hand back toward the holder; `modular/pan_vertical` (south), `pan_horizontal` (east), `pan_west` and `pan_north` (handle behind the pan) share one light. Devices use horizontal/vertical assets as appropriate. The bin opening's long edge faces the reachable operation side; wall-facing details follow that side. Serving windows retain their map footprint. Fire, smoke, washing and sprint effects follow game state and pause with gameplay.

## Asset changes and verification

Add atlas rectangles, frame data and needed metadata together. Rectangles use the PNG top-left origin; set `SpriteFrame.originalSize` consistently. Keep runtime atlases free of private paths or generation history. Graphics fallbacks preserve readability if a resource fails.

Build with Cocos Creator 3.8.8, run affected asset/geometry tests, then inspect actual browser views for all affected directions and maps. Check visible proportions, work-surface alignment, click targets, held items and action frames. Static contact sheets help asset review but do not replace browser interaction checks. Asset provenance and rights are reviewed before public distribution; see [third-party notices](../../THIRD_PARTY_NOTICES.md).

---

## 中文说明

# 美术接入指南

ChefJeff 使用固定像素视角、方向化角色、模块柜墙、配料叠层和动作特效。Cocos 从 `cocos-kitchen/assets/resources/art/` 读取本地图集，`LevelOneArt.ts` 管理资源，`KitchenClient.ts` 组合场景。

## 几何与层级

`KitchenGeometry.ts` 集中世界到屏幕投影和台面锚点。地图 `presentation.station_views` 将柜体排列轴、设备资源轴与角色操作侧分开。案板、盘子、食材、选框和特效共用可见操作面位置。

逻辑占格与访问位置保留在地图数据中，按 alpha 边界等比缩放素材，不靠拉伸柜体或挪人物弥补工具错位。柜体、厨师和地面物品共用深度排序。手和工具的方向层级需对应角色位于柜台前、后或侧面的位置。

## 角色与烹饪

人类厨师为棕发、白衬衫、蓝背带裤；Jeff 为短臂履带机器人、厨师帽和红领巾。不同朝向保留身高与比例。切菜使用方向姿态、独立刀具与轻微切击反馈，站位遵循工位可达侧。背向角色下刀时刀被身体自然遮挡可以接受，举刀时需可辨认。

投掷沿用已绘制的切菜手臂（无刀帧）：第 0 帧举起为蓄力，1 平伸、2 前下、3 前上为出手。`KitchenGeometry.throwPose` 按任意瞄准角度选择身体朝向和手臂；侧身占 120°，斜向用手臂俯仰表现，不转成正面或背面。手中物品放在该姿势画好的手部位置（`grip` 沿 `arm_deg` 外移几像素），背面时在身体后方，手指叠层盖在物品上。不做任意角度旋转，像素保持清晰。若存在可选美术包 `art/throw-diagonal-v1`（`throw/<player|jeff>/<斜向>/<windup|release>`，见[美术需求](throw-diagonal-spec.md)），瞄准方向在斜向 ±22.5° 内时改用这些斜向身体，朝上的斜向物品在身体后方。

切好番茄使用片状、生菜使用叶片，切配与盘中叠层共用形态。汉堡按固定顺序显示，与放料先后无关，缺料层隐藏；美术不判断菜谱合法性。

平底锅手柄朝向厨师：在灶台或柜台上朝工位操作侧（`facing`），拿在手里时朝向持锅者；`modular/pan_vertical`（朝下）、`pan_horizontal`（朝右）、`pan_west`、`pan_north`（手柄在锅后）光照一致。设备使用对应横／纵资源。垃圾桶开口长边面向可接触操作侧，靠墙细节随之定向；出餐口保留地图占格。火、烟、洗碗和冲刺特效跟随状态，并随游戏暂停。

## 素材修改与验证

图集矩形、帧数据和必要元数据一起更新，矩形使用 PNG 左上原点，保持 `SpriteFrame.originalSize` 一致。运行图集不含私人路径或生成历史，缺图时以 Graphics 回退保持可读。

用 Cocos Creator 3.8.8 构建，运行相关素材／几何测试，再检查受影响地图和朝向的实际浏览器画面，包括比例、台面对位、点击目标、持物和动作帧。静态联系表辅助审图，不替代实机交互检查。公开分发前审阅素材来源及权利，见[第三方说明](../../THIRD_PARTY_NOTICES.md)。
