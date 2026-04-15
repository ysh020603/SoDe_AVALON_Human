"""
Game_Avalon_Streamlit: Wrapper around the core Avalon engine for the Streamlit platform.

Inherits Game_Avalon_Multiturn with minimal overrides:
  - _broadcast(): additionally pushes events to SQLite for frontend consumption
  - save_log():   redirects log output to logs/Avalon/human_vs_LLM/
"""

import os
from typing import List

from Game.Avalon_multiturn import Game_Avalon_Multiturn
from Agents.Agent import Agent


class Game_Avalon_Streamlit(Game_Avalon_Multiturn):
    def __init__(self, agents: List[Agent], log_tag: str = "",
                 shared_state=None, room_id: str = None):
        if len(agents) != 7:
            raise ValueError("Streamlit mode only supports 7-player games.")

        super().__init__(agents, log_tag=log_tag)
        self.shared_state = shared_state
        self.room_id = room_id

    def _broadcast(self, text, exclude=[]):
        super()._broadcast(text, exclude)

        if self.shared_state and self.room_id:
            for pid in self.agent_memories:
                if pid not in exclude:
                    self.shared_state.push_event(
                        self.room_id, pid, "broadcast", text
                    )

    def save_log(self):
        original_log_tag = self.log_tag
        self.log_tag = (
            os.path.join("human_vs_LLM", self.log_tag) if self.log_tag else "human_vs_LLM"
        )
        try:
            super().save_log()
        finally:
            self.log_tag = original_log_tag

        if self.shared_state and self.room_id:
            self.shared_state.update_room_status(self.room_id, "finished")

    def run_game(self):
        if self.shared_state and self.room_id:
            self.shared_state.update_room_status(self.room_id, "playing")
            self._push_private_info_to_humans()
        return super().run_game()

    def _push_private_info_to_humans(self):
        """Push each human player's system prompt (role perspective) to their frontend."""
        from Agents.Agent_Streamlit_Human import Agent_Streamlit_Human
        for agent in self.agents:
            if isinstance(agent, Agent_Streamlit_Human):
                pid = agent.player_id
                memory = self.agent_memories.get(pid, [])
                if memory and memory[0]["role"] == "system":
                    sys_prompt = memory[0]["content"]
                    show_text = sys_prompt.split("[Game Environment]:")[1].split("[Faction Explanations]:")[0] + sys_prompt.split("[Visibility]:")[1].split("[Strategy]:")[0]
                    self.shared_state.push_event(
                        self.room_id,
                        pid,
                        "private_info",
                        f"<b>👁️ 你的角色设定与视角：</b><br>"
                        f"<pre style='white-space: pre-wrap; font-family: inherit;'>"
                        f"{show_text}</pre>",
                    )
