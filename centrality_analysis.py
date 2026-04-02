# src/centrality_analysis.py
import networkx as nx
import pandas as pd
import numpy as np
from typing import Dict, List, Optional


class CentralityAnalyzer:
    def __init__(self):
        self.metrics = {}

    def calculate_all_centralities(self, G: nx.Graph) -> pd.DataFrame:
        """计算所有中心性指标"""
        if len(G.nodes()) == 0:
            return pd.DataFrame()

        print(f"计算 {len(G.nodes())} 个节点的中心性...")

        centralities = {}

        try:
            # 度中心性
            centralities['degree'] = nx.degree_centrality(G)

            # 介数中心性
            try:
                centralities['betweenness'] = nx.betweenness_centrality(G)
            except:
                centralities['betweenness'] = {node: 0 for node in G.nodes()}

            # 接近中心性
            try:
                centralities['closeness'] = nx.closeness_centrality(G)
            except:
                centralities['closeness'] = {node: 0 for node in G.nodes()}

            # PageRank
            centralities['pagerank'] = nx.pagerank(G)

        except Exception as e:
            print(f"中心性计算警告: {e}")
            # 如果复杂中心性失败，至少计算度中心性
            centralities['degree'] = nx.degree_centrality(G)
            for metric in ['betweenness', 'closeness', 'pagerank']:
                centralities[metric] = {node: 0 for node in G.nodes()}

        # 转换为DataFrame
        df = pd.DataFrame(centralities)

        # 计算综合中心性
        weights = {'degree': 0.4, 'betweenness': 0.3, 'closeness': 0.2, 'pagerank': 0.1}
        df['composite_centrality'] = 0
        for metric, weight in weights.items():
            if metric in df.columns:
                df['composite_centrality'] += df[metric] * weight

        return df.sort_values('composite_centrality', ascending=False)

    def identify_critical_nodes(self, G: nx.Graph, top_k: int = 10) -> List:
        """识别关键节点"""
        if len(G.nodes()) == 0:
            return []

        centrality_df = self.calculate_all_centralities(G)
        return centrality_df.head(top_k).index.tolist()