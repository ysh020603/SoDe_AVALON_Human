import json

# 定义一个兼容的 Human Agent
class Agent_Human:
    def __init__(self, player_id, role):
        self.player_id = player_id
        self.role = role
        self.llm_config = {"type": "Human"}

    def call(self, messages):
        """
        messages 格式: [{"role": "user", "content": "..."}]
        """
        print(f"\n{'='*20} 🎮 人类玩家 {self.player_id} ({self.role}) {'='*20}")
        # 取出最后一条消息（即当前的Prompt）
        prompt_text = messages[-1]['content']
        print(prompt_text)
        print("-" * 30)

        is_voting = "vote" in prompt_text or "投票" in prompt_text

        while True:
            try:
                if is_voting:
                    val = input("🗳️ 请输入投票对象ID (数字): ").strip()
                    if not val.isdigit(): raise ValueError("必须输入数字")
                    return json.dumps({"vote": int(val)})
                else:
                    val = input("🗣️ 请输入描述内容: ").strip()
                    if not val: raise ValueError("内容不能为空")
                    return json.dumps({"describe": val}, ensure_ascii=False)
            except Exception as e:
                print(f"❌ 输入错误: {e}")