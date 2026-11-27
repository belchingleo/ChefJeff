# Level 5 — Swapped sides

Level 4 with the chefs swapped: the same kitchen, the same orders and order seed, the same target. Only the spawn seed differs (1 instead of 0), so the human starts on the upper side, with the four ingredient sources, the two stoves, the counter the extinguisher starts on, the serving window and a bin, and Jeff on the lower side, with the two boards, the sink and drying rack, the dirty-plate return and the second bin. Food, plates, pans and tools cross on the dividing counters or are thrown within 4 cells, as on Level 4.

Every dish needs both chefs: the human fetches and passes the raw beef and vegetables down, Jeff chops them and passes them back, the human cooks, plates and serves, and Jeff washes the plates and passes clean ones up. One chef alone serves nothing (`requires_pair: true`; `tests/test_level_five.py`).

The target is ¥90, as on Level 4: the scripted reference pair is calibrated in both role assignments, so the two levels' calibration runs are the same (median 190 over order seeds 1–21, solo −80 to −40; `docs/architecture/reports/calibration.json`). Level 5 is switched off for players in `level_switches.json`; a machine shows it with `python3 levels.py set level-5 on`.

What Jeff is told is worked out from the engine's reach, so every request switch works here unchanged: `reach_note` and `split_floor` list the stations and operations on each side, and `step_check` (since it names whoever is on the boards' side) says "Within your reach to chop now", "the boards are on your side" and "the supplies are on the other chef's side". For scripted rounds the human's role is the runner: `scripts/model_rounds.py --level level-5 --human runner`.

---

## 中文说明

# 第五关：换位协作

第四关把两位厨师对调：同一间厨房、同一组订单和订单种子、同一个目标，只有出生种子不同（1，第四关是 0）。人类出生在上面，那里是四个食材箱、两个灶台、放着灭火器的柜台、出餐口和一个垃圾桶；Jeff 在下面，那里是两块案板、水槽和沥水架、脏盘回收和第二个垃圾桶。食物、盘子、锅和工具和第四关一样，放到中间那排柜台上，或者在 4 格内扔过去。

每道菜都要两个人：人类取生肉和蔬菜递下去，Jeff 切好递回来，人类煎、装盘、出餐；Jeff 洗盘子，把干净盘子递上来。一个人单干一单也出不了（`requires_pair: true`；`tests/test_level_five.py`）。

目标 ¥90，和第四关一样：脚本参考组合两种分工都会试，所以两关的校准结果相同（订单种子 1–21 的中位数 190，单人 −80 到 −40；`docs/architecture/reports/calibration.json`）。第五关在 `level_switches.json` 里对玩家关闭；本机用 `python3 levels.py set level-5 on` 打开。

Jeff 收到的提示都按引擎算出的可达范围生成，所以所有提示开关在这一关原样可用：`reach_note` 和 `split_floor` 写明每边有哪些工位和工序；`step_check` 现在按“谁在案板那边”来写，会说“Within your reach to chop now”“the boards are on your side”“the supplies are on the other chef's side”。脚本对局里人类扮演取料、煎、上菜的角色：`scripts/model_rounds.py --level level-5 --human runner`。
