# src/critical_node_analyzer.py
import networkx as nx
import pandas as pd
import numpy as np
from typing import Dict, List, Tuple, Any
from centrality_analysis import CentralityAnalyzer
from utils import normalize_dict_values, merge_centrality_scores


class CriticalNodeAnalyzer:
    def __init__(self):
        self.centrality_analyzer = CentralityAnalyzer()

    def comprehensive_critical_node_analysis(self, G: nx.Graph, top_k: int = 10) -> Dict[str, Any]:
        """综合关键节点分析"""
        if G.number_of_nodes() == 0:
            return {}

        print(f"开始关键节点分析，网络包含 {G.number_of_nodes()} 个节点...")

        analysis_results = {}

        # 1. 基础中心性分析
        centrality_df = self.centrality_analyzer.calculate_all_centralities(G)
        analysis_results['centrality_df'] = centrality_df

        # 2. 多维度关键节点识别
        analysis_results['critical_nodes_by_metric'] = self._identify_nodes_by_metrics(centrality_df, top_k)

        # 3. 鲁棒性分析
        analysis_results['robustness_analysis'] = self._analyze_network_robustness(G, centrality_df)

        # 4. 功能角色分析
        analysis_results['functional_roles'] = self._analyze_functional_roles(G, centrality_df)

        # 5. 综合评分排名
        analysis_results['composite_ranking'] = self._calculate_composite_ranking(centrality_df, top_k)

        return analysis_results

    def _identify_nodes_by_metrics(self, centrality_df: pd.DataFrame, top_k: int) -> Dict[str, List]:
        """按不同指标识别关键节点"""
        metrics = ['degree', 'betweenness', 'closeness', 'pagerank', 'composite_centrality']
        critical_nodes = {}

        for metric in metrics:
            if metric in centrality_df.columns:
                top_nodes = centrality_df.nlargest(top_k, metric)[[metric]]
                critical_nodes[metric] = [
                    (node, score) for node, score in zip(top_nodes.index, top_nodes[metric])
                ]

        return critical_nodes

    def _analyze_network_robustness(self, G: nx.Graph, centrality_df: pd.DataFrame) -> Dict[str, Any]:
        """网络鲁棒性分析"""
        robustness = {}

        if G.number_of_nodes() == 0:
            return robustness

        # 基础网络指标
        robustness['original_metrics'] = {
            'connected_components': nx.number_connected_components(G),
            'density': nx.density(G),
            'average_clustering': nx.average_clustering(G)
        }

        # 模拟节点移除的影响
        top_nodes = centrality_df.head(5).index.tolist()
        removal_impact = {}

        for node in top_nodes[:3]:  # 测试前3个关键节点
            G_removed = G.copy()
            G_removed.remove_node(node)

            impact = {
                'components_change': nx.number_connected_components(G_removed) - robustness['original_metrics'][
                    'connected_components'],
                'density_change': nx.density(G_removed) - robustness['original_metrics']['density'],
                'efficiency_change': self._calculate_global_efficiency(G_removed) - self._calculate_global_efficiency(G)
            }
            removal_impact[node] = impact

        robustness['removal_impact'] = removal_impact
        return robustness

    def _calculate_global_efficiency(self, G: nx.Graph) -> float:
        """计算全局效率"""
        if G.number_of_nodes() < 2:
            return 0.0

        try:
            efficiencies = []
            for node in G.nodes():
                path_lengths = []
                for target in G.nodes():
                    if node != target:
                        try:
                            path_length = nx.shortest_path_length(G, node, target)
                            path_lengths.append(path_length)
                        except:
                            continue
                if path_lengths:
                    efficiency = 1.0 / np.mean(path_lengths)
                    efficiencies.append(efficiency)

            return np.mean(efficiencies) if efficiencies else 0.0
        except:
            return 0.0

    def _analyze_functional_roles(self, G: nx.Graph, centrality_df: pd.DataFrame) -> Dict[str, List]:
        """分析节点的功能角色"""
        from utils import get_platform_type

        functional_roles = {
            'command_control': [],
            'sensor_hubs': [],
            'communication_relays': [],
            'influencers': []
        }

        # 基于中心性特征分类
        for node in centrality_df.index:
            node_type = get_platform_type(node)
            degree = centrality_df.loc[node, 'degree'] if 'degree' in centrality_df.columns else 0
            betweenness = centrality_df.loc[node, 'betweenness'] if 'betweenness' in centrality_df.columns else 0
            closeness = centrality_df.loc[node, 'closeness'] if 'closeness' in centrality_df.columns else 0

            # 指挥控制节点（高接近中心性）
            if closeness > 0.7:
                functional_roles['command_control'].append((node, closeness))

            # 传感器枢纽（高度中心性）
            if degree > 0.8 and 'radar' in node_type:
                functional_roles['sensor_hubs'].append((node, degree))

            # 通信中继（高介数中心性）
            if betweenness > 0.6:
                functional_roles['communication_relays'].append((node, betweenness))

            # 影响力节点（综合中心性高）
            composite = centrality_df.loc[
                node, 'composite_centrality'] if 'composite_centrality' in centrality_df.columns else 0
            if composite > 0.7:
                functional_roles['influencers'].append((node, composite))

        # 按分数排序
        for role in functional_roles:
            functional_roles[role].sort(key=lambda x: x[1], reverse=True)

        return functional_roles

    def _calculate_composite_ranking(self, centrality_df: pd.DataFrame, top_k: int) -> List[Tuple[str, float, Dict]]:
        """计算综合排名"""
        if centrality_df.empty:
            return []

        composite_scores = []

        for node in centrality_df.index:
            scores = {}
            # 标准化各项指标
            for metric in ['degree', 'betweenness', 'closeness', 'pagerank']:
                if metric in centrality_df.columns:
                    scores[metric] = centrality_df.loc[node, metric]

            # 计算加权综合分（可调整权重）
            weights = {'degree': 0.25, 'betweenness': 0.3, 'closeness': 0.25, 'pagerank': 0.2}
            composite_score = 0
            for metric, weight in weights.items():
                if metric in scores:
                    composite_score += scores[metric] * weight

            composite_scores.append((node, composite_score, scores))

        # 按综合分排序
        composite_scores.sort(key=lambda x: x[1], reverse=True)

        return composite_scores[:top_k]

    def generate_critical_node_report(self, analysis_results: Dict[str, Any]) -> str:
        """生成关键节点分析报告"""
        if not analysis_results:
            return "无分析结果"

        report = "# 关键节点分析报告\n\n"

        # 综合排名
        if 'composite_ranking' in analysis_results:
            report += "## 综合关键节点排名\n\n"
            report += "| 排名 | 节点 | 综合分数 | 度中心性 | 介数中心性 | 接近中心性 |\n"
            report += "|------|------|----------|----------|------------|------------|\n"

            for i, (node, composite_score, scores) in enumerate(analysis_results['composite_ranking'][:10], 1):
                degree = scores.get('degree', 0)
                betweenness = scores.get('betweenness', 0)
                closeness = scores.get('closeness', 0)

                report += f"| {i} | {node} | {composite_score:.3f} | {degree:.3f} | {betweenness:.3f} | {closeness:.3f} |\n"

        # 功能角色分析
        if 'functional_roles' in analysis_results:
            report += "\n## 功能角色分析\n\n"
            for role, nodes in analysis_results['functional_roles'].items():
                if nodes:
                    report += f"### {role}\n"
                    for node, score in nodes[:5]:
                        report += f"- {node}: {score:.3f}\n"
                    report += "\n"

        # 鲁棒性分析
        if 'robustness_analysis' in analysis_results:
            report += "## 网络鲁棒性分析\n\n"
            robustness = analysis_results['robustness_analysis']

            if 'removal_impact' in robustness:
                report += "### 关键节点移除影响\n"
                for node, impact in robustness['removal_impact'].items():
                    report += f"- **{node}**: 连通分量变化 {impact['components_change']}, "
                    report += f"密度变化 {impact['density_change']:.3f}, "
                    report += f"效率变化 {impact['efficiency_change']:.3f}\n"

        return report