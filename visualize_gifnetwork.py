import pandas as pd
import networkx as nx
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation
import os

# ================= 配置区域 =================
input_csv = 'soj_ew_radar_interactions.csv'
output_gif = 'network_200s.gif'  # 输出的文件名
max_time = 200.0  # 【修改点1】设置截止时间为200秒
# ===========================================

# 检查文件是否存在
if not os.path.exists(input_csv):
    print(f"错误：找不到文件 {input_csv}。请先运行数据提取脚本。")
    exit()

# 1. 读取数据
df = pd.read_csv(input_csv)

# 2. 数据清洗
detection_col = '8'
if detection_col in df.columns:
    df[detection_col] = df[detection_col].astype(str).str.upper()
else:
    print(f"警告：找不到列 '{detection_col}'，请检查CSV表头。")
    exit()

# 【关键步骤】过滤掉 200秒 之后的数据
df = df[df['time（时间）'] <= max_time]

if df.empty:
    print(f"警告：在 0-{max_time} 秒内没有找到符合条件的数据。")
    exit()

# 3. 按时间分组
grouped = df.groupby('time（时间）')
time_steps = sorted(grouped.groups.keys())
print(f"即将生成动画，共包含 {len(time_steps)} 个时间帧 (0s - {max_time}s)...")

# 4. 初始化图
G = nx.Graph()
pos = None  # 初始位置设为 None (修复之前的报错)
fig, ax = plt.subplots(figsize=(10, 8))


def get_node_color(node_name):
    """设置颜色"""
    name = str(node_name).lower()
    if 'radar' in name:
        return 'red'
    elif 'soj' in name:
        return 'blue'
    return 'green'


def update(frame_idx):
    ax.clear()

    current_time = time_steps[frame_idx]

    # 获取当前帧数据
    if current_time in grouped.groups:
        current_data = grouped.get_group(current_time)

        # 添加边
        for _, row in current_data.iterrows():
            if row[detection_col] == 'TRUE':
                u = row['platform（所有者或源平台）']
                v = row['interactor']
                if pd.notna(u) and pd.notna(v):
                    G.add_edge(u, v)

    # 如果图是空的，处理
    if G.number_of_nodes() == 0:
        ax.set_title(f"Time: {current_time} (No Data)")
        return

    # 布局算法
    global pos
    pos = nx.spring_layout(G, pos=pos, k=0.5, iterations=50)

    colors = [get_node_color(node) for node in G.nodes()]

    nx.draw(G, pos, ax=ax,
            with_labels=True,
            node_color=colors,
            node_size=600,
            font_color='white',
            font_size=9,
            edge_color='gray',
            width=1.5)

    ax.set_title(f"Combat Network - Time: {current_time}s", fontsize=14)

    # 打印进度条效果
    print(f"正在处理第 {frame_idx + 1}/{len(time_steps)} 帧...", end='\r')


# 5. 生成并保存动画
ani = FuncAnimation(fig, update, frames=len(time_steps), interval=200, repeat=False)

print("\n开始保存GIF，请稍候（文件生成需要一些时间）...")

# 【修改点2】使用 pillow 保存，不需要安装额外软件
# fps=5 表示每秒播放5帧，你可以根据需要调整速度
try:
    ani.save(output_gif, writer='pillow', fps=3)
    print(f"\n✅ 成功！动画已保存为: {os.path.abspath(output_gif)}")
except Exception as e:
    print(f"\n❌ 保存失败: {e}")
    print("提示：请确保安装了 pillow 库 (pip install Pillow)")