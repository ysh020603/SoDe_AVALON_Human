"""
Avalon Human-in-the-Loop Streamlit Application.

Three views:
  1. Login & Lobby   – enter nickname, create/join room
  2. Host Dashboard  – configure 7 seats (human / LLM), start game
  3. Player Game UI  – see game events, submit decisions when prompted
"""

import os
import sys
import json
import time
import uuid
import random
import threading
import streamlit as st

# ---------------------------------------------------------------------------
# Path setup so imports work when launched from project root
# ---------------------------------------------------------------------------
_project_root = os.path.dirname(os.path.abspath(__file__))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from shared_state import SharedStateManager
from Agents.Agent_Streamlit_Human import Agent_Streamlit_Human
from Agents.Agent import Agent
from Game.Avalon_Streamlit_Engine import Game_Avalon_Streamlit
from Tool.callopenai import api_call_format

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
GOOD_ROLES = ["Merlin", "Percival", "Loyal Servant"]
EVIL_ROLES = ["Morgana", "Assassin", "Minion", "Oberon", "Mordred"]
ROLES_7P = ["Merlin", "Percival", "Loyal Servant", "Loyal Servant",
            "Morgana", "Assassin", "Oberon"]

# ---------------------------------------------------------------------------
# Load model configs from JSON file (written by run_human_llm.py)
# ---------------------------------------------------------------------------
_MODEL_CONFIG_PATH = os.path.join(_project_root, "model_configs.json")


def _load_model_configs():
    if os.path.exists(_MODEL_CONFIG_PATH):
        with open(_MODEL_CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


MODEL_CONFIGS = _load_model_configs()

# ---------------------------------------------------------------------------
# Shared state singleton (one per Streamlit process)
# ---------------------------------------------------------------------------
_DB_PATH = os.path.join(_project_root, "game_shared_state.db")


@st.cache_resource
def get_shared_state():
    return SharedStateManager(db_path=_DB_PATH)


# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------
st.set_page_config(page_title="Avalon – Human vs LLM", page_icon="🏰", layout="wide")

# ---------------------------------------------------------------------------
# Session state defaults
# ---------------------------------------------------------------------------
_DEFAULTS = {
    "view": "login",
    "session_id": str(uuid.uuid4()),
    "nickname": "",
    "room_id": "",
    "is_host": False,
    "seat_number": -1,
    "last_event_id": 0,
}
for k, v in _DEFAULTS.items():
    if k not in st.session_state:
        st.session_state[k] = v

shared = get_shared_state()


# =========================================================================== #
#  GAME ENGINE LAUNCHER (runs in background thread)
# =========================================================================== #

_game_threads = {}


def _run_engine(room_id, seat_config, model_configs_snapshot):
    """Target function for the game-engine background thread."""
    ss = SharedStateManager(db_path=_DB_PATH)
    agents = []
    for seat_num in sorted(seat_config.keys()):
        slot = seat_config[seat_num]
        role = slot["role"]
        if slot["type"] == "human":
            agent = Agent_Streamlit_Human(
                player_id=seat_num,
                role=role,
                nickname=slot["nickname"],
                shared_state=ss,
                room_id=room_id,
            )
        else:
            model_key = slot["model_key"]
            llm_cfg = model_configs_snapshot[model_key].copy()
            agent = Agent(
                player_id=seat_num,
                role=role,
                llm_config=llm_cfg,
                llm_func=api_call_format,
            )
        agents.append(agent)

    engine = Game_Avalon_Streamlit(
        agents=agents,
        log_tag=room_id,
        shared_state=ss,
        room_id=room_id,
    )
    engine.run_game()


def start_game(room_id, seat_config, model_configs_snapshot):
    t = threading.Thread(
        target=_run_engine,
        args=(room_id, seat_config, model_configs_snapshot),
        daemon=True,
    )
    _game_threads[room_id] = t
    t.start()


# =========================================================================== #
#  CSS
# =========================================================================== #
st.markdown("""
<style>
.event-box {
    background: #f0f2f6; border-radius: 8px; padding: 10px 14px;
    margin-bottom: 6px; font-size: 0.92em; line-height: 1.5;
}
.event-box.action-needed {
    background: #fff3cd; border-left: 4px solid #ffc107;
}
.role-badge {
    display: inline-block; padding: 2px 10px; border-radius: 12px;
    font-weight: 600; font-size: 0.85em;
}
.role-good { background: #d4edda; color: #155724; }
.role-evil { background: #f8d7da; color: #721c24; }
.score-board {
    font-size: 1.1em; font-weight: bold;
    padding: 8px 16px; border-radius: 8px; background: #e9ecef;
}
</style>
""", unsafe_allow_html=True)


# =========================================================================== #
#  VIEW 1: LOGIN & LOBBY
# =========================================================================== #

def view_login():
    st.title("🏰 Avalon – Human vs LLM")
    st.markdown("---")

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("加入 / 创建房间")
        nickname = st.text_input("你的昵称", value=st.session_state.nickname,
                                 max_chars=20, key="input_nickname")
        room_id = st.text_input("房间号 (留空则自动创建)", value="",
                                max_chars=20, key="input_room")
        create_new = st.checkbox("创建新房间 (我是房间主)", value=False)

        if st.button("确认加入", type="primary", use_container_width=True):
            if not nickname.strip():
                st.error("请输入昵称")
                return

            st.session_state.nickname = nickname.strip()

            if create_new or not room_id.strip():
                rid = room_id.strip() if room_id.strip() else f"room_{uuid.uuid4().hex[:6]}"
                shared.create_room(rid, st.session_state.session_id)
                shared.register_player(rid, st.session_state.session_id,
                                       st.session_state.nickname, is_host=True)
                st.session_state.room_id = rid
                st.session_state.is_host = True
                st.session_state.view = "host"
                st.rerun()
            else:
                rid = room_id.strip()
                room = shared.get_room(rid)
                if not room:
                    st.error(f"房间 {rid} 不存在")
                    return
                if room["status"] != "waiting":
                    st.error("该房间已在游戏中或已结束")
                    return
                shared.register_player(rid, st.session_state.session_id,
                                       st.session_state.nickname, is_host=False)
                st.session_state.room_id = rid
                st.session_state.is_host = False
                st.session_state.view = "lobby_wait"
                st.rerun()

    with col2:
        st.subheader("游戏说明")
        st.markdown("""
        **阿瓦隆 (The Resistance: Avalon)** 是一款社交推理游戏。

        - **7 人局**：4 Good vs 3 Evil
        - 角色：Merlin, Percival, 2x Loyal Servant, Morgana, Assassin, Oberon
        - 好人目标：完成 3 次任务
        - 坏人目标：破坏 3 次任务，或在好人获胜后刺杀 Merlin

        房间主创建房间后，可以为 7 个座位分配人类玩家或 LLM 模型。
        """)


# =========================================================================== #
#  VIEW 1.5: LOBBY WAIT (non-host players waiting for game to start)
# =========================================================================== #

def view_lobby_wait():
    st.title("🏰 等待房间主开始游戏...")
    st.info(f"房间: **{st.session_state.room_id}** | 你的昵称: **{st.session_state.nickname}**")

    room = shared.get_room(st.session_state.room_id)
    if not room:
        st.error("房间不存在")
        return

    players = shared.get_players(st.session_state.room_id)
    st.markdown("### 当前房间内玩家")
    for p in players:
        tag = " 👑 (房间主)" if p["is_host"] else ""
        st.write(f"- {p['nickname']}{tag}")

    if room["status"] == "playing":
        player = shared.get_player_by_session(st.session_state.session_id)
        if player and player["seat_number"] > 0:
            st.session_state.seat_number = player["seat_number"]
            st.session_state.view = "game"
            st.rerun()

    time.sleep(3)
    st.rerun()


# =========================================================================== #
#  VIEW 2: HOST DASHBOARD
# =========================================================================== #

def view_host():
    st.title("👑 房间主控制台")
    st.info(f"房间号: **{st.session_state.room_id}** — 将此房间号分享给其他玩家")

    room = shared.get_room(st.session_state.room_id)
    if room and room["status"] == "playing":
        st.session_state.view = "game"
        st.rerun()

    players = shared.get_players(st.session_state.room_id)
    human_players = [p for p in players if not p["is_host"]]

    st.markdown("### 已连接的人类玩家")
    if human_players:
        for p in human_players:
            st.write(f"- {p['nickname']}")
    else:
        st.write("暂无其他玩家加入")

    st.markdown("---")
    st.markdown("### 座位配置 (7 人局)")
    st.caption("为每个座位指定人类玩家或 LLM 模型。角色将在开始后随机分配。")

    model_names = list(MODEL_CONFIGS.keys()) if MODEL_CONFIGS else ["(无可用模型)"]
    human_nicknames = [p["nickname"] for p in human_players]
    type_options = ["LLM 模型"] + [f"人类: {n}" for n in human_nicknames]
    if not human_nicknames:
        type_options = ["LLM 模型"]

    host_as_player = st.checkbox("房间主也作为玩家参与游戏", value=False)
    if host_as_player:
        type_options.append(f"人类: {st.session_state.nickname} (Host)")

    seat_assignments = {}
    cols = st.columns(4)
    for seat_idx in range(7):
        col = cols[seat_idx % 4]
        with col:
            st.markdown(f"**座位 {seat_idx + 1}**")
            seat_type = st.selectbox(
                "类型", type_options,
                key=f"seat_type_{seat_idx}",
                label_visibility="collapsed",
            )
            if seat_type == "LLM 模型":
                if MODEL_CONFIGS:
                    model_key = st.selectbox(
                        "模型", model_names,
                        key=f"seat_model_{seat_idx}",
                        label_visibility="collapsed",
                    )
                else:
                    model_key = None
                    st.warning("无模型配置")
                seat_assignments[seat_idx + 1] = {"type": "llm", "model_key": model_key}
            else:
                nick = seat_type.replace("人类: ", "").replace(" (Host)", "")
                seat_assignments[seat_idx + 1] = {"type": "human", "nickname": nick}

    st.markdown("---")

    if st.button("🚀 开始游戏", type="primary", use_container_width=True):
        human_seats = [s for s, v in seat_assignments.items() if v["type"] == "human"]
        llm_seats = [s for s, v in seat_assignments.items() if v["type"] == "llm"]

        if not MODEL_CONFIGS and llm_seats:
            st.error("未配置任何 LLM 模型，请先在 model_configs.json 中添加模型配置")
            return

        used_nicknames = [seat_assignments[s]["nickname"] for s in human_seats]
        if len(used_nicknames) != len(set(used_nicknames)):
            st.error("同一个人类玩家不能占据多个座位")
            return

        roles = ROLES_7P.copy()
        random.shuffle(roles)

        seat_config = {}
        for seat_num in range(1, 8):
            assignment = seat_assignments[seat_num]
            role = roles[seat_num - 1]
            faction = "Good" if role in GOOD_ROLES else "Evil"
            entry = {**assignment, "role": role, "faction": faction}
            seat_config[seat_num] = entry

        for seat_num, cfg in seat_config.items():
            if cfg["type"] == "human":
                nick = cfg["nickname"]
                matched = None
                for p in players:
                    if p["nickname"] == nick:
                        matched = p
                        break
                if matched:
                    shared.assign_seat(
                        st.session_state.room_id,
                        matched["session_id"],
                        seat_num,
                        role=cfg["role"],
                        faction=cfg["faction"],
                    )

        shared.set_room_config(
            st.session_state.room_id,
            json.dumps(seat_config, ensure_ascii=False),
            json.dumps({str(k): v for k, v in seat_config.items()}, ensure_ascii=False),
        )

        start_game(st.session_state.room_id, seat_config, MODEL_CONFIGS)

        host_player = shared.get_player_by_session(st.session_state.session_id)
        if host_player and host_player["seat_number"] > 0:
            st.session_state.seat_number = host_player["seat_number"]
            st.session_state.view = "game"
        else:
            st.session_state.view = "host_observe"

        time.sleep(1)
        st.rerun()

    if st.button("🔄 刷新玩家列表"):
        st.rerun()


# =========================================================================== #
#  VIEW 2.5: HOST OBSERVE (host is not a player, just watching)
# =========================================================================== #

def view_host_observe():
    st.title("👑 房间主观战模式")
    room = shared.get_room(st.session_state.room_id)
    if not room:
        st.error("房间不存在")
        return

    status = room["status"]
    st.info(f"房间: {st.session_state.room_id} | 状态: {status}")

    if status == "finished":
        st.success("🎉 游戏已结束！请查看 logs/Avalon/human_vs_LLM/ 目录获取完整日志。")
        if st.button("返回大厅"):
            st.session_state.view = "login"
            st.rerun()
        return

    st.markdown("### 游戏进行中...")
    st.caption("作为观战房间主，你无法看到任何玩家的私密信息。请等待游戏结束后查看日志。")

    time.sleep(4)
    st.rerun()


# =========================================================================== #
#  VIEW 3: PLAYER GAME UI
# =========================================================================== #

def view_game():
    room = shared.get_room(st.session_state.room_id)
    if not room:
        st.error("房间不存在")
        return

    player = shared.get_player_by_session(st.session_state.session_id)
    if not player or player["seat_number"] < 1:
        st.warning("你尚未被分配座位，请等待...")
        time.sleep(3)
        st.rerun()
        return

    seat = player["seat_number"]
    role = player["role"]
    faction = player["faction"]
    st.session_state.seat_number = seat

    # ---- Header ----
    faction_cls = "role-good" if faction == "Good" else "role-evil"
    st.markdown(f"""
    <div style="display:flex; align-items:center; gap:16px; margin-bottom:12px;">
        <h2 style="margin:0;">🏰 Avalon</h2>
        <span style="font-size:1.1em;">你是 <b>Player {seat}</b></span>
        <span class="role-badge {faction_cls}">{role} ({faction})</span>
    </div>
    """, unsafe_allow_html=True)

    status = room["status"]
    if status == "finished":
        st.success("🎉 游戏已结束！")
        _render_events(seat)
        if st.button("返回大厅"):
            st.session_state.view = "login"
            st.rerun()
        return

    # ---- Game events timeline ----
    _render_events(seat)

    # ---- Action area ----
    st.markdown("---")
    pending = shared.get_pending_action(st.session_state.room_id, seat)

    if pending:
        _render_action_form(pending, role, faction)
    else:
        st.info("⏳ 等待其他玩家操作中...")
        time.sleep(3)
        st.rerun()


def _render_events(seat):
    """Display game events visible to this player."""
    events = shared.get_events(
        st.session_state.room_id, seat,
        since_id=0,
    )

    if not events:
        return

    st.markdown("### 📜 游戏进程")
    container = st.container(height=400)
    with container:
        for ev in events:
            content = ev["content"]
            st.markdown(f'<div class="event-box">{content}</div>', unsafe_allow_html=True)

    if events:
        st.session_state.last_event_id = events[-1]["id"]


def _render_action_form(pending, role, faction):
    """Render the appropriate input form based on the current phase."""
    phase = pending["phase"]
    prompt_text = pending["prompt_text"]
    action_id = pending["id"]
    context = json.loads(pending["context_json"]) if pending["context_json"] else {}

    st.markdown("### 🎯 轮到你行动了！")

    with st.expander("📋 查看完整指令 (与 LLM 一致的 Prompt)", expanded=False):
        st.text(prompt_text)

    if phase == "speech":
        _form_speech(action_id, prompt_text)
    elif phase == "proposal":
        team_size = context.get("team_size", 2)
        _form_proposal(action_id, team_size)
    elif phase == "voting":
        _form_voting(action_id)
    elif phase == "execution":
        _form_execution(action_id, role, faction)
    elif phase == "assassination":
        _form_assassination(action_id)
    else:
        st.warning(f"未知阶段: {phase}")


def _form_speech(action_id, prompt_text):
    st.markdown("**💬 发言阶段** — 请表达你的观点和建议")

    observations = ""
    if "== Information you missed/observed ==" in prompt_text:
        parts = prompt_text.split("== Current Task Instruction ==")
        observations = parts[0].replace("== Information you missed/observed ==", "").strip()

    if observations:
        with st.expander("📢 最新游戏信息", expanded=True):
            st.text(observations)

    statement = st.text_area("你的发言", height=120, key="speech_input",
                             placeholder="输入你想对其他玩家说的话...")
    if st.button("📤 提交发言", type="primary", key="submit_speech"):
        if not statement.strip():
            st.error("发言不能为空")
            return
        response = json.dumps({"statement": statement.strip()}, ensure_ascii=False)
        shared.submit_response(action_id, response)
        st.success("发言已提交！")
        time.sleep(1)
        st.rerun()


def _form_proposal(action_id, team_size):
    st.markdown(f"**👥 组队阶段** — 你是队长！请选择 **{team_size}** 名队员执行任务")

    all_players = list(range(1, 8))
    selected = st.multiselect(
        f"选择 {team_size} 名队员",
        options=all_players,
        format_func=lambda x: f"Player {x}",
        max_selections=team_size,
        key="proposal_input",
    )
    if st.button("📤 提交队伍", type="primary", key="submit_proposal"):
        if len(selected) != team_size:
            st.error(f"请恰好选择 {team_size} 名队员")
            return
        response = json.dumps({"team": sorted(selected)})
        shared.submit_response(action_id, response)
        st.success("队伍已提交！")
        time.sleep(1)
        st.rerun()


def _form_voting(action_id):
    st.markdown("**🗳️ 投票阶段** — 是否同意当前队伍提案？")

    vote = st.radio(
        "你的投票",
        options=["✅ 同意 (Approve)", "❌ 反对 (Reject)"],
        key="voting_input",
    )
    if st.button("📤 提交投票", type="primary", key="submit_voting"):
        v = vote.startswith("✅")
        response = json.dumps({"vote": v})
        shared.submit_response(action_id, response)
        st.success("投票已提交！")
        time.sleep(1)
        st.rerun()


def _form_execution(action_id, role, faction):
    st.markdown("**⚔️ 任务执行阶段** — 选择任务结果")

    if faction == "Good":
        st.info("作为好人阵营，你 **必须** 选择任务成功。")
        if st.button("✅ 任务成功 (Success)", type="primary", key="submit_execution"):
            response = json.dumps({"success": True})
            shared.submit_response(action_id, response)
            st.success("已提交：任务成功")
            time.sleep(1)
            st.rerun()
    else:
        choice = st.radio(
            "你的选择",
            options=["✅ 任务成功 (Success) — 伪装为好人",
                     "❌ 任务失败 (Fail) — 破坏任务"],
            key="execution_input",
        )
        if st.button("📤 提交", type="primary", key="submit_execution"):
            success = choice.startswith("✅")
            response = json.dumps({"success": success})
            shared.submit_response(action_id, response)
            st.success("已提交！")
            time.sleep(1)
            st.rerun()


def _form_assassination(action_id):
    st.markdown("**🗡️ 刺杀阶段** — 你是刺客！选择你认为是 Merlin 的玩家")

    all_players = list(range(1, 8))
    target = st.selectbox(
        "选择刺杀目标",
        options=all_players,
        format_func=lambda x: f"Player {x}",
        key="assassination_input",
    )
    if st.button("🗡️ 确认刺杀", type="primary", key="submit_assassination"):
        response = json.dumps({"target": target})
        shared.submit_response(action_id, response)
        st.success("刺杀指令已发出！")
        time.sleep(1)
        st.rerun()


# =========================================================================== #
#  ROUTER
# =========================================================================== #

def main():
    view = st.session_state.view
    if view == "login":
        view_login()
    elif view == "lobby_wait":
        view_lobby_wait()
    elif view == "host":
        view_host()
    elif view == "host_observe":
        view_host_observe()
    elif view == "game":
        view_game()
    else:
        st.session_state.view = "login"
        st.rerun()


if __name__ == "__main__":
    main()
