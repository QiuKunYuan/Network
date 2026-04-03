#!/usr/bin/env python3
"""
生成综合复杂网络可视化图
使用项目已有的 CombatNetworkBuilder 构建 4 层网络，
输出 complex_network.png（Spring + Circular 双视图）
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from data_processor import AFSIMDataProcessor
from network_builder import CombatNetworkBuilder
import networkx as nx
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np

CSV_PATH = '/Users/qky/Desktop/HZ/111.csv'
OUT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'outputs', 'complex_network.png')

# ── 构建网络 ──────────────────────────────────────────────────────────────────
proc    = AFSIMDataProcessor(CSV_PATH)
builder = CombatNetworkBuilder()
nets    = builder.build_multi_layer_network(proc)

# 用综合网络作为主图，同时保留各子层信息
G_integrated = nets.get('integrated', nx.Graph())
G_sensor      = nets.get('sensor',      nx.DiGraph())
G_command     = nets.get('command',     nx.DiGraph())
G_comm        = nets.get('communication', nx.Graph())

print("网络构建结果:")
for k, v in nets.items():
    print(f"  {k}: {v.number_of_nodes()} 节点, {v.number_of_edges()} 边")

# 如果综合网络节点太少，用 sensor 网络补充
if G_integrated.number_of_nodes() < 5:
    print("综合网络节点不足，改用 sensor 网络")
    G_integrated = G_sensor.to_undirected()

# ── 节点着色（按名称关键字判断类型）────────────────────────────────────────
TYPE_COLOR = {
    'radar':   '#1565c0',
    'soj':     '#d84315',
    'ucav':    '#2e7d32',
    'sam':     '#c62828',
    'iads':    '#2e7d32',
    'cmdr':    '#2e7d32',
    'command': '#2e7d32',
    'default': '#546e7a',
}
TYPE_LABEL = {
    'radar': 'Radar/Sensor', 'soj': 'EW/SOJ',
    'ucav': 'UCAV/Command', 'sam': 'SAM/Weapon',
    'iads': 'IADS/Command', 'default': 'Other',
}

def node_type(n):
    nl = n.lower()
    for k in ('sam', 'soj', 'ucav', 'iads', 'cmdr', 'command', 'radar'):
        if k in nl:
            return k
    return 'default'

def short_label(n):
    parts = n.split('_')
    if len(parts) >= 2 and parts[0].isdigit():
        rest = '_'.join(p for p in parts[1:] if p not in ('large', 'small', 'medium'))
        return f"{parts[0]}_{rest}"[:12]
    return n[:12]

# ── 画布 ──────────────────────────────────────────────────────────────────────
fig, axes = plt.subplots(1, 2, figsize=(24, 12), facecolor='#0d1117')
fig.patch.set_facecolor('#0d1117')

deg      = dict(G_integrated.degree())
max_deg  = max(deg.values()) if deg else 1
n_colors = [TYPE_COLOR.get(node_type(n), TYPE_COLOR['default']) for n in G_integrated.nodes()]
n_sizes  = [100 + 500 * (deg.get(n, 0) / max_deg) for n in G_integrated.nodes()]
labels   = {n: short_label(n) for n in G_integrated.nodes()}

# 边分类
intra_edges, inter_edges = [], []
for u, v, d in G_integrated.edges(data=True):
    layers = d.get('layers', [])
    if len(layers) > 1:
        inter_edges.append((u, v))
    else:
        intra_edges.append((u, v))

# ── 左图：Spring Layout ───────────────────────────────────────────────────────
ax1 = axes[0]
ax1.set_facecolor('#0d1117')
pos1 = nx.spring_layout(G_integrated, seed=42, k=1.2, iterations=80)

nx.draw_networkx_edges(G_integrated, pos1, edgelist=intra_edges, ax=ax1,
                       alpha=0.25, edge_color='#546e7a', width=0.8)
nx.draw_networkx_edges(G_integrated, pos1, edgelist=inter_edges, ax=ax1,
                       alpha=0.55, edge_color='#f9a825', width=1.6, style='dashed')
nx.draw_networkx_nodes(G_integrated, pos1, ax=ax1,
                       node_color=n_colors, node_size=n_sizes,
                       alpha=0.92, edgecolors='white', linewidths=0.7)
nx.draw_networkx_labels(G_integrated, pos1, labels=labels, ax=ax1,
                        font_size=5.5, font_color='#e6edf3', font_weight='bold')

# 度中心性热力圈
dc = nx.degree_centrality(G_integrated)
top5 = sorted(dc.items(), key=lambda x: x[1], reverse=True)[:5]
for n, c in top5:
    if n in pos1:
        x, y = pos1[n]
        circle = plt.Circle((x, y), 0.06 * c * 3, color='#f9a825',
                             fill=False, lw=1.5, alpha=0.5)
        ax1.add_patch(circle)

ax1.set_title('Integrated Combat Network  —  Spring Layout\n(gold dashed = multi-layer edges)',
              color='#e6edf3', fontsize=12, fontweight='bold', pad=14)
ax1.set_axis_off()

# ── 右图：Kamada-Kawai Layout ─────────────────────────────────────────────────
ax2 = axes[1]
ax2.set_facecolor('#0d1117')

try:
    pos2 = nx.kamada_kawai_layout(G_integrated)
except Exception:
    pos2 = nx.circular_layout(G_integrated)

nx.draw_networkx_edges(G_integrated, pos2, edgelist=intra_edges, ax=ax2,
                       alpha=0.22, edge_color='#546e7a', width=0.8)
nx.draw_networkx_edges(G_integrated, pos2, edgelist=inter_edges, ax=ax2,
                       alpha=0.55, edge_color='#f9a825', width=1.6, style='dashed')
nx.draw_networkx_nodes(G_integrated, pos2, ax=ax2,
                       node_color=n_colors, node_size=n_sizes,
                       alpha=0.92, edgecolors='white', linewidths=0.7)
nx.draw_networkx_labels(G_integrated, pos2, labels=labels, ax=ax2,
                        font_size=5.5, font_color='#e6edf3', font_weight='bold')

ax2.set_title('Integrated Combat Network  —  Kamada-Kawai Layout\n(energy-minimized positioning)',
              color='#e6edf3', fontsize=12, fontweight='bold', pad=14)
ax2.set_axis_off()

# ── 图例 ──────────────────────────────────────────────────────────────────────
legend_items = [
    mpatches.Patch(color='#1565c0', label='Radar / Sensor'),
    mpatches.Patch(color='#d84315', label='EW / SOJ'),
    mpatches.Patch(color='#2e7d32', label='Command / UCAV'),
    mpatches.Patch(color='#c62828', label='SAM / Weapon'),
    mpatches.Patch(color='#546e7a', label='Other'),
    plt.Line2D([0],[0], color='#546e7a', lw=1.5, label='Single-layer edge'),
    plt.Line2D([0],[0], color='#f9a825', lw=1.5, linestyle='dashed', label='Multi-layer edge'),
]
fig.legend(handles=legend_items, loc='lower center', ncol=7,
           facecolor='#161b22', edgecolor='#30363d',
           labelcolor='#e6edf3', fontsize=9.5, framealpha=0.92,
           bbox_to_anchor=(0.5, 0.01))

plt.tight_layout(rect=[0, 0.07, 1, 1])
os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
plt.savefig(OUT_PATH, dpi=120, bbox_inches='tight', facecolor='#0d1117')
plt.close()
print(f'Saved → {OUT_PATH}')
