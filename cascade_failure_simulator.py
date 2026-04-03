# src/cascade_failure_simulator.py
"""
级联失效模拟模块

模拟对作战网络关键节点进行随机移除时的级联失效过程：
  1. 从综合排名前 10 的关键节点中随机选取移除顺序
  2. 每移除一个节点，重新计算网络指标（连通性、效率、最大连通分量等）
  3. 重复多轮（Monte Carlo），统计平均失效曲线
  4. 输出 Markdown 格式的详细分析报告

级联失效机制：
  - 节点移除后，其邻居节点的"负载"增加（度减少导致剩余节点压力上升）
  - 当某节点的度降为 0（孤立），视为自动失效
  - 连通分量数量增加代表网络分裂
"""

import networkx as nx
import numpy as np
import pandas as pd
import random
from typing import Dict, List, Tuple, Any, Optional
from datetime import datetime
from collections import defaultdict


class CascadeFailureSimulator:
    """
    级联失效模拟器
    支持单层网络和超网（多层网络）
    """

    def __init__(self, n_rounds: int = 30, random_seed: int = 42):
        """
        :param n_rounds: Monte Carlo 重复轮数（越多结果越稳定）
        :param random_seed: 随机种子
        """
        self.n_rounds = n_rounds
        self.random_seed = random_seed
        random.seed(random_seed)
        np.random.seed(random_seed)

    # ─────────────────────────────────────────────
    # 公开接口
    # ─────────────────────────────────────────────

    def simulate(self,
                 G: nx.Graph,
                 critical_nodes: List[str],
                 top_k: int = 10) -> Dict[str, Any]:
        """
        对网络 G 的前 top_k 关键节点进行随机移除级联失效模拟

        :param G: 目标网络（有向/无向均可）
        :param critical_nodes: 按重要性排序的节点列表（取前 top_k 个）
        :param top_k: 参与模拟的关键节点数量
        :return: 模拟结果字典
        """
        # 取前 top_k 个关键节点（过滤不在图中的）
        target_nodes = [n for n in critical_nodes if n in G.nodes()][:top_k]

        if not target_nodes:
            print("  [级联失效] 无有效关键节点，跳过模拟")
            return {}

        print(f"  [级联失效] 开始模拟，目标节点={len(target_nodes)}，轮数={self.n_rounds}...")

        # 转为无向图便于连通性分析
        G_base = G.to_undirected() if G.is_directed() else G.copy()

        # 基准指标
        baseline = self._compute_metrics(G_base)

        # 多轮 Monte Carlo 模拟
        all_rounds = []
        for round_idx in range(self.n_rounds):
            round_result = self._simulate_one_round(G_base, target_nodes, baseline)
            all_rounds.append(round_result)

        # 汇总统计
        summary = self._aggregate_rounds(all_rounds, target_nodes, baseline)

        # 单节点影响分析（确定性，每次只移除一个节点）
        single_removal = self._analyze_single_removal(G_base, target_nodes, baseline)

        return {
            'baseline': baseline,
            'target_nodes': target_nodes,
            'monte_carlo_summary': summary,
            'single_removal_analysis': single_removal,
            'all_rounds_raw': all_rounds
        }

    def simulate_hyper_network(self,
                               hyper_data: Dict[str, Any],
                               critical_nodes: List[str],
                               top_k: int = 10) -> Dict[str, Any]:
        """
        对超网进行级联失效模拟（同时在各层和超网整体上评估影响）
        """
        hyper_net = hyper_data.get('hyper_network', nx.MultiDiGraph())
        layers = hyper_data.get('layers', {})

        if hyper_net.number_of_nodes() == 0:
            return {}

        # 超网整体模拟
        hyper_simple = self._to_simple_undirected(hyper_net)
        hyper_result = self.simulate(hyper_simple, critical_nodes, top_k)

        # 各层分别模拟
        layer_results = {}
        for layer_name, layer_net in layers.items():
            if layer_net.number_of_nodes() == 0:
                continue
            # 过滤出在该层存在的关键节点
            layer_nodes = [n for n in critical_nodes if n in layer_net.nodes()]
            if not layer_nodes:
                continue
            layer_result = self.simulate(layer_net, layer_nodes, min(top_k, len(layer_nodes)))
            layer_results[layer_name] = layer_result

        return {
            'hyper_result': hyper_result,
            'layer_results': layer_results
        }

    # ─────────────────────────────────────────────
    # 核心模拟逻辑
    # ─────────────────────────────────────────────

    def _simulate_one_round(self,
                            G_base: nx.Graph,
                            target_nodes: List[str],
                            baseline: Dict[str, float]) -> List[Dict[str, Any]]:
        """
        单轮模拟：随机打乱移除顺序，逐步移除节点并记录指标变化
        """
        G = G_base.copy()
        removal_order = target_nodes.copy()
        random.shuffle(removal_order)

        steps = []
        removed_so_far = []

        for step, node in enumerate(removal_order):
            if node not in G.nodes():
                continue

            # 记录移除前的邻居（用于级联判断）
            neighbors_before = list(G.neighbors(node))

            # 移除节点
            G.remove_node(node)
            removed_so_far.append(node)

            # 检查级联失效：邻居中是否有节点因此孤立
            cascade_isolated = []
            for nb in neighbors_before:
                if nb in G.nodes() and G.degree(nb) == 0:
                    cascade_isolated.append(nb)
                    G.remove_node(nb)

            # 计算当前指标
            metrics = self._compute_metrics(G)
            metrics['step'] = step + 1
            metrics['removed_node'] = node
            metrics['cascade_isolated'] = cascade_isolated
            metrics['total_removed'] = len(removed_so_far) + len(cascade_isolated)

            # 相对于基准的变化率
            metrics['efficiency_drop_pct'] = (
                (baseline['global_efficiency'] - metrics['global_efficiency'])
                / baseline['global_efficiency'] * 100
                if baseline['global_efficiency'] > 0 else 0
            )
            metrics['lcc_drop_pct'] = (
                (baseline['lcc_size'] - metrics['lcc_size'])
                / baseline['lcc_size'] * 100
                if baseline['lcc_size'] > 0 else 0
            )

            steps.append(metrics)

        return steps

    def _analyze_single_removal(self,
                                G_base: nx.Graph,
                                target_nodes: List[str],
                                baseline: Dict[str, float]) -> List[Dict[str, Any]]:
        """
        确定性分析：每次只移除一个节点，评估其单独影响
        """
        results = []
        for node in target_nodes:
            if node not in G_base.nodes():
                continue
            G_temp = G_base.copy()
            G_temp.remove_node(node)
            metrics = self._compute_metrics(G_temp)

            results.append({
                'node': node,
                'efficiency_after': metrics['global_efficiency'],
                'efficiency_drop': baseline['global_efficiency'] - metrics['global_efficiency'],
                'efficiency_drop_pct': (
                    (baseline['global_efficiency'] - metrics['global_efficiency'])
                    / baseline['global_efficiency'] * 100
                    if baseline['global_efficiency'] > 0 else 0
                ),
                'lcc_size_after': metrics['lcc_size'],
                'lcc_drop_pct': (
                    (baseline['lcc_size'] - metrics['lcc_size'])
                    / baseline['lcc_size'] * 100
                    if baseline['lcc_size'] > 0 else 0
                ),
                'components_after': metrics['n_components'],
                'components_increase': metrics['n_components'] - baseline['n_components'],
                'density_after': metrics['density'],
                'density_drop': baseline['density'] - metrics['density'],
            })

        # 按效率下降排序
        results.sort(key=lambda x: x['efficiency_drop'], reverse=True)
        return results

    def _aggregate_rounds(self,
                          all_rounds: List[List[Dict]],
                          target_nodes: List[str],
                          baseline: Dict[str, float]) -> Dict[str, Any]:
        """
        汇总多轮 Monte Carlo 结果，计算均值和标准差
        """
        max_steps = max(len(r) for r in all_rounds) if all_rounds else 0
        if max_steps == 0:
            return {}

        # 按步骤汇总
        step_stats = []
        for step_idx in range(max_steps):
            step_data = []
            for round_data in all_rounds:
                if step_idx < len(round_data):
                    step_data.append(round_data[step_idx])

            if not step_data:
                continue

            eff_drops = [s['efficiency_drop_pct'] for s in step_data]
            lcc_drops = [s['lcc_drop_pct'] for s in step_data]
            n_comps = [s['n_components'] for s in step_data]

            step_stats.append({
                'step': step_idx + 1,
                'efficiency_drop_mean': np.mean(eff_drops),
                'efficiency_drop_std': np.std(eff_drops),
                'lcc_drop_mean': np.mean(lcc_drops),
                'lcc_drop_std': np.std(lcc_drops),
                'n_components_mean': np.mean(n_comps),
                'n_components_std': np.std(n_comps),
            })

        # 找到网络崩溃点（效率下降超过 50%）
        collapse_step = None
        for stat in step_stats:
            if stat['efficiency_drop_mean'] >= 50.0:
                collapse_step = stat['step']
                break

        return {
            'step_stats': step_stats,
            'collapse_step': collapse_step,
            'final_efficiency_drop': step_stats[-1]['efficiency_drop_mean'] if step_stats else 0,
            'final_lcc_drop': step_stats[-1]['lcc_drop_mean'] if step_stats else 0,
        }

    # ─────────────────────────────────────────────
    # 指标计算
    # ─────────────────────────────────────────────

    def _compute_metrics(self, G: nx.Graph) -> Dict[str, float]:
        """计算网络关键指标"""
        metrics = {
            'n_nodes': G.number_of_nodes(),
            'n_edges': G.number_of_edges(),
            'density': nx.density(G) if G.number_of_nodes() > 1 else 0.0,
            'n_components': nx.number_connected_components(G) if G.number_of_nodes() > 0 else 0,
            'lcc_size': 0,
            'global_efficiency': 0.0,
        }

        if G.number_of_nodes() == 0:
            return metrics

        # 最大连通分量大小
        if G.number_of_nodes() > 0:
            components = list(nx.connected_components(G))
            metrics['lcc_size'] = max(len(c) for c in components) if components else 0

        # 全局效率（采样加速，避免大图超时）
        metrics['global_efficiency'] = self._fast_global_efficiency(G)

        return metrics

    def _fast_global_efficiency(self, G: nx.Graph, max_nodes: int = 100) -> float:
        """快速全局效率计算（对大图采样）"""
        if G.number_of_nodes() < 2:
            return 0.0

        nodes = list(G.nodes())
        # 大图采样
        if len(nodes) > max_nodes:
            nodes = random.sample(nodes, max_nodes)

        total = 0.0
        count = 0
        for src in nodes:
            try:
                lengths = nx.single_source_shortest_path_length(G, src)
                for tgt, dist in lengths.items():
                    if tgt != src and dist > 0:
                        total += 1.0 / dist
                        count += 1
            except Exception:
                continue

        return total / count if count > 0 else 0.0

    def _to_simple_undirected(self, G: nx.MultiDiGraph) -> nx.Graph:
        """MultiDiGraph → 简单无向图"""
        simple = nx.Graph()
        simple.add_nodes_from(G.nodes(data=True))
        for u, v, data in G.edges(data=True):
            w = data.get('weight', 1.0)
            if simple.has_edge(u, v):
                simple[u][v]['weight'] += w
            else:
                simple.add_edge(u, v, weight=w)
        return simple

    # ─────────────────────────────────────────────
    # 报告生成
    # ─────────────────────────────────────────────

    def generate_markdown_report(self,
                                 sim_result: Dict[str, Any],
                                 shapley_results: Optional[Dict[str, Any]] = None,
                                 network_name: str = "作战超网") -> str:
        """
        生成完整的 Markdown 格式级联失效分析报告

        :param sim_result: simulate() 或 simulate_hyper_network() 的返回值
        :param shapley_results: ShapelyGravityAnalyzer.analyze_hyper_network() 的返回值（可选）
        :param network_name: 网络名称（用于报告标题）
        :return: Markdown 字符串
        """
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        # 判断是超网结果还是单层结果
        if 'hyper_result' in sim_result:
            return self._generate_hyper_report(sim_result, shapley_results, network_name, now)
        else:
            return self._generate_single_report(sim_result, shapley_results, network_name, now)

    def _generate_hyper_report(self, sim_result, shapley_results, network_name, now):
        """生成超网级联失效报告"""
        hyper = sim_result.get('hyper_result', {})
        layer_results = sim_result.get('layer_results', {})

        report = f"# {network_name} 级联失效分析报告\n\n"
        report += f"> 生成时间：{now}  \n"
        report += f"> 分析方法：Monte Carlo 随机节点移除 + Shapley 值重心分析\n\n"
        report += "---\n\n"

        # 执行摘要
        report += "## 执行摘要\n\n"
        baseline = hyper.get('baseline', {})
        summary = hyper.get('monte_carlo_summary', {})
        target_nodes = hyper.get('target_nodes', [])

        report += f"本报告对 **{network_name}** 的前 **{len(target_nodes)}** 个关键节点进行了随机移除级联失效模拟，"
        report += f"评估网络在节点失效情况下的鲁棒性。\n\n"

        if baseline:
            report += f"**基准网络状态**：节点数 {baseline.get('n_nodes', 0)}，"
            report += f"边数 {baseline.get('n_edges', 0)}，"
            report += f"全局效率 {baseline.get('global_efficiency', 0):.4f}，"
            report += f"最大连通分量 {baseline.get('lcc_size', 0)} 个节点\n\n"

        if summary:
            collapse = summary.get('collapse_step')
            final_eff_drop = summary.get('final_efficiency_drop', 0)
            final_lcc_drop = summary.get('final_lcc_drop', 0)

            if collapse:
                report += f"⚠️ **网络崩溃点**：移除第 **{collapse}** 个关键节点后，网络全局效率下降超过 50%\n\n"
            else:
                report += f"✅ 移除全部 {len(target_nodes)} 个关键节点后，网络效率下降未超过 50%（韧性较强）\n\n"

            report += f"- 移除全部关键节点后，平均效率下降：**{final_eff_drop:.1f}%**\n"
            report += f"- 最大连通分量平均缩减：**{final_lcc_drop:.1f}%**\n\n"

        report += "---\n\n"

        # Shapley 重心分析
        if shapley_results:
            report += "## Shapley 值重心分析\n\n"
            from shapely_gravity_analyzer import ShapelyGravityAnalyzer
            analyzer = ShapelyGravityAnalyzer()
            report += analyzer.generate_shapley_report_section(shapley_results)
            report += "---\n\n"

        # 单节点影响分析
        report += "## 关键节点单独移除影响分析\n\n"
        report += "> 每次仅移除一个节点，评估其对网络的独立破坏力\n\n"

        single = hyper.get('single_removal_analysis', [])
        if single:
            report += "| 排名 | 节点 | 效率下降 | 效率下降% | LCC缩减% | 连通分量增加 |\n"
            report += "|------|------|----------|-----------|----------|-------------|\n"
            for i, item in enumerate(single[:10], 1):
                report += (f"| {i} | `{item['node']}` | "
                           f"{item['efficiency_drop']:.4f} | "
                           f"{item['efficiency_drop_pct']:.1f}% | "
                           f"{item['lcc_drop_pct']:.1f}% | "
                           f"+{item['components_increase']} |\n")
            report += "\n"

        report += "---\n\n"

        # Monte Carlo 逐步失效曲线
        report += "## Monte Carlo 级联失效过程（逐步统计）\n\n"
        report += f"> 共进行 {self.n_rounds} 轮随机移除模拟，以下为均值 ± 标准差\n\n"

        step_stats = summary.get('step_stats', [])
        if step_stats:
            report += "| 移除步骤 | 效率下降均值 | 效率下降标准差 | LCC缩减均值 | 连通分量均值 |\n"
            report += "|----------|-------------|---------------|------------|-------------|\n"
            for stat in step_stats:
                report += (f"| 第{stat['step']}步 | "
                           f"{stat['efficiency_drop_mean']:.1f}% | "
                           f"±{stat['efficiency_drop_std']:.1f}% | "
                           f"{stat['lcc_drop_mean']:.1f}% | "
                           f"{stat['n_components_mean']:.1f} |\n")
            report += "\n"

        report += "---\n\n"

        # 各层级联失效分析
        if layer_results:
            report += "## 各层级联失效分析\n\n"
            for layer_name, layer_res in layer_results.items():
                report += f"### {layer_name} 层\n\n"
                lb = layer_res.get('baseline', {})
                ls = layer_res.get('monte_carlo_summary', {})
                lsingle = layer_res.get('single_removal_analysis', [])

                if lb:
                    report += f"基准：节点 {lb.get('n_nodes', 0)}，效率 {lb.get('global_efficiency', 0):.4f}\n\n"

                if lsingle:
                    report += "最高影响节点（单独移除）：\n\n"
                    report += "| 节点 | 效率下降% | LCC缩减% |\n"
                    report += "|------|-----------|----------|\n"
                    for item in lsingle[:5]:
                        report += f"| `{item['node']}` | {item['efficiency_drop_pct']:.1f}% | {item['lcc_drop_pct']:.1f}% |\n"
                    report += "\n"

                if ls:
                    collapse = ls.get('collapse_step')
                    if collapse:
                        report += f"⚠️ 该层崩溃点：第 **{collapse}** 步\n\n"
                    else:
                        report += f"✅ 该层韧性较强，未达到崩溃阈值\n\n"

        report += "---\n\n"

        # 结论与建议
        report += "## 结论与防御建议\n\n"
        report += self._generate_recommendations(hyper, single)

        return report

    def _generate_single_report(self, sim_result, shapley_results, network_name, now):
        """生成单层网络级联失效报告"""
        report = f"# {network_name} 级联失效分析报告\n\n"
        report += f"> 生成时间：{now}\n\n"
        report += "---\n\n"

        baseline = sim_result.get('baseline', {})
        summary = sim_result.get('monte_carlo_summary', {})
        single = sim_result.get('single_removal_analysis', [])
        target_nodes = sim_result.get('target_nodes', [])

        report += "## 基准网络状态\n\n"
        if baseline:
            report += f"- 节点数：{baseline.get('n_nodes', 0)}\n"
            report += f"- 边数：{baseline.get('n_edges', 0)}\n"
            report += f"- 全局效率：{baseline.get('global_efficiency', 0):.4f}\n"
            report += f"- 最大连通分量：{baseline.get('lcc_size', 0)}\n"
            report += f"- 连通分量数：{baseline.get('n_components', 0)}\n\n"

        if shapley_results:
            report += "## Shapley 值重心分析\n\n"
            from shapely_gravity_analyzer import ShapelyGravityAnalyzer
            analyzer = ShapelyGravityAnalyzer()
            report += analyzer.generate_shapley_report_section(shapley_results)

        report += "## 关键节点单独移除影响\n\n"
        if single:
            report += "| 排名 | 节点 | 效率下降% | LCC缩减% | 连通分量增加 |\n"
            report += "|------|------|-----------|----------|-------------|\n"
            for i, item in enumerate(single[:10], 1):
                report += (f"| {i} | `{item['node']}` | "
                           f"{item['efficiency_drop_pct']:.1f}% | "
                           f"{item['lcc_drop_pct']:.1f}% | "
                           f"+{item['components_increase']} |\n")
            report += "\n"

        report += "## Monte Carlo 级联失效过程\n\n"
        step_stats = summary.get('step_stats', [])
        if step_stats:
            report += "| 步骤 | 效率下降均值 | LCC缩减均值 | 连通分量均值 |\n"
            report += "|------|-------------|------------|-------------|\n"
            for stat in step_stats:
                report += (f"| {stat['step']} | "
                           f"{stat['efficiency_drop_mean']:.1f}% | "
                           f"{stat['lcc_drop_mean']:.1f}% | "
                           f"{stat['n_components_mean']:.1f} |\n")
            report += "\n"

        report += "## 结论\n\n"
        report += self._generate_recommendations(sim_result, single)

        return report

    def _generate_recommendations(self, sim_result: Dict, single_removal: List[Dict]) -> str:
        """根据模拟结果生成防御建议"""
        recs = ""

        summary = sim_result.get('monte_carlo_summary', {})
        collapse_step = summary.get('collapse_step')
        final_drop = summary.get('final_efficiency_drop', 0)

        # 脆弱性评级
        if collapse_step and collapse_step <= 3:
            recs += "**脆弱性评级：🔴 极高**\n\n"
            recs += f"网络在仅移除 {collapse_step} 个关键节点后即发生崩溃，极度脆弱。\n\n"
        elif collapse_step and collapse_step <= 6:
            recs += "**脆弱性评级：🟠 较高**\n\n"
            recs += f"网络在移除 {collapse_step} 个关键节点后发生崩溃，需重点防护。\n\n"
        elif final_drop > 30:
            recs += "**脆弱性评级：🟡 中等**\n\n"
            recs += f"移除全部关键节点后效率下降 {final_drop:.1f}%，存在一定脆弱性。\n\n"
        else:
            recs += "**脆弱性评级：🟢 较低**\n\n"
            recs += "网络具有较强韧性，关键节点失效对整体影响有限。\n\n"

        # 最危险节点
        if single_removal:
            top3 = single_removal[:3]
            recs += "**最高优先级防护节点**：\n\n"
            for i, item in enumerate(top3, 1):
                recs += (f"{i}. `{item['node']}`：单独移除导致效率下降 "
                         f"**{item['efficiency_drop_pct']:.1f}%**，"
                         f"LCC 缩减 **{item['lcc_drop_pct']:.1f}%**\n")
            recs += "\n"

        recs += "**防御建议**：\n\n"
        recs += "1. 对最高优先级节点实施冗余备份，确保单点失效不影响整体功能\n"
        recs += "2. 增加关键节点之间的旁路连接，提升网络连通冗余度\n"
        recs += "3. 建立分布式指挥架构，避免过度依赖单一指挥节点\n"
        recs += "4. 定期进行级联失效演练，验证网络韧性\n\n"

        return recs
