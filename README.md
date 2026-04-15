# Avalon 多轮博弈平台

基于阿瓦隆（The Resistance: Avalon）桌游的多轮博弈仿真与实时对战平台，支持两种运行模式：

- **模式一：LLM vs LLM 自动仿真** — 全自动多轮实验，用于评估不同大模型在社交推理场景下的博弈能力
- **模式二：Human Team vs AI Team 阵营对抗** — 人类小队 vs AI 小队，选择阵营后一键开局，座位和角色每局随机分配

---

## 项目结构

```
SoDe_Avalon_human/
├── Agents/
│   ├── Agent.py                      # LLM Agent 基类（act / _construct_instruction / call）
│   ├── Agent_human.py                # CLI 人类 Agent（已有，未接入主游戏）
│   └── Agent_Streamlit_Human.py      # [新增] Streamlit 人类代理，继承 Agent
├── Game/
│   ├── Avalon_multiturn.py           # 核心游戏引擎 Game_Avalon_Multiturn
│   └── Avalon_Streamlit_Engine.py    # [新增] Streamlit 引擎包装器，继承核心引擎
├── prompts/
│   └── Avalon_system_prompts.py      # 角色 Prompt 模板 + JSON 输出格式说明
├── Tool/
│   ├── callopenai.py                 # OpenAI API 调用封装
│   └── Json_extractor.py             # 从 LLM 回复中提取 JSON
├── shared_state.py                   # [新增] SQLite 共享状态管理器
├── app.py                            # [新增] Streamlit 主应用（3 个视图）
├── run_human_llm.py                  # [新增] Human vs LLM 启动脚本
├── run_simulation_avalon.py          # LLM vs LLM 仿真入口
├── run_avalon.sh                     # LLM vs LLM tmux 并行启动脚本
├── count.py                          # 日志统计工具
├── requirements.txt                  # [新增] Python 依赖
└── README.md                         # 本文件
```

标注 `[新增]` 的文件为 Human vs LLM 模式专用，**不修改任何原有文件**。

---

## 环境准备

### Python 依赖

```bash
pip install -r requirements.txt
```

核心依赖：`openai`、`streamlit`

### LLM 服务

需要至少一个兼容 OpenAI API 格式的 LLM 推理服务（如 vLLM、ollama 或云端 API），用于为 LLM 座位提供推理能力。

---

## 模式一：LLM vs LLM 自动仿真

### 配置

编辑 `run_avalon.sh`，修改以下变量：

| 变量 | 说明 |
|------|------|
| `MODEL_A_NAME` / `MODEL_B_NAME` | 模型名称 |
| `MODEL_A_API_KEY` / `MODEL_B_API_KEY` | API Key（本地 vLLM 填 `EMPTY`） |
| `MODEL_A_BASE_URL` / `MODEL_B_BASE_URL` | API 端点地址 |
| `MODEL_A_TEMP` / `MODEL_B_TEMP` | 温度参数（`None` 使用默认） |
| `PLAYER_NUM` | 玩家人数（5-10） |
| `TOTAL_ROUNDS` | 总实验轮数 |
| `PARALLEL_WORKERS` | tmux 并行窗口数 |

### 运行

```bash
bash run_avalon.sh
```

或直接运行 Python 脚本：

```bash
python run_simulation_avalon.py \
    --rounds 20 \
    --player_num 7 \
    --model_a_name "ModelA" \
    --model_a_key "EMPTY" \
    --model_a_url "http://localhost:8000/v1" \
    --model_b_name "ModelB" \
    --model_b_key "EMPTY" \
    --model_b_url "http://localhost:8001/v1"
```

### 日志输出

- 单局详细日志：`logs/Avalon/<log_tag>/<时间戳>/`
  - `.json` — 完整 game_log（讨论、投票、任务执行记录）
  - `_game_condition.json` — 结构化时间线
  - `.txt` — 人类可读战报
- 实验汇总：`ex_log/<log_tag>/experiment_summary.jsonl`

---

## 模式二：Human Team vs AI Team 阵营对抗

### 架构概述

```
┌─────────────────────────────────────────────────────┐
│              Streamlit 进程 (单进程多会话)             │
│                                                     │
│  ┌──────────┐  ┌──────────┐  ┌──────────────────┐  │
│  │ Host 会话 │  │ 玩家A 会话│  │ Game Engine 线程  │  │
│  └─────┬────┘  └─────┬────┘  └────────┬─────────┘  │
│        │             │                │             │
└────────┼─────────────┼────────────────┼─────────────┘
         │             │                │
    ┌────▼─────────────▼────────────────▼────┐
    │         SQLite 共享状态数据库            │
    │       (game_shared_state.db)           │
    └────────────────────────────────────────┘
```

- **Streamlit 前端**：每个浏览器标签页是一个独立会话，负责展示游戏界面和收集人类输入
- **SQLite 中间层**：桥接前端与后端，存储待处理动作、游戏事件流、房间/玩家状态
- **Game Engine 后台线程**：运行核心引擎；轮到 LLM 时直接调用 API，轮到人类时阻塞等待前端提交决策

### 新增文件说明

| 文件 | 职责 |
|------|------|
| `shared_state.py` | SQLite 共享状态管理器，封装房间、玩家、待处理动作、事件流的 CRUD 和阻塞等待 |
| `Agents/Agent_Streamlit_Human.py` | 继承 `Agent` 基类，`act()` 中将 prompt 写入 SQLite 并阻塞等待人类回复 |
| `Game/Avalon_Streamlit_Engine.py` | 继承 `Game_Avalon_Multiturn`，覆盖 `_broadcast()` 写入事件流，覆盖 `save_log()` 重定向日志 |
| `app.py` | Streamlit 主应用，包含登录大厅、Host 阵营配置面板、玩家游戏界面三个视图 |
| `run_human_llm.py` | 启动脚本：写入模型配置、重置数据库、启动 Streamlit 服务 |
| `requirements.txt` | Python 依赖声明 |

### 快速启动

#### 第 1 步：配置 LLM 模型

编辑 `run_human_llm.py` 中的 `MODEL_CONFIGS` 字典，添加你的 LLM 模型：

```python
MODEL_CONFIGS = {
    "Qwen3-32B": {
        "name": "Qwen3-32B",
        "api_url_config": {
            "api_key": "EMPTY",
            "base_url": "http://your-server:8815/v1",
        },
        "inference_config": {
            "model": "Qwen3-32B",
            "temperature": 0.7,
            "top_p": 0.8,
            "max_tokens": 8192,
        },
    },
    # 添加更多模型...
}
```

#### 第 2 步：启动服务

```bash
python run_human_llm.py --port 8501
```

服务启动后会在终端打印访问地址。

#### 第 3 步：房间主创建房间

1. 在浏览器中打开 `http://<服务器IP>:8501`
2. 输入昵称，勾选"创建新房间"，点击"确认加入"
3. 进入 Host 阵营配置面板后，记下屏幕上显示的**房间号**

#### 第 4 步：其他人类玩家加入

1. 在各自的浏览器（可以是不同电脑）中打开相同地址
2. 输入昵称和房间号，点击"确认加入"
3. 进入等待界面

#### 第 5 步：配置阵营

在 Host 配置面板中：
- 选择人类阵营：**Good**（需 4 名人类玩家）或 **Evil**（需 3 名人类玩家）
- 选择驱动敌对阵营的 LLM 模型
- 房间主默认参与游戏（可取消勾选改为观战）
- 等待人数满足后即可开始

#### 第 6 步：一键开始游戏

点击"随机分配座位并开始游戏"按钮。座位号 1-7 全局随机打乱，角色在各自阵营内随机分配。每局的人机位置和具体角色都不同。

#### 第 7 步：游戏进行中

每个玩家在自己的浏览器中：
- 查看自己的角色和阵营信息
- 看到游戏进程的实时更新
- 轮到自己时，根据当前阶段提交操作

### 游戏操作指南

| 游戏阶段 | 操作方式 | 说明 |
|---------|---------|------|
| 发言 (Speech) | 文本输入框 | 自由发言，分析局势、表达观点 |
| 组队 (Proposal) | 多选框 | 作为队长时选择指定人数的队员 |
| 投票 (Voting) | 单选按钮 | 同意或反对当前队伍提案 |
| 执行 (Execution) | 单选按钮 | 好人只能选成功；坏人可选成功或失败 |
| 刺杀 (Assassination) | 下拉选择 | 仅刺客，选择认为是 Merlin 的玩家 |

### 信息隔离与双盲机制

- **Prompt 一致性**：人类玩家看到的指令文本与 LLM 收到的 Prompt 完全一致（`Agent_Streamlit_Human` 继承了 `Agent` 的 `_construct_instruction()` 方法）
- **观测一致性**：所有玩家通过相同的 `_broadcast()` 机制接收公共信息
- **随机 ID 映射**：座位号 1-7 每局全局随机打乱，人类玩家无法从编号判断其他玩家是人还是 LLM
- **阵营锁定**：人类玩家统一分配到选定阵营，LLM 统一分配到对方阵营，阵营内角色随机
- **完全隔离的会话**：每个 Streamlit 标签页只能看到属于自己的信息

### 一键重开新局

游戏结束后，房主可点击"重新开启新一局"按钮，系统会清空本局所有数据（事件、待处理动作、座位分配），将房间重置为等待状态。所有玩家页面自动回到大厅，无需重新加入房间，即可开启下一局。

### Human vs LLM 日志

日志保存在 `logs/Avalon/human_vs_LLM/<房间号>/` 目录下，包含：
- `.json` — 完整 game_log
- `_game_condition.json` — 结构化时间线（`players_config` 中人类玩家的 model 字段为 `Human_<昵称>`）
- `.txt` — 人类可读战报

---

## 日志格式说明

### game_log JSON

```json
{
  "meta_info": { "mode": "Avalon_Multiturn", "player_count": 7, ... },
  "agents_info": { "player_1": { "role": "Merlin", "config": {...}, "system_prompt": "..." }, ... },
  "game_process": [
    {
      "round": 1,
      "quest_config": { "team_size": 2, "req_fails": 1 },
      "attempts": [ { "leader": 3, "discussions": [...], "proposed_team": [1,3], "votes": [...] } ],
      "mission_result": { "fail_cards": 0, "details": [...] },
      "outcome": "good_point"
    }
  ],
  "final_result": "good_win"
}
```

### game_condition JSON

结构化的游戏时间线，包含每一步的 agent 信息、原始回复和提取结果，适合做后续数据分析。

---

## 注意事项

1. **端口占用**：默认使用 8501 端口，可通过 `--port` 参数修改
2. **LLM 超时**：人类玩家的操作超时默认为 600 秒（10 分钟），LLM 调用超时取决于 OpenAI client 的配置
3. **多人连接**：Streamlit 天然支持多人同时访问，每个浏览器标签页是独立会话
4. **数据库重置**：每次运行 `run_human_llm.py` 会自动清空之前的游戏数据。如需保留，请备份 `game_shared_state.db`
5. **局内重开**：游戏结束后房主可一键重开新局，无需重启服务或重新加入房间
6. **原有代码不受影响**：所有新增文件通过继承实现，`run_simulation_avalon.py` 和 `run_avalon.sh` 仍可独立使用
