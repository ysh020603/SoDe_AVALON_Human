from typing import Any, Dict, List, Optional

from Agents.Agent import Agent

# Must match Agent.act delimiter for replacing only the task tail on the current user turn.
_TASK_INSTRUCTION_MARKER = "== Current Task Instruction ==\n"


class BeliefAgent(Agent):
    """
    Identity-belief LLM calls reuse the same dialogue prefix as the main game thread: belief
    system prompt, then copied user/assistant history without the latest game assistant turn;
    the current user message keeps its observation prefix while the task block is swapped for
    the belief JSON instruction.
    """

    def __init__(
        self,
        player_id: int,
        role: str,
        llm_config: Dict[str, Any],
        llm_func,
    ):
        super().__init__(player_id, role, llm_config, llm_func)
        self.belief_system_content: str = ""

    def init_belief_system(self, system_content: str) -> None:
        self.belief_system_content = system_content

    def _construct_belief_instruction(self, phase: str, context: Dict[str, Any]) -> str:
        if context is None:
            context = {}

        if phase == "speech":
            return """
[Identity Belief Task — Discussion Phase]
Given the dialogue and observations above (same context as your main game turn, before you output your speech there).
Update your belief about every player's role.
Output only the JSON object in the format specified in the system prompt (player_roles for all players).
""".strip()

        elif phase == "proposal":
            ts = context.get("team_size", 0)
            return f"""
[Identity Belief Task — Team Proposal Phase]
You are the Leader and must propose a team of {ts} players for the quest (handled in the main game channel).
Given the context above, output your current belief about every player's role as JSON (player_roles for all players).
""".strip()

        elif phase == "voting":
            rid = context.get("round", 0)
            return f"""
[Identity Belief Task — Voting Phase]
Round {rid}: you are about to vote on the proposed team (main game channel).
Given the context above, output your current belief about every player's role as JSON (player_roles for all players).
""".strip()

        elif phase == "execution":
            rid = context.get("round", 0)
            return f"""
[Identity Belief Task — Mission Phase]
Round {rid}: you may execute the mission (main game channel).
Given the context above, output your current belief about every player's role as JSON (player_roles for all players).
""".strip()

        elif phase == "assassination":
            return """
[Identity Belief Task — Assassination Phase]
The Good faction won the quests; you may choose an assassination target (main game channel).
Given the context above, output your current belief about every player's role as JSON (player_roles for all players).
""".strip()

        return """
[Identity Belief Task]
Given the context above, output your current belief about every player's role as JSON (player_roles for all players).
""".strip()

    def infer_identities(
        self,
        phase: str,
        main_memory: List[Dict[str, str]],
        context: Optional[Dict[str, Any]] = None,
    ) -> str:
        if context is None:
            context = {}

        if len(main_memory) < 3:
            print(
                f"[BeliefAgent] infer_identities: memory too short (len={len(main_memory)}), "
                "returning empty belief JSON."
            )
            return "{}"

        if main_memory[-1].get("role") != "assistant" or main_memory[-2].get("role") != "user":
            print(
                "[BeliefAgent] infer_identities: expected last messages user then assistant; "
                "returning empty belief JSON."
            )
            return "{}"

        history = [{"role": m["role"], "content": m["content"]} for m in main_memory[1:-1]]
        raw_user = main_memory[-2]["content"]

        if _TASK_INSTRUCTION_MARKER in raw_user:
            prefix, _, _ = raw_user.partition(_TASK_INSTRUCTION_MARKER)
            new_user_content = (
                prefix
                + _TASK_INSTRUCTION_MARKER
                + self._construct_belief_instruction(phase, context)
            )
        else:
            print(
                "[BeliefAgent] infer_identities: missing task marker in user content; "
                "appending belief task block."
            )
            new_user_content = (
                raw_user.rstrip()
                + "\n\n"
                + _TASK_INSTRUCTION_MARKER
                + self._construct_belief_instruction(phase, context)
            )

        messages: List[Dict[str, str]] = [
            {"role": "system", "content": self.belief_system_content}
        ]
        messages.extend(history)
        messages.append({"role": "user", "content": new_user_content})
        return self.call(messages)
