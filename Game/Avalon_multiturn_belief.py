import re
from collections import Counter
from typing import Dict, List, Tuple

from Agents.AgentWithBelief import BeliefAgent
from Game.Avalon_multiturn import Game_Avalon_Multiturn
from prompts.Avalon_belief_prompts import get_avalon_belief_system_prompt
from Tool.Json_extractor import extract_json


class Game_Avalon_MultiturnWithBelief(Game_Avalon_Multiturn):
    """
    Extends the base multiturn game with parallel identity-belief LLM calls.
    Belief uses the same dialogue prefix as the main thread (belief system + history without the
    latest game assistant), with the current user task block swapped for identity JSON output.
    Each decision record in game_condition gains optional identity_belief.player_roles
    via _post_call_identity_belief + parent _consume_identity_belief_snapshot().
    """

    def __init__(self, agents, log_tag: str = ""):
        super().__init__(agents, log_tag=log_tag)
        self._init_belief_system_prompts()

    def _board_description(self) -> str:
        role_counts = Counter([a.role for a in self.agents])
        board_desc = ", ".join([f"{count} {role}" for role, count in role_counts.items()])
        quest_config_list = self.quest_configs[self.player_count]
        quest_details = []
        for i, num in enumerate(quest_config_list):
            count = abs(num)
            fails_needed = 2 if num < 0 else 1
            detail = f"Quest {i+1}: {count} players"
            if fails_needed > 1:
                detail += " (requires 2 fail cars to fail mission)"
            quest_details.append(detail)
        board_desc += f". Mission Configuration: {', '.join(quest_details)}."
        return board_desc

    def _belief_kwargs_from_game_system_message(self, agent: BeliefAgent) -> Dict:
        """
        Build the same kwargs as get_avalon_prompt, using the already-generated game system
        message so visibility strings (esp. Percival's shuffled Merlin/Morgana order) match.
        """
        pid = agent.player_id
        role = agent.role
        text = self.agent_memories[pid][0]["content"]
        kwargs: Dict = {"player_id": pid}
        visible_evils_for_evil = [p for p in self.evils if self.role_map[p] != "Oberon"]
        merlin_sees = [p for p in self.evils if self.role_map[p] != "Mordred"]

        if role == "Merlin":
            m = re.search(r"You can see the Bad Guys:\s*(\[[^\]]+\])", text)
            kwargs["seen_evils"] = m.group(1) if m else str(merlin_sees)
        elif role == "Percival":
            m = re.search(r"might be Merlin:\s*(\[[^\]]+\])", text)
            kwargs["seen_merlin_morgana"] = m.group(1) if m else str(
                [p for p, r in self.role_map.items() if r in ("Merlin", "Morgana")]
            )
        elif role in self.evil_roles and role != "Oberon":
            m = re.search(r"Teammates:\s*(\[[^\]]+\])", text)
            teammates = [p for p in visible_evils_for_evil if p != pid]
            kwargs["teammates"] = m.group(1) if m else str(teammates)

        return kwargs

    def _init_belief_system_prompts(self) -> None:
        board_desc = self._board_description()

        for agent in self.agents:
            if not isinstance(agent, BeliefAgent):
                continue
            kwargs = self._belief_kwargs_from_game_system_message(agent)

            sys_msg = get_avalon_belief_system_prompt(
                role_name=agent.role,
                player_count=self.player_count,
                board_config=board_desc,
                **kwargs,
            )
            agent.init_belief_system(sys_msg)

    def call_agent(self, pid, phase, context=None) -> Tuple[str, List]:
        if context is None:
            context = {}
        self._post_call_identity_belief = None
        response, messages = super().call_agent(pid, phase, context)
        agent = self.get_agent(pid)
        if isinstance(agent, BeliefAgent):
            belief_raw = agent.infer_identities(phase, self.agent_memories[pid], context)
            parsed = extract_json(belief_raw, key=None)
            pr = None
            if isinstance(parsed, dict):
                pr = parsed.get("player_roles")
            self._post_call_identity_belief = {"player_roles": pr}
        return response, messages
