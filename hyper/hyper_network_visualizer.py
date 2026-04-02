# src/hyper/hyper_network_visualizer.py

import matplotlib.pyplot as plt
import networkx as nx
import numpy as np
from mpl_toolkits.mplot3d import Axes3D
from typing import Dict, Any


class HyperNetworkVisualizer:
    def __init__(self, figsize=(12, 12)):
        self.figsize = figsize
        self.layer_z = {'sensor': 0, 'ew': 1.2, 'command': 2.4, 'weapon': 3.6}  # 稍微拉开间距
        self.layer_colors = {
            'sensor': '#3498db', 'command': '#2ecc71',
            'weapon': '#e74c3c', 'ew': '#f39c12'
        }
        self.pos_cache = {}

    # def visualize_hyper_network(self, hyper_network_data: Dict[str, Any], save_path: str = None, azim: int = 35):
    #     H = hyper_network_data.get('hyper_network')
    #     if H is None: return
    #
    #     fig = plt.figure(figsize=self.figsize)
    #     ax = fig.add_subplot(111, projection='3d')
    #
    #     # 1. 坐标锁定
    #     new_nodes = [n for n in H.nodes() if n not in self.pos_cache]
    #     if new_nodes:
    #         for node in new_nodes:
    #             self.pos_cache[node] = (np.random.uniform(-1, 1), np.random.uniform(-1, 1))
    #
    #     # 2. 绘制层级底座平面 (这是增强层次感的关键)
    #     for layer_name, z_val in self.layer_z.items():
    #         # 绘制一个正方形平面
    #         x_surf = np.array([[-1.2, 1.2], [-1.2, 1.2]])
    #         y_surf = np.array([[-1.2, -1.2], [1.2, 1.2]])
    #         z_surf = np.full((2, 2), z_val)
    #         ax.plot_surface(x_surf, y_surf, z_surf, alpha=0.03, color=self.layer_colors[layer_name])
    #
    #         # 在平面角落下标层名
    #         ax.text(-1.2, -1.2, z_val, f" {layer_name.upper()} LAYER",
    #                 color=self.layer_colors[layer_name], fontsize=12, fontweight='bold')
    #
    #     # 3. 绘制边和节点 (逻辑同前，确保使用修正后的 layer 属性)
    #     pos_3d = {n: (self.pos_cache[n][0], self.pos_cache[n][1],
    #                   self.layer_z.get(H.nodes[n].get('layer', 'sensor'), 0)) for n in H.nodes()}
    #
    #     for u, v, data in H.edges(data=True):
    #         x, y, z = zip(pos_3d[u], pos_3d[v])
    #         is_inter = data.get('type') == 'inter'
    #         ax.plot(x, y, z, color='#e74c3c' if is_inter else '#5dade2',
    #                 alpha=0.6 if is_inter else 0.1, linewidth=1.2)
    #
    #     for layer_name, color in self.layer_colors.items():
    #         nodes = [n for n, d in H.nodes(data=True) if d.get('layer') == layer_name]
    #         if nodes:
    #             xs, ys, zs = zip(*[pos_3d[n] for n in nodes])
    #             ax.scatter(xs, ys, zs, c=color, s=200, edgecolors='white', alpha=0.9, depthshade=True)
    #
    #     # 4. 【关键步骤】：锁定比例和范围，防止“塌陷”
    #     ax.set_box_aspect((1, 1, 1.2))  # X:Y:Z 的物理比例，让 Z 轴挺拔起来
    #     ax.set_xlim(-1.3, 1.3)
    #     ax.set_ylim(-1.3, 1.3)
    #     ax.set_zlim(-0.2, 4.0)
    #     ax.set_axis_off()
    #
    #
    #     # 视角微调：让 3D 感更强
    #     ax.view_init(elev=22, azim=azim)
    #
    #     if save_path:
    #         plt.savefig(save_path, dpi=150, bbox_inches='tight', facecolor='#f0f2f6')
    #     plt.close(fig)

    def visualize_hyper_network(self, hyper_network_data: Dict[str, Any], save_path: str = None,
                                azim: int = 35, gravity_node: str = None):
        H = hyper_network_data.get('hyper_network')
        if H is None: return

        fig = plt.figure(figsize=self.figsize)
        ax = fig.add_subplot(111, projection='3d')

        # 1. 坐标锁定逻辑
        new_nodes = [n for n in H.nodes() if n not in self.pos_cache]
        if new_nodes:
            for node in new_nodes:
                self.pos_cache[node] = (np.random.uniform(-1, 1), np.random.uniform(-1, 1))

        # 2. 绘制层级底座平面
        for layer_name, z_val in self.layer_z.items():
            x_surf = np.array([[-1.2, 1.2], [-1.2, 1.2]])
            y_surf = np.array([[-1.2, -1.2], [1.2, 1.2]])
            z_surf = np.full((2, 2), z_val)
            ax.plot_surface(x_surf, y_surf, z_surf, alpha=0.03, color=self.layer_colors[layer_name])
            ax.text(-1.2, -1.2, z_val, f" {layer_name.upper()} LAYER",
                    color=self.layer_colors[layer_name], fontsize=10, fontweight='bold')

        # 3. 计算 3D 坐标
        pos_3d = {n: (self.pos_cache[n][0], self.pos_cache[n][1],
                      self.layer_z.get(H.nodes[n].get('layer', 'sensor'), 0)) for n in H.nodes()}

        # 4. 绘制连边
        for u, v, data in H.edges(data=True):
            x, y, z = zip(pos_3d[u], pos_3d[v])
            is_inter = data.get('type') == 'inter'
            ax.plot(x, y, z, color='#e74c3c' if is_inter else '#5dade2',
                    alpha=0.6 if is_inter else 0.1, linewidth=1.2)

        # 5. 分层绘制节点
        for layer_name, color in self.layer_colors.items():
            nodes = [n for n, d in H.nodes(data=True) if d.get('layer') == layer_name]
            if nodes:
                xs, ys, zs = zip(*[pos_3d[n] for n in nodes])
                ax.scatter(xs, ys, zs, c=color, s=150, edgecolors='white', alpha=0.7, depthshade=True)

        # --- 新增：动态展示重心逻辑 ---
        if gravity_node and gravity_node in pos_3d:
            gx, gy, gz = pos_3d[gravity_node]
            # 1. 绘制重心的“发光层”（一个更大的半透明圆点）
            ax.scatter([gx], [gy], [gz], color='yellow', s=600, alpha=0.3, edgecolors='orange', linewidth=2)
            # 2. 绘制重心的垂直投影线，帮助定位其在哪一层
            ax.plot([gx, gx], [gy, gy], [-0.2, gz], color='orange', linestyle=':', linewidth=1.5, alpha=0.6)
            # 3. 添加文字标注
            ax.text(gx, gy, gz + 0.2, "🌟 CENTER OF GRAVITY", color='#d35400',
                    fontsize=12, fontweight='bold', ha='center',
                    bbox=dict(facecolor='white', alpha=0.6, edgecolor='none', pad=1))
        # ----------------------------

        # 6. 视图设置
        ax.set_box_aspect((1, 1, 1.2))
        ax.set_xlim(-1.3, 1.3);
        ax.set_ylim(-1.3, 1.3);
        ax.set_zlim(-0.2, 4.0)
        ax.set_axis_off()
        ax.view_init(elev=22, azim=azim)

        if save_path:
            plt.savefig(save_path, dpi=120, bbox_inches='tight', facecolor='#f0f2f6')
        plt.close(fig)