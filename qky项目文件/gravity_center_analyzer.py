# src/gravity_center_analyzer.py
import networkx as nx
import pandas as pd
import numpy as np
from typing import Dict, List, Tuple, Any
from centrality_analysis import CentralityAnalyzer
from utils import normalize_dict_values


class GravityCenterAnalyzer:
    def __init__(self):
        self.centrality_analyzer = CentralityAnalyzer()

    def analyze_network_gravity(self, G: nx.Graph) -> Dict[str, Any]:
        """分析网络重心"""
        if G.number_of_nodes() == 0:
            return {}

        print(f"开始网络重心分析...")

        gravity_analysis = {}

        # 1. 计算基础重心
        gravity_analysis['basic_gravity'] = self._calculate_basic_gravity_center(G)

        # 2. 影响力分布分析
        gravity_analysis['influence_distribution'] = self._analyze_influence_distribution(G)

        # 3. 重心稳定性分析
        gravity_analysis['stability_analysis'] = self._analyze_gravity_stability(G)

        # 4. 多重心识别
        gravity_analysis['multiple_centers'] = self._identify_multiple_centers(G)

        return gravity_analysis

    def _calculate_basic_gravity_center(self, G: nx.Graph) -> Dict[str, Any]:
        """计算基础重心指标"""
        centrality_df = self.centrality_analyzer.calculate_all_centralities(G)

        if centrality_df.empty:
            return {}

        # 影响力质量（总中心性）
        critical_mass = centrality_df['composite_centrality'].sum()

        # 影响力半径（基于网络直径和中心性）
        try:
            diameter = nx.diameter(G) if nx.is_connected(G) else 0
            avg_centrality = centrality_df['composite_centrality'].mean()
            influence_radius = diameter * avg_centrality
        except:
            influence_radius = 0

        # 重心节点（最高中心性）
        gravity_node = centrality_df['composite_centrality'].idxmax()
        gravity_score = centrality_df['composite_centrality'].max()

        # 重心区域（前10%节点）
        top_percentile = max(1, len(centrality_df) // 10)
        gravity_region = centrality_df.head(top_percentile).index.tolist()

        return {
            'gravity_node': gravity_node,
            'gravity_score': gravity_score,
            'critical_mass': critical_mass,
            'influence_radius': influence_radius,
            'gravity_region': gravity_region,
            'gravity_dominance': gravity_score / critical_mass if critical_mass > 0 else 0
        }

    def _analyze_influence_distribution(self, G: nx.Graph) -> Dict[str, Any]:
        """分析影响力分布"""
        centrality_df = self.centrality_analyzer.calculate_all_centralities(G)

        if centrality_df.empty:
            return {}

        composite_scores = centrality_df['composite_centrality']

        # 基尼系数（衡量不平等性）
        gini_coefficient = self._calculate_gini_coefficient(composite_scores.values)

        # 影响力集中度
        top_10_percent = composite_scores.nlargest(max(1, len(composite_scores) // 10))
        concentration_ratio = top_10_percent.sum() / composite_scores.sum()

        # 分布类型判断
        if concentration_ratio > 0.8:
            distribution_type = "高度集中"
        elif concentration_ratio > 0.5:
            distribution_type = "中等集中"
        else:
            distribution_type = "相对分散"

        return {
            'gini_coefficient': gini_coefficient,
            'concentration_ratio': concentration_ratio,
            'distribution_type': distribution_type,
            'top_10_nodes': list(zip(top_10_percent.index, top_10_percent.values))
        }

    def _calculate_gini_coefficient(self, values: np.ndarray) -> float:
        """计算基尼系数"""
        if len(values) == 0:
            return 0.0

        # 排序并计算累积
        sorted_values = np.sort(values)
        n = len(sorted_values)
        index = np.arange(1, n + 1)

        # 基尼系数公式
        gini = (np.sum((2 * index - n - 1) * sorted_values)) / (n * np.sum(sorted_values))
        return gini

    def _analyze_gravity_stability(self, G: nx.Graph) -> Dict[str, Any]:
        """分析重心稳定性"""
        centrality_df = self.centrality_analyzer.calculate_all_centralities(G)

        if centrality_df.empty or len(centrality_df) < 2:
            return {}

        composite_scores = centrality_df['composite_centrality']

        # 计算分数差异
        sorted_scores = composite_scores.sort_values(ascending=False)
        top_score = sorted_scores.iloc[0]
        second_score = sorted_scores.iloc[1] if len(sorted_scores) > 1 else 0

        # 稳定性指标
        score_gap = top_score - second_score
        stability_ratio = score_gap / top_score if top_score > 0 else 0

        if stability_ratio > 0.3:
            stability_level = "高度稳定"
        elif stability_ratio > 0.1:
            stability_level = "中等稳定"
        else:
            stability_level = "不稳定"

        return {
            'top_node': sorted_scores.index[0],
            'top_score': top_score,
            'second_node': sorted_scores.index[1] if len(sorted_scores) > 1 else None,
            'second_score': second_score,
            'score_gap': score_gap,
            'stability_ratio': stability_ratio,
            'stability_level': stability_level
        }

    def _identify_multiple_centers(self, G: nx.Graph) -> Dict[str, Any]:
        """识别多重心结构"""
        centrality_df = self.centrality_analyzer.calculate_all_centralities(G)

        if centrality_df.empty:
            return {}

        composite_scores = centrality_df['composite_centrality']

        # 使用聚类识别多个重心
        from sklearn.cluster import KMeans

        try:
            # 准备数据
            scores_2d = composite_scores.values.reshape(-1, 1)

            # 尝试2-3个聚类
            best_centers = []
            for n_clusters in [2, 3]:
                if len(scores_2d) >= n_clusters:
                    kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
                    clusters = kmeans.fit_predict(scores_2d)

                    # 每个聚类的中心节点
                    cluster_centers = []
                    for i in range(n_clusters):
                        cluster_indices = np.where(clusters == i)[0]
                        if len(cluster_indices) > 0:
                            cluster_scores = composite_scores.iloc[cluster_indices]
                            center_node = cluster_scores.idxmax()
                            cluster_centers.append((center_node, cluster_scores.max()))

                    best_centers.append(cluster_centers)

            # 选择最优的聚类结果
            multiple_centers = best_centers[0] if best_centers else []

            return {
                'multiple_centers': multiple_centers,
                'has_multiple_centers': len(multiple_centers) > 1,
                'primary_center': multiple_centers[0] if multiple_centers else None,
                'secondary_centers': multiple_centers[1:] if len(multiple_centers) > 1 else []
            }

        except Exception as e:
            print(f"多重心识别失败: {e}")
            return {
                'multiple_centers': [],
                'has_multiple_centers': False,
                'primary_center': None,
                'secondary_centers': []
            }

    def analyze_gravity_evolution(self, network_sequence: List[nx.Graph]) -> pd.DataFrame:
        """分析重心演化过程"""
        evolution_data = []

        for i, G in enumerate(network_sequence):
            if G.number_of_nodes() == 0:
                continue

            gravity_analysis = self.analyze_network_gravity(G)
            basic_gravity = gravity_analysis.get('basic_gravity', {})
            stability = gravity_analysis.get('stability_analysis', {})
            influence_dist = gravity_analysis.get('influence_distribution', {})

            evolution_data.append({
                'time_step': i,
                'gravity_node': basic_gravity.get('gravity_node'),
                'gravity_score': basic_gravity.get('gravity_score', 0),
                'critical_mass': basic_gravity.get('critical_mass', 0),
                'influence_radius': basic_gravity.get('influence_radius', 0),
                'stability_level': stability.get('stability_level', '未知'),
                'concentration_ratio': influence_dist.get('concentration_ratio', 0),
                'gini_coefficient': influence_dist.get('gini_coefficient', 0)
            })

        return pd.DataFrame(evolution_data)

    def generate_gravity_report(self, analysis_results: Dict[str, Any]) -> str:
        """生成重心分析报告"""
        if not analysis_results:
            return "无分析结果"

        report = "# 网络重心分析报告\n\n"

        # 基础重心信息
        if 'basic_gravity' in analysis_results:
            bg = analysis_results['basic_gravity']
            report += "## 基础重心分析\n\n"
            report += f"- **重心节点**: {bg.get('gravity_node', '无')}\n"
            report += f"- **重心分数**: {bg.get('gravity_score', 0):.3f}\n"
            report += f"- **影响力质量**: {bg.get('critical_mass', 0):.3f}\n"
            report += f"- **影响力半径**: {bg.get('influence_radius', 0):.2f}\n"
            report += f"- **重心 dominance**: {bg.get('gravity_dominance', 0):.1%}\n"
            report += f"- **重心区域节点数**: {len(bg.get('gravity_region', []))}\n\n"

        # 稳定性分析
        if 'stability_analysis' in analysis_results:
            stability = analysis_results['stability_analysis']
            report += "## 重心稳定性分析\n\n"
            report += f"- **稳定性等级**: {stability.get('stability_level', '未知')}\n"
            report += f"- **分数差距**: {stability.get('score_gap', 0):.3f}\n"
            report += f"- **稳定性比率**: {stability.get('stability_ratio', 0):.1%}\n\n"

        # 影响力分布
        if 'influence_distribution' in analysis_results:
            influence = analysis_results['influence_distribution']
            report += "## 影响力分布分析\n\n"
            report += f"- **分布类型**: {influence.get('distribution_type', '未知')}\n"
            report += f"- **基尼系数**: {influence.get('gini_coefficient', 0):.3f}\n"
            report += f"- **集中度比率**: {influence.get('concentration_ratio', 0):.1%}\n\n"

        # 多重心分析
        if 'multiple_centers' in analysis_results:
            multi = analysis_results['multiple_centers']
            report += "## 多重心结构分析\n\n"
            report += f"- **多重心存在**: {'是' if multi.get('has_multiple_centers') else '否'}\n"

            if multi.get('has_multiple_centers'):
                report += "- **主要重心**: {} (分数: {:.3f})\n".format(
                    multi['primary_center'][0], multi['primary_center'][1])

                if multi.get('secondary_centers'):
                    report += "- **次要重心**:\n"
                    for center, score in multi['secondary_centers']:
                        report += f"  - {center}: {score:.3f}\n"

        return report