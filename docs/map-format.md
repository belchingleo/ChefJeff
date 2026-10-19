# Map data format — schema versions 1 and 2

Maps are UTF-8 JSON at `maps/<map-id>.json`. Levels 1–3 are included and use schema 2. `map_definition.py` loads, validates, atomically saves and extracts geometry; invalid documents cannot replace the target file.

A map contains `schema_version`, `id`, `revision`, `size`, `walls`, `equipment` and optional `presentation`. Coordinates start at the top-left: x increases right, y down. Width and height must be integers from 5 to 64. Walls form a complete outer boundary without duplicate cells, and remaining walkable floor must be connected.

Each station has a unique nonempty `id`, a `cell`, walkable `access`, and `facing` from `north`, `south`, `east`, `west`. Ordinary access is orthogonally adjacent; station cells cannot overlap walls or other stations.

Corner counters may use `"reach":"corner"` with diagonal access. This exception applies only to `counter` IDs: both adjoining orthogonal cells must be stations, no orthogonal side may have walkable floor, and the diagonal access must be walkable. Such counters occupy an existing wall corner without consuming another floor cell. Ordinary stations cannot use this exception to operate through walls.

## Schema 2: equipment instances

Schema 2 keeps every geometry rule below and adds instance semantics: top-level `areas` (`{"prep": {"name": "处理区"}}`) and optional `floor_areas` (`{"axis": "x", "split": 7, "below": "prep", "at_or_above": "cook"}`); each station adds `type` (an equipment-catalog type such as `board`, `stove`, `counter`, `ingredient_source`), `name`, `area` and optional `params` (an ingredient source needs `{"item": "beef"}`). The level's equipment catalog decides whether a type exists. Station order is the engine's station order. Corner reach is allowed for `type: counter`. Schema-1 maps still load: types are inferred from the historical ID conventions (`b*` board, `p*` stove, `counter*`/`plates` counter, …). See [configuration contract](architecture/configuration-contract.md).

## Presentation

`presentation` is separate from gameplay geometry. Themes include `courtyard`, `street`, `terrace`; corner caps refer to wall cells. Decorations accept only `decoration_window`, `decoration_menu`, `decoration_rail`, `decoration_flowerbox`, `decoration_lamp`, `decoration_plant`; use the `north_wall` anchor on top-wall cells, with scale 0.1–0.6. JSON does not contain executable code or arbitrary resource paths.

`presentation.station_views` is keyed by station ID. `run_axis` describes the cabinet run, and `device_axis` the asset's long axis; both are `horizontal` or `vertical`. They are explicitly authored rather than inferred from interaction `facing`. Older maps may omit them; unknown IDs and invalid axes are rejected.

Level 1's boards and side cabinets are vertical; its top/bottom runs are horizontal. Level 2's central run is horizontal and side runs vertical. Level 3's side/central columns are vertical, top/bottom rows horizontal. Corners follow their top/bottom row. These fields change presentation only, not the collision cells or access points extracted by `geometry()`.

## Footprints and operation sides

Optional `cells` declares a station footprint, for example `"cell":[12,5], "cells":[[12,5]]`. Without it, the footprint is the primary cell. It must contain that cell, be unique and orthogonally connected, and avoid overlaps. Access must adjoin at least one footprint cell. Navigation, player selection, agent operation and snapshots share this footprint. Current serving windows occupy 1×1 cells; synthetic maps test larger footprints.

`facing` identifies the chef's interaction side: a right-wall serving window uses `west`, with delivery toward the right; a left-wall window uses `east`. Directional assets share a fixed camera and do not change the footprint by stretching.

## From coordinates to a playable map

`map_definition.build_map(name, size, stations, theme='street', revision=1)` turns station coordinates into a schema-2 map that has passed `validate_map`. Each station is `(id, x, y, facing)` or an object `{"id", "cell", "facing"}` with optional `type`, `name`, `params`, `area`. Derived: a closed boundary wall; `access` is the cell the station faces, or, for a counter boxed in by counters (a run's corner), the free diagonal between its two neighbours with `reach: corner`; `type` from the historical ID conventions (`b1` board, `p1` stove, `fridge`/`lettuce`/`tomato`/`bread` sources with their `params`, `serve`, `sink`, `returns`, `bin`, `extinguisher`), otherwise `counter`; `name` is the ID; areas `prep`/`cook` split across the longer side (`floor_areas`). A station that faces a wall or another station and is not such a corner is rejected by name.

Levels place their starting plates, pans and extinguisher by station type (`initial_inventory[].at_type`, see the [configuration contract](architecture/configuration-contract.md)), so a level's rules run on any map that has the stations it needs. Before playing a new map, audit it:

```sh
python3 scripts/audit_map.py maps/level-2.json
python3 scripts/audit_map.py layout.json --level level-2 --seeds 1 2 3
python3 scripts/audit_map.py layouts.json --json
```

The input is a map document, a layout `{"name": "island", "size": [14, 10], "stations": [["fridge", 2, 1, "south"], ...]}`, or a list of layouts. Each map runs with the rules, recipes, orders and inventory of `--level` (default `level-2`); on another map than the level's own, the chefs spawn either side of the floor-area split. The audit reports: validation; whether the level bundle with this map freezes (resolver diagnostics if not); Space from every station's access cell (and a step closer), facing it, selects that station; engine walking has no point that no direction can leave; the page geometry (`KitchenGeometry.ts` compiled with `tsc`, as `tests/test_client_walk.py` does) never starts a walk stuck and draws floor items in front of the cabinet behind; a warning for each 1-cell-wide corridor that is the only route between stations (two chefs cannot pass each other there); dishes served by the scripted solo chef and the scripted pair. It exits 1 when a check fails; warnings alone pass. It is local and calls no model.

To ship a map, save it with `save_map` as `maps/<id>.json`, add a level in `content/levels/` whose `map_ref` names it, and audit both. The Chinese section below includes a field fragment, not a runnable map: its abbreviated wall list does not enclose the boundary. Visual editing, arbitrary recipes and custom station types are roadmap work.

---

## 中文说明

# 地图数据格式（schema version 1 与 2）

地图以 UTF-8 JSON 保存于 `maps/<地图 id>.json`。当前提供第 1–3 关，均为 schema 2。

**Schema 2** 保留下文全部几何规则，并增加设备实例语义：顶层 `areas`（如 `{"prep": {"name": "处理区"}}`）与可选 `floor_areas`；每个工位增加 `type`（设备目录中的类型，如 `board`、`stove`、`counter`、`ingredient_source`）、`name`、`area` 和可选 `params`（食材源需 `{"item": "beef"}`）。类型是否存在由关卡引用的设备目录判定；工位顺序即引擎工位顺序；斜角访问适用于 `type: counter`。Schema 1 地图仍可加载，按历史 ID 约定推断类型。详见[配置契约](architecture/configuration-contract.md)。`map_definition.py` 提供本地加载、校验、原子保存和几何提取；保存前会再次校验，非法文档不会覆盖目标文件。

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

## 从坐标生成可玩地图

`map_definition.build_map(name, size, stations, theme='street', revision=1)` 把工位坐标转成通过 `validate_map` 的 schema 2 地图。每个工位写作 `(id, x, y, facing)`，或对象 `{"id", "cell", "facing"}`，可选 `type`、`name`、`params`、`area`。自动推导：封闭的外圈墙；`access` 取工位朝向的那一格；被柜台围住的柜台（一排柜台的转角）取两侧相邻柜台之间的空斜角，并标 `reach: corner`；`type` 按历史 ID 约定推断（`b1` 案板、`p1` 灶台、`fridge`/`lettuce`/`tomato`/`bread` 食材源及其 `params`、`serve`、`sink`、`returns`、`bin`、`extinguisher`），其余为 `counter`；`name` 即 ID；`prep`/`cook` 两区沿较长边对半划分（`floor_areas`）。朝向墙或其他工位、又不是上述转角柜台的工位，会按 ID 报错。

关卡的初始盘子、锅和灭火器按工位类型放置（`initial_inventory[].at_type`，见[配置契约](architecture/configuration-contract.md)），因此关卡规则可以在任何具备所需工位的地图上运行。新地图上手前先审查：

```sh
python3 scripts/audit_map.py maps/level-2.json
python3 scripts/audit_map.py layout.json --level level-2 --seeds 1 2 3
python3 scripts/audit_map.py layouts.json --json
```

输入可以是地图文档、坐标布局 `{"name": "island", "size": [14, 10], "stations": [["fridge", 2, 1, "south"], ...]}`，或布局列表。每张地图使用 `--level`（默认 `level-2`）的规则、菜谱、订单和初始物品；不是该关自己的地图时，两名厨师分别出生在地面分区线两侧。报告内容：地图校验；关卡配置包换上这张地图后能否冻结（不能时给出解析诊断）；从每个工位的操作格（以及再靠近一步）面向工位按 Space 是否选中它；引擎行走中是否存在任何方向都走不出的点；网页几何（用 `tsc` 编译 `KitchenGeometry.ts`，与 `tests/test_client_walk.py` 相同）不会让行走从卡住处开始，地面物品画在身后柜台之前；每条作为工位之间唯一通路的单格宽走廊给出警告（两名厨师在其中无法错身）；脚本单人与脚本双人各出餐多少。任一检查失败时退出码为 1，仅有警告时通过。全程本地运行，不调用模型。

要发布地图：用 `save_map` 保存为 `maps/<id>.json`，在 `content/levels/` 添加 `map_ref` 指向它的关卡，然后审查两者。尚未实现可视化地图编辑器、任意菜谱或自定义工位；格式校验通过不代表这些能力已经验收。地图内容本身不携带可执行代码或任意资源路径。
