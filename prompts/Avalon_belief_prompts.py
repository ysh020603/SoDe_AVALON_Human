"""
Belief / opponent-modeling system prompts for Avalon.
Reuses GAME_RULE and ROLE_PROMPTS from Avalon_system_prompts without modifying that module.
"""

from prompts.Avalon_system_prompts import (
    GAME_RULE,
    JSON_OUTPUT_INSTRUCTION,
    JSON_OUTPUT_INSTRUCTION_ONLY_ASSASSIN,
    ROLE_PROMPTS,
)

BELIEF_JSON_INSTRUCTION = """
### Identity Belief Task (Parallel Mental Model)
This is NOT a game action. Your only job here is to output your current belief about **every** player's role.

**DO NOT** use Markdown code blocks (e.g., ```json); output only a single raw JSON object on one line.

**Required JSON shape:**
{
  "player_roles": {
    "1": "<role name or Unknown>",
    "2": "<role name or Unknown>",
    ...
  }
}

**Rules:**
- Keys in `player_roles` MUST be string IDs for all players from 1 to N (N = total player count). No omissions.
- For yourself (`player_id` in [Your ID]): set the value to your true role name (which you know).
- For players whose identity is explicitly revealed to you by the rules (e.g., the evil players known to Merlin, the two candidates seen by Percival, evil teammates): set the value to the confirmed role. If there is identity ambiguity that cannot be resolved into a single role based on available game information, uniformly output "Unknown".
- For all other players: you must infer a unique and definite role identity based on existing game information. Only when there are no clues at all and no valid inference can be made may you uniformly output "Unknown".
- Each player can only be assigned one role per judgment; multiple or ambiguous roles are not allowed.
- Use the standard in-game role terms: Merlin, Percival, Loyal Servant, Morgana, Assassin, Mordred, Oberon, Minion.
""".strip()


def get_avalon_belief_system_prompt(role_name, player_count, board_config, **kwargs):
    """
    Same structure as get_avalon_prompt: role block still uses the normal game JSON output specs,
    with BELIEF_JSON_INSTRUCTION appended so identity-belief calls share full game-task context.
    """
    base = GAME_RULE.format(
        player_count=player_count,
        board_config_description=board_config,
    )

    specific = ROLE_PROMPTS.get(role_name, ROLE_PROMPTS["Loyal Servant"])
    game_instruction = (
        JSON_OUTPUT_INSTRUCTION_ONLY_ASSASSIN
        if role_name == "Assassin"
        else JSON_OUTPUT_INSTRUCTION
    )
    kwargs["output_instruction"] = game_instruction + "\n\n" + BELIEF_JSON_INSTRUCTION

    try:
        formatted_specific = specific.format(**kwargs)
    except KeyError as e:
        print(f"[Warning] Belief prompt formatting missing key: {e}")
        formatted_specific = specific

    return base + "\n" + formatted_specific
