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

# ── 中文字体配置 ──────────────────────────────────────────────────────────────
def _setup_chinese_font():
    """尝试设置中文字体，优先使用系统内置字体"""
    import matplotlib.font_manager as fm
    import os
    candidates = [
        '/System/Library/Fonts/STHeiti Medium.ttc',
        '/System/Library/Fonts/STHeiti Light.ttc',
        '/Library/Fonts/Arial Unicode.ttf',
        '/System/Library/Fonts/Supplemental/Arial Unicode.ttf',
        '/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc',
        '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',
    ]
    for path in candidates:
        if os.path.exists(path):
            try:
                prop = fm.FontProperties(fname=path)
                fname = prop.get_name()
                matplotlib.rcParams['font.family'] = 'sans-serif'
                matplotlib.rcParams['font.sans-serif'] = [fname, 'DejaVu Sans']
                matplotlib.rcParams['axes.unicode_minus'] = False
                return fname
            except Exception:
                continue
    for name in ['STHeiti', 'Heiti TC', 'PingFang SC', 'SimHei', 'WenQuanYi Zen Hei']:
        matplotlib.rcParams['font.sans-serif'] = [name, 'DejaVu Sans']
        matplotlib.rcParams['axes.unicode_minus'] = False
        return name
    return None

_CJK_FONT = _setup_chinese_font()


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

        # ── 计算有节点的层（active_layers）及压缩后的 z 坐标映射 ──────────────
        active_layers = [
            l for l in LAYER_ORDER
            if any(d.get('layer') == l for _, d in H.nodes(data=True))
        ]
        if not active_layers:
            active_layers = LAYER_ORDER  # 兜底：全部显示

        # 将有节点的层均匀分布在 z 轴上，间距 2.5
        layer_z_map = {
            l: i * 2.5
            for i, l in enumerate(active_layers)
        }

        # 用压缩后的 z 坐标重建 pos_3d
        pos_3d = {}
        for n, d in H.nodes(data=True):
            layer = d.get('layer', 'sensor')
            z = layer_z_map.get(layer, 0.0)
            x, y = self.pos_cache.get(n, (0.0, 0.0))
            pos_3d[n] = (x, y, z)

        # ── 绘制 3D 部分 ──────────────────────────────────────────────────────
        self._draw_layer_planes(ax3d, active_layers, layer_z_map)
        self._draw_edges(ax3d, H, pos_3d)
        self._draw_nodes(ax3d, H, pos_3d, gravity_node)
        if gravity_node and gravity_node in pos_3d:
            self._draw_gravity(ax3d, pos_3d[gravity_node], gravity_node)
        self._draw_title(fig, H, gravity_node, frame_meta, active_layers)
        self._draw_legend(fig, active_layers)

        n_active = len(active_layers)
        z_top = (n_active - 1) * 2.5
        elev = 30 + 4 * np.sin(np.radians(azim * 0.5))
        ax3d.set_box_aspect((1, 1, max(1.2, 0.45 * n_active)))
        ax3d.set_xlim(-1.35, 1.35)
        ax3d.set_ylim(-1.35, 1.35)
        ax3d.set_zlim(-0.6, z_top + 1.3)
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

    def _draw_layer_planes(self, ax, active_layers: list, layer_z_map: dict):
        """只渲染 active_layers 中的层，z 坐标使用 layer_z_map 中的压缩值"""
        N = 7
        xs = np.linspace(-1.3, 1.3, N)
        ys = np.linspace(-1.3, 1.3, N)
        for layer in active_layers:
            _, face_c, edge_c, _, label_c = LAYER_CFG[layer]
            z = layer_z_map[layer]
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
        max_deg = max(degrees.values()) if degrees else 0
        max_deg = max_deg or 1   # 防止所有节点度数为 0 时除零

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
                                   if not p.isdigit())
                    label = f'{num}_{rest}' if rest else num
                else:
                    label = n
                # 截断过长标签
                if len(label) > 12:
                    label = label[:11] + '…'
                fs = 7.5 if deg >= active_thresh else 6.0
                ax.text(x, y, z + 0.18, label,
                        color=label_c, fontsize=fs,
                        fontweight='bold' if deg >= active_thresh else 'normal',
                        ha='center', va='bottom', zorder=8,
                        alpha=0.95 if deg >= active_thresh else 0.65)

    def _draw_gravity(self, ax, pos, gravity_node):
        x, y, z = pos
        ax.scatter([x], [y], [z],
                   c='#FFD700', s=900, marker='*',
                   edgecolors='#FF6F00', linewidths=2.0,
                   alpha=1.0, depthshade=False, zorder=12)
        label = gravity_node
        if len(label) > 14:
            label = label[:13] + '…'
        ax.text(x, y, z + 0.35, f'★ {label}',
                color='#FF6F00', fontsize=9, fontweight='bold',
                ha='center', va='bottom', zorder=13)

    def _draw_title(self, fig, H, gravity_node, frame_meta, active_layers=None):
        n_nodes = H.number_of_nodes()
        n_edges = H.number_of_edges()
        if frame_meta:
            fi = frame_meta.get('frame_idx', 0) + 1
            ft = frame_meta.get('total_frames', 1)
            t0 = frame_meta.get('t_start', 0)
            t1 = frame_meta.get('t_end', 0)
            title = (f'Combat Hyper-Network  |  Frame {fi}/{ft}  '
                     f't={t0:.0f}~{t1:.0f}s  |  '
                     f'Nodes={n_nodes}  Edges={n_edges}')
        else:
            title = (f'Combat Hyper-Network  |  '
                     f'Nodes={n_nodes}  Edges={n_edges}')
        if gravity_node:
            gn = gravity_node if len(gravity_node) <= 16 else gravity_node[:15] + '…'
            title += f'  |  CoG: {gn}'
        if active_layers and len(active_layers) < len(LAYER_ORDER):
            missing = [l.upper() for l in LAYER_ORDER if l not in active_layers]
            title += f'  |  (No {"/".join(missing)} Layer)'
        fig.text(0.5, 0.985, title,
                 ha='center', va='top',
                 fontsize=11, fontweight='bold', color='#1a237e')

    def _draw_legend(self, fig, active_layers=None):
        layers_to_show = active_layers if active_layers else LAYER_ORDER
        patches = [
            mpatches.Patch(color=LAYER_CFG[l][3], label=f'{l.upper()} Layer')
            for l in layers_to_show
        ]
        patches.append(mpatches.Patch(color='#FFD700', label='CoG Node ★'))
        fig.legend(handles=patches,
                   loc='lower left', bbox_to_anchor=(0.01, 0.01),
                   ncol=len(patches), fontsize=8,
                   framealpha=0.85, edgecolor='#b0bec5')

    # ── 右侧面板公共绘制 ──────────────────────────────────────────────────────

    def _draw_bar_panel(self, ax, names, values, gravity_node, H,
                        title='', xlabel='', bar_alpha=0.80):
        if not names:
            ax.text(0.5, 0.5, 'No Data', ha='center', va='center',
                    transform=ax.transAxes, color='#90a4ae', fontsize=10)
            ax.set_title(title, fontsize=9, fontweight='bold',
                         color='#1a237e', pad=6)
            return

        colors = []
        for n in names:
            lyr = _get_node_layer(H, n)
            c = LAYER_BAR_COLOR.get(lyr, LAYER_BAR_COLOR['unknown'])
            if n == gravity_node:
                c = '#FFD700'
            colors.append(c)

        y_pos = range(len(names))
        bars = ax.barh(y_pos, values, color=colors, alpha=bar_alpha,
                       edgecolor='white', linewidth=0.8, height=0.65)

        # 标签：截断过长名称
        disp_names = []
        for n in names:
            dn = n if len(n) <= 14 else n[:13] + '…'
            disp_names.append(dn)

        ax.set_yticks(list(y_pos))
        ax.set_yticklabels(disp_names, fontsize=7.5)
        ax.set_xlabel(xlabel, fontsize=7.5, color='#455a64')
        ax.set_xlim(0, max(values) * 1.18 if values else 1)
        ax.tick_params(axis='x', labelsize=7)
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.spines['left'].set_color('#cfd8dc')
        ax.spines['bottom'].set_color('#cfd8dc')

        # 数值标注
        for bar, val in zip(bars, values):
            ax.text(bar.get_width() + max(values) * 0.02 if values else 0.02,
                    bar.get_y() + bar.get_height() / 2,
                    f'{val:.3f}', va='center', ha='left',
                    fontsize=6.5, color='#455a64')

        ax.xaxis.grid(True, color='#cfd8dc', linewidth=0.5, linestyle='--')
        ax.set_title(title, fontsize=9, fontweight='bold',
                     color='#1a237e', pad=6, loc='center')

    # ── 右上：度中心性 Top-10 ─────────────────────────────────────────────────
    def _draw_degree_bar(self, ax, H, gravity_node, frame_meta):
        """右上：归一化度中心性 Top-10 水平条形图
        若当前帧无边（度数全为0），则显示全局度数并标注 No Activity
        """
        deg = dict(H.degree())
        total_edges = H.number_of_edges()
        no_activity = (total_edges == 0)

        if no_activity:
            # 无边帧：用节点存在性（每个节点度数视为1）作为兜底，显示节点列表
            deg_norm = {n: 1.0 for n in H.nodes()}
        else:
            max_deg = max(deg.values()) if deg else 1
            max_deg = max_deg or 1
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

        if no_activity:
            sub += '  ⚠ No Activity'

        self._draw_bar_panel(
            ax, names, values, gravity_node, H,
            title=f'Degree Centrality  Top-10\n{sub}',
            xlabel='Normalized Degree' if not no_activity else 'Node Presence (No Edges)',
            bar_alpha=0.45 if no_activity else 0.78,
        )

        if no_activity:
            ax.text(0.98, 0.02, 'No Activity\nin this frame',
                    ha='right', va='bottom', transform=ax.transAxes,
                    fontsize=8, color='#b71c1c', alpha=0.75,
                    style='italic')

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
            title=f'Shapley Score  Top-10\n{sub}',
            xlabel='Shapley Score',
            bar_alpha=0.82,
        )
