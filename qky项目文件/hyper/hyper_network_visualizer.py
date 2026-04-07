# src/hyper/hyper_network_visualizer.py
"""
3D 超网可视化引擎 v6
布局：左侧 3D 旋转超网（70%宽）+ 右侧双指标面板（30%宽）
       右上：度中心性 Top-10（经典网络分析）
       右下：Shapley 分数 Top-10（合作博弈论边际贡献）
重心计算：degree_norm * 0.4 + shapley * 0.6 加权融合
背景：浅蓝灰 #eef2f8，深色文字，高对比线条
"""

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.gridspec as gridspec
from mpl_toolkits.mplot3d import Axes3D   # noqa: F401
import numpy as np
from typing import Dict, Any, Optional, List


# ── 配色 ──────────────────────────────────────────────────────────────────────
BG_COLOR  = '#eef2f8'
BAR_BG    = '#f8faff'   # 条形图区背景

LAYER_CFG = {
    # layer: (z, 平面填充, 边框色, 节点色, 标签色)
    'sensor':  (0.0, '#d6eaff', '#1565c0', '#1565c0', '#0d47a1'),
    'ew':      (2.5, '#fff0cc', '#d84315', '#d84315', '#bf360c'),
    'command': (5.0, '#d4f0dc', '#2e7d32', '#2e7d32', '#1b5e20'),
    'weapon':  (7.5, '#ffd8d8', '#c62828', '#c62828', '#b71c1c'),
}
LAYER_ORDER = ['sensor', 'ew', 'command', 'weapon']

# 层对应的条形图颜色
LAYER_BAR_COLOR = {
    'sensor':  '#1565c0',
    'ew':      '#d84315',
    'command': '#2e7d32',
    'weapon':  '#c62828',
    'unknown': '#546e7a',
}


def _edge_style(data: dict) -> tuple:
    color = data.get('color', '')
    if '#e74c3c' in color:   return ('#c62828', 0.88, 2.4, 6)
    if '#9b59b6' in color:   return ('#d84315', 0.82, 2.0, 5)
    if '#2ecc71' in color:   return ('#2e7d32', 0.60, 1.4, 4)
    if '#3498db' in color:   return ('#1565c0', 0.45, 1.1, 3)
    return                          ('#455a64', 0.30, 0.9, 2)


def _get_node_layer(H, node: str) -> str:
    if H.has_node(node):
        return H.nodes[node].get('layer', 'unknown')
    return 'unknown'


class HyperNetworkVisualizer:
    def __init__(self, figsize=(22, 12)):
        self.figsize = figsize
        self.pos_cache: Dict[str, tuple] = {}

    def visualize_hyper_network(
        self,
        hyper_network_data: Dict[str, Any],
        save_path: Optional[str] = None,
        azim: float = 35,
        gravity_node: Optional[str] = None,
        frame_meta: Optional[dict] = None,
        shapley_scores: Optional[Dict[str, float]] = None,
    ):
        H = hyper_network_data.get('hyper_network')
        if H is None:
            return

        self._ensure_pos(H)

        pos_3d = {}
        for n, d in H.nodes(data=True):
            layer = d.get('layer', 'sensor')
            z = LAYER_CFG.get(layer, LAYER_CFG['sensor'])[0]
            x, y = self.pos_cache.get(n, (0.0, 0.0))
            pos_3d[n] = (x, y, z)

        # ── 画布：左 3D（70%）+ 右双面板（30%）──────────────────────────────
        fig = plt.figure(figsize=self.figsize, facecolor=BG_COLOR)
        fig.patch.set_facecolor(BG_COLOR)

        # 外层网格：左右两列
        gs_outer = gridspec.GridSpec(
            1, 2,
            width_ratios=[2.2, 1],
            left=0.01, right=0.99,
            top=0.97, bottom=0.03,
            wspace=0.04
        )

        # 左：3D 超网
        ax3d = fig.add_subplot(gs_outer[0], projection='3d')
        ax3d.set_facecolor(BG_COLOR)
        for pane in (ax3d.xaxis.pane, ax3d.yaxis.pane, ax3d.zaxis.pane):
            pane.fill = False
            pane.set_edgecolor('none')
        ax3d.set_axis_off()

        # 右：上下两个子图（度中心性 + Shapley）
        gs_right = gridspec.GridSpecFromSubplotSpec(
            2, 1,
            subplot_spec=gs_outer[1],
            hspace=0.50,
            height_ratios=[1, 1]
        )
        ax_deg     = fig.add_subplot(gs_right[0])
        ax_shapley = fig.add_subplot(gs_right[1])
        ax_deg.set_facecolor(BAR_BG)
        ax_shapley.set_facecolor(BAR_BG)

        # ── 绘制 3D 部分 ──────────────────────────────────────────────────────
        self._draw_layer_planes(ax3d)
        self._draw_edges(ax3d, H, pos_3d)
        self._draw_nodes(ax3d, H, pos_3d, gravity_node)
        if gravity_node and gravity_node in pos_3d:
            self._draw_gravity(ax3d, pos_3d[gravity_node], gravity_node)
        self._draw_title(fig, H, gravity_node, frame_meta)
        self._draw_legend(fig)

        elev = 30 + 4 * np.sin(np.radians(azim * 0.5))
        ax3d.set_box_aspect((1, 1, 1.8))
        ax3d.set_xlim(-1.35, 1.35)
        ax3d.set_ylim(-1.35, 1.35)
        ax3d.set_zlim(-0.6, 8.8)
        ax3d.view_init(elev=elev, azim=azim)

        # ── 绘制度中心性条形图（上）────────────────────────────────────────────
        self._draw_degree_bar(ax_deg, H, gravity_node, frame_meta)

        # ── 绘制 Shapley 条形图（下）──────────────────────────────────────────
        self._draw_shapley_bar(ax_shapley, H, shapley_scores, gravity_node, frame_meta)

        if save_path:
            plt.savefig(save_path, dpi=120, bbox_inches='tight',
                        facecolor=BG_COLOR, edgecolor='none')
        plt.close(fig)

    # ── 内部方法 ──────────────────────────────────────────────────────────────

    def _ensure_pos(self, H):
        GOLDEN = 2.399963
        layer_buckets: Dict[str, list] = {l: [] for l in LAYER_ORDER}
        for n, d in H.nodes(data=True):
            if n not in self.pos_cache:
                layer_buckets[d.get('layer', 'sensor')].append(n)

        for layer, nodes in layer_buckets.items():
            if not nodes:
                continue
            existing_cnt = sum(
                1 for n in self.pos_cache
                if H.has_node(n) and H.nodes[n].get('layer') == layer
            )
            total = existing_cnt + len(nodes)
            for i, n in enumerate(nodes):
                idx = existing_cnt + i
                r = 0.20 + 0.72 * np.sqrt((idx + 0.5) / max(total, 1))
                angle = GOLDEN * idx
                x = float(np.clip(r * np.cos(angle), -0.92, 0.92))
                y = float(np.clip(r * np.sin(angle), -0.92, 0.92))
                self.pos_cache[n] = (x, y)

    def _draw_layer_planes(self, ax):
        N = 7
        xs = np.linspace(-1.3, 1.3, N)
        ys = np.linspace(-1.3, 1.3, N)
        for layer in LAYER_ORDER:
            z, face_c, edge_c, _, label_c = LAYER_CFG[layer]
            xx, yy = np.meshgrid([-1.3, 1.3], [-1.3, 1.3])
            zz = np.full_like(xx, z, dtype=float)
            ax.plot_surface(xx, yy, zz, color=face_c, alpha=0.35,
                            linewidth=0, antialiased=False, zorder=1)
            for xi in xs:
                ax.plot([xi, xi], [-1.3, 1.3], [z, z],
                        color=edge_c, alpha=0.30, lw=0.7, zorder=2)
            for yi in ys:
                ax.plot([-1.3, 1.3], [yi, yi], [z, z],
                        color=edge_c, alpha=0.30, lw=0.7, zorder=2)
            cx = [-1.3, 1.3, 1.3, -1.3, -1.3]
            cy = [-1.3, -1.3, 1.3, 1.3, -1.3]
            ax.plot(cx, cy, [z]*5, color=edge_c, alpha=0.90, lw=2.5, zorder=3)
            ax.text(-1.28, -1.28, z + 0.12,
                    f'  {layer.upper()} LAYER',
                    color=label_c, fontsize=10, fontweight='bold',
                    alpha=0.95, zorder=10)

    def _draw_edges(self, ax, H, pos_3d):
        for u, v, data in H.edges(data=True):
            if u not in pos_3d or v not in pos_3d:
                continue
            x0, y0, z0 = pos_3d[u]
            x1, y1, z1 = pos_3d[v]
            ec, alpha, lw, zo = _edge_style(data)
            if abs(z0 - z1) > 0.5:
                zmid = (z0 + z1) / 2 + 0.3
                ax.plot([x0, (x0+x1)/2, x1],
                        [y0, (y0+y1)/2, y1],
                        [z0, zmid, z1],
                        color=ec, alpha=alpha, lw=lw, zorder=zo,
                        solid_capstyle='round')
            else:
                ax.plot([x0, x1], [y0, y1], [z0, z1],
                        color=ec, alpha=alpha*0.65, lw=lw*0.8,
                        zorder=zo, solid_capstyle='round')

    def _draw_nodes(self, ax, H, pos_3d, gravity_node):
        degrees = dict(H.degree())
        max_deg = max(degrees.values()) if degrees else 1

        for layer in LAYER_ORDER:
            _, _, _, node_c, label_c = LAYER_CFG[layer]
            nodes = [n for n, d in H.nodes(data=True)
                     if d.get('layer') == layer
                     and n != gravity_node
                     and n in pos_3d]
            if not nodes:
                continue
            xs = [pos_3d[n][0] for n in nodes]
            ys = [pos_3d[n][1] for n in nodes]
            zs = [pos_3d[n][2] for n in nodes]
            sizes = [100 + 260 * (degrees.get(n, 0) / max_deg) for n in nodes]

            ax.scatter(xs, ys, zs, c=node_c,
                       s=[s * 3.0 for s in sizes],
                       alpha=0.12, edgecolors='none',
                       depthshade=False, zorder=4)
            ax.scatter(xs, ys, zs, c=node_c, s=sizes,
                       edgecolors='white', linewidths=1.2,
                       alpha=0.92, depthshade=True, zorder=5)

            # 节点标签
            layer_degs = [degrees.get(n, 0) for n in nodes]
            median_deg = sorted(layer_degs)[len(layer_degs) // 2] if layer_degs else 0
            active_thresh = max(median_deg, 1)

            for n, x, y, z in zip(nodes, xs, ys, zs):
                deg = degrees.get(n, 0)
                parts = n.split('_')
                if len(parts) >= 2 and parts[0].isdigit():
                    num = parts[0]
                    rest = '_'.join(p for p in parts[1:]
                                   if p not in ('large', 'small', 'medium'))
                    short = f'{num}_{rest}'
                else:
                    short = n
                if len(short) > 12:
                    short = short[:11] + '.'
                if deg >= active_thresh:
                    ax.text(x, y, z + 0.20, short,
                            color=label_c, fontsize=6.5, fontweight='bold',
                            ha='center', va='bottom', alpha=0.92, zorder=6)
                else:
                    ax.text(x, y, z + 0.18, short,
                            color=label_c, fontsize=5.0, fontweight='normal',
                            ha='center', va='bottom', alpha=0.50, zorder=6)

    def _draw_gravity(self, ax, pos: tuple, name: str):
        gx, gy, gz = pos
        for s, a in [(3500, 0.10), (1500, 0.22), (500, 0.70)]:
            ax.scatter([gx], [gy], [gz], c='#f9a825', s=s,
                       alpha=a, edgecolors='none', depthshade=False, zorder=8)
        ax.scatter([gx], [gy], [gz], c='#e65100', s=120,
                   edgecolors='#f9a825', linewidths=2.5,
                   alpha=1.0, depthshade=False, zorder=9)
        z_top = gz + 1.2
        for lw, a, c in [(7, 0.08, '#f9a825'), (2.5, 0.35, '#f9a825'),
                         (1.0, 0.75, '#e65100')]:
            ax.plot([gx, gx], [gy, gy], [gz, z_top],
                    color=c, lw=lw, alpha=a, zorder=7)
        # 节点名标签
        parts = name.split('_')
        if len(parts) >= 2 and parts[0].isdigit():
            cog_label = f"{parts[0]}_{'_'.join(p for p in parts[1:] if p not in ('large','small','medium'))}"
        else:
            cog_label = name
        if len(cog_label) > 11:
            cog_label = cog_label[:10] + '.'
        ax.text(gx, gy, gz + 0.22, cog_label,
                color='#e65100', fontsize=6.5, fontweight='bold',
                ha='center', va='bottom', alpha=0.95, zorder=10)
        # 3D 图内右上角固定标注
        short = name if len(name) <= 14 else name[:13] + '.'
        ax.figure.text(
            0.66, 0.97,
            f'★  CoG: {short}',
            color='#b71c1c', fontsize=9.5, fontweight='bold',
            va='top', ha='right', fontfamily='monospace',
            bbox=dict(facecolor='#fff8e1', alpha=0.92,
                      edgecolor='#f9a825', boxstyle='round,pad=0.4',
                      linewidth=1.6)
        )

    def _draw_title(self, fig, H, gravity_node, frame_meta):
        n_nodes = H.number_of_nodes()
        n_edges = H.number_of_edges()
        if frame_meta:
            t0 = frame_meta.get('t_start', 0)
            t1 = frame_meta.get('t_end', 0)
            fi = frame_meta.get('frame_idx', 0) + 1
            ft = frame_meta.get('total_frames', 1)
            time_str = f't = {t0:.0f}s ~ {t1:.0f}s   [{fi}/{ft}]'
        else:
            time_str = ''
        title = (f'AFSIM  Hyper-Network  |  {time_str}\n'
                 f'Nodes: {n_nodes}   Edges: {n_edges}')
        fig.text(0.34, 0.975, title,
                 ha='center', va='top',
                 color='#1a237e', fontsize=10, fontweight='bold',
                 fontfamily='monospace',
                 bbox=dict(facecolor='#ffffff', alpha=0.88,
                           edgecolor='#3949ab', boxstyle='round,pad=0.4',
                           linewidth=1.2))

    def _draw_legend(self, fig):
        layer_items = [
            mpatches.Patch(facecolor='#1565c0', edgecolor='#0d47a1', lw=1.0, label='SENSOR LAYER'),
            mpatches.Patch(facecolor='#d84315', edgecolor='#bf360c', lw=1.0, label='EW LAYER'),
            mpatches.Patch(facecolor='#2e7d32', edgecolor='#1b5e20', lw=1.0, label='COMMAND LAYER'),
            mpatches.Patch(facecolor='#c62828', edgecolor='#b71c1c', lw=1.0, label='WEAPON LAYER'),
        ]
        edge_items = [
            plt.Line2D([0],[0], color='#1565c0', lw=1.6, alpha=0.75, label='Sensor detection'),
            plt.Line2D([0],[0], color='#c62828', lw=2.4, alpha=0.92, label='Weapon engagement'),
            plt.Line2D([0],[0], color='#d84315', lw=2.2, alpha=0.88, label='EW jamming'),
            plt.Line2D([0],[0], color='#2e7d32', lw=1.6, alpha=0.75, label='Command link'),
            plt.Line2D([0],[0], marker='*', color='w',
                       markerfacecolor='#f9a825', markersize=13,
                       markeredgecolor='#e65100', label='Center of Gravity'),
        ]
        fig.legend(
            handles=layer_items + edge_items,
            loc='lower left',
            bbox_to_anchor=(0.01, 0.01),
            facecolor='#ffffff', edgecolor='#90a4ae',
            labelcolor='#1a237e', fontsize=7.5,
            framealpha=0.90, handlelength=1.8,
            borderpad=0.7, labelspacing=0.45,
            ncol=1,
        )

    # ── 公共辅助：截短节点名 ──────────────────────────────────────────────────
    @staticmethod
    def _shorten(n: str, maxlen: int = 14) -> str:
        parts = n.split('_')
        if len(parts) >= 2 and parts[0].isdigit():
            rest = '_'.join(p for p in parts[1:] if p not in ('large', 'small', 'medium'))
            s = f"{parts[0]}_{rest}"
        else:
            s = n
        return s[:maxlen] + '.' if len(s) > maxlen else s

    # ── 公共辅助：绘制单个水平条形图面板 ────────────────────────────────────
    def _draw_bar_panel(self, ax, names, values, gravity_node, H,
                        title: str, xlabel: str, bar_alpha: float = 0.88):
        """通用水平条形图绘制，文字清晰、高对比度"""
        ax.set_facecolor(BAR_BG)
        if not names:
            ax.set_visible(False)
            return

        # 颜色按层分配
        colors = []
        for n in names:
            layer = _get_node_layer(H, n)
            colors.append(LAYER_BAR_COLOR.get(layer, LAYER_BAR_COLOR['unknown']))

        y_pos = np.arange(len(names))
        bars = ax.barh(y_pos, values, color=colors, alpha=bar_alpha,
                       edgecolor='white', linewidth=0.7, height=0.62)

        # 高亮 CoG 节点
        for i, n in enumerate(names):
            if n == gravity_node:
                bars[i].set_edgecolor('#e65100')
                bars[i].set_linewidth(2.2)
                bars[i].set_alpha(1.0)

        # 数值标签 —— 带背景色块保证可读性
        max_val = max(values) if values else 1.0
        for i, (val, n) in enumerate(zip(values, names)):
            is_cog = (n == gravity_node)
            txt = f'{val:.3f}' + ('  ★' if is_cog else '')
            fc  = '#fff3e0' if is_cog else '#ffffff'
            ec  = '#e65100' if is_cog else '#b0bec5'
            tc  = '#b71c1c' if is_cog else '#1a237e'
            ax.text(val + max_val * 0.015, i, txt,
                    va='center', ha='left', fontsize=8.0,
                    color=tc, fontweight='bold',
                    bbox=dict(facecolor=fc, edgecolor=ec,
                              boxstyle='round,pad=0.20', linewidth=0.9,
                              alpha=0.95))

        # Y 轴节点名 —— 白色背景色块 + 加大字号
        ax.set_yticks(y_pos)
        short_names = [self._shorten(n) for n in names]
        ax.set_yticklabels(short_names, fontsize=9.0, fontweight='bold')
        for tick, n in zip(ax.get_yticklabels(), names):
            layer = _get_node_layer(H, n)
            tick.set_color(LAYER_BAR_COLOR.get(layer, '#263238'))
            if n == gravity_node:
                tick.set_fontsize(10.0)
                tick.set_color('#b71c1c')
            # 白色背景让文字在任何条形颜色上都清晰
            tick.set_bbox(dict(facecolor='white', edgecolor='none',
                               alpha=0.85, pad=2.0))

        # 轴样式
        ax.set_xlim(0, max_val * 1.58)
        ax.set_xlabel(xlabel, fontsize=8, color='#37474f', labelpad=3)
        ax.tick_params(axis='x', labelsize=7.5, colors='#546e7a')
        ax.tick_params(axis='y', length=0, pad=4)
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.spines['left'].set_visible(False)
        ax.spines['bottom'].set_color('#b0bec5')
        ax.set_axisbelow(True)
        ax.xaxis.grid(True, color='#cfd8dc', linewidth=0.5, linestyle='--')
        ax.set_title(title, fontsize=9, fontweight='bold',
                     color='#1a237e', pad=6, loc='center')

    # ── 右上：度中心性 Top-10 ─────────────────────────────────────────────────
    def _draw_degree_bar(self, ax, H, gravity_node, frame_meta):
        """右上：归一化度中心性 Top-10 水平条形图"""
        deg = dict(H.degree())
        max_deg = max(deg.values()) if deg else 1
        deg_norm = {n: v / max_deg for n, v in deg.items()}

        top10 = sorted(deg_norm.items(), key=lambda x: x[1], reverse=True)[:10]
        top10_disp = list(reversed(top10))   # 最高分在顶部
        names  = [x[0] for x in top10_disp]
        values = [x[1] for x in top10_disp]

        if frame_meta:
            t0 = frame_meta.get('t_start', 0)
            t1 = frame_meta.get('t_end', 0)
            sub = f't={t0:.0f}~{t1:.0f}s'
        else:
            sub = 'Global'

        self._draw_bar_panel(
            ax, names, values, gravity_node, H,
            title=f'Degree Centrality  Top-10\n{sub}',
            xlabel='Normalized Degree',
            bar_alpha=0.78,
        )

    # ── 右下：Shapley 分数 Top-10 ─────────────────────────────────────────────
    def _draw_shapley_bar(self, ax, H, shapley_scores, gravity_node, frame_meta):
        """右下：Shapley 分数 Top-10 水平条形图"""
        if shapley_scores:
            scores = shapley_scores
        else:
            # 无 Shapley 数据时用度数归一化替代
            deg = dict(H.degree())
            total = sum(deg.values()) or 1
            scores = {n: v / total for n, v in deg.items()}

        top10 = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:10]
        top10_disp = list(reversed(top10))
        names  = [x[0] for x in top10_disp]
        values = [x[1] for x in top10_disp]

        if frame_meta:
            t0 = frame_meta.get('t_start', 0)
            t1 = frame_meta.get('t_end', 0)
            sub = f't={t0:.0f}~{t1:.0f}s'
        else:
            sub = 'Global'

        self._draw_bar_panel(
            ax, names, values, gravity_node, H,
            title=f'Shapley + Degree Fusion  Top-10\n{sub}',
            xlabel='Fusion Score (Shapley×0.5 + Degree×0.5)',
            bar_alpha=0.88,
        )
