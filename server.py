#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
server.py — AFSIM 超网分析后端服务
====================================
提供 REST API：
  POST /api/upload      上传 CSV，触发分析流程（异步）
  GET  /api/status      查询当前分析状态与进度
  GET  /api/results     获取最新分析结果元数据
  POST /api/cancel      取消当前分析

启动：
  python server.py
  python server.py --port 5001
"""

import os
import sys
import json
import time
import shutil
import threading
import traceback
import subprocess
import argparse
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import io

# ── 路径配置 ──────────────────────────────────────────────────────────────────
_THIS_DIR   = Path(__file__).parent.resolve()
_PROJECT_DIR = _THIS_DIR                                    # qky项目文件/
_VUE_PUBLIC  = _THIS_DIR.parent / 'hyper-viz' / 'public'   # hyper-viz/public/

# 确保 public 目录存在
_VUE_PUBLIC.mkdir(parents=True, exist_ok=True)
(_VUE_PUBLIC / 'frames').mkdir(exist_ok=True)
(_VUE_PUBLIC / 'reports').mkdir(exist_ok=True)

# ── 全局状态 ──────────────────────────────────────────────────────────────────
_state = {
    'status':    'idle',      # idle | running | done | error
    'progress':  0,           # 0-100
    'stage':     '',          # 当前阶段描述
    'log':       [],          # 最近日志行（最多 200 条）
    'csv_name':  '',
    'csv_rows':  0,
    'started_at': None,
    'finished_at': None,
    'error':     '',
    'results': {
        'total_frames': 0,
        'nodes': 0,
        'edges': 0,
        'cog_node': '',
        'cog_score': 0.0,
        'has_video': False,
        'has_reports': False,
        'has_complex_network': False,
    }
}
_state_lock = threading.Lock()
_analysis_thread = None
_cancel_flag = threading.Event()


def _log(msg: str):
    """线程安全地追加日志"""
    with _state_lock:
        _state['log'].append(f"[{time.strftime('%H:%M:%S')}] {msg}")
        if len(_state['log']) > 200:
            _state['log'] = _state['log'][-200:]
    print(msg)


def _set_state(**kwargs):
    with _state_lock:
        _state.update(kwargs)


# ── 分析流程（在子线程中运行）────────────────────────────────────────────────

def _run_analysis(csv_path: str):
    """完整分析流程，产物直接写入 hyper-viz/public/"""
    global _cancel_flag
    _cancel_flag.clear()

    try:
        _set_state(status='running', progress=2, stage='初始化环境',
                   started_at=time.time(), error='')
        _log(f"▶ 开始分析: {csv_path}")

        # ── 动态导入（避免顶层 import 失败影响服务启动）──────────────
        sys.path.insert(0, str(_PROJECT_DIR))
        sys.path.insert(0, str(_PROJECT_DIR / 'hyper'))

        import numpy as np
        import pandas as pd
        import networkx as nx
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt

        from data_processor import AFSIMDataProcessor
        from hyper.hyper_network_builder import CombatHyperNetworkBuilder
        from hyper.hyper_network_analyzer import HyperNetworkAnalyzer
        from hyper.hyper_network_visualizer import HyperNetworkVisualizer
        from shapely_gravity_analyzer import ShapelyGravityAnalyzer
        from cascade_failure_simulator import CascadeFailureSimulator

        if _cancel_flag.is_set():
            _set_state(status='idle', stage='已取消'); return

        # ── Step 1: 加载数据 ──────────────────────────────────────────
        _set_state(progress=5, stage='加载 CSV 数据')
        _log('[Step 1] 加载 AFSIM 仿真数据...')
        processor = AFSIMDataProcessor(csv_path)
        info = processor.get_data_info()
        _log(f'  数据行数: {info["total_rows"]}  平台数: {info["platforms_count"]}')
        with _state_lock:
            _state['csv_rows'] = info['total_rows']

        if _cancel_flag.is_set():
            _set_state(status='idle', stage='已取消'); return

        # ── Step 2: 构建超网 ──────────────────────────────────────────
        _set_state(progress=15, stage='构建多层超网')
        _log('[Step 2] 构建全量超网...')
        builder = CombatHyperNetworkBuilder()
        hyper_data = builder.build_hyper_network(processor)
        H = hyper_data['hyper_network']
        _log(f'  超网节点: {H.number_of_nodes()}  边: {H.number_of_edges()}')

        if _cancel_flag.is_set():
            _set_state(status='idle', stage='已取消'); return

        # ── Step 3: Shapley + 级联失效分析 ───────────────────────────
        _set_state(progress=30, stage='Shapley 重心分析 + 级联失效模拟')
        _log('[Step 3] 超网分析（Shapley + 级联失效）...')
        analyzer = HyperNetworkAnalyzer(shapley_samples=150, cascade_rounds=20)
        analysis = analyzer.analyze_hyper_network(hyper_data)

        gravity_node = None
        shapley_scores_dict = None
        shapley_gravity = analysis.get('shapley_gravity', {})
        gravity_info = shapley_gravity.get('gravity_analysis', {})
        if gravity_info:
            gravity_node = gravity_info.get('gravity_node')
            top10 = gravity_info.get('top10_nodes', [])
            _log(f'  🌟 重心节点: {gravity_node}  分数: {gravity_info.get("gravity_score", 0):.4f}')
            if top10:
                shapley_scores_dict = {n: s for n, s in top10}
                deg = dict(H.degree())
                total_deg = sum(deg.values()) or 1
                for n in H.nodes():
                    if n not in shapley_scores_dict:
                        shapley_scores_dict[n] = deg.get(n, 0) / total_deg * 0.01

        if _cancel_flag.is_set():
            _set_state(status='idle', stage='已取消'); return

        # ── Step 4: 生成视频帧 ────────────────────────────────────────
        _set_state(progress=40, stage='生成 3D 旋转动画帧')
        _log('[Step 4] 生成视频帧序列...')

        N_FRAMES = 60
        frames_dir = _VUE_PUBLIC / 'frames'
        frames_dir.mkdir(exist_ok=True)

        # 清空旧帧
        for old in frames_dir.glob('frame_*.png'):
            old.unlink()

        visualizer = HyperNetworkVisualizer(figsize=(20, 11))

        from data_processor import _find_col, _COL_ALIASES
        time_col = processor._col.get('time') or processor.df.columns[0]
        t_min = float(processor.df[time_col].min())
        t_max = float(processor.df[time_col].max())
        step = max(1.0, (t_max - t_min) / N_FRAMES)
        windows = processor.get_time_windows(window_size=step, step=step)
        if len(windows) > N_FRAMES:
            indices = np.linspace(0, len(windows) - 1, N_FRAMES, dtype=int)
            windows = [windows[i] for i in indices]

        total_frames = len(windows)
        _log(f'  实际帧数: {total_frames}  时间范围: {t_min:.0f}~{t_max:.0f}s')

        # 预构建帧图
        frame_graphs = []
        original_df = processor.df
        original_col = processor._col
        for t_start, t_end, df_subset in windows:
            processor.df = df_subset
            processor._col = {k: _find_col(df_subset, k) for k in _COL_ALIASES}
            G_snap = nx.Graph()
            G_snap.add_nodes_from(H.nodes(data=True))
            for src, tgt, w in processor.extract_sensor_detections():
                G_snap.add_edge(src, tgt, color='#3498db', weight=w, type='intra')
            for src, tgt, w in processor.extract_weapon_engagements():
                G_snap.add_edge(src, tgt, color='#e74c3c', weight=w, type='inter')
            for src, tgt, w in processor.extract_jamming_relations():
                G_snap.add_edge(src, tgt, color='#9b59b6', weight=w, type='inter')
            for sub, cmd in processor.extract_platform_hierarchy().items():
                G_snap.add_edge(sub, cmd, color='#2ecc71', weight=0.5, type='inter')
            frame_graphs.append((t_start, t_end, G_snap))
        processor.df = original_df
        processor._col = original_col

        # 渲染帧
        frame_paths = []
        azim_start = 35
        azim_step = 360.0 / max(total_frames, 1)
        for frame_idx, (t_start, t_end, G_snap) in enumerate(frame_graphs):
            if _cancel_flag.is_set():
                _set_state(status='idle', stage='已取消'); return

            frame_path = frames_dir / f'frame_{frame_idx:04d}.png'
            azim = azim_start + frame_idx * azim_step
            snap_data = dict(hyper_data)
            snap_data['hyper_network'] = G_snap
            try:
                visualizer.visualize_hyper_network(
                    snap_data,
                    save_path=str(frame_path),
                    azim=azim,
                    gravity_node=gravity_node,
                    frame_meta={
                        't_start': t_start, 't_end': t_end,
                        'frame_idx': frame_idx, 'total_frames': total_frames,
                    },
                    shapley_scores=shapley_scores_dict,
                )
                frame_paths.append(str(frame_path))
            except Exception as e:
                _log(f'  ⚠️ 帧 {frame_idx} 渲染失败: {e}')
                frame_paths.append('')

            # 更新进度 40→75
            pct = 40 + int((frame_idx + 1) / total_frames * 35)
            _set_state(progress=pct,
                       stage=f'渲染帧 {frame_idx+1}/{total_frames}')

        _log(f'  ✅ 帧渲染完毕，共 {len([p for p in frame_paths if p])} 帧')

        # ── Step 5: 合成 MP4 ──────────────────────────────────────────
        _set_state(progress=78, stage='合成 MP4 视频')
        _log('[Step 5] 合成 MP4...')
        mp4_path = _VUE_PUBLIC / 'hyper_network_animation.mp4'
        ffmpeg_bin = shutil.which('ffmpeg') or '/opt/homebrew/bin/ffmpeg'
        if os.path.exists(ffmpeg_bin):
            cmd = [
                ffmpeg_bin, '-y',
                '-framerate', '2',
                '-i', str(frames_dir / 'frame_%04d.png'),
                '-vf', 'scale=trunc(iw/2)*2:trunc(ih/2)*2',
                '-vcodec', 'libx264', '-crf', '18', '-preset', 'fast',
                '-pix_fmt', 'yuv420p',
                str(mp4_path)
            ]
            ret = subprocess.run(cmd, capture_output=True)
            if ret.returncode == 0 and mp4_path.exists():
                size_mb = mp4_path.stat().st_size / 1024 / 1024
                _log(f'  🎬 MP4 已生成: {size_mb:.2f} MB')
            else:
                _log(f'  ⚠️ ffmpeg 失败: {ret.stderr.decode()[:200]}')
        else:
            _log(f'  ℹ️ 未找到 ffmpeg，跳过 MP4 合成')

        if _cancel_flag.is_set():
            _set_state(status='idle', stage='已取消'); return

        # ── Step 6: 生成复杂网络图 ────────────────────────────────────
        _set_state(progress=82, stage='生成综合复杂网络图')
        _log('[Step 6] 生成综合复杂网络图...')
        try:
            _generate_complex_network(processor, hyper_data, _VUE_PUBLIC / 'complex_network.png')
            _log('  ✅ 复杂网络图已生成')
        except Exception as e:
            _log(f'  ⚠️ 复杂网络图生成失败: {e}')
            traceback.print_exc()

        # ── Step 7: 生成报告 ──────────────────────────────────────────
        _set_state(progress=90, stage='生成分析报告')
        _log('[Step 7] 生成 Markdown 报告...')
        reports_dir = _VUE_PUBLIC / 'reports'
        reports_dir.mkdir(exist_ok=True)

        try:
            _generate_reports(info, hyper_data, analysis, total_frames,
                              csv_path, reports_dir)
            # 同时复制到 public 根目录（兼容旧路径）
            for fname in ['full_analysis_report.md', 'cascade_failure_report.md']:
                src = reports_dir / fname
                if src.exists():
                    shutil.copy2(src, _VUE_PUBLIC / fname)
            _log('  ✅ 报告已生成')
        except Exception as e:
            _log(f'  ⚠️ 报告生成失败: {e}')
            traceback.print_exc()

        # ── 完成 ──────────────────────────────────────────────────────
        _set_state(
            progress=100,
            stage='分析完成',
            status='done',
            finished_at=time.time(),
            results={
                'total_frames': total_frames,
                'nodes': H.number_of_nodes(),
                'edges': H.number_of_edges(),
                'cog_node': gravity_node or '',
                'cog_score': float(gravity_info.get('gravity_score', 0)) if gravity_info else 0.0,
                'has_video': mp4_path.exists() if 'mp4_path' in dir() else False,
                'has_reports': True,
                'has_complex_network': (_VUE_PUBLIC / 'complex_network.png').exists(),
            }
        )
        elapsed = time.time() - _state['started_at']
        _log(f'✅ 全部完成！耗时 {elapsed:.1f} 秒')

    except Exception as e:
        _log(f'❌ 分析失败: {e}')
        traceback.print_exc()
        _set_state(status='error', error=str(e), stage='分析失败')


def _generate_complex_network(processor, hyper_data, out_path: Path):
    """生成综合复杂网络双视图（Spring + Kamada-Kawai）"""
    import networkx as nx
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches

    # 尝试使用项目内的 CombatNetworkBuilder
    try:
        sys.path.insert(0, str(_PROJECT_DIR))
        from network_builder import CombatNetworkBuilder
        nb = CombatNetworkBuilder()
        G = nb.build_network(processor)
    except Exception:
        # fallback：直接从 hyper_data 构建
        G = hyper_data.get('hyper_network', nx.Graph())

    if G.number_of_nodes() == 0:
        return

    # 节点颜色
    def node_color(n):
        nl = str(n).lower()
        if any(k in nl for k in ['sam', 'launcher', 'missile', 'ttr']): return '#c62828'
        if any(k in nl for k in ['iads', 'cmdr', 'command', 'c2', 'ucav']): return '#2e7d32'
        if any(k in nl for k in ['_soj', 'soj_', 'jammer']) or nl.endswith('soj'): return '#d84315'
        if any(k in nl for k in ['radar', 'sensor', 'esm']): return '#1565c0'
        return '#546e7a'

    colors = [node_color(n) for n in G.nodes()]

    fig, axes = plt.subplots(1, 2, figsize=(22, 10))
    fig.patch.set_facecolor('#0d1117')

    layouts = [
        ('Spring Layout', nx.spring_layout(G, seed=42, k=2.5/max(G.number_of_nodes()**0.5, 1))),
        ('Kamada-Kawai', nx.kamada_kawai_layout(G) if G.number_of_nodes() < 200 else nx.spring_layout(G, seed=7)),
    ]

    for ax, (title, pos) in zip(axes, layouts):
        ax.set_facecolor('#0d1117')
        nx.draw_networkx_edges(G, pos, ax=ax, alpha=0.25, width=0.8,
                               edge_color='#8b949e')
        nx.draw_networkx_nodes(G, pos, ax=ax, node_color=colors,
                               node_size=280, edgecolors='white', linewidths=0.5, alpha=0.9)
        nx.draw_networkx_labels(G, pos, ax=ax, font_size=5.5,
                                font_color='white', font_weight='bold')
        ax.set_title(title, color='white', fontsize=13, pad=10)
        ax.set_axis_off()

    legend_items = [
        mpatches.Patch(color='#1565c0', label='Radar/Sensor'),
        mpatches.Patch(color='#d84315', label='EW/SOJ'),
        mpatches.Patch(color='#2e7d32', label='Command/UCAV'),
        mpatches.Patch(color='#c62828', label='SAM/Weapon'),
        mpatches.Patch(color='#546e7a', label='Other'),
    ]
    fig.legend(handles=legend_items, loc='lower center', ncol=5,
               facecolor='#161b22', edgecolor='#30363d',
               labelcolor='white', fontsize=10, framealpha=0.9)

    fig.suptitle(
        f'Integrated Combat Network  |  Nodes: {G.number_of_nodes()}  Edges: {G.number_of_edges()}',
        color='white', fontsize=14, y=0.98
    )
    plt.tight_layout(rect=[0, 0.06, 1, 0.96])
    plt.savefig(str(out_path), dpi=120, bbox_inches='tight',
                facecolor='#0d1117', edgecolor='none')
    plt.close(fig)


def _generate_reports(info, hyper_data, analysis, total_frames,
                      csv_path, reports_dir: Path):
    """生成 Markdown 报告"""
    from datetime import datetime
    import networkx as nx

    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    H = hyper_data.get('hyper_network', nx.Graph())
    layers = hyper_data.get('layers', {})
    cross_edges = hyper_data.get('cross_layer_edges', [])

    shapley_gravity = analysis.get('shapley_gravity', {})
    gravity_info = shapley_gravity.get('gravity_analysis', {})
    cascade = analysis.get('cascade_failure', {})
    hyper_result = cascade.get('hyper_result', {})

    # ── 综合报告 ──────────────────────────────────────────────────
    report = f"# AFSIM 作战超网综合分析报告\n\n"
    report += f"> 生成时间：{now}  \n"
    report += f"> 数据文件：`{os.path.basename(csv_path)}`  \n"
    report += f"> 分析方法：多层超网 + Shapley 值重心分析 + Monte Carlo 级联失效模拟\n\n---\n\n"

    report += "## 1. 数据概况\n\n"
    report += (f"本次分析使用 AFSIM 仿真数据，共 **{info.get('total_rows', 0):,}** 行记录，"
               f"**{info.get('total_columns', 0)}** 列，"
               f"涉及 **{info.get('platforms_count', 0)}** 个作战平台，"
               f"**{len(info.get('message_types', {}))}** 种消息类型。\n\n")

    msg_types = info.get('message_types', {})
    if msg_types:
        report += "主要消息类型分布：\n\n| 消息类型 | 记录数 |\n|----------|--------|\n"
        for t, c in sorted(msg_types.items(), key=lambda x: x[1], reverse=True)[:10]:
            report += f"| `{t}` | {c:,} |\n"
        report += "\n"

    report += "## 2. 超网结构分析\n\n"
    report += (f"构建的作战超网包含 **{H.number_of_nodes()}** 个节点，**{H.number_of_edges()}** 条边，"
               f"**{len(cross_edges)}** 个跨层连接，分为以下 {len(layers)} 个功能层：\n\n")
    report += "| 层名 | 节点数 | 边数 | 功能描述 |\n|------|--------|------|----------|\n"
    layer_desc = {
        'sensor': '传感器探测层（雷达/ESM 探测关系）',
        'command': '指挥控制层（C2 指挥链路）',
        'weapon': '武器打击层（SAM/导弹打击关系）',
        'ew': '电子战层（干扰/压制关系）'
    }
    for ln, lnet in layers.items():
        report += f"| {ln} | {lnet.number_of_nodes()} | {lnet.number_of_edges()} | {layer_desc.get(ln, ln)} |\n"
    report += "\n"

    report += "## 3. Shapley 值重心分析\n\n"
    report += ("> Shapley 值来自合作博弈论，衡量每个节点对网络整体连通效率的边际贡献，"
               "能识别那些单独看不起眼但缺少它整体崩溃的关键节点。\n\n")
    if gravity_info:
        report += (f"**超网重心节点**：`{gravity_info.get('gravity_node', 'N/A')}`  \n"
                   f"**Shapley 分数**：{gravity_info.get('gravity_score', 0):.4f}  \n"
                   f"**稳定性**：{gravity_info.get('stability', 'N/A')}  \n"
                   f"**分数差距**：{gravity_info.get('score_gap', 0):.4f}\n\n")
        top10 = gravity_info.get('top10_nodes', [])
        if top10:
            report += "**Top-10 关键节点（Shapley + 中心性融合排名）**\n\n| 排名 | 节点 | 融合分数 |\n|------|------|----------|\n"
            for i, (node, score) in enumerate(top10, 1):
                report += f"| {i} | `{node}` | {score:.4f} |\n"
            report += "\n"

    report += "## 4. 级联失效分析\n\n"
    baseline = hyper_result.get('baseline', {})
    summary = hyper_result.get('monte_carlo_summary', {})
    single = hyper_result.get('single_removal_analysis', [])
    target_nodes = hyper_result.get('target_nodes', [])
    if baseline:
        report += (f"基准网络：节点 {baseline.get('n_nodes', 0)}，"
                   f"边 {baseline.get('n_edges', 0)}，"
                   f"全局效率 {baseline.get('global_efficiency', 0):.4f}，"
                   f"最大连通分量 {baseline.get('lcc_size', 0)} 节点\n\n")
    if summary:
        collapse = summary.get('collapse_step')
        final_drop = summary.get('final_efficiency_drop', 0)
        if collapse:
            report += f"⚠️ **网络崩溃点**：移除第 **{collapse}** 个关键节点后，全局效率下降超过 50%\n\n"
        else:
            report += f"✅ 移除全部 {len(target_nodes)} 个关键节点后，网络效率下降未超过 50%（韧性较强）\n\n"
        report += f"移除全部关键节点后：平均效率下降 **{final_drop:.1f}%**，LCC 缩减 **{summary.get('final_lcc_drop', 0):.1f}%**\n\n"
    if single:
        report += "**关键节点单独移除影响（Top-10）**\n\n| 排名 | 节点 | 效率下降% | LCC缩减% | 连通分量增加 |\n|------|------|-----------|----------|-------------|\n"
        for i, item in enumerate(single[:10], 1):
            report += (f"| {i} | `{item['node']}` | "
                       f"{item['efficiency_drop_pct']:.1f}% | "
                       f"{item['lcc_drop_pct']:.1f}% | "
                       f"+{item['components_increase']} |\n")
        report += "\n"

    report += "## 5. 超网动态演化视频帧\n\n"
    report += f"共生成 **{total_frames}** 帧超网快照，保存于 `public/frames/` 目录。\n\n"

    report += "## 6. 结论与防御建议\n\n"
    if gravity_info:
        gn = gravity_info.get('gravity_node', 'N/A')
        st = gravity_info.get('stability', 'N/A')
        report += (f"通过 Shapley 值重心分析，识别出作战超网的核心重心节点为 `{gn}`，"
                   f"其稳定性评级为 [{st}]。该节点在多层网络中具有最高的边际贡献，"
                   "是整个作战体系的关键枢纽。\n\n")
    if summary:
        collapse = summary.get('collapse_step')
        final_drop = summary.get('final_efficiency_drop', 0)
        if collapse and collapse <= 3:
            report += f"级联失效模拟显示，网络在仅移除 **{collapse}** 个关键节点后即发生崩溃，脆弱性极高。\n\n"
        elif final_drop > 30:
            report += f"级联失效模拟显示，移除全部关键节点后网络效率下降 {final_drop:.1f}%，存在一定脆弱性。\n\n"
        else:
            report += "级联失效模拟显示，网络具有较强韧性，关键节点失效对整体影响有限。\n\n"
    report += ("**防御建议**：\n\n"
               "1. 对重心节点实施冗余备份，确保单点失效不影响整体功能\n"
               "2. 增加关键节点之间的旁路连接，提升网络连通冗余度\n"
               "3. 建立分布式指挥架构，避免过度依赖单一指挥节点\n"
               "4. 定期进行级联失效演练，验证网络韧性\n\n")

    with open(reports_dir / 'full_analysis_report.md', 'w', encoding='utf-8') as f:
        f.write(report)

    # ── 级联失效子报告 ────────────────────────────────────────────
    cascade_md = analysis.get('cascade_report_md', '')
    if not cascade_md:
        cascade_md = f"# 级联失效分析报告\n\n> 生成时间：{now}\n\n"
        if summary:
            cascade_md += f"## 模拟结果摘要\n\n"
            cascade_md += f"- 崩溃步骤：{summary.get('collapse_step', '未崩溃')}\n"
            cascade_md += f"- 最终效率下降：{summary.get('final_efficiency_drop', 0):.1f}%\n"
            cascade_md += f"- LCC 缩减：{summary.get('final_lcc_drop', 0):.1f}%\n\n"
        if single:
            cascade_md += "## 关键节点影响排名\n\n| 排名 | 节点 | 效率下降% |\n|------|------|----------|\n"
            for i, item in enumerate(single[:15], 1):
                cascade_md += f"| {i} | `{item['node']}` | {item['efficiency_drop_pct']:.1f}% |\n"

    with open(reports_dir / 'cascade_failure_report.md', 'w', encoding='utf-8') as f:
        f.write(cascade_md)


# ── HTTP 请求处理器 ───────────────────────────────────────────────────────────

class APIHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # 静默 HTTP 日志

    def _send_json(self, data: dict, status: int = 200):
        body = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == '/api/status':
            with _state_lock:
                data = {
                    'status':      _state['status'],
                    'progress':    _state['progress'],
                    'stage':       _state['stage'],
                    'csv_name':    _state['csv_name'],
                    'csv_rows':    _state['csv_rows'],
                    'started_at':  _state['started_at'],
                    'finished_at': _state['finished_at'],
                    'error':       _state['error'],
                    'results':     _state['results'],
                    'log':         _state['log'][-30:],  # 最近 30 条
                }
            self._send_json(data)

        elif path == '/api/results':
            with _state_lock:
                self._send_json(_state['results'])

        elif path == '/api/log':
            with _state_lock:
                self._send_json({'log': _state['log']})

        else:
            self._send_json({'error': 'Not found'}, 404)

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == '/api/upload':
            self._handle_upload()
        elif path == '/api/cancel':
            _cancel_flag.set()
            _set_state(status='idle', stage='已取消', progress=0)
            self._send_json({'ok': True, 'message': '已取消分析'})
        else:
            self._send_json({'error': 'Not found'}, 404)

    def _handle_upload(self):
        global _analysis_thread

        # 检查是否已在运行
        if _state['status'] == 'running':
            self._send_json({'ok': False, 'error': '分析正在进行中，请等待完成或取消后再上传'}, 409)
            return

        content_type = self.headers.get('Content-Type', '')
        content_length = int(self.headers.get('Content-Length', 0))

        if 'multipart/form-data' not in content_type:
            self._send_json({'ok': False, 'error': '请使用 multipart/form-data 上传'}, 400)
            return

        # 解析 multipart
        body = self.rfile.read(content_length)
        boundary = content_type.split('boundary=')[-1].strip().encode()

        csv_data = None
        csv_name = 'uploaded.csv'

        # 简单解析 multipart
        parts = body.split(b'--' + boundary)
        for part in parts:
            if b'Content-Disposition' not in part:
                continue
            header_end = part.find(b'\r\n\r\n')
            if header_end == -1:
                continue
            headers_raw = part[:header_end].decode('utf-8', errors='ignore')
            content = part[header_end + 4:]
            # 去掉末尾 \r\n
            if content.endswith(b'\r\n'):
                content = content[:-2]

            if 'filename=' in headers_raw:
                # 提取文件名：只取 Content-Disposition 行，避免跨行污染
                cd_line = ''
                for line in headers_raw.splitlines():
                    if 'Content-Disposition' in line:
                        cd_line = line
                        break
                for h in cd_line.split(';'):
                    h = h.strip()
                    if h.lower().startswith('filename='):
                        csv_name = h.split('=', 1)[1].strip().strip('"').strip()
                        break
                csv_data = content

        if csv_data is None:
            self._send_json({'ok': False, 'error': '未找到 CSV 文件'}, 400)
            return

        # 保存 CSV 到临时位置
        upload_path = _PROJECT_DIR / 'uploaded_data.csv'
        with open(upload_path, 'wb') as f:
            f.write(csv_data)

        _set_state(
            status='running', progress=1, stage='准备中',
            csv_name=csv_name, error='', log=[],
            results={
                'total_frames': 0, 'nodes': 0, 'edges': 0,
                'cog_node': '', 'cog_score': 0.0,
                'has_video': False, 'has_reports': False, 'has_complex_network': False,
            }
        )

        # 启动分析线程
        _analysis_thread = threading.Thread(
            target=_run_analysis,
            args=(str(upload_path),),
            daemon=True
        )
        _analysis_thread.start()

        self._send_json({
            'ok': True,
            'message': f'已接收 {csv_name}，分析已启动',
            'csv_name': csv_name,
        })


# ── 主入口 ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description='AFSIM 超网分析后端服务')
    parser.add_argument('--port', type=int, default=5001, help='监听端口（默认 5001）')
    parser.add_argument('--host', default='127.0.0.1', help='监听地址（默认 127.0.0.1）')
    args = parser.parse_args()

    print(f"🚀 AFSIM 分析后端服务启动")
    print(f"   监听: http://{args.host}:{args.port}")
    print(f"   项目目录: {_PROJECT_DIR}")
    print(f"   Vue public: {_VUE_PUBLIC}")
    print(f"   API: POST /api/upload  GET /api/status  POST /api/cancel")

    server = HTTPServer((args.host, args.port), APIHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\n⏹ 服务已停止')


if __name__ == '__main__':
    main()
