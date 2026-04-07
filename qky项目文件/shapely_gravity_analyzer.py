# src/shapely_gravity_analyzer.py
"""
基于 Shapley 值的超网重心分析模块

Shapley 值来自合作博弈论，用于衡量每个节点对整个网络"联盟价值"的边际贡献。
在作战网络中，Shapley 值能更公平地评估每个节点的真实重要性：
  - 不仅考虑节点自身的中心性，还考虑它与其他节点的协同效应
  - 能识别出那些"单独看不起眼，但缺少它整体崩溃"的关键节点

算法流程：
  1. 定义联盟价值函数 v(S)：子集 S 的网络连通效率
  2. 对每个节点 i，计算其 Shapley 值：
     φ_i = Σ_{S⊆N\{i}} [|S|!(n-|S|-1)!/n!] * [v(S∪{i}) - v(S)]
  3. 由于精确计算是 O(2^n)，使用蒙特卡洛采样近似
"""

import networkx as nx
import numpy as np
import pandas as pd
from typing import Dict, List, Any, Optional
import random
from collections import defaultdict


class ShapelyGravityAnalyzer:
    """
    基于 Shapley 值的网络重心分析器
    支持单层网络和超网（多层网络）
    """

    def __init__(self, n_samples: int = 200, random_seed: int = 42):
        """
        :param n_samples: 蒙特卡洛采样次数（越大越精确，但越慢）
        :param random_seed: 随机种子，保证结果可复现
        """
        self.n_samples = n_samples
        self.random_seed = random_seed
        random.seed(random_seed)
        np.random.seed(random_seed)

    # ─────────────────────────────────────────────
    # 公开接口
    # ─────────────────────────────────────────────

    def analyze_single_network(self, G: nx.Graph) -> Dict[str, Any]:
        """
        对单层网络计算 Shapley 重心分析
        :param G: NetworkX 图（有向/无向均可）
        :return: 分析结果字典
        """
        if G.number_of_nodes() == 0:
            return {}

        print(f"  [Shapley] 开始单层网络分析，节点数={G.number_of_nodes()}，采样={self.n_samples}...")

        # 转为无向图用于连通性计算
        G_undirected = G.to_undirected() if G.is_directed() else G

        nodes = list(G_undirected.nodes())
        shapley_values = self._compute_shapley_values(G_undirected, nodes)

        return self._build_result(shapley_values, G_undirected, layer_name="single")

    def analyze_hyper_network(self, hyper_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        对超网（多层网络）计算跨层 Shapley 重心分析
        :param hyper_data: CombatHyperNetworkBuilder.build_hyper_network() 的返回值
        :return: 分析结果字典
        """
        layers = hyper_data.get('layers', {})
        cross_edges = hyper_data.get('cross_layer_edges', [])
        hyper_net = hyper_data.get('hyper_network', nx.MultiDiGraph())

        if hyper_net.number_of_nodes() == 0:
            return {}

        print(f"  [Shapley] 开始超网分析，总节点数={hyper_net.number_of_nodes()}，层数={len(layers)}...")

        results = {}

        # 1. 各层内 Shapley 值
        layer_shapley = {}
        for layer_name, layer_net in layers.items():
            if layer_net.number_of_nodes() == 0:
                continue
            G_u = layer_net.to_undirected()
            nodes = list(G_u.nodes())
            sv = self._compute_shapley_values(G_u, nodes)
            layer_shapley[layer_name] = sv
            print(f"    层 [{layer_name}]: {len(sv)} 个节点完成 Shapley 计算")

        results['layer_shapley'] = layer_shapley

        # 2. 跨层综合 Shapley 值（在超网整体上计算）
        hyper_simple = self._to_simple_undirected(hyper_net)
        all_nodes = list(hyper_simple.nodes())
        cross_shapley = self._compute_shapley_values(hyper_simple, all_nodes)
        results['cross_layer_shapley'] = cross_shapley

        # 3. 跨层桥梁加权：参与跨层连接的节点额外加分
        bridge_bonus = self._compute_bridge_bonus(all_nodes, cross_edges)
        shapley_with_bridge = {}
        for node in all_nodes:
            base  = cross_shapley.get(node, 0.0)
            bonus = bridge_bonus.get(node, 0.0)
            shapley_with_bridge[node] = base * 0.7 + bonus * 0.3
        shapley_with_bridge = self._normalize(shapley_with_bridge)
        results['cross_layer_shapley_norm'] = shapley_with_bridge

        # 4. 度中心性归一化
        deg = dict(hyper_simple.degree())
        max_deg = max(deg.values()) if deg else 1
        degree_norm = {n: deg.get(n, 0) / max_deg for n in all_nodes}
        results['degree_centrality_norm'] = degree_norm

        # 5. 加权融合：degree * 0.4 + shapley * 0.6 → 最终重心分数
        #    度中心性是经典基础指标，Shapley 是高级协同贡献指标，各有侧重
        combined_shapley = {}
        for node in all_nodes:
            d_score = degree_norm.get(node, 0.0)
            s_score = shapley_with_bridge.get(node, 0.0)
            combined_shapley[node] = d_score * 0.4 + s_score * 0.6

        # 归一化
        combined_shapley = self._normalize(combined_shapley)
        results['combined_shapley'] = combined_shapley

        # 6. 重心识别（基于融合分数）
        results['gravity_analysis'] = self._build_result(combined_shapley, hyper_simple, layer_name="hyper")

        # 5. 层级重要性排名
        results['layer_importance'] = self._rank_layer_importance(layer_shapley)

        return results

    # ─────────────────────────────────────────────
    # 核心算法：蒙特卡洛 Shapley 值估计
    # ─────────────────────────────────────────────

    def _compute_shapley_values(self, G: nx.Graph, nodes: List[str]) -> Dict[str, float]:
        """
        蒙特卡洛近似 Shapley 值
        每次随机排列所有节点，计算每个节点加入时的边际贡献
        """
        n = len(nodes)
        if n == 0:
            return {}
        if n == 1:
            return {nodes[0]: 1.0}

        shapley_values = defaultdict(float)

        for _ in range(self.n_samples):
            # 随机排列
            perm = nodes.copy()
            random.shuffle(perm)

            # 逐步加入节点，计算边际贡献
            current_set = set()
            prev_value = 0.0

            for node in perm:
                current_set.add(node)
                curr_value = self._coalition_value(G, current_set)
                marginal = curr_value - prev_value
                shapley_values[node] += marginal
                prev_value = curr_value

        # 平均
        for node in nodes:
            shapley_values[node] /= self.n_samples

        return dict(shapley_values)

    def _coalition_value(self, G: nx.Graph, node_set: set) -> float:
        """
        联盟价值函数 v(S)：子集 S 诱导子图的全局效率
        全局效率 = 平均最短路径长度的倒数（越高越好）
        """
        if len(node_set) <= 1:
            return 0.0

        subgraph = G.subgraph(node_set)

        # 计算全局效率（考虑不连通情况）
        total_efficiency = 0.0
        n = len(node_set)
        pairs = n * (n - 1)

        if pairs == 0:
            return 0.0

        for source in node_set:
            try:
                lengths = nx.single_source_shortest_path_length(subgraph, source)
                for target, dist in lengths.items():
                    if target != source and dist > 0:
                        total_efficiency += 1.0 / dist
            except Exception:
                continue

        return total_efficiency / pairs

    # ─────────────────────────────────────────────
    # 辅助方法
    # ─────────────────────────────────────────────

    def _compute_bridge_bonus(self, nodes: List[str], cross_edges: List[Dict]) -> Dict[str, float]:
        """计算跨层桥梁加分：节点参与的跨层连接越多，加分越高"""
        bonus = defaultdict(float)
        total = len(cross_edges)
        if total == 0:
            return {}

        for edge in cross_edges:
            src = edge.get('source_node', '')
            tgt = edge.get('target_node', '')
            w = edge.get('weight', 1.0)
            if src in nodes:
                bonus[src] += w
            if tgt in nodes:
                bonus[tgt] += w

        return self._normalize(dict(bonus))

    def _to_simple_undirected(self, G: nx.MultiDiGraph) -> nx.Graph:
        """将 MultiDiGraph 转为简单无向图，合并重边权重"""
        simple = nx.Graph()
        simple.add_nodes_from(G.nodes(data=True))
        for u, v, data in G.edges(data=True):
            w = data.get('weight', 1.0)
            if simple.has_edge(u, v):
                simple[u][v]['weight'] += w
            else:
                simple.add_edge(u, v, weight=w)
        return simple

    def _normalize(self, d: Dict[str, float]) -> Dict[str, float]:
        """Min-Max 归一化到 [0, 1]"""
        if not d:
            return {}
        vals = list(d.values())
        mn, mx = min(vals), max(vals)
        if mx == mn:
            return {k: 1.0 for k in d}
        return {k: (v - mn) / (mx - mn) for k, v in d.items()}

    def _build_result(self, shapley_values: Dict[str, float],
                      G: nx.Graph, layer_name: str) -> Dict[str, Any]:
        """构建标准化的分析结果"""
        if not shapley_values:
            return {}

        sorted_nodes = sorted(shapley_values.items(), key=lambda x: x[1], reverse=True)

        gravity_node = sorted_nodes[0][0]
        gravity_score = sorted_nodes[0][1]

        top10 = sorted_nodes[:10]
        top10_pct = max(1, len(sorted_nodes) // 10)
        gravity_region = [n for n, _ in sorted_nodes[:top10_pct]]

        # 稳定性：第一名与第二名的分差
        if len(sorted_nodes) >= 2:
            gap = sorted_nodes[0][1] - sorted_nodes[1][1]
            stability = "高度稳定" if gap > 0.3 else ("中等稳定" if gap > 0.1 else "不稳定")
        else:
            gap = 0.0
            stability = "高度稳定"

        return {
            'layer': layer_name,
            'gravity_node': gravity_node,
            'gravity_score': gravity_score,
            'top10_nodes': top10,
            'gravity_region': gravity_region,
            'stability': stability,
            'score_gap': gap,
            'all_shapley_values': dict(sorted_nodes)
        }

    def _rank_layer_importance(self, layer_shapley: Dict[str, Dict[str, float]]) -> List[tuple]:
        """按各层节点平均 Shapley 值排名层的重要性"""
        layer_scores = []
        for layer_name, sv in layer_shapley.items():
            if sv:
                avg = np.mean(list(sv.values()))
                max_val = max(sv.values())
                layer_scores.append((layer_name, avg, max_val))
        layer_scores.sort(key=lambda x: x[1], reverse=True)
        return layer_scores

    def generate_shapley_report_section(self, shapley_results: Dict[str, Any]) -> str:
        """生成 Shapley 分析的 Markdown 报告片段"""
        if not shapley_results:
            return "### Shapley 重心分析\n\n> 无数据\n\n"

        report = "### Shapley 值重心分析\n\n"
        report += "> Shapley 值来自合作博弈论，衡量每个节点对网络整体连通效率的边际贡献，能识别协同关键节点。\n\n"

        gravity = shapley_results.get('gravity_analysis', {})
        if gravity:
            report += f"**超网重心节点**：`{gravity.get('gravity_node', 'N/A')}` "
            report += f"（Shapley 分数：{gravity.get('gravity_score', 0):.4f}，"
            report += f"稳定性：{gravity.get('stability', 'N/A')}）\n\n"

            top10 = gravity.get('top10_nodes', [])
            if top10:
                report += "**Top-10 关键节点（Shapley 排名）**\n\n"
                report += "| 排名 | 节点 | Shapley 值 |\n"
                report += "|------|------|------------|\n"
                for i, (node, score) in enumerate(top10, 1):
                    report += f"| {i} | `{node}` | {score:.4f} |\n"
                report += "\n"

        layer_importance = shapley_results.get('layer_importance', [])
        if layer_importance:
            report += "**各层重要性排名（按平均 Shapley 值）**\n\n"
            report += "| 层名 | 平均 Shapley | 最大 Shapley |\n"
            report += "|------|-------------|-------------|\n"
            for layer_name, avg, mx in layer_importance:
                report += f"| {layer_name} | {avg:.4f} | {mx:.4f} |\n"
            report += "\n"

        return report
