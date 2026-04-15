import os
import json
import glob
from collections import defaultdict

# ================= 配置区域 =================

BASE_LOG_DIR = "SoDe_Avalon/logs/Avalon" 

LOG_TAG = "Qwen3-235B-A22B_VS_0_6B_avalon"

# 模型名称标识 (必须是 json config name 字段中包含的字符串)
# 对应 Shell 脚本里的 MODEL_A_NAME 和 MODEL_B_NAME
MODEL_A_NAME = "Qwen3-235B-A22B"
MODEL_B_NAME = "0_6B_avalon" 
# ===========================================

def get_faction(role):
    """根据角色名判断阵营"""
    good_roles = ["Merlin", "Percival", "Loyal Servant"]
    evil_roles = ["Morgana", "Assassin", "Mordred", "Oberon", "Minion"]
    
    if role in good_roles: return "Good"
    if role in evil_roles: return "Evil"
    return "Unknown"

def analyze():
    # 初始化统计数据结构
    # 新增 'assassin_wins' 字段
    stats = {
        MODEL_A_NAME: {
            "total": 0, "wins": 0, 
            "good_plays": 0, "good_wins": 0, 
            "evil_plays": 0, "evil_wins": 0, 
            "assassin_wins": 0  # <--- 新增：刺杀获胜计数
        },
        MODEL_B_NAME: {
            "total": 0, "wins": 0, 
            "good_plays": 0, "good_wins": 0, 
            "evil_plays": 0, "evil_wins": 0, 
            "assassin_wins": 0  # <--- 新增：刺杀获胜计数
        }
    }

    # 构建搜索路径
    search_path = os.path.join(BASE_LOG_DIR, LOG_TAG, "**", "*.json")
    json_files = glob.glob(search_path, recursive=True)

    print(f"正在扫描目录: {os.path.join(BASE_LOG_DIR, LOG_TAG)}")
    print(f"找到日志文件数: {len(json_files)}")

    valid_files_count = 0

    for file_path in json_files:
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # 1. 检查游戏是否结束
            final_res = data.get("final_result")
            if not final_res or final_res == "unfinished":
                continue 

            valid_files_count += 1
            
            # 判定获胜阵营
            # evil_win_missions 或 evil_win_assassination 都是 Evil 赢
            winning_faction = "Good" if final_res == "good_win" else "Evil"
            
            # 判定是否通过刺杀获胜
            is_assassination_win = (final_res == "evil_win_assassination")

            # 2. 遍历该局所有玩家
            agents = data.get("agents_info", {})
            for p_key, info in agents.items():
                
                # --- 提取模型名称 ---
                config = info.get("config", {})
                model_name_in_log = ""
                
                if isinstance(config, dict):
                    model_name_in_log = config.get("name", "")
                else:
                    model_name_in_log = str(config)
                
                # --- 匹配当前玩家属于哪个模型 ---
                current_model_key = None
                if MODEL_A_NAME in model_name_in_log:
                    current_model_key = MODEL_A_NAME
                elif MODEL_B_NAME in model_name_in_log:
                    current_model_key = MODEL_B_NAME
                
                if current_model_key:
                    role = info.get("role")
                    faction = get_faction(role)
                    
                    s = stats[current_model_key]
                    s["total"] += 1
                    
                    # 统计分阵营胜率
                    if faction == "Good":
                        s["good_plays"] += 1
                        if winning_faction == "Good":
                            s["good_wins"] += 1
                            s["wins"] += 1
                    elif faction == "Evil":
                        s["evil_plays"] += 1
                        if winning_faction == "Evil":
                            s["evil_wins"] += 1
                            s["wins"] += 1
                            
                            # 统计刺杀获胜 (只有坏人赢了，且是刺杀赢的才算)
                            if is_assassination_win:
                                s["assassin_wins"] += 1

        except Exception as e:
            print(f"跳过文件 {os.path.basename(file_path)}: {e}")

    # ================= 打印报表 =================
    print(f"\n{'='*115}")
    print(f"  Avalon 实验结果统计")
    print(f" 目录: {LOG_TAG}")
    print(f" 有效对局数: {valid_files_count}")
    print(f"{'='*115}")
    
    # 修改表头，增加刺杀列
    headers = ["Model Name", "Role Count", "Overall WR", "Good WR (Win/Total)", "Evil WR (Win/Total)", "Assassin Wins (Count/EvilWins)"]
    print(f"{headers[0]:<25} | {headers[1]:<10} | {headers[2]:<10} | {headers[3]:<20} | {headers[4]:<20} | {headers[5]:<25}")
    print("-" * 115)

    for model_name in [MODEL_A_NAME, MODEL_B_NAME]:
        d = stats[model_name]
        total = d["total"]
        
        if total == 0:
            print(f"{model_name:<25} | {'0':<10} | {'N/A':<10} | {'N/A':<20} | {'N/A':<20} | {'N/A':<25}")
            continue

        # 计算胜率
        overall_wr = (d["wins"] / total) * 100
        
        good_wr_str = "N/A"
        if d["good_plays"] > 0:
            g_rate = (d["good_wins"] / d["good_plays"]) * 100
         
            good_wr_str = f"{g_rate:5.1f}% ({d['good_wins']/4}/{d['good_plays']/4})"
            
        evil_wr_str = "N/A"
        assassin_str = "N/A"
        if d["evil_plays"] > 0:
            e_rate = (d["evil_wins"] / d["evil_plays"]) * 100
            evil_wr_str = f"{e_rate:5.1f}% ({d['evil_wins']/3}/{d['evil_plays']/3})"
            
            # 计算刺杀占坏人胜利的比例
            ass_wins = d['assassin_wins']
            evil_total_wins = d['evil_wins']
            if evil_total_wins > 0:
                ass_rate = (ass_wins / evil_total_wins) * 100
                assassin_str = f"{ass_wins/3} ({ass_rate:.1f}%)"
            else:
                assassin_str = f"{ass_wins} (0.0%)"

        print(f"{model_name:<25} | {total*2/7:<10} | {overall_wr:5.1f}%    | {good_wr_str:<20} | {evil_wr_str:<20} | {assassin_str:<25}")

    print(f"{'='*115}\n")
    

if __name__ == "__main__":
    analyze()