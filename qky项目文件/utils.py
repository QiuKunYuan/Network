# src/utils.py
import yaml
import json
import pickle
import pandas as pd
import numpy as np
import networkx as nx
from typing import Any, Dict, List, Optional, Union
import os
from datetime import datetime
import logging


def setup_logging(log_dir: str = "outputs/reports"):
    """设置日志记录"""
    os.makedirs(log_dir, exist_ok=True)

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(os.path.join(log_dir, 'naval_analysis.log')),
            logging.StreamHandler()
        ]
    )
    return logging.getLogger(__name__)


def load_config(config_path: str) -> Dict[str, Any]:
    """加载YAML配置文件"""
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        logger = setup_logging()
        logger.info(f"配置文件加载成功: {config_path}")
        return config
    except Exception as e:
        print(f"配置文件加载失败: {e}")
        return {}


def save_config(config: Dict[str, Any], config_path: str):
    """保存配置到YAML文件"""
    try:
        with open(config_path, 'w', encoding='utf-8') as f:
            yaml.dump(config, f, default_flow_style=False, allow_unicode=True, indent=2)
        print(f"配置已保存: {config_path}")
    except Exception as e:
        print(f"配置保存失败: {e}")


def save_network(G: nx.Graph, filepath: str, format: str = 'graphml'):
    """保存网络对象"""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)

    try:
        if format == 'graphml':
            nx.write_graphml(G, filepath)
        elif format == 'gexf':
            nx.write_gexf(G, filepath)
        elif format == 'pickle':
            with open(filepath, 'wb') as f:
                pickle.dump(G, f)
        else:
            nx.write_edgelist(G, filepath)

        print(f"网络已保存: {filepath}")
    except Exception as e:
        print(f"网络保存失败: {e}")


def load_network(filepath: str, format: str = 'graphml') -> Optional[nx.Graph]:
    """加载网络对象"""
    try:
        if format == 'graphml':
            G = nx.read_graphml(filepath)
        elif format == 'gexf':
            G = nx.read_gexf(filepath)
        elif format == 'pickle':
            with open(filepath, 'rb') as f:
                G = pickle.load(f)
        else:
            G = nx.read_edgelist(filepath)

        print(f"网络已加载: {filepath}")
        return G
    except Exception as e:
        print(f"网络加载失败: {e}")
        return None


def calculate_network_metrics(G: nx.Graph) -> Dict[str, float]:
    """计算网络拓扑指标 - 修复版本"""
    metrics = {}

    try:
        metrics['number_of_nodes'] = G.number_of_nodes()
        metrics['number_of_edges'] = G.number_of_edges()

        # 处理空网络
        if G.number_of_nodes() == 0:
            return {
                'number_of_nodes': 0.0, 'number_of_edges': 0.0, 'density': 0.0,
                'average_degree': 0.0, 'diameter': 0.0, 'average_path_length': 0.0,
                'connected_components': 0.0, 'clustering_coefficient': 0.0, 'transitivity': 0.0,
                'is_directed': False
            }

        # 处理有向图
        is_directed = G.is_directed()
        metrics['is_directed'] = is_directed

        # 密度计算
        metrics['density'] = nx.density(G)

        # 平均度计算
        degrees = [d for _, d in G.degree()]
        metrics['average_degree'] = np.mean(degrees) if degrees else 0.0

        # 对于有向图，只计算基本指标
        if is_directed:
            metrics['diameter'] = 0.0
            metrics['average_path_length'] = 0.0
            metrics['connected_components'] = float(nx.number_weakly_connected_components(G))
            metrics['clustering_coefficient'] = 0.0
            metrics['transitivity'] = 0.0
        else:
            # 无向图的完整指标计算
            if nx.is_connected(G) and G.number_of_nodes() > 1:
                metrics['diameter'] = float(nx.diameter(G))
                metrics['average_path_length'] = float(nx.average_shortest_path_length(G))
            else:
                # 对于非连通图，计算最大连通分量
                if G.number_of_nodes() > 0:
                    largest_cc = max(nx.connected_components(G), key=len)
                    subgraph = G.subgraph(largest_cc)
                    if len(largest_cc) > 1:
                        metrics['diameter'] = float(nx.diameter(subgraph))
                        metrics['average_path_length'] = float(nx.average_shortest_path_length(subgraph))
                    else:
                        metrics['diameter'] = 0.0
                        metrics['average_path_length'] = 0.0
                    metrics['connected_components'] = float(nx.number_connected_components(G))
                else:
                    metrics['diameter'] = 0.0
                    metrics['average_path_length'] = 0.0
                    metrics['connected_components'] = 0.0

            metrics['clustering_coefficient'] = float(nx.average_clustering(G))
            metrics['transitivity'] = float(nx.transitivity(G))

    except Exception as e:
        print(f"网络指标计算失败: {e}")
        # 确保所有指标都有默认值
        default_metrics = {
            'number_of_nodes': 0.0, 'number_of_edges': 0.0, 'density': 0.0,
            'average_degree': 0.0, 'diameter': 0.0, 'average_path_length': 0.0,
            'connected_components': 0.0, 'clustering_coefficient': 0.0, 'transitivity': 0.0,
            'is_directed': False
        }
        metrics.update(default_metrics)

    return metrics


def export_metrics_to_csv(metrics_dict: Dict[str, Dict[str, float]],
                          filename: str = "network_metrics.csv"):
    """导出网络指标到CSV"""
    if not metrics_dict:
        print("没有网络指标数据可导出")
        return pd.DataFrame()

    df = pd.DataFrame(metrics_dict).T
    filepath = f"outputs/metrics/{filename}"
    os.makedirs(os.path.dirname(filepath), exist_ok=True)

    df.to_csv(filepath, encoding='utf-8-sig')
    print(f"网络指标已导出: {filepath}")
    return df


def generate_report(analysis_results: Dict[str, Any],
                    filename: str = "analysis_report.md"):
    """生成分析报告 - 修复格式化问题"""
    if not analysis_results:
        print("没有分析结果可生成报告")
        return ""

    report_content = f"""# 海战网络分析报告

生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## 网络概览

"""

    # 添加网络基本信息 - 修复格式化问题
    for network_name, results in analysis_results.items():
        if 'metrics' in results:
            metrics = results['metrics']
            report_content += f"### {network_name}网络\n\n"
            report_content += f"- 节点数: {metrics.get('number_of_nodes', 0)}\n"
            report_content += f"- 边数: {metrics.get('number_of_edges', 0)}\n"

            # 安全格式化数字
            density = metrics.get('density', 0.0)
            avg_degree = metrics.get('average_degree', 0.0)
            clustering = metrics.get('clustering_coefficient', 0.0)
            transitivity = metrics.get('transitivity', 0.0)

            report_content += f"- 网络密度: {density:.3f}\n"
            report_content += f"- 平均度: {avg_degree:.2f}\n"
            report_content += f"- 聚类系数: {clustering:.3f}\n"
            report_content += f"- 传递性: {transitivity:.3f}\n\n"

    # 添加关键节点信息
    report_content += "## 关键节点分析\n\n"
    for network_name, results in analysis_results.items():
        if 'critical_nodes' in results:
            critical_nodes = results['critical_nodes']
            report_content += f"### {network_name}网络关键节点\n\n"

            if critical_nodes and isinstance(critical_nodes, list):
                if critical_nodes and isinstance(critical_nodes[0], tuple) and len(critical_nodes[0]) == 2:
                    # 如果是(节点, 分数)元组列表
                    for i, (node, score) in enumerate(critical_nodes[:5], 1):
                        report_content += f"{i}. {node}: {score:.3f}\n"
                else:
                    # 如果只是节点名称列表
                    for i, node in enumerate(critical_nodes[:5], 1):
                        # 尝试从centrality_df获取分数
                        if 'centrality_df' in results and node in results['centrality_df'].index:
                            score = results['centrality_df'].loc[node, 'composite_centrality']
                            report_content += f"{i}. {node}: {score:.3f}\n"
                        else:
                            report_content += f"{i}. {node}\n"
            report_content += "\n"

    # 添加网络拓扑分析
    report_content += "## 网络拓扑分析\n\n"
    for network_name, results in analysis_results.items():
        if 'metrics' in results:
            metrics = results['metrics']
            report_content += f"### {network_name}网络拓扑\n\n"

            connected_components = metrics.get('connected_components', 1)
            diameter = metrics.get('diameter', 0.0)
            avg_path_length = metrics.get('average_path_length', 0.0)

            if connected_components > 1:
                report_content += f"- 连通分量: {int(connected_components)} 个\n"
                report_content += f"- 网络直径: {int(diameter)}\n"
                report_content += f"- 平均路径长度: {avg_path_length:.2f}\n"
            else:
                report_content += "- 网络是连通的\n"
                report_content += f"- 网络直径: {int(diameter)}\n"
                report_content += f"- 平均路径长度: {avg_path_length:.2f}\n"

            report_content += f"- 传递性: {metrics.get('transitivity', 0.0):.3f}\n\n"

    # 添加分析总结
    report_content += "## 分析总结\n\n"

    total_nodes = sum(results.get('metrics', {}).get('number_of_nodes', 0) for results in analysis_results.values())
    total_edges = sum(results.get('metrics', {}).get('number_of_edges', 0) for results in analysis_results.values())

    report_content += f"- 总节点数: {total_nodes}\n"
    report_content += f"- 总边数: {total_edges}\n"
    report_content += f"- 分析网络数: {len(analysis_results)}\n"

    # 找出最重要的关键节点
    all_critical_nodes = []
    for results in analysis_results.values():
        if 'critical_nodes' in results:
            nodes = results['critical_nodes']
            if nodes and isinstance(nodes, list):
                if nodes and isinstance(nodes[0], tuple):
                    all_critical_nodes.extend([(node, score) for node, score in nodes[:3]])
                else:
                    all_critical_nodes.extend([(node, 1.0) for node in nodes[:3]])

    if all_critical_nodes:
        report_content += "\n## 全局关键节点\n\n"
        # 按分数排序（如果可用）
        if all(isinstance(node[1], (int, float)) for node in all_critical_nodes):
            all_critical_nodes.sort(key=lambda x: x[1], reverse=True)

        for i, (node, score) in enumerate(all_critical_nodes[:5], 1):
            if isinstance(score, (int, float)):
                report_content += f"{i}. {node}: {score:.3f}\n"
            else:
                report_content += f"{i}. {node}\n"

    # 保存报告
    filepath = f"outputs/reports/{filename}"
    os.makedirs(os.path.dirname(filepath), exist_ok=True)

    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(report_content)
        print(f"分析报告已生成: {filepath}")
    except Exception as e:
        print(f"报告生成失败: {e}")

    return report_content


def normalize_dict_values(data_dict: Dict[Any, float]) -> Dict[Any, float]:
    """归一化字典值到[0,1]范围"""
    if not data_dict:
        return {}

    values = list(data_dict.values())
    min_val = min(values)
    max_val = max(values)

    if max_val == min_val:
        return {k: 1.0 for k in data_dict.keys()}

    return {k: (v - min_val) / (max_val - min_val) for k, v in data_dict.items()}


def merge_centrality_scores(centrality_dicts: List[Dict[Any, float]],
                            weights: Optional[List[float]] = None) -> Dict[Any, float]:
    """合并多个中心性分数"""
    if not centrality_dicts:
        return {}

    if weights is None:
        weights = [1.0] * len(centrality_dicts)

    if len(centrality_dicts) != len(weights):
        raise ValueError("中心性字典和权重列表长度必须一致")

    # 归一化每个中心性分数
    normalized_dicts = [normalize_dict_values(d) for d in centrality_dicts]

    # 合并分数
    merged_scores = {}
    all_nodes = set()
    for d in normalized_dicts:
        all_nodes.update(d.keys())

    for node in all_nodes:
        score = 0.0
        for i, d in enumerate(normalized_dicts):
            score += d.get(node, 0.0) * weights[i]
        merged_scores[node] = score

    return merged_scores


def detect_network_changes(network_sequence: List[nx.Graph]) -> pd.DataFrame:
    """检测网络结构变化"""
    changes = []

    for i in range(1, len(network_sequence)):
        G_prev = network_sequence[i - 1]
        G_curr = network_sequence[i]

        change_metrics = {
            'time_step': i,
            'nodes_added': len(set(G_curr.nodes()) - set(G_prev.nodes())),
            'nodes_removed': len(set(G_prev.nodes()) - set(G_curr.nodes())),
            'edges_added': len(set(G_curr.edges()) - set(G_prev.edges())),
            'edges_removed': len(set(G_prev.edges()) - set(G_curr.edges())),
            'density_change': float(nx.density(G_curr) - nx.density(G_prev))
        }
        changes.append(change_metrics)

    return pd.DataFrame(changes)


def get_platform_type(platform_id: str) -> str:
    """根据平台ID推断平台类型"""
    if not platform_id or not isinstance(platform_id, str):
        return 'unknown'

    platform_id_lower = platform_id.lower()

    if any(keyword in platform_id_lower for keyword in ['radar', 'ew_radar', 'acq_radar']):
        return 'radar'
    elif any(keyword in platform_id_lower for keyword in ['sam', 'launcher', 'ttr']):
        return 'sam_system'
    elif any(keyword in platform_id_lower for keyword in ['command', 'cmdr', 'iads']):
        return 'command_control'
    elif any(keyword in platform_id_lower for keyword in ['soj', 'jammer']):
        return 'ew_platform'
    elif any(keyword in platform_id_lower for keyword in ['target']):
        return 'target'
    else:
        return 'unknown'


def create_timestamp() -> str:
    """创建时间戳用于文件名"""
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def safe_float_format(value, format_spec: str = ".3f") -> str:
    """安全格式化浮点数"""
    try:
        if isinstance(value, (int, float)):
            return format(value, format_spec)
        else:
            return str(value)
    except:
        return str(value)


# 初始化日志
logger = setup_logging()