"""
Agent_Streamlit_Human: A human player agent for the Streamlit-based Avalon platform.

Inherits from Agent to reuse _construct_instruction(), ensuring the human player
sees exactly the same prompt as an LLM would. Instead of calling an LLM, it writes
the prompt to the shared SQLite state and blocks until the frontend submits a response.
"""

import json
from typing import Dict, Any, List

from Agents.Agent import Agent


class Agent_Streamlit_Human(Agent):
    def __init__(self, player_id: int, role: str, nickname: str,
                 shared_state, room_id: str):
        super().__init__(
            player_id=player_id,
            role=role,
            llm_config={"name": f"Human_{nickname}", "type": "human"},
            llm_func=None,
        )
        self.nickname = nickname
        self.shared_state = shared_state
        self.room_id = room_id

    def act(self, memory: List[Dict[str, str]], phase: str,
            observations: List[str], context: Dict[str, Any] = None,
            game_condition: Dict[str, Any] = None) -> str:
        if context is None:
            context = {}

        full_user_content = ""
        if observations:
            full_user_content += "== Information you missed/observed ==\n"
            full_user_content += "\n".join(observations) + "\n\n"

        instruction = self._construct_instruction(phase, context)
        full_user_content += "== Current Task Instruction ==\n"
        full_user_content += instruction

        memory.append({"role": "user", "content": full_user_content})

        action_id = self.shared_state.post_pending_action(
            room_id=self.room_id,
            seat_number=self.player_id,
            phase=phase,
            prompt_text=full_user_content,
            context_json=json.dumps(context, ensure_ascii=False),
        )

        response = self.shared_state.wait_for_response(action_id, timeout=600)

        memory.append({"role": "assistant", "content": response})
        return response
