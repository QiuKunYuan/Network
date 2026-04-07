# src/centrality_analysis.py
import networkx as nx
import pandas as pd
import numpy as np
from typing import Dict, List, Optional


class CentralityAnalyzer:
    def __init__(self):
        self.metrics = {}

    def calculate_all_centralities(self, G: nx.Graph,
                                   shapley_values: Optional[Dict[str, float]] = None) -> pd.DataFrame:
        """
        计算所有中心性指标，并可选地融合 Shapley 值。

        :param G: 网络图
        :param shapley_values: 预先计算好的 Shapley 值字典 {node: score}（已归一化到[0,1]）
                               若为 None，则不参与融合，composite_centrality 保持原有权重
        :return: 包含各指标和综合分数的 DataFrame
        """
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
            except Exception:
                centralities['betweenness'] = {node: 0 for node in G.nodes()}

            # 接近中心性
            try:
                centralities['closeness'] = nx.closeness_centrality(G)
            except Exception:
                centralities['closeness'] = {node: 0 for node in G.nodes()}

            # PageRank
            try:
                centralities['pagerank'] = nx.pagerank(G, max_iter=200)
            except Exception:
                centralities['pagerank'] = {node: 1.0 / len(G.nodes()) for node in G.nodes()}

        except Exception as e:
            print(f"中心性计算警告: {e}")
            centralities['degree'] = nx.degree_centrality(G)
            for metric in ['betweenness', 'closeness', 'pagerank']:
                centralities[metric] = {node: 0 for node in G.nodes()}

        # 转换为 DataFrame
        df = pd.DataFrame(centralities)

        # ── 综合中心性（原有四指标加权）──────────────────────────────
        # 权重：度(0.4) + 介数(0.3) + 接近(0.2) + PageRank(0.1)
        base_weights = {'degree': 0.4, 'betweenness': 0.3, 'closeness': 0.2, 'pagerank': 0.1}
        df['composite_centrality'] = 0.0
        for metric, weight in base_weights.items():
            if metric in df.columns:
                df['composite_centrality'] += df[metric] * weight

        # ── Shapley 融合分数（新增）──────────────────────────────────
        # 若传入 shapley_values，则计算融合分数：
        #   fused_score = composite_centrality × 0.5 + shapley_value × 0.5
        # 两者各占 50%，可通过参数调整
        if shapley_values is not None and len(shapley_values) > 0:
            # 将 shapley_values 对齐到 df 的索引（缺失节点补 0）
            sv_series = pd.Series(shapley_values, name='shapley')
            df = df.join(sv_series, how='left')
            df['shapley'] = df['shapley'].fillna(0.0)

            # 归一化 composite_centrality 到 [0,1]（与 shapley 量纲对齐）
            cc_min = df['composite_centrality'].min()
            cc_max = df['composite_centrality'].max()
            if cc_max > cc_min:
                df['composite_centrality_norm'] = (
                    (df['composite_centrality'] - cc_min) / (cc_max - cc_min)
                )
            else:
                df['composite_centrality_norm'] = 1.0

            # 融合分数
            df['fused_score'] = (
                df['composite_centrality_norm'] * 0.5 +
                df['shapley'] * 0.5
            )
            print(f"  Shapley 融合完成，fused_score 范围: "
                  f"{df['fused_score'].min():.4f} ~ {df['fused_score'].max():.4f}")

            # 以融合分数作为最终排序依据
            return df.sort_values('fused_score', ascending=False)
        else:
            # 无 Shapley 时，保持原有逻辑
            return df.sort_values('composite_centrality', ascending=False)

    def identify_critical_nodes(self, G: nx.Graph, top_k: int = 10,
                                shapley_values: Optional[Dict[str, float]] = None) -> List:
        """识别关键节点（支持 Shapley 融合）"""
        if len(G.nodes()) == 0:
            return []

        centrality_df = self.calculate_all_centralities(G, shapley_values=shapley_values)

        # 优先用融合分数排序，否则用综合中心性
        sort_col = 'fused_score' if 'fused_score' in centrality_df.columns else 'composite_centrality'
        return centrality_df.sort_values(sort_col, ascending=False).head(top_k).index.tolist()
