#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
run_analysis.py
===============
端到端主入口：AFSIM 仿真数据 → 超网构建 → Shapley 重心分析 → 级联失效模拟
                → 视频帧序列 → 分析报告

用法：
    python run_analysis.py                          # 使用默认 111.csv
    python run_analysis.py --csv path/to/data.csv  # 指定数据文件
    python run_analysis.py --frames 30             # 指定视频帧数
    python run_analysis.py --no-video              # 跳过视频帧生成
"""

import sys
import os
import argparse
import time
import traceback
from pathlib import Path

# ── 路径设置 ──────────────────────────────────────────────────────────────────
_THIS_DIR = Path(__file__).parent.resolve()
sys.path.insert(0, str(_THIS_DIR))
sys.path.insert(0, str(_THIS_DIR / 'hyper'))

# ── 输出目录 ──────────────────────────────────────────────────────────────────
OUTPUT_DIR = _THIS_DIR / 'outputs'
FRAMES_DIR = OUTPUT_DIR / 'frames'
REPORTS_DIR = OUTPUT_DIR / 'reports'

for d in [OUTPUT_DIR, FRAMES_DIR, REPORTS_DIR]:
    d.mkdir(parents=True, exist_ok=True)


# ─────────────────────────────────────────────────────────────────────────────
# 导入模块（带友好错误提示）
# ─────────────────────────────────────────────────────────────────────────────

def _import_or_die(module_name, pip_name=None):
    try:
        return __import__(module_name)
    except ImportError:
        pkg = pip_name or module_name
        print(f"❌ 缺少依赖：{module_name}，请运行：pip install {pkg}")
        sys.exit(1)


_import_or_die('networkx')
_import_or_die('pandas')
_import_or_die('numpy')
_import_or_die('matplotlib')

import numpy as np
import pandas as pd
import networkx as nx
import matplotlib
matplotlib.use('Agg')  # 无头模式，不弹窗
import matplotlib.pyplot as plt

from data_processor import SimDataProcessor
from centrality_analysis import CentralityAnalyzer
from hyper.hyper_network_builder import CombatHyperNetworkBuilder
from hyper.hyper_network_analyzer import HyperNetworkAnalyzer
from hyper.hyper_network_visualizer import HyperNetworkVisualizer
from shapely_gravity_analyzer import ShapelyGravityAnalyzer
from cascade_failure_simulator import CascadeFailureSimulator


# ─────────────────────────────────────────────────────────────────────────────
# 主分析流程
# ─────────────────────────────────────────────────────────────────────────────

class FullAnalysisPipeline:
    def __init__(self, csv_path: str, n_frames: int = 60,
                 shapley_samples: int = 150, cascade_rounds: int = 20,
                 generate_video: bool = True):
        self.csv_path = csv_path
        self.n_frames = n_frames
        self.shapley_samples = shapley_samples
        self.cascade_rounds = cascade_rounds
        self.generate_video = generate_video

        self.processor = None
        self.builder = CombatHyperNetworkBuilder()
        self.analyzer = HyperNetworkAnalyzer(
            shapley_samples=shapley_samples,
            cascade_rounds=cascade_rounds
        )
        self.visualizer = HyperNetworkVisualizer(figsize=(20, 11))
        self.centrality_analyzer = CentralityAnalyzer()

        self.results = {}

    def run(self):
        """执行完整分析流程"""
        t0 = time.time()
        print("=" * 60)
        print("  AFSIM 超网重心分析 + 级联失效模拟  ")
        print("=" * 60)

        # Step 1: 加载数据
        print("\n[Step 1] 加载 AFSIM 仿真数据...")
        self._step1_load_data()

        # Step 2: 构建全量超网（用于 Shapley + 级联失效）
        print("\n[Step 2] 构建全量超网...")
        self._step2_build_full_hyper_network()

        # Step 3: 超网分析（Shapley + 级联失效）
        print("\n[Step 3] 超网分析（Shapley 重心 + 级联失效）...")
        self._step3_analyze_hyper_network()

        # Step 4: 生成视频帧序列
        if self.generate_video:
            print(f"\n[Step 4] 生成视频帧序列（{self.n_frames} 帧）...")
            self._step4_generate_video_frames()
        else:
            print("\n[Step 4] 跳过视频帧生成（--no-video）")

        # Step 5: 生成综合分析报告
        print("\n[Step 5] 生成综合分析报告...")
        self._step5_generate_report()

        elapsed = time.time() - t0
        print(f"\n✅ 全部完成！耗时 {elapsed:.1f} 秒")
        print(f"   输出目录: {OUTPUT_DIR}")
        print(f"   视频帧:   {FRAMES_DIR}")
        print(f"   报告:     {REPORTS_DIR}")

    # ─────────────────────────────────────────────
    # Step 1: 加载数据
    # ─────────────────────────────────────────────

    def _step1_load_data(self):
        if not os.path.exists(self.csv_path):
            print(f"❌ 路径不存在: {self.csv_path}")
            sys.exit(1)

        self.processor = SimDataProcessor(self.csv_path)
        info = self.processor.get_data_info()
        print(f"  加载表数: {len(info['tables_loaded'])}")
        print(f"  数据行数: {info['total_rows']}")
        print(f"  平台数:   {info['platforms_count']}")
        print(f"  消息类型: {len(info['message_types'])} 种")
        self.results['data_info'] = info

    # ─────────────────────────────────────────────
    # Step 2: 构建全量超网
    # ─────────────────────────────────────────────

    def _step2_build_full_hyper_network(self):
        hyper_data = self.builder.build_hyper_network(self.processor)
        self.results['hyper_data'] = hyper_data

        H = hyper_data['hyper_network']
        print(f"  超网节点: {H.number_of_nodes()}")
        print(f"  超网边数: {H.number_of_edges()}")
        print(f"  跨层连接: {len(hyper_data['cross_layer_edges'])}")

        # 各层统计
        for layer_name, layer_net in hyper_data['layers'].items():
            print(f"  [{layer_name}] {layer_net.number_of_nodes()} 节点, "
                  f"{layer_net.number_of_edges()} 边")

    # ─────────────────────────────────────────────
    # Step 3: 超网分析
    # ─────────────────────────────────────────────

    def _step3_analyze_hyper_network(self):
        hyper_data = self.results['hyper_data']
        analysis = self.analyzer.analyze_hyper_network(hyper_data)
        self.results['analysis'] = analysis

        # 打印关键结果
        shapley_gravity = analysis.get('shapley_gravity', {})
        gravity = shapley_gravity.get('gravity_analysis', {})
        if gravity:
            print(f"  🌟 超网重心节点: {gravity.get('gravity_node', 'N/A')}")
            print(f"     Shapley 分数: {gravity.get('gravity_score', 0):.4f}")
            print(f"     稳定性:       {gravity.get('stability', 'N/A')}")

            top10 = gravity.get('top10_nodes', [])
            if top10:
                print(f"  Top-5 关键节点:")
                for i, (node, score) in enumerate(top10[:5], 1):
                    print(f"    {i}. {node} ({score:.4f})")

        cascade = analysis.get('cascade_failure', {})
        hyper_result = cascade.get('hyper_result', {})
        summary = hyper_result.get('monte_carlo_summary', {})
        if summary:
            collapse = summary.get('collapse_step')
            final_drop = summary.get('final_efficiency_drop', 0)
            if collapse:
                print(f"  ⚠️ 级联失效崩溃点: 第 {collapse} 步")
            print(f"  最终效率下降: {final_drop:.1f}%")

    # ─────────────────────────────────────────────
    # Step 4: 生成视频帧 + GIF（与原 visualize_gifnetwork.py 风格一致）
    # ─────────────────────────────────────────────

    # 节点颜色映射（与原版保持一致，扩展超网层）
    _NODE_COLORS = {
        'radar':   '#e74c3c',   # 红：雷达/传感器
        'soj':     '#3498db',   # 蓝：SOJ/电子战
        'iads':    '#2ecc71',   # 绿：IADS/指挥
        'cmdr':    '#2ecc71',
        'command': '#2ecc71',
        'sam':     '#f39c12',   # 橙：SAM/武器
        'launcher':'#f39c12',
        'missile': '#f39c12',
        'ew':      '#9b59b6',   # 紫：电子战其他
        'default': '#95a5a6',   # 灰：未知
    }

    # 层标签颜色（用于图例）
    _LAYER_COLORS = {
        'sensor':  '#3498db',
        'command': '#2ecc71',
        'weapon':  '#e74c3c',
        'ew':      '#f39c12',
    }

    def _get_node_color(self, node_name: str) -> str:
        """按节点名称关键字返回颜色（与原版 get_node_color 逻辑一致）"""
        n = str(node_name).lower()
        for kw, color in self._NODE_COLORS.items():
            if kw in n:
                return color
        return self._NODE_COLORS['default']

    # ── 分层布局常量 ─────────────────────────────────────────────────
    # 4 层从下到上：sensor(0) → ew(1) → command(2) → weapon(3)
    _LAYER_ORDER  = ['sensor', 'ew', 'command', 'weapon']
    # _LAYER_Y 在运行时动态计算，这里只是占位（会被 _compute_layer_y 覆盖）
    _LAYER_Y      = {'sensor': 0.0, 'ew': 1.0, 'command': 2.0, 'weapon': 3.0}
    _LAYER_BG     = {'sensor': '#1a3a5c', 'ew': '#3d1a5c',
                     'command': '#1a5c2a', 'weapon': '#5c1a1a'}
    _LAYER_LABEL  = {'sensor': 'SENSOR LAYER',  'ew': 'EW LAYER',
                     'command': 'COMMAND LAYER', 'weapon': 'WEAPON LAYER'}
    # 层间最小间距（中心到中心）
    _LAYER_GAP    = 0.18

    def _classify_node_layer(self, node: str) -> str:
        """
        根据节点名称判断所属层（优先级从高到低）：
          weapon  > command > ew > sensor
        注意：ew_radar / acq_radar 是雷达传感器，归 sensor 层；
              只有纯 soj / jammer 才归 ew 层。
        """
        n = node.lower()
        # weapon 层：SAM 系统、发射架、导弹、TTR 跟踪雷达
        if any(k in n for k in ['sam', 'launcher', 'missile', 'ttr']):
            return 'weapon'
        # command 层：指挥控制、IADS、UCAV（无人机作为指挥节点）
        if any(k in n for k in ['iads', 'cmdr', 'command', 'c2', 'ucav']):
            return 'command'
        # ew 层：纯电子战压制节点（SOJ 干扰机、jammer）
        # 注意：ew_radar 虽含 ew，但本质是雷达传感器，不归此层
        if any(k in n for k in ['_soj', 'soj_', 'jammer']) or n.endswith('soj'):
            return 'ew'
        # sensor 层：所有雷达（ew_radar、acq_radar、radar 等）及其他
        return 'sensor'

    # 每层最多每行放多少个节点（超过则换行）
    _MAX_PER_ROW = 12
    # 每层行间距（Y 方向）
    _ROW_SPACING = 0.38

    def _build_layered_pos(self, nodes) -> dict:
        """
        分层布局：
        - 不同层固定在不同 Y 区间（层间距 1.0）
        - 同层节点超过 _MAX_PER_ROW 时自动换行，奇偶行交错（蜂窝状）
        - 节点位置一旦计算就缓存，保证跨帧稳定不乱跳
        """
        # 按层分组（只处理尚未缓存的节点）
        layer_buckets = {l: [] for l in self._LAYER_ORDER}
        for n in nodes:
            if n not in self._layered_pos_cache:
                layer_buckets[self._classify_node_layer(n)].append(n)

        for layer, new_nodes in layer_buckets.items():
            if not new_nodes:
                continue

            y_base = self._LAYER_Y[layer]
            # 已缓存的同层节点（用于续排）
            existing = [(k, v) for k, v in self._layered_pos_cache.items()
                        if self._classify_node_layer(k) == layer]
            start_idx = len(existing)

            for i, n in enumerate(new_nodes):
                idx = start_idx + i
                row = idx // self._MAX_PER_ROW
                col = idx % self._MAX_PER_ROW

                # 该行实际节点数（最后一行可能不满）
                total_in_layer = start_idx + len(new_nodes)
                rows_total = (total_in_layer - 1) // self._MAX_PER_ROW + 1
                # 当前行节点数
                if row < rows_total - 1:
                    n_in_row = self._MAX_PER_ROW
                else:
                    n_in_row = total_in_layer - row * self._MAX_PER_ROW

                xs = np.linspace(-0.95, 0.95, max(n_in_row, 1))
                x = xs[col]

                # 奇数行向右偏移半格（蜂窝交错）
                if row % 2 == 1:
                    x += (xs[1] - xs[0]) * 0.5 if len(xs) > 1 else 0

                # Y：多行时在层内向上堆叠，层中心对齐
                y_offset = row * self._ROW_SPACING
                # 整体向下移半格，让层中心保持在 y_base
                y_center_offset = ((rows_total - 1) * self._ROW_SPACING) / 2
                y = y_base + y_offset - y_center_offset

                self._layered_pos_cache[n] = (x, y)

        return {n: self._layered_pos_cache[n] for n in nodes
                if n in self._layered_pos_cache}

    def _compute_dynamic_y(self, active_nodes):
        """
        根据各层实际行数动态计算层中心 Y 坐标。
        空层只占 _LAYER_GAP 高度，有节点的层按行数分配高度。
        从下（sensor）到上（weapon）累加。
        返回 (layer_y_dict, layer_row_counts, y_max)
        """
        layer_row_counts = {}
        for layer in self._LAYER_ORDER:
            nodes_in_layer = [n for n in active_nodes
                              if self._classify_node_layer(n) == layer]
            layer_row_counts[layer] = (
                0 if not nodes_in_layer
                else (len(nodes_in_layer) - 1) // self._MAX_PER_ROW + 1
            )

        # 每层占用的半高
        def half_h(rows):
            return 0.18 if rows == 0 else rows * self._ROW_SPACING * 0.5 + 0.22

        layer_y = {}
        y_cursor = 0.0
        for layer in self._LAYER_ORDER:
            rows = layer_row_counts[layer]
            hh = half_h(rows)
            layer_y[layer] = y_cursor + hh          # 层中心
            y_cursor += hh * 2 + self._LAYER_GAP    # 下一层起点

        y_max = y_cursor
        return layer_y, layer_row_counts, y_max

    def _draw_layered_frame(self, ax, t_start, t_end, G,
                            gravity_node, frame_idx, total_frames):
        """在 ax 上绘制一帧分层超网图"""
        ax.clear()
        ax.set_facecolor('#0d1117')

        active_nodes = [n for n in G.nodes() if G.degree(n) > 0]

        # ── 动态计算各层 Y 坐标 ────────────────────────────────────
        layer_y, layer_row_counts, y_max = self._compute_dynamic_y(active_nodes)
        # 更新实例变量，供 _build_layered_pos 使用
        self._LAYER_Y = layer_y

        if not active_nodes:
            ax.text(0.5, 0.5,
                    f"t = {t_start:.0f}s ~ {t_end:.0f}s\n(No active interactions)",
                    ha='center', va='center', color='#aaaaaa', fontsize=13,
                    transform=ax.transAxes)
            ax.set_xlim(-1.3, 1.3)
            ax.set_ylim(-0.15, y_max + 0.15)
            self._draw_layer_backgrounds(ax, layer_row_counts, layer_y)
            ax.set_axis_off()
            return

        # 计算分层坐标（使用最新的 layer_y）
        pos = self._build_layered_pos(active_nodes)
        G_active = G.subgraph([n for n in active_nodes if n in pos])

        # ── 1. 层背景色块（动态高度 + 动态 Y）────────────────────
        self._draw_layer_backgrounds(ax, layer_row_counts, layer_y)

        # ── 2. 连边（层内 vs 跨层用不同样式）─────────────────────
        intra_edges, inter_edges = [], []
        intra_colors, inter_colors = [], []
        for u, v in G_active.edges():
            if u not in pos or v not in pos:
                continue
            lu = self._classify_node_layer(u)
            lv = self._classify_node_layer(v)
            ec = G_active[u][v].get('color', '#aaaaaa')
            if lu == lv:
                intra_edges.append((u, v))
                intra_colors.append(ec)
            else:
                inter_edges.append((u, v))
                inter_colors.append(ec)

        if intra_edges:
            nx.draw_networkx_edges(G_active, pos, ax=ax,
                                   edgelist=intra_edges,
                                   edge_color=intra_colors,
                                   alpha=0.35, width=1.0, style='solid')
        if inter_edges:
            nx.draw_networkx_edges(G_active, pos, ax=ax,
                                   edgelist=inter_edges,
                                   edge_color=inter_colors,
                                   alpha=0.75, width=1.8, style='dashed')

        # ── 3. 节点（按层分批绘制，颜色与层一致）─────────────────
        layer_node_color = {
            'sensor':  '#3498db',
            'ew':      '#9b59b6',
            'command': '#2ecc71',
            'weapon':  '#e74c3c',
        }
        for layer in self._LAYER_ORDER:
            layer_nodes = [n for n in G_active.nodes()
                           if n in pos and self._classify_node_layer(n) == layer
                           and n != gravity_node]
            if layer_nodes:
                nx.draw_networkx_nodes(G_active, pos, ax=ax,
                                       nodelist=layer_nodes,
                                       node_color=layer_node_color[layer],
                                       node_size=420,
                                       edgecolors='white', linewidths=0.8,
                                       alpha=0.90)

        # ── 4. 重心节点金色高亮 ────────────────────────────────────
        if gravity_node and gravity_node in pos:
            # 光晕
            nx.draw_networkx_nodes(G_active, pos, ax=ax,
                                   nodelist=[gravity_node],
                                   node_color='#FFD700',
                                   node_size=2200, alpha=0.20)
            # 实心
            nx.draw_networkx_nodes(G_active, pos, ax=ax,
                                   nodelist=[gravity_node],
                                   node_color='#FFD700',
                                   node_size=900,
                                   edgecolors='#FF6600', linewidths=2.5,
                                   alpha=1.0)
            # 标注文字
            gx, gy = pos[gravity_node]
            ax.text(gx, gy + 0.18, f'★ CoG: {gravity_node}',
                    ha='center', va='bottom', fontsize=8,
                    color='#FFD700', fontweight='bold',
                    bbox=dict(facecolor='#0d1117', alpha=0.6,
                              edgecolor='#FFD700', boxstyle='round,pad=0.2'))

        # ── 5. 节点标签（智能截短）────────────────────────────────
        short_labels = {}
        for n in G_active.nodes():
            label = n
            parts = label.split('_')
            # 规则：保留数字编号 + 类型关键词，去掉中间冗余词
            # 例："1100_ew_radar" → "1100_ew_r"
            #     "3320_large_sam_ttr" → "3320_sam_ttr"
            #     "100_soj" → "100_soj"
            if len(parts) >= 2 and parts[0].isdigit():
                num = parts[0]
                rest = '_'.join(p for p in parts[1:] if p not in ('large', 'small', 'medium'))
                label = f"{num}_{rest}"
            # 超长截断（保留前12字符）
            if len(label) > 12:
                label = label[:11] + '.'
            short_labels[n] = label
        nx.draw_networkx_labels(G_active, pos, ax=ax,
                                labels=short_labels,
                                font_size=6.5, font_color='white',
                                font_weight='bold')

        # ── 6. 图例 ────────────────────────────────────────────────
        legend_items = [
            plt.Line2D([0],[0], marker='o', color='w',
                       markerfacecolor=layer_node_color[l],
                       markersize=9, label=self._LAYER_LABEL[l])
            for l in self._LAYER_ORDER
        ]
        legend_items += [
            plt.Line2D([0],[0], color='#aaaaaa', lw=1.0,
                       linestyle='solid',  label='Intra-layer edge'),
            plt.Line2D([0],[0], color='#ffffff', lw=1.8,
                       linestyle='dashed', label='Inter-layer edge'),
        ]
        if gravity_node:
            legend_items.append(
                plt.Line2D([0],[0], marker='*', color='w',
                           markerfacecolor='#FFD700',
                           markersize=13, label='Center of Gravity')
            )
        ax.legend(handles=legend_items, loc='upper right',
                  facecolor='#161b22', edgecolor='#30363d',
                  labelcolor='white', fontsize=7, framealpha=0.9,
                  handlelength=1.5)

        # ── 7. 标题 & 进度条 ───────────────────────────────────────
        ax.set_title(
            f"AFSIM Hyper-Network  |  t = {t_start:.0f}s ~ {t_end:.0f}s  "
            f"|  Active nodes: {G_active.number_of_nodes()}  "
            f"Edges: {G_active.number_of_edges()}",
            color='white', fontsize=11, pad=10
        )
        ax.set_xlim(-1.3, 1.3)
        ax.set_ylim(-0.12, y_max + 0.12)
        ax.set_axis_off()

        # 底部进度条
        progress = (frame_idx + 1) / total_frames
        bar_x_end = -1.3 + 2.6 * progress
        y_bar = -0.08
        ax.plot([-1.3, bar_x_end], [y_bar, y_bar],
                color='#FFD700', linewidth=5, alpha=0.75,
                solid_capstyle='butt', zorder=10)

    def _draw_layer_backgrounds(self, ax, layer_row_counts=None, layer_y=None):
        """
        绘制各层的半透明背景色块和层名标签。
        layer_row_counts: {layer: rows}  layer_y: {layer: y_center}
        """
        import matplotlib.patches as mpatches
        layer_bg_alpha = {
            'sensor':  ('#1a3a5c', 0.28),
            'ew':      ('#3d1a5c', 0.28),
            'command': ('#1a5c2a', 0.28),
            'weapon':  ('#5c1a1a', 0.28),
        }
        layer_colors_text = ['#5dade2', '#a569bd', '#52be80', '#ec7063']
        _ly = layer_y if layer_y else self._LAYER_Y

        for idx, layer in enumerate(self._LAYER_ORDER):
            y_center = _ly.get(layer, self._LAYER_Y[layer])
            color, alpha = layer_bg_alpha[layer]

            # 动态高度
            if layer_row_counts and layer in layer_row_counts:
                rows = layer_row_counts[layer]
                half_h = 0.18 if rows == 0 else rows * self._ROW_SPACING * 0.5 + 0.22
            else:
                half_h = 0.52

            rect = mpatches.FancyBboxPatch(
                (-1.28, y_center - half_h), 2.56, half_h * 2,
                boxstyle='round,pad=0.02',
                facecolor=color, edgecolor=layer_colors_text[idx],
                linewidth=0.6, alpha=alpha,
                transform=ax.transData, zorder=0
            )
            ax.add_patch(rect)
            ax.text(-1.25, y_center + half_h - 0.06,
                    self._LAYER_LABEL[layer],
                    va='top', ha='left', fontsize=8,
                    color=layer_colors_text[idx],
                    fontweight='bold', alpha=0.95, zorder=2)

    def _step4_generate_video_frames(self):
        """
        按时间窗口切片，生成 3D 立体旋转超网 GIF。
        每帧调用 HyperNetworkVisualizer.visualize_hyper_network()，
        azim 角度随帧递增，实现 360° 旋转动画。
        """
        from PIL import Image

        np.random.seed(42)

        t_min, t_max = self.processor.get_time_range()
        # 时间窗口：均匀切成 n_frames 段，窗口宽度 = 步长（不重叠，切片更短更密集）
        step = max(1.0, (t_max - t_min) / self.n_frames)

        windows = self.processor.get_time_windows(window_size=step, step=step)
        if len(windows) > self.n_frames:
            indices = np.linspace(0, len(windows) - 1, self.n_frames, dtype=int)
            windows = [windows[i] for i in indices]

        total_frames = len(windows)
        print(f"  实际生成帧数: {total_frames}  (时间范围 {t_min:.0f}s ~ {t_max:.0f}s, 窗口={step:.1f}s)")

        # 获取重心节点 & Shapley 分数字典
        gravity_node = None
        shapley_scores_dict = None
        shapley_gravity = self.results.get('analysis', {}).get('shapley_gravity', {})
        gravity_info = shapley_gravity.get('gravity_analysis', {})
        if gravity_info:
            gravity_node = gravity_info.get('gravity_node')
            print(f"  重心节点（高亮）: {gravity_node}")
            # 构建 {node: score} 字典供副图使用
            top10 = gravity_info.get('top10_nodes', [])
            if top10:
                shapley_scores_dict = {n: s for n, s in top10}
                # 补充其余节点（用度数归一化作为占位）
                H_full = self.results['hyper_data']['hyper_network']
                deg = dict(H_full.degree())
                total_deg = sum(deg.values()) or 1
                for n in H_full.nodes():
                    if n not in shapley_scores_dict:
                        shapley_scores_dict[n] = deg.get(n, 0) / total_deg * 0.01

        # ── 预构建所有帧的图快照 ──────────────────────────────────
        full_H = self.results['hyper_data']['hyper_network']
        frame_graphs = []

        for t_start, t_end, sub_proc in windows:
            G_snap = nx.Graph()
            G_snap.add_nodes_from(full_H.nodes(data=True))

            for src, tgt, w in sub_proc.extract_sensor_detections():
                G_snap.add_edge(src, tgt, color='#3498db', weight=w, type='intra')
            for src, tgt, w in sub_proc.extract_weapon_engagements():
                G_snap.add_edge(src, tgt, color='#e74c3c', weight=w, type='inter')
            for src, tgt, w in sub_proc.extract_jamming_relations():
                G_snap.add_edge(src, tgt, color='#9b59b6', weight=w, type='inter')
            for sub, cmd in sub_proc.extract_platform_hierarchy().items():
                G_snap.add_edge(sub, cmd, color='#2ecc71', weight=0.5, type='inter')

            frame_graphs.append((t_start, t_end, G_snap))

        # ── 逐帧渲染 3D 旋转图 ────────────────────────────────────
        print("  开始渲染 3D 旋转动画帧...")
        frame_paths = []
        pil_frames = []

        # 初始方位角 35°，每帧旋转 360/total_frames 度
        azim_start = 35
        azim_step = 360.0 / max(total_frames, 1)

        for frame_idx, (t_start, t_end, G_snap) in enumerate(frame_graphs):
            frame_path = FRAMES_DIR / f"frame_{frame_idx:04d}.png"
            azim = azim_start + frame_idx * azim_step

            # 构造 visualizer 所需的 hyper_network_data 格式
            snap_data = dict(self.results['hyper_data'])
            snap_data['hyper_network'] = G_snap

            try:
                self.visualizer.visualize_hyper_network(
                    snap_data,
                    save_path=str(frame_path),
                    azim=azim,
                    gravity_node=gravity_node,
                    frame_meta={
                        't_start': t_start,
                        't_end':   t_end,
                        'frame_idx': frame_idx,
                        'total_frames': total_frames,
                    },
                    shapley_scores=shapley_scores_dict,
                )
                frame_paths.append(str(frame_path))
                print(f"  渲染帧 {frame_idx + 1}/{total_frames}  t={t_start:.0f}~{t_end:.0f}s  azim={azim:.1f}°...", end='\r')
            except Exception as e:
                print(f"\n  ⚠️ 帧 {frame_idx} 渲染失败: {e}")
                traceback.print_exc()
                frame_paths.append('')

        print(f"\n  所有帧渲染完毕，开始合成 GIF...")

        # ── 用 pillow 合成 GIF ────────────────────────────────────
        gif_path = OUTPUT_DIR / 'hyper_network_animation.gif'
        for fp in frame_paths:
            if fp and Path(fp).exists():
                try:
                    img = Image.open(fp).convert('RGBA')
                    pil_frames.append(img)
                except Exception as e:
                    print(f"  ⚠️ 读取帧图片失败 {fp}: {e}")

        if pil_frames:
            try:
                pil_frames[0].save(
                    str(gif_path),
                    save_all=True,
                    append_images=pil_frames[1:],
                    loop=0,
                    duration=500,   # 每帧 500ms ≈ fps≈2，旋转更慢更清晰
                    optimize=False
                )
                print(f"  🎬 GIF 已生成: {gif_path}  ({gif_path.stat().st_size // 1024} KB)")
            except Exception as e:
                print(f"  ⚠️ GIF 合成失败: {e}")
                traceback.print_exc()
        else:
            print("  ⚠️ 没有可用帧，GIF 未生成")

        self.results['frame_paths'] = frame_paths
        self.results['gif_path'] = str(gif_path)
        print(f"  ✅ 单帧 PNG 已保存至: {FRAMES_DIR}")

        # ── 用 ffmpeg 合成 MP4 ────────────────────────────────────
        ffmpeg_bin = '/opt/homebrew/bin/ffmpeg'
        mp4_path = OUTPUT_DIR / 'hyper_network_animation.mp4'
        if os.path.exists(ffmpeg_bin) and frame_paths:
            print("  开始用 ffmpeg 合成 MP4...")
            # 帧率 2fps（与 GIF 500ms/帧一致），libx264 高质量
            cmd = (
                f'{ffmpeg_bin} -y '
                f'-framerate 2 '
                f'-i "{FRAMES_DIR}/frame_%04d.png" '
                f'-vf "scale=trunc(iw/2)*2:trunc(ih/2)*2" '
                f'-vcodec libx264 -crf 18 -preset slow '
                f'-pix_fmt yuv420p '
                f'"{mp4_path}"'
            )
            ret = os.system(cmd)
            if ret == 0 and mp4_path.exists():
                size_mb = mp4_path.stat().st_size / 1024 / 1024
                print(f"  🎬 MP4 已生成: {mp4_path}  ({size_mb:.2f} MB)")
                self.results['mp4_path'] = str(mp4_path)
            else:
                print(f"  ⚠️ ffmpeg 合成 MP4 失败（返回码 {ret}）")
        else:
            if not os.path.exists(ffmpeg_bin):
                print(f"  ℹ️ 未找到 ffmpeg ({ffmpeg_bin})，跳过 MP4 合成")

    # ─────────────────────────────────────────────
    # Step 5: 生成综合报告
    # ─────────────────────────────────────────────

    def _step5_generate_report(self):
        """生成综合 Markdown 分析报告"""
        from datetime import datetime
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        report = self._build_report(now)

        # 保存报告
        report_path = REPORTS_DIR / 'full_analysis_report.md'
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(report)
        print(f"  ✅ 综合报告已保存: {report_path}")

        # 同时保存级联失效子报告（如果存在）
        cascade_md = self.results.get('analysis', {}).get('cascade_report_md', '')
        if cascade_md:
            cascade_path = REPORTS_DIR / 'cascade_failure_report.md'
            with open(cascade_path, 'w', encoding='utf-8') as f:
                f.write(cascade_md)
            print(f"  ✅ 级联失效报告已保存: {cascade_path}")

        self.results['report_path'] = str(report_path)

    def _build_report(self, now: str) -> str:
        """构建完整 Markdown 报告"""
        data_info = self.results.get('data_info', {})
        hyper_data = self.results.get('hyper_data', {})
        analysis = self.results.get('analysis', {})
        frame_paths = self.results.get('frame_paths', [])

        H = hyper_data.get('hyper_network', nx.MultiDiGraph())
        layers = hyper_data.get('layers', {})
        cross_edges = hyper_data.get('cross_layer_edges', [])

        shapley_gravity = analysis.get('shapley_gravity', {})
        gravity_info = shapley_gravity.get('gravity_analysis', {})
        cascade = analysis.get('cascade_failure', {})
        hyper_result = cascade.get('hyper_result', {})

        report = f"# AFSIM 作战超网综合分析报告\n\n"
        report += f"> 生成时间：{now}  \n"
        report += f"> 数据文件：`{os.path.basename(self.csv_path)}`  \n"
        report += f"> 分析方法：多层超网 + Shapley 值重心分析 + Monte Carlo 级联失效模拟\n\n"
        report += "---\n\n"

        # 1. 数据概况
        report += "## 1. 数据概况\n\n"
        report += f"本次分析使用 AFSIM 仿真数据，共 **{data_info.get('total_rows', 0):,}** 行记录，"
        report += f"**{data_info.get('total_columns', 0)}** 列，"
        report += f"涉及 **{data_info.get('platforms_count', 0)}** 个作战平台，"
        report += f"**{len(data_info.get('message_types', {}))}** 种消息类型。\n\n"

        msg_types = data_info.get('message_types', {})
        if msg_types:
            report += "主要消息类型分布：\n\n"
            report += "| 消息类型 | 记录数 |\n"
            report += "|----------|--------|\n"
            for t, c in sorted(msg_types.items(), key=lambda x: x[1], reverse=True)[:10]:
                report += f"| `{t}` | {c:,} |\n"
            report += "\n"

        # 2. 超网结构
        report += "## 2. 超网结构分析\n\n"
        report += f"构建的作战超网包含 **{H.number_of_nodes()}** 个节点，**{H.number_of_edges()}** 条边，"
        report += f"**{len(cross_edges)}** 个跨层连接，分为以下 {len(layers)} 个功能层：\n\n"

        report += "| 层名 | 节点数 | 边数 | 功能描述 |\n"
        report += "|------|--------|------|----------|\n"
        layer_desc = {
            'sensor': '传感器探测层（雷达/ESM 探测关系）',
            'command': '指挥控制层（C2 指挥链路）',
            'weapon': '武器打击层（SAM/导弹打击关系）',
            'ew': '电子战层（干扰/压制关系）'
        }
        for layer_name, layer_net in layers.items():
            desc = layer_desc.get(layer_name, layer_name)
            report += f"| {layer_name} | {layer_net.number_of_nodes()} | {layer_net.number_of_edges()} | {desc} |\n"
        report += "\n"

        hyper_metrics = hyper_data.get('metrics', {})
        if hyper_metrics:
            report += f"超网跨层密度：{hyper_metrics.get('cross_layer_density', 0):.4f}，"
            report += f"层间耦合强度：{hyper_metrics.get('layer_coupling_strength', 0):.4f}，"
            report += f"跨层连通性：{hyper_metrics.get('cross_layer_connectivity', 0):.4f}\n\n"

        # 3. Shapley 重心分析
        report += "## 3. Shapley 值重心分析\n\n"
        report += "> Shapley 值来自合作博弈论，衡量每个节点对网络整体连通效率的边际贡献，"
        report += "能识别那些单独看不起眼但缺少它整体崩溃的关键节点。\n\n"

        if gravity_info:
            report += f"**超网重心节点**：`{gravity_info.get('gravity_node', 'N/A')}`  \n"
            report += f"**Shapley 分数**：{gravity_info.get('gravity_score', 0):.4f}  \n"
            report += f"**稳定性**：{gravity_info.get('stability', 'N/A')}  \n"
            report += f"**分数差距**：{gravity_info.get('score_gap', 0):.4f}\n\n"

            top10 = gravity_info.get('top10_nodes', [])
            if top10:
                report += "**Top-10 关键节点（Shapley + 中心性融合排名）**\n\n"
                report += "| 排名 | 节点 | 融合分数 |\n"
                report += "|------|------|----------|\n"
                for i, (node, score) in enumerate(top10, 1):
                    report += f"| {i} | `{node}` | {score:.4f} |\n"
                report += "\n"

        layer_importance = shapley_gravity.get('layer_importance', [])
        if layer_importance:
            report += "**各层重要性排名（按平均 Shapley 值）**\n\n"
            report += "| 排名 | 层名 | 平均 Shapley | 最大 Shapley |\n"
            report += "|------|------|-------------|-------------|\n"
            for i, (layer_name, avg, mx) in enumerate(layer_importance, 1):
                report += f"| {i} | {layer_name} | {avg:.4f} | {mx:.4f} |\n"
            report += "\n"

        # 4. 级联失效分析
        report += "## 4. 级联失效分析\n\n"
        baseline = hyper_result.get('baseline', {})
        summary = hyper_result.get('monte_carlo_summary', {})
        single = hyper_result.get('single_removal_analysis', [])
        target_nodes = hyper_result.get('target_nodes', [])

        if baseline:
            report += f"基准网络：节点 {baseline.get('n_nodes', 0)}，"
            report += f"边 {baseline.get('n_edges', 0)}，"
            report += f"全局效率 {baseline.get('global_efficiency', 0):.4f}，"
            report += f"最大连通分量 {baseline.get('lcc_size', 0)} 节点\n\n"

        if summary:
            collapse = summary.get('collapse_step')
            final_drop = summary.get('final_efficiency_drop', 0)
            final_lcc = summary.get('final_lcc_drop', 0)

            if collapse:
                report += f"⚠️ **网络崩溃点**：移除第 **{collapse}** 个关键节点后，全局效率下降超过 50%\n\n"
            else:
                report += f"✅ 移除全部 {len(target_nodes)} 个关键节点后，网络效率下降未超过 50%（韧性较强）\n\n"

            report += f"移除全部关键节点后：平均效率下降 **{final_drop:.1f}%**，LCC 缩减 **{final_lcc:.1f}%**\n\n"

        if single:
            report += "**关键节点单独移除影响（Top-10）**\n\n"
            report += "| 排名 | 节点 | 效率下降% | LCC缩减% | 连通分量增加 |\n"
            report += "|------|------|-----------|----------|-------------|\n"
            for i, item in enumerate(single[:10], 1):
                report += (f"| {i} | `{item['node']}` | "
                           f"{item['efficiency_drop_pct']:.1f}% | "
                           f"{item['lcc_drop_pct']:.1f}% | "
                           f"+{item['components_increase']} |\n")
            report += "\n"

        step_stats = summary.get('step_stats', []) if summary else []
        if step_stats:
            report += "**Monte Carlo 级联失效过程（均值）**\n\n"
            report += "| 移除步骤 | 效率下降均值 | LCC缩减均值 | 连通分量均值 |\n"
            report += "|----------|-------------|------------|-------------|\n"
            for stat in step_stats:
                report += (f"| 第{stat['step']}步 | "
                           f"{stat['efficiency_drop_mean']:.1f}% | "
                           f"{stat['lcc_drop_mean']:.1f}% | "
                           f"{stat['n_components_mean']:.1f} |\n")
            report += "\n"

        # 5. 视频帧信息
        if frame_paths:
            report += "## 5. 超网动态演化视频帧\n\n"
            report += f"共生成 **{len(frame_paths)}** 帧超网快照，保存于 `outputs/frames/` 目录。\n\n"
            gif_path = OUTPUT_DIR / 'hyper_network_animation.gif'
            if gif_path.exists():
                report += f"GIF 动画：`outputs/hyper_network_animation.gif`\n\n"

        # 6. 结论与建议
        report += "## 6. 结论与防御建议\n\n"
        report += self._generate_conclusion(gravity_info, single, summary)

        return report

    def _generate_conclusion(self, gravity_info, single_removal, summary):
        """生成结论段落"""
        conclusion = ""

        if gravity_info:
            gravity_node = gravity_info.get('gravity_node', 'N/A')
            stability = gravity_info.get('stability', 'N/A')
            conclusion += f"通过 Shapley 值重心分析，识别出作战超网的核心重心节点为 `{gravity_node}`，"
            conclusion += f"其稳定性评级为 [{stability}]。该节点在多层网络中具有最高的边际贡献，"
            conclusion += "是整个作战体系的关键枢纽。\n\n"

        if summary:
            collapse = summary.get('collapse_step')
            final_drop = summary.get('final_efficiency_drop', 0)
            if collapse and collapse <= 3:
                conclusion += f"级联失效模拟显示，网络在仅移除 **{collapse}** 个关键节点后即发生崩溃，"
                conclusion += "脆弱性极高，需立即采取加固措施。\n\n"
            elif final_drop > 30:
                conclusion += f"级联失效模拟显示，移除全部关键节点后网络效率下降 {final_drop:.1f}%，"
                conclusion += "存在一定脆弱性，建议重点防护高影响节点。\n\n"
            else:
                conclusion += "级联失效模拟显示，网络具有较强韧性，关键节点失效对整体影响有限。\n\n"

        if single_removal:
            top3 = single_removal[:3]
            conclusion += "**最高优先级防护节点**：\n\n"
            for i, item in enumerate(top3, 1):
                conclusion += (f"{i}. `{item['node']}`：单独移除导致效率下降 "
                               f"**{item['efficiency_drop_pct']:.1f}%**\n")
            conclusion += "\n"

        conclusion += "**防御建议**：\n\n"
        conclusion += "1. 对重心节点实施冗余备份，确保单点失效不影响整体功能\n"
        conclusion += "2. 增加关键节点之间的旁路连接，提升网络连通冗余度\n"
        conclusion += "3. 建立分布式指挥架构，避免过度依赖单一指挥节点\n"
        conclusion += "4. 定期进行级联失效演练，验证网络韧性\n\n"

        return conclusion


def parse_args():
    parser = argparse.ArgumentParser(
        description='AFSIM 超网重心分析 + 级联失效模拟',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument('--csv', default=str(_THIS_DIR),
                        help='仿真数据目录路径（默认：脚本所在目录）')
    parser.add_argument('--frames', type=int, default=20,
                        help='视频帧数量（默认：20）')
    parser.add_argument('--shapley-samples', type=int, default=150,
                        help='Shapley 蒙特卡洛采样次数（默认：150）')
    parser.add_argument('--cascade-rounds', type=int, default=20,
                        help='级联失效 Monte Carlo 轮数（默认：20）')
    parser.add_argument('--no-video', action='store_true',
                        help='跳过视频帧生成')
    return parser.parse_args()


if __name__ == '__main__':
    args = parse_args()

    pipeline = FullAnalysisPipeline(
        csv_path=args.csv,
        n_frames=args.frames,
        shapley_samples=args.shapley_samples,
        cascade_rounds=args.cascade_rounds,
        generate_video=not args.no_video
    )
    pipeline.run()
