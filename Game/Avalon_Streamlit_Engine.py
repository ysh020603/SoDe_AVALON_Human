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
        return super().run_game()
