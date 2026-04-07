import networkx as nx
import numpy as np
import pandas as pd
from typing import Dict, Tuple,List

from src.centrality_analysis import CentralityAnalyzer


class GravityAnalyzer:
    def __init__(self):
        pass

    def calculate_network_gravity_center(self, G: nx.Graph,
                                         weight_metric: str = 'composite_centrality') -> Dict:
        """计算网络重心"""
        if len(G.nodes) == 0:
            return {}

        # 获取节点中心性作为权重
        centrality_analyzer = CentralityAnalyzer()
        centrality_df = centrality_analyzer.calculate_all_centralities(G)

        # 计算加权重心
        total_weight = centrality_df[weight_metric].sum()

        # 这里需要结合节点的实际位置信息
        # 简化示例，实际应从AFSIM数据中提取实体位置
        gravity_center = {
            'influence_radius': self._calculate_influence_radius(G, centrality_df),
            'critical_mass': total_weight,
            'most_influential_nodes': centrality_df.head(5).index.tolist()
        }

        return gravity_center

    def analyze_gravity_shifts(self, network_sequence: List[nx.Graph]) -> pd.DataFrame:
        """分析重心漂移"""
        shifts = []

        for i, G in enumerate(network_sequence):
            gravity = self.calculate_network_gravity_center(G)
            shifts.append({
                'time_step': i,
                'critical_mass': gravity['critical_mass'],
                'influence_radius': gravity['influence_radius'],
                'top_node': gravity['most_influential_nodes'][0] if gravity['most_influential_nodes'] else None
            })

        return pd.DataFrame(shifts)

    def _calculate_influence_radius(self, G: nx.Graph, centrality_df: pd.DataFrame) -> float:
        """计算影响力半径"""
        if len(G.nodes) < 2:
            return 0.0

        # 基于网络直径和中心性分布计算影响力半径
        try:
            diameter = nx.diameter(G)
            avg_centrality = centrality_df['composite_centrality'].mean()
            return diameter * avg_centrality
        except:
            return len(G.nodes) * 0.1