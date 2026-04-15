#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
server.py — 超网分析后端服务
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
import zipfile
import tempfile
from typing import Optional

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

# ── 全局可调参数（前端配置页写入，分析时读取）────────────────────────────────
_config = {
    # ── Shapley 分析 ──────────────────────────────────────────
    'shapley_samples':        150,    # 蒙特卡洛采样次数（越大越精确，越慢）
    'cascade_rounds':         20,     # 级联失效 Monte Carlo 轮数
    # ── 重心融合权重（degree_w + shapley_w 应 = 1.0）─────────
    'degree_weight':          0.4,    # 度中心性权重
    'shapley_weight':         0.6,    # Shapley 值权重
    # ── 桥梁加分融合（shapley_base_w + bridge_w 应 = 1.0）────
    'shapley_base_weight':    0.7,    # 基础 Shapley 保留比例
    'bridge_bonus_weight':    0.3,    # 跨层桥梁加分比例
    # ── 逐帧动态融合（global_w + frame_deg_w 应 = 1.0）───────
    'frame_global_weight':    0.5,    # 全局 Shapley 在帧融合中的权重
    'frame_degree_weight':    0.5,    # 当前帧度数在帧融合中的权重
    # ── 视频帧生成 ────────────────────────────────────────────
    'n_frames':               60,     # 生成帧总数
    'video_fps':              2,      # 视频帧率（fps）
    'video_crf':              18,     # 视频质量（0=无损，51=最差，18=高质量）
    'azim_start':             35,     # 3D 旋转起始方位角（度）
    # ── 时间窗口 ──────────────────────────────────────────────
    'time_window_override':   0,      # 手动指定时间窗口大小（秒），0=自动
    # ── 复杂网络图 ────────────────────────────────────────────
    'cn_betweenness_k':       100,    # 介数中心性采样节点数（越大越精确）
    'cn_top_n':               10,     # 中心性排名展示 Top-N（兼容旧字段）
    # ── 关键节点展示模式 ──────────────────────────────────────
    'top_n_mode':             'abs',  # 展示模式：abs=固定数量 / pct=百分比 / all=全部
    'top_n_abs':              10,     # 固定数量模式：展示前 N 个节点
    'top_n_pct':              10,     # 百分比模式：展示前 N% 节点
    # ── 级联失效崩溃阈值 ──────────────────────────────────────
    'collapse_threshold_pct': 50.0,   # 效率下降超过此百分比视为网络崩溃
}
_config_lock = threading.Lock()


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


# ── 上传数据路径解析辅助函数 ──────────────────────────────────────────────────

# 全局临时目录（进程生命周期内保留，避免重复解压）
_upload_tmp_dir: Optional[str] = None


def _resolve_upload(csv_data: bytes, csv_name: str) -> str:
    """
    将上传的原始字节保存到磁盘，返回数据目录路径（str）。

    支持两种上传格式：
      1. ZIP 包（csv_name 以 .zip 结尾）→ 解压到临时目录，返回目录路径
      2. 单个 CSV 文件 → 写入 uploaded_data/ 子目录，返回该目录路径
    """
    global _upload_tmp_dir

    # 清理上次的临时目录
    if _upload_tmp_dir and os.path.isdir(_upload_tmp_dir):
        try:
            shutil.rmtree(_upload_tmp_dir)
        except Exception:
            pass

    _upload_tmp_dir = tempfile.mkdtemp(prefix='hyper_upload_')

    if csv_name.lower().endswith('.zip'):
        # ZIP 包：解压到临时目录
        try:
            with zipfile.ZipFile(io.BytesIO(csv_data)) as zf:
                zf.extractall(_upload_tmp_dir)
            _log(f'  ZIP 解压完成: {_upload_tmp_dir}')
        except zipfile.BadZipFile as e:
            raise ValueError(f'ZIP 文件损坏: {e}')
        return _upload_tmp_dir
    else:
        # 单个 CSV：写入临时目录
        csv_path = os.path.join(_upload_tmp_dir, csv_name)
        with open(csv_path, 'wb') as f:
            f.write(csv_data)
        return _upload_tmp_dir


def _resolve_data_dir(path: str) -> str:
    """
    将传入的路径统一解析为数据目录路径。

    - 如果是目录 → 直接返回
    - 如果是 ZIP 文件 → 解压到临时目录，返回目录路径
    - 如果是单个 CSV 文件 → 返回其父目录（兼容旧版单文件上传）
    """
    if os.path.isdir(path):
        return path
    if os.path.isfile(path):
        if path.lower().endswith('.zip'):
            tmp = tempfile.mkdtemp(prefix='hyper_zip_')
            with zipfile.ZipFile(path) as zf:
                zf.extractall(tmp)
            return tmp
        # 单个 CSV：返回父目录
        return os.path.dirname(path) or '.'
    raise FileNotFoundError(f'数据路径不存在: {path}')


def _save_csv_files(csv_files: dict) -> str:
    """
    将前端上传的多个 CSV 文件（{filename: bytes}）写入临时目录，返回目录路径。
    每次调用会清理上次的临时目录。
    """
    global _upload_tmp_dir

    if _upload_tmp_dir and os.path.isdir(_upload_tmp_dir):
        try:
            shutil.rmtree(_upload_tmp_dir)
        except Exception:
            pass

    _upload_tmp_dir = tempfile.mkdtemp(prefix='hyper_upload_')

    for fname, data in csv_files.items():
        # 只取文件名部分，防止路径穿越
        safe_name = os.path.basename(fname)
        with open(os.path.join(_upload_tmp_dir, safe_name), 'wb') as f:
            f.write(data)

    _log(f'  已写入 {len(csv_files)} 个 CSV 到临时目录: {_upload_tmp_dir}')
    return _upload_tmp_dir


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

        from data_processor import SimDataProcessor
        from hyper.hyper_network_builder import CombatHyperNetworkBuilder
        from hyper.hyper_network_analyzer import HyperNetworkAnalyzer
        from hyper.hyper_network_visualizer import HyperNetworkVisualizer
        from shapely_gravity_analyzer import ShapelyGravityAnalyzer
        from cascade_failure_simulator import CascadeFailureSimulator

        if _cancel_flag.is_set():
            _set_state(status='idle', stage='已取消'); return

        # ── Step 1: 加载数据 ──────────────────────────────────────────
        _set_state(progress=5, stage='加载 CSV 数据')
        _log('[Step 1] 加载仿真数据...')
        # csv_path 可能是目录、ZIP 文件或单个 CSV（兼容旧版）
        csv_dir = _resolve_data_dir(csv_path)
        processor = SimDataProcessor(csv_dir)
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
        # ── 读取当前配置快照（分析期间不受前端修改影响）────────────
        with _config_lock:
            cfg = dict(_config)

        _set_state(progress=30, stage='Shapley 重心分析 + 级联失效模拟')
        _log('[Step 3] 超网分析（Shapley + 级联失效）...')
        _log(f'  配置: shapley_samples={cfg["shapley_samples"]}  cascade_rounds={cfg["cascade_rounds"]}')
        analyzer = HyperNetworkAnalyzer(
            shapley_samples=cfg['shapley_samples'],
            cascade_rounds=cfg['cascade_rounds'],
        )
        # 计算 Shapley top_n：与复杂网络中心性使用相同的展示模式
        _mode = cfg.get('top_n_mode', 'abs')
        if _mode == 'all':
            _shapley_top_n = 0          # 0 = 全部
        elif _mode == 'pct':
            # 超网节点数尚未知，先用 abs 占位；_build_result 内部会截断到实际节点数
            _shapley_top_n = cfg.get('top_n_abs', 10)
        else:
            _shapley_top_n = cfg.get('top_n_abs', cfg.get('cn_top_n', 10))
        analysis = analyzer.analyze_hyper_network(
            hyper_data,
            degree_weight=cfg['degree_weight'],
            shapley_weight=cfg['shapley_weight'],
            shapley_base_weight=cfg['shapley_base_weight'],
            bridge_bonus_weight=cfg['bridge_bonus_weight'],
            top_n=_shapley_top_n,
        )

        gravity_node = None
        shapley_scores_dict = None
        shapley_gravity = analysis.get('shapley_gravity', {})
        gravity_info = shapley_gravity.get('gravity_analysis', {})
        if gravity_info:
            # pct 模式：现在知道超网节点数了，重新截断 topn_nodes
            if cfg.get('top_n_mode', 'abs') == 'pct':
                _all_sv = gravity_info.get('all_shapley_values', {})
                _n_hyper = len(_all_sv) if _all_sv else H.number_of_nodes()
                _pct_n = max(1, int(_n_hyper * cfg.get('top_n_pct', 10) / 100))
                _sorted_sv = sorted(_all_sv.items(), key=lambda x: x[1], reverse=True)
                gravity_info['top10_nodes'] = _sorted_sv[:_pct_n]
                gravity_info['topn_nodes']  = _sorted_sv[:_pct_n]
                gravity_info['top_n_actual'] = _pct_n
            gravity_node = gravity_info.get('gravity_node')
            _log(f'  🌟 重心节点: {gravity_node}  分数: {gravity_info.get("gravity_score", 0):.4f}')
            # 优先使用 combined_shapley（度+Shapley 融合分数）作为条形图数据
            combined = shapley_gravity.get('combined_shapley', {})
            if combined:
                shapley_scores_dict = dict(combined)
            else:
                # 回退：用 top10 列表
                top10 = gravity_info.get('top10_nodes', [])
                if top10:
                    shapley_scores_dict = {n: s for n, s in top10}
            # 补充未在列表中的节点（用归一化度数作为默认分）
            if shapley_scores_dict is not None:
                deg = dict(H.degree())
                max_deg = max(deg.values()) if deg else 0
                max_deg = max_deg or 1
                for n in H.nodes():
                    if n not in shapley_scores_dict:
                        shapley_scores_dict[n] = deg.get(n, 0) / max_deg * 0.01

        if _cancel_flag.is_set():
            _set_state(status='idle', stage='已取消'); return

        # ── Step 4: 生成视频帧 ────────────────────────────────────────
        _set_state(progress=40, stage='生成 3D 旋转动画帧')
        _log('[Step 4] 生成视频帧序列...')

        N_FRAMES = cfg['n_frames']
        frames_dir = _VUE_PUBLIC / 'frames'
        frames_dir.mkdir(exist_ok=True)

        # 清空旧帧
        for old in frames_dir.glob('frame_*.png'):
            old.unlink()

        visualizer = HyperNetworkVisualizer(figsize=(20, 11))

        # 时间范围由 processor 统一提供，不再直接访问 df
        t_min, t_max = processor.get_time_range()
        if cfg['time_window_override'] > 0:
            step = float(cfg['time_window_override'])
        else:
            step = max(1.0, (t_max - t_min) / N_FRAMES)
        windows = processor.get_time_windows(window_size=step, step=step)
        if len(windows) > N_FRAMES:
            indices = np.linspace(0, len(windows) - 1, N_FRAMES, dtype=int)
            windows = [windows[i] for i in indices]

        total_frames = len(windows)
        _log(f'  实际帧数: {total_frames}  时间范围: {t_min:.0f}~{t_max:.0f}s')

        # 预构建帧图：直接使用 sub_processor（_SnapProcessor），无需手动 patch df
        frame_graphs = []
        for t_start, t_end, sub_proc in windows:
            G_snap = nx.Graph()
            G_snap.add_nodes_from(H.nodes(data=True))
            for src, tgt, w in sub_proc.extract_sensor_detections():
                G_snap.add_edge(src, tgt, color='#3498db', weight=w, type='intra')
            for src, tgt, w in sub_proc.extract_weapon_engagements():
                G_snap.add_edge(src, tgt, color='#e74c3c', weight=w, type='inter')
            for src, tgt, w in sub_proc.extract_jamming_relations():
                G_snap.add_edge(src, tgt, color='#9b59b6', weight=w, type='inter')
            for sub, cmd in sub_proc.extract_platform_hierarchy().items():
                G_snap.add_edge(sub, cmd, color='#2ecc71', weight=0.5, type='inter')
            frame_graphs.append((t_start, t_end, G_snap))

        # 渲染帧
        frame_paths = []
        azim_start = cfg['azim_start']
        azim_step = 360.0 / max(total_frames, 1)
        _fw_global = cfg['frame_global_weight']
        _fw_degree = cfg['frame_degree_weight']
        for frame_idx, (t_start, t_end, G_snap) in enumerate(frame_graphs):
            if _cancel_flag.is_set():
                _set_state(status='idle', stage='已取消'); return

            frame_path = frames_dir / f'frame_{frame_idx:04d}.png'
            azim = azim_start + frame_idx * azim_step
            snap_data = dict(hyper_data)
            snap_data['hyper_network'] = G_snap

            # ── 逐帧动态 Shapley 近似 ──────────────────────────────────────
            # 公式：frame_score = global_shapley * frame_global_weight + frame_degree_norm * frame_degree_weight
            frame_deg = dict(G_snap.degree())
            max_frame_deg = max(frame_deg.values()) if frame_deg else 0
            max_frame_deg = max_frame_deg or 1   # 防止所有节点度数为 0 时除零
            frame_deg_norm = {n: v / max_frame_deg for n, v in frame_deg.items()}

            if shapley_scores_dict:
                dynamic_scores = {}
                all_nodes_snap = set(frame_deg.keys()) | set(shapley_scores_dict.keys())
                for n in all_nodes_snap:
                    g_s = shapley_scores_dict.get(n, 0.0)
                    d_s = frame_deg_norm.get(n, 0.0)
                    dynamic_scores[n] = g_s * _fw_global + d_s * _fw_degree
                # 归一化到 [0,1]
                max_ds = max(dynamic_scores.values()) if dynamic_scores else 1
                min_ds = min(dynamic_scores.values()) if dynamic_scores else 0
                rng = max_ds - min_ds or 1
                dynamic_scores = {n: (v - min_ds) / rng for n, v in dynamic_scores.items()}
            else:
                dynamic_scores = frame_deg_norm

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
                    shapley_scores=dynamic_scores,   # 传入动态融合分数
                )
                frame_paths.append(str(frame_path))
            except Exception as e:
                import traceback as _tb
                _log(f'  ⚠️ 帧 {frame_idx} 渲染失败: {e} | {_tb.format_exc().splitlines()[-2]}')
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

        # 收集实际存在的帧，重命名为连续序列，避免空洞导致 ffmpeg 失败
        actual_frames = sorted(frames_dir.glob('frame_*.png'))
        if actual_frames and os.path.exists(ffmpeg_bin):
            # 重命名为连续序列 seq_0000.png ...
            seq_dir = frames_dir / 'seq'
            seq_dir.mkdir(exist_ok=True)
            for old_f in seq_dir.glob('seq_*.png'):
                old_f.unlink()
            for i, fp in enumerate(actual_frames):
                import shutil as _sh
                _sh.copy2(str(fp), str(seq_dir / f'seq_{i:04d}.png'))
            cmd = [
                ffmpeg_bin, '-y',
                '-framerate', str(cfg['video_fps']),
                '-i', str(seq_dir / 'seq_%04d.png'),
                '-vf', 'scale=trunc(iw/2)*2:trunc(ih/2)*2',
                '-vcodec', 'libx264', '-crf', str(cfg['video_crf']), '-preset', 'fast',
                '-pix_fmt', 'yuv420p',
                str(mp4_path)
            ]
            ret = subprocess.run(cmd, capture_output=True)
            if ret.returncode == 0 and mp4_path.exists():
                size_mb = mp4_path.stat().st_size / 1024 / 1024
                _log(f'  🎬 MP4 已生成: {size_mb:.2f} MB ({len(actual_frames)} 帧)')
            else:
                _log(f'  ⚠️ ffmpeg 失败: {ret.stderr.decode()[:300]}')
        elif not actual_frames:
            _log(f'  ⚠️ 无可用帧，跳过 MP4 合成')
        else:
            _log(f'  ℹ️ 未找到 ffmpeg，跳过 MP4 合成')

        if _cancel_flag.is_set():
            _set_state(status='idle', stage='已取消'); return

        # ── Step 6: 生成复杂网络图 ────────────────────────────────────
        _set_state(progress=82, stage='生成综合复杂网络图')
        _log('[Step 6] 生成综合复杂网络图...')
        cn_metrics = {}
        try:
            cn_metrics = _generate_complex_network(processor, hyper_data, _VUE_PUBLIC / 'complex_network.png', cfg=cfg) or {}
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
                              csv_path, reports_dir, cn_metrics=cn_metrics)
            # 同时复制到 public 根目录（兼容旧路径）
            for fname in ['full_analysis_report.md', 'cascade_failure_report.md',
                          'complex_network_report.md']:
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
                't_min': float(t_min),
                't_max': float(t_max),
            }
        )
        elapsed = time.time() - _state['started_at']
        _log(f'✅ 全部完成！耗时 {elapsed:.1f} 秒')

    except Exception as e:
        _log(f'❌ 分析失败: {e}')
        traceback.print_exc()
        _set_state(status='error', error=str(e), stage='分析失败')


def _generate_complex_network(processor, hyper_data, out_path: Path, cfg: dict = None) -> dict:
    """生成综合复杂网络双视图（Spring + Kamada-Kawai），返回网络指标字典"""
    if cfg is None:
        cfg = _config
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
        nets = nb.build_multi_layer_network(processor)
        G = nets.get('integrated', nx.Graph())
        # integrated 为空时用各层合并
        if G.number_of_nodes() == 0:
            G = nx.Graph()
            for k, v in nets.items():
                if k != 'integrated':
                    G = nx.compose(G, v.to_undirected() if v.is_directed() else v)
    except Exception:
        # fallback：直接从 hyper_data 构建
        G = hyper_data.get('hyper_network', nx.Graph())

    if G.number_of_nodes() == 0:
        return {}

    # 统一转为简单无向图，确保所有 networkx 算法兼容
    if G.is_directed():
        G = G.to_undirected()
    if G.is_multigraph():
        G = nx.Graph(G)  # MultiGraph → 普通 Graph（合并多重边）

    # 节点颜色：复用 CombatHyperNetworkBuilder._classify_node 保持与超网分层一致
    try:
        from hyper.hyper_network_builder import CombatHyperNetworkBuilder as _HNB
        _classifier = _HNB()._classify_node
    except Exception:
        _classifier = None

    _LAYER_COLOR = {
        'weapon':  '#c62828',
        'command': '#2e7d32',
        'ew':      '#d84315',
        'sensor':  '#1565c0',
        'unknown': '#546e7a',
    }

    def node_color(n):
        if _classifier:
            lyr = _classifier(n)
            return _LAYER_COLOR.get(lyr, '#546e7a')
        # fallback（_classifier 不可用时）
        nl = str(n).lower()
        if any(k in nl for k in ['_ttr', 'acq_radar', 'ew_radar', 'radar_company']): return '#1565c0'
        if any(k in nl for k in ['_battalion', '_cmdr', 'iads', 'ucav', 'command', 'c2']): return '#2e7d32'
        if nl.endswith('_target') or nl == 'target': return '#1565c0'
        if any(k in nl for k in ['launcher', 'missile', 'torpedo', 'weapon', 'munition']): return '#c62828'
        if any(k in nl for k in ['_soj', 'soj_', 'jammer']) or nl.endswith('soj'): return '#d84315'
        if any(k in nl for k in ['radar', 'sensor', 'esm', 'acq', 'sam']): return '#1565c0'
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

    # ── 计算网络指标 ──────────────────────────────────────────────
    metrics = {}
    try:
        metrics['n_nodes'] = G.number_of_nodes()
        metrics['n_edges'] = G.number_of_edges()
        metrics['density'] = nx.density(G)
        metrics['avg_degree'] = (2 * G.number_of_edges() / G.number_of_nodes()
                                 if G.number_of_nodes() > 0 else 0)

        # 连通分量
        comps = list(nx.connected_components(G))
        metrics['n_components'] = len(comps)
        metrics['lcc_size'] = max(len(c) for c in comps) if comps else 0
        metrics['lcc_ratio'] = metrics['lcc_size'] / metrics['n_nodes'] if metrics['n_nodes'] else 0

        # 在最大连通子图上计算
        Gc = G.subgraph(max(comps, key=len)).copy() if comps else G
        metrics['avg_clustering'] = nx.average_clustering(Gc)
        metrics['avg_path_length'] = (nx.average_shortest_path_length(Gc)
                                      if nx.is_connected(Gc) and Gc.number_of_nodes() < 500
                                      else None)
        metrics['diameter'] = (nx.diameter(Gc)
                               if nx.is_connected(Gc) and Gc.number_of_nodes() < 500
                               else None)

        # 中心性 Top-N（根据展示模式动态计算）
        _bet_k  = min(cfg.get('cn_betweenness_k', 100), G.number_of_nodes())
        _n_nodes = G.number_of_nodes()
        _mode   = cfg.get('top_n_mode', 'abs')
        if _mode == 'all':
            _top_n = _n_nodes
        elif _mode == 'pct':
            _top_n = max(1, int(_n_nodes * cfg.get('top_n_pct', 10) / 100))
        else:  # abs
            _top_n = cfg.get('top_n_abs', cfg.get('cn_top_n', 10))
        deg_cent = nx.degree_centrality(G)
        bet_cent = nx.betweenness_centrality(G, normalized=True, k=_bet_k)
        close_cent = nx.closeness_centrality(Gc)

        metrics['top_degree']      = sorted(deg_cent.items(),   key=lambda x: x[1], reverse=True)[:_top_n]
        metrics['top_betweenness'] = sorted(bet_cent.items(),   key=lambda x: x[1], reverse=True)[:_top_n]
        metrics['top_closeness']   = sorted(close_cent.items(), key=lambda x: x[1], reverse=True)[:_top_n]
        metrics['top_n_actual']    = _top_n  # 记录实际展示数量，供报告使用

        # 节点类型分布（复用 _classifier，与节点颜色保持一致）
        type_count = {'radar_sensor': 0, 'ew_soj': 0, 'command': 0, 'weapon': 0, 'other': 0}
        _lyr_to_tc = {'sensor': 'radar_sensor', 'ew': 'ew_soj',
                      'command': 'command', 'weapon': 'weapon', 'unknown': 'other'}
        for n in G.nodes():
            lyr = _classifier(n) if _classifier else 'unknown'
            tc_key = _lyr_to_tc.get(lyr, 'other')
            type_count[tc_key] += 1
        metrics['type_count'] = type_count

        # 度分布统计
        degrees = [d for _, d in G.degree()]
        metrics['max_degree'] = max(degrees) if degrees else 0
        metrics['min_degree'] = min(degrees) if degrees else 0
        import numpy as _np
        metrics['degree_std'] = float(_np.std(degrees)) if degrees else 0.0
    except Exception as _e:
        import traceback as _tb
        print(f'[cn_metrics] 指标计算出错: {_e}')
        _tb.print_exc()

    return metrics


def _generate_reports(info, hyper_data, analysis, total_frames,
                      csv_path, reports_dir: Path, cn_metrics: dict = None):
    """生成 Markdown 报告"""
    if cn_metrics is None:
        cn_metrics = {}
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
    report = f"# 超网分析系统 综合分析报告\n\n"
    report += f"> 生成时间：{now}  \n"
    report += f"> 数据文件：`{os.path.basename(csv_path)}`  \n"
    report += f"> 分析方法：多层超网 + Shapley 值重心分析 + Monte Carlo 级联失效模拟\n\n---\n\n"

    report += "## 1. 数据概况\n\n"
    report += (f"本次分析共 **{info.get('total_rows', 0):,}** 行记录，"
               f"**{info.get('total_columns', 0)}** 列，"
               f"涉及 **{info.get('platforms_count', 0)}** 个平台节点，"
               f"**{len(info.get('message_types', {}))}** 种消息类型。\n\n")

    msg_types = info.get('message_types', {})
    if msg_types:
        report += "主要消息类型分布：\n\n| 消息类型 | 记录数 |\n|----------|--------|\n"
        for t, c in sorted(msg_types.items(), key=lambda x: x[1], reverse=True)[:10]:
            report += f"| `{t}` | {c:,} |\n"
        report += "\n"

    report += "## 2. 超网结构分析\n\n"
    report += (f"构建的超网包含 **{H.number_of_nodes()}** 个节点，**{H.number_of_edges()}** 条边，"
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
        topn = gravity_info.get('top10_nodes', [])
        _stn = gravity_info.get('top_n_actual', len(topn))
        if topn:
            report += f"**Top-{_stn} 关键节点（Shapley + 中心性融合排名）**\n\n| 排名 | 节点 | 融合分数 |\n|------|------|----------|\n"
            for i, (node, score) in enumerate(topn, 1):
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
        # 展示数量与 Shapley 保持一致
        _sn_single = gravity_info.get('top_n_actual', 10) if gravity_info else 10
        report += f"**关键节点单独移除影响（Top-{_sn_single}）**\n\n| 排名 | 节点 | 效率下降% | LCC缩减% | 连通分量增加 |\n|------|------|-----------|----------|-------------|\n"
        for i, item in enumerate(single[:_sn_single], 1):
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
        report += (f"通过 Shapley 值重心分析，识别出超网的核心重心节点为 `{gn}`，"
                   f"其稳定性评级为 [{st}]。该节点在多层网络中具有最高的边际贡献，"
                   "是整个网络体系的关键枢纽。\n\n")
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
               "4. 定期进行级联失效仿真，验证网络韧性\n\n")

    # ── 第7节：综合复杂网络分析（嵌入综合报告） ──────────────────
    if cn_metrics:
        report += "## 7. 综合复杂网络分析\n\n"
        report += (f"综合复杂网络共包含 **{cn_metrics.get('n_nodes', 0)}** 个节点、"
                   f"**{cn_metrics.get('n_edges', 0)}** 条边，"
                   f"网络密度为 **{cn_metrics.get('density', 0):.4f}**，"
                   f"平均度为 **{cn_metrics.get('avg_degree', 0):.2f}**。\n\n")

        n_comp = cn_metrics.get('n_components', 1)
        lcc_r = cn_metrics.get('lcc_ratio', 1.0)
        report += (f"网络共有 **{n_comp}** 个连通分量，最大连通分量包含 "
                   f"**{cn_metrics.get('lcc_size', 0)}** 个节点（占全网 {lcc_r*100:.1f}%）。")
        if lcc_r >= 0.9:
            report += " 网络整体连通性良好。\n\n"
        elif lcc_r >= 0.6:
            report += " 网络存在一定程度的碎片化，部分节点游离于主网之外。\n\n"
        else:
            report += " ⚠️ 网络碎片化严重，大量节点未能接入主连通分量。\n\n"

        apl = cn_metrics.get('avg_path_length')
        diam = cn_metrics.get('diameter')
        clust = cn_metrics.get('avg_clustering', 0)
        if apl is not None:
            report += (f"最大连通子图的平均最短路径长度为 **{apl:.3f}**，"
                       f"网络直径为 **{diam}**，"
                       f"平均聚类系数为 **{clust:.4f}**。\n\n")
        else:
            report += f"最大连通子图平均聚类系数为 **{clust:.4f}**（网络规模较大，跳过路径长度计算）。\n\n"

        tc = cn_metrics.get('type_count', {})
        if tc:
            report += "**节点类型分布**\n\n| 类型 | 数量 |\n|------|------|\n"
            type_label = {
                'radar_sensor': '雷达/传感器',
                'ew_soj': '电子战/SOJ',
                'command': '指挥/UCAV',
                'weapon': '武器/SAM',
                'other': '其他',
            }
            for k, label in type_label.items():
                report += f"| {label} | {tc.get(k, 0)} |\n"
            report += "\n"

        top_deg = cn_metrics.get('top_degree', [])
        top_bet = cn_metrics.get('top_betweenness', [])
        top_clo = cn_metrics.get('top_closeness', [])
        _tn = cn_metrics.get('top_n_actual', len(top_deg))
        if top_deg:
            report += f"**度中心性 Top-{_tn}**\n\n| 排名 | 节点 | 度中心性 |\n|------|------|----------|\n"
            for i, (n, v) in enumerate(top_deg, 1):
                report += f"| {i} | `{n}` | {v:.4f} |\n"
            report += "\n"
        if top_bet:
            report += f'**介数中心性 Top-{_tn}**（衡量节点作为「桥梁」的能力）\n\n| 排名 | 节点 | 介数中心性 |\n|------|------|------------|\n'
            for i, (n, v) in enumerate(top_bet, 1):
                report += f"| {i} | `{n}` | {v:.4f} |\n"
            report += "\n"
        if top_clo:
            report += f"**接近中心性 Top-{_tn}**（衡量节点到达其他节点的效率）\n\n| 排名 | 节点 | 接近中心性 |\n|------|------|------------|\n"
            for i, (n, v) in enumerate(top_clo, 1):
                report += f"| {i} | `{n}` | {v:.4f} |\n"
            report += "\n"

        # 小世界性判断
        if apl is not None and cn_metrics.get('n_nodes', 0) > 5:
            import math
            n = cn_metrics['n_nodes']
            expected_apl = math.log(n) / math.log(max(cn_metrics.get('avg_degree', 2), 2))
            if apl <= expected_apl * 1.5 and clust > 0.1:
                report += "> 🔍 **小世界特性**：该网络平均路径较短且聚类系数较高，具有典型的小世界网络特征，信息传播效率高但也意味着级联失效风险较大。\n\n"

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

    # ── 独立复杂网络报告 ──────────────────────────────────────────
    if cn_metrics:
        cn_report = f"# 综合复杂网络分析报告\n\n"
        cn_report += f"> 生成时间：{now}  \n"
        cn_report += f"> 数据文件：`{os.path.basename(csv_path)}`\n\n---\n\n"

        cn_report += "## 1. 网络基本属性\n\n"
        cn_report += f"| 指标 | 数值 |\n|------|------|\n"
        cn_report += f"| 节点数 | {cn_metrics.get('n_nodes', 0)} |\n"
        cn_report += f"| 边数 | {cn_metrics.get('n_edges', 0)} |\n"
        cn_report += f"| 网络密度 | {cn_metrics.get('density', 0):.4f} |\n"
        cn_report += f"| 平均度 | {cn_metrics.get('avg_degree', 0):.2f} |\n"
        cn_report += f"| 最大度 | {cn_metrics.get('max_degree', 0)} |\n"
        cn_report += f"| 最小度 | {cn_metrics.get('min_degree', 0)} |\n"
        cn_report += f"| 度标准差 | {cn_metrics.get('degree_std', 0):.3f} |\n"
        cn_report += f"| 连通分量数 | {cn_metrics.get('n_components', 1)} |\n"
        cn_report += f"| 最大连通分量节点数 | {cn_metrics.get('lcc_size', 0)} |\n"
        cn_report += f"| 最大连通分量占比 | {cn_metrics.get('lcc_ratio', 0)*100:.1f}% |\n"
        cn_report += f"| 平均聚类系数 | {cn_metrics.get('avg_clustering', 0):.4f} |\n"
        apl = cn_metrics.get('avg_path_length')
        diam = cn_metrics.get('diameter')
        cn_report += f"| 平均最短路径长度 | {f'{apl:.3f}' if apl else '—（网络过大）'} |\n"
        cn_report += f"| 网络直径 | {diam if diam else '—（网络过大）'} |\n\n"

        tc = cn_metrics.get('type_count', {})
        if tc:
            cn_report += "## 2. 节点类型分布\n\n"
            cn_report += "| 类型 | 数量 | 占比 |\n|------|------|------|\n"
            total_n = cn_metrics.get('n_nodes', 1)
            type_label = {
                'radar_sensor': '雷达/传感器',
                'ew_soj': '电子战/SOJ',
                'command': '指挥/UCAV',
                'weapon': '武器/SAM',
                'other': '其他',
            }
            for k, label in type_label.items():
                cnt = tc.get(k, 0)
                cn_report += f"| {label} | {cnt} | {cnt/total_n*100:.1f}% |\n"
            cn_report += "\n"

        top_deg = cn_metrics.get('top_degree', [])
        top_bet = cn_metrics.get('top_betweenness', [])
        top_clo = cn_metrics.get('top_closeness', [])
        _tn = cn_metrics.get('top_n_actual', len(top_deg))

        cn_report += "## 3. 中心性分析\n\n"
        if top_deg:
            cn_report += f"### 3.1 度中心性 Top-{_tn}\n\n度中心性反映节点的直接连接数量，值越高说明该节点与越多其他节点直接相连。\n\n"
            cn_report += "| 排名 | 节点 | 度中心性 |\n|------|------|----------|\n"
            for i, (n, v) in enumerate(top_deg, 1):
                cn_report += f"| {i} | `{n}` | {v:.4f} |\n"
            cn_report += "\n"
        if top_bet:
            cn_report += f'### 3.2 介数中心性 Top-{_tn}\n\n介数中心性衡量节点作为网络「桥梁」的能力，高介数节点一旦失效会导致大量路径中断。\n\n'
            cn_report += "| 排名 | 节点 | 介数中心性 |\n|------|------|------------|\n"
            for i, (n, v) in enumerate(top_bet, 1):
                cn_report += f"| {i} | `{n}` | {v:.4f} |\n"
            cn_report += "\n"
        if top_clo:
            cn_report += f"### 3.3 接近中心性 Top-{_tn}\n\n接近中心性衡量节点到达网络中所有其他节点的平均效率，值越高说明信息传播越快。\n\n"
            cn_report += "| 排名 | 节点 | 接近中心性 |\n|------|------|------------|\n"
            for i, (n, v) in enumerate(top_clo, 1):
                cn_report += f"| {i} | `{n}` | {v:.4f} |\n"
            cn_report += "\n"

        cn_report += "## 4. 网络拓扑特征解读\n\n"
        density = cn_metrics.get('density', 0)
        if density < 0.1:
            cn_report += f"网络密度为 {density:.4f}，属于**稀疏网络**，节点间连接较少，信息传播依赖少数关键路径。\n\n"
        elif density < 0.4:
            cn_report += f"网络密度为 {density:.4f}，属于**中等密度网络**，具有一定的连接冗余。\n\n"
        else:
            cn_report += f"网络密度为 {density:.4f}，属于**稠密网络**，节点间连接丰富，具有较强的抗毁性。\n\n"

        if apl is not None and cn_metrics.get('n_nodes', 0) > 5:
            import math
            n_val = cn_metrics['n_nodes']
            avg_d = max(cn_metrics.get('avg_degree', 2), 2)
            expected_apl = math.log(n_val) / math.log(avg_d)
            clust = cn_metrics.get('avg_clustering', 0)
            if apl <= expected_apl * 1.5 and clust > 0.1:
                cn_report += ("> 🔍 **小世界特性检测**：该网络平均路径长度（{:.3f}）接近随机网络理论值（{:.3f}），"
                              "且聚类系数（{:.4f}）显著高于随机网络，具有典型的**小世界网络**特征。"
                              "这意味着信息/指令可以快速在全网传播，但也使得级联失效更容易扩散。\n\n"
                              ).format(apl, expected_apl, clust)

        cn_report += "## 5. 关键节点风险评估\n\n"
        if top_bet:
            top1_bet = top_bet[0][0]
            top1_bet_v = top_bet[0][1]
            cn_report += (f"介数中心性最高的节点为 `{top1_bet}`（介数={top1_bet_v:.4f}），"
                          f'该节点是网络中最重要的「桥梁」节点，其失效将对网络连通性造成最大冲击。\n\n')
        if top_deg:
            top1_deg = top_deg[0][0]
            cn_report += (f"度中心性最高的节点为 `{top1_deg}`，直接连接最多，"
                          f'是网络中的「枢纽」节点，需重点防护。\n\n')

        with open(reports_dir / 'complex_network_report.md', 'w', encoding='utf-8') as f:
            f.write(cn_report)


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

        elif path == '/api/config':
            with _config_lock:
                self._send_json(dict(_config))

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
        elif path == '/api/config':
            self._handle_config()
        else:
            self._send_json({'error': 'Not found'}, 404)

    def _handle_config(self):
        """POST /api/config — 更新可调参数"""
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length)
        try:
            new_cfg = json.loads(body.decode('utf-8'))
        except Exception as e:
            self._send_json({'ok': False, 'error': f'JSON 解析失败: {e}'}, 400)
            return

        # 类型校验 + 写入（只更新已知 key，防止注入）
        _NUM_KEYS = {
            'shapley_samples': int,
            'cascade_rounds': int,
            'degree_weight': float,
            'shapley_weight': float,
            'shapley_base_weight': float,
            'bridge_bonus_weight': float,
            'frame_global_weight': float,
            'frame_degree_weight': float,
            'n_frames': int,
            'video_fps': int,
            'video_crf': int,
            'azim_start': float,
            'time_window_override': float,
            'cn_betweenness_k': int,
            'cn_top_n': int,
            'top_n_abs': int,
            'top_n_pct': int,
            'collapse_threshold_pct': float,
        }
        _STR_KEYS = {'top_n_mode'}   # 合法值：abs / pct / all
        updated = {}
        errors = []
        with _config_lock:
            for k, typ in _NUM_KEYS.items():
                if k in new_cfg:
                    try:
                        _config[k] = typ(new_cfg[k])
                        updated[k] = _config[k]
                    except (ValueError, TypeError) as e:
                        errors.append(f'{k}: {e}')
            for k in _STR_KEYS:
                if k in new_cfg:
                    v = str(new_cfg[k])
                    if k == 'top_n_mode' and v not in ('abs', 'pct', 'all'):
                        errors.append(f'{k}: 非法值 {v!r}，必须为 abs/pct/all')
                    else:
                        _config[k] = v
                        updated[k] = v
        if errors:
            self._send_json({'ok': False, 'error': '; '.join(errors)}, 400)
        else:
            self._send_json({'ok': True, 'updated': updated, 'config': dict(_config)})

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

        # 解析 multipart：收集所有 files 字段（多个 CSV）和 dir_name 字段
        body = self.rfile.read(content_length)
        boundary = content_type.split('boundary=')[-1].strip().encode()

        csv_files: dict = {}   # {filename: bytes}
        dir_name = 'sim_data'

        parts = body.split(b'--' + boundary)
        for part in parts:
            if b'Content-Disposition' not in part:
                continue
            header_end = part.find(b'\r\n\r\n')
            if header_end == -1:
                continue
            headers_raw = part[:header_end].decode('utf-8', errors='ignore')
            content = part[header_end + 4:]
            if content.endswith(b'\r\n'):
                content = content[:-2]

            # 提取 Content-Disposition 行
            cd_line = ''
            for line in headers_raw.splitlines():
                if 'Content-Disposition' in line:
                    cd_line = line
                    break

            # 解析字段名和文件名
            field_name = ''
            file_name  = ''
            for seg in cd_line.split(';'):
                seg = seg.strip()
                if seg.lower().startswith('name='):
                    field_name = seg.split('=', 1)[1].strip().strip('"')
                elif seg.lower().startswith('filename='):
                    file_name = seg.split('=', 1)[1].strip().strip('"')

            if field_name == 'files' and file_name.lower().endswith('.csv'):
                csv_files[file_name] = content
            elif field_name == 'dir_name' and not file_name:
                dir_name = content.decode('utf-8', errors='ignore').strip() or dir_name

        if not csv_files:
            self._send_json({'ok': False, 'error': '未找到 CSV 文件，请选择包含仿真数据的目录'}, 400)
            return

        # 将所有 CSV 写入临时目录
        upload_path = _save_csv_files(csv_files)
        display_name = f'{dir_name}/ ({len(csv_files)} 个 CSV)'

        _set_state(
            status='running', progress=1, stage='准备中',
            csv_name=display_name, error='', log=[],
            results={
                'total_frames': 0, 'nodes': 0, 'edges': 0,
                'cog_node': '', 'cog_score': 0.0,
                'has_video': False, 'has_reports': False, 'has_complex_network': False,
            }
        )

        # 启动分析线程
        _analysis_thread = threading.Thread(
            target=_run_analysis,
            args=(upload_path,),
            daemon=True
        )
        _analysis_thread.start()

        self._send_json({
            'ok': True,
            'message': f'已接收 {display_name}，分析已启动',
            'csv_name': display_name,
        })


# ── 主入口 ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description='超网分析后端服务')
    parser.add_argument('--port', type=int, default=5001, help='监听端口（默认 5001）')
    parser.add_argument('--host', default='127.0.0.1', help='监听地址（默认 127.0.0.1）')
    args = parser.parse_args()

    print(f"🚀 超网分析后端服务启动")
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
