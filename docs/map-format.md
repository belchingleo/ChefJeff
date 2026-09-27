# Map data format — schema version 1

Maps are UTF-8 JSON at `maps/level-<number>.json`. Levels 1–3 are included. `map_definition.py` loads, validates, atomically saves and extracts geometry; invalid documents cannot replace the target file.

A map contains `schema_version`, `id`, `revision`, `size`, `walls`, `equipment` and optional `presentation`. Coordinates start at the top-left: x increases right, y down. Width and height must be integers from 5 to 64. Walls form a complete outer boundary without duplicate cells, and remaining walkable floor must be connected.

Each station has a unique nonempty `id`, a `cell`, walkable `access`, and `facing` from `north`, `south`, `east`, `west`. Ordinary access is orthogonally adjacent; station cells cannot overlap walls or other stations.

Corner counters may use `"reach":"corner"` with diagonal access. This exception applies only to `counter` IDs: both adjoining orthogonal cells must be stations, no orthogonal side may have walkable floor, and the diagonal access must be walkable. Such counters occupy an existing wall corner without consuming another floor cell. Ordinary stations cannot use this exception to operate through walls.

## Presentation

`presentation` is separate from gameplay geometry. Themes include `courtyard`, `street`, `terrace`; corner caps refer to wall cells. Decorations accept only `decoration_window`, `decoration_menu`, `decoration_rail`, `decoration_flowerbox`, `decoration_lamp`, `decoration_plant`; use the `north_wall` anchor on top-wall cells, with scale 0.1–0.6. JSON does not contain executable code or arbitrary resource paths.

`presentation.station_views` is keyed by station ID. `run_axis` describes the cabinet run, and `device_axis` the asset's long axis; both are `horizontal` or `vertical`. They are explicitly authored rather than inferred from interaction `facing`. Older maps may omit them; unknown IDs and invalid axes are rejected.

Level 1's boards and side cabinets are vertical; its top/bottom runs are horizontal. Level 2's central run is horizontal and side runs vertical. Level 3's side/central columns are vertical, top/bottom rows horizontal. Corners follow their top/bottom row. These fields change presentation only, not the collision cells or access points extracted by `geometry()`.

## Footprints and operation sides

Optional `cells` declares a station footprint, for example `"cell":[12,5], "cells":[[12,5]]`. Without it, the footprint is the primary cell. It must contain that cell, be unique and orthogonally connected, and avoid overlaps. Access must adjoin at least one footprint cell. Navigation, player selection, agent operation and snapshots share this footprint. Current serving windows occupy 1×1 cells; synthetic maps test larger footprints.

`facing` identifies the chef's interaction side: a right-wall serving window uses `west`, with delivery toward the right; a left-wall window uses `east`. Directional assets share a fixed camera and do not change the footprint by stretching.

## Example and roadmap

The Chinese section below includes a field fragment, not a runnable map: its abbreviated wall list does not enclose the boundary. Start from a complete map in `maps/` for editing. Local JSON load/validate/save is available; visual editing, arbitrary recipes and custom station types are roadmap work. A valid map document alone does not enable those runtime features.

---

## 中文说明

# 地图数据格式（schema version 1）

地图以 UTF-8 JSON 保存于 `maps/level-<编号>.json`。当前提供第 1–3 关。`map_definition.py` 提供本地加载、校验、原子保存和几何提取；保存前会再次校验，非法文档不会覆盖目标文件。

以下是**字段示意片段**，不是可直接校验或运行的完整地图（例如 `walls` 只列出一个格子，未封闭边界）：

```json
{
  "schema_version": 1,
  "id": "level-1",
  "revision": 1,
  "size": [14, 9],
  "walls": [[0, 0]],
  "equipment": [
    {"id": "b2", "cell": [2, 1], "access": [2, 2], "facing": "south"}
  ],
  "presentation": {
    "theme": "courtyard",
    "wall_style": "warm-timber",
    "cabinet_style": "blue-enamel",
    "corner_caps": [],
    "decorations": [],
    "exterior": {},
    "station_views": {
      "b2": {"run_axis": "vertical", "device_axis": "vertical"}
    }
  }
}
```

坐标原点在左上角，`[x, y]` 的 x 向右、y 向下。尺寸是 `[宽, 高]`，两边都须为 5–64 的整数。`walls` 列出不可通行格，外圈边界必须完整封闭且墙格不能重复。每个工位需有唯一、非空的 `id`、不与墙或其他工位重叠的 `cell`、可通行的 `access`，以及 `north`、`south`、`east`、`west` 之一的 `facing`。普通工位的 `access` 必须与工位格四邻接。剩余可走地面必须连通。

角落柜台可使用特殊字段 `{ "reach": "corner" }`，并将 `access` 指向一个斜对角地面格。这个例外仅适用于 `counter` 前缀的柜台：两侧正交相邻格都必须是工位，柜台的四邻接位置不能有可走地面，且斜角 `access` 必须可通行。这样柜台沿用被墙占据的内角位置，玩家从指定斜角接近并操作；角落柜台和墙占据相同格位，不会额外侵占可走地面。普通工位不能用斜角访问绕过墙或隔墙。

`presentation` 保存外观数据，与 `walls` 和 `equipment` 所定义的玩法几何分开。已知主题为 `courtyard`、`street`、`terrace`；`corner_caps` 只能指向墙格。`decorations` 目前只接受 `decoration_window`、`decoration_menu`、`decoration_rail`、`decoration_flowerbox`、`decoration_lamp`、`decoration_plant` 这些资源名，锚点须为 `north_wall`，并放在顶部墙格，缩放范围为 0.1–0.6。装饰资源用受限名称引用，不在地图 JSON 中写入任意文件路径或代码。

`presentation.station_views` 用工位 `id` 为键，记录展示布局轴向：`run_axis` 描述工位在场景中的排列轴，`device_axis` 描述单个设备素材的轴向。二者都只能是 `horizontal` 或 `vertical`，由展示数据显式指定，不从工位的操作朝向 `equipment.facing` 推断。旧地图可以省略 `station_views`，校验会按兼容方式接受。未知工位 ID 或非法轴向会被拒绝。

当前三张地图的轴向约定为：第一关 b1、b2、b3 和左右边缘柜台为纵向，顶部、底部柜台为横向；第二关中间横排为横向，左右墙边柜台为纵向；第三关左右与中间纵列为纵向，顶部和底部排为横向。转角按其所在的顶部或底部排设为横向。新增这些值只影响展示；`geometry()` 提取的碰撞格、操作朝向和访问位置不受影响。更新后的地图 revision 为 3，布局标识为 `level-1-3` 等。

## 工位占格与素材朝向

工位可以提供可选 `cells`，例如 `"cell": [12,5], "cells": [[12,5]]`。
省略时等同于只占 `cell`。占格集合必须包含主格、没有重复、四邻连通，
不能与其他工位或墙重叠；普通操作位需与任意一个占格四邻接。
寻路阻挡、玩家目标选择、AI 操作位置和状态快照使用同一集合。
多格接口已有合成地图测试；当前三关出餐口均为 **1×1 格**，不是两个窗口。

`facing` 指厨师操作侧：右墙出餐口为 west，外送方向向右；左墙为 east，
外送方向向左。图像使用同一固定相机下的独立朝向资源，不通过拉伸画布
改变占格。

## 当前编辑边界

当前实现支持本地 JSON 的加载、校验和保存，以及既有三关数据迁移后的几何读取。保存接口允许调用方指定本地目标路径，但地图内容本身不携带可执行代码或任意资源路径。尚未实现可视化地图编辑器，也未实现任意菜谱、自定义工位或让新地图配置驱动完整运行流程；格式校验通过不代表这些能力已经验收。
