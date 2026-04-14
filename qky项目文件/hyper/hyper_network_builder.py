# hyper/hyper_network_builder.py
# -*- coding: utf-8 -*-
"""
CombatHyperNetworkBuilder — 多层超网构建器
==========================================
完全通过 SimDataProcessor 的公开方法获取数据，
不再直接访问 processor.df / processor._col，
与具体数据格式解耦。

四层结构：
  sensor  — 传感器/探测层（DetectEvent）
  command — 指挥控制层（Communication + 层级关系）
  weapon  — 武器打击层（WeaponFire + MunitionDetonation + AttackOrder）
  ew      — 电子战层  （JamingEvent）
"""

import networkx as nx
import pandas as pd
from typing import Dict, List, Tuple, Any


class CombatHyperNetworkBuilder:
    def __init__(self):
        self.layers: Dict[str, nx.DiGraph] = {}
        self.cross_layer_edges: List[Dict] = []
        self.hyper_network = nx.MultiDiGraph()

    # ─────────────────────────────────────────────────────────────────
    # 主入口
    # ─────────────────────────────────────────────────────────────────

    def build_hyper_network(self, processor) -> Dict[str, Any]:
        """
        构建作战超网。
        节点持久化（不清除），边动态化（每次重建）。
        """
        self.layers = {}
        self.cross_layer_edges = []
        self.hyper_network.remove_edges_from(list(self.hyper_network.edges()))

        # 1. 构建各层
        self._build_all_layers(processor)

        # 2. 建立跨层连接
        self._build_cross_layer_connections()

        # 3. 节点合并到超网
        # 策略：节点的最终层由构建层名（layer_name）决定，不用关键词覆盖。
        # 同一节点出现在多层时，优先级：weapon > ew > sensor > command
        # （sensor > command：让执行探测的舰艇显示在 sensor 层，体现探测功能）
        # 导弹类平台用 _classify_node 识别并强制归入 weapon 层
        LAYER_PRIORITY = {'weapon': 4, 'ew': 3, 'sensor': 2, 'command': 1}
        for layer_name, layer_net in self.layers.items():
            for node in layer_net.nodes():
                # 导弹/鱼雷等弹药类强制归入 weapon 层
                classified = self._classify_node(node)
                if classified == 'weapon':
                    final_layer = 'weapon'
                elif classified == 'ew':
                    final_layer = 'ew'
                else:
                    final_layer = layer_name   # 其他平台直接用构建层名
                if node not in self.hyper_network:
                    self.hyper_network.add_node(node, layer=final_layer)
                else:
                    cur = self.hyper_network.nodes[node].get('layer', 'command')
                    if LAYER_PRIORITY.get(final_layer, 0) > LAYER_PRIORITY.get(cur, 0):
                        self.hyper_network.nodes[node]['layer'] = final_layer

            for u, v, data in layer_net.edges(data=True):
                self.hyper_network.add_edge(u, v, **data, type='intra')

        # 4. 跨层连接
        for edge in self.cross_layer_edges:
            u, v = edge['source_node'], edge['target_node']
            for n, lyr in [(u, edge['source_layer']), (v, edge['target_layer'])]:
                if n not in self.hyper_network:
                    classified = self._classify_node(n)
                    final_layer = classified if classified != 'unknown' else lyr
                    self.hyper_network.add_node(n, layer=final_layer)
            self.hyper_network.add_edge(u, v,
                                        weight=edge['weight'],
                                        type='inter')

        # 5. 兜底：超网仍为空时从平台列表构建
        if self.hyper_network.number_of_nodes() == 0:
            print("  ⚠️ 超网为空，启用兜底构建...")
            self._fallback_build(processor)

        # 6. 计算指标
        metrics = self._calculate_hyper_metrics()

        print(f"超网构建完成: {self.hyper_network.number_of_nodes()} 节点, "
              f"{self.hyper_network.number_of_edges()} 边")

        return {
            'layers':            self.layers,
            'cross_layer_edges': self.cross_layer_edges,
            'hyper_network':     self.hyper_network,
            'metrics':           metrics,
        }

    def build_hyper_network_from_subset(self, processor,
                                        df_subset=None) -> Dict[str, Any]:
        """
        兼容旧接口：使用时间切片快照构建超网。
        新版 processor.get_time_windows() 直接返回 sub_processor，
        所以 df_subset 参数已废弃，直接忽略。
        """
        return self.build_hyper_network(processor)

    # ─────────────────────────────────────────────────────────────────
    # 各层构建
    # ─────────────────────────────────────────────────────────────────

    def _build_all_layers(self, processor):
        self.layers['sensor']  = self._build_sensor_layer(processor)
        self.layers['command'] = self._build_command_layer(processor)
        self.layers['weapon']  = self._build_weapon_layer(processor)
        self.layers['ew']      = self._build_ew_layer(processor)

        print("各网络层构建完成:")
        for name, net in self.layers.items():
            print(f"  {name}: {net.number_of_nodes()} 节点, "
                  f"{net.number_of_edges()} 边")

    def _build_sensor_layer(self, processor) -> nx.DiGraph:
        """
        传感器层：DetectEvent → Processor（探测主体）→ cTargetname
        兜底：把 BaseEntity 中传感器类型的平台加为孤立节点
        """
        G = nx.DiGraph()

        for src, tgt, w in processor.extract_sensor_detections():
            G.add_edge(src, tgt,
                       relation='detects', layer='sensor', weight=w)

        # 兜底：从平台列表补充传感器节点
        if G.number_of_nodes() == 0:
            for plat in processor.get_all_platforms():
                if self._classify_node(plat) == 'sensor':
                    G.add_node(plat, layer='sensor')

        return G

    def _build_command_layer(self, processor) -> nx.DiGraph:
        """
        指挥控制层：
          1. Communication → sendName → receiveName（通信即指挥）
          2. extract_platform_hierarchy → 载机/飞机层级
        兜底：把 BaseEntity 中指挥类型的平台加为孤立节点
        """
        G = nx.DiGraph()

        # 通信边（双向通信取单向：发送方→接收方）
        for src, tgt, w in processor.extract_communication_links():
            G.add_edge(src, tgt,
                       relation='communicates', layer='command', weight=w)

        # 层级关系（下级→上级 反转为 上级→下级）
        for subordinate, commander in processor.extract_platform_hierarchy().items():
            G.add_edge(commander, subordinate,
                       relation='commands', layer='command', weight=0.8)

        # 兜底
        if G.number_of_nodes() == 0:
            for plat in processor.get_all_platforms():
                if self._classify_node(plat) == 'command':
                    G.add_node(plat, layer='command')

        return G

    def _build_weapon_layer(self, processor) -> nx.DiGraph:
        """
        武器打击层：WeaponFire + MunitionDetonation + AttackOrder
        """
        G = nx.DiGraph()

        for src, tgt, w in processor.extract_weapon_engagements():
            if G.has_edge(src, tgt):
                # 取最大权重
                G[src][tgt]['weight'] = max(G[src][tgt]['weight'], w)
            else:
                G.add_edge(src, tgt,
                           relation='engages', layer='weapon', weight=w)

        # 兜底
        if G.number_of_nodes() == 0:
            for plat in processor.get_all_platforms():
                if self._classify_node(plat) == 'weapon':
                    G.add_node(plat, layer='weapon')

        return G

    def _build_ew_layer(self, processor) -> nx.DiGraph:
        """
        电子战层：JamingEvent → attackName → targetName
        """
        G = nx.DiGraph()

        for src, tgt, w in processor.extract_jamming_relations():
            G.add_edge(src, tgt,
                       relation='jams', layer='ew', weight=w)

        # 兜底
        if G.number_of_nodes() == 0:
            for plat in processor.get_all_platforms():
                if self._classify_node(plat) == 'ew':
                    G.add_node(plat, layer='ew')

        return G

    def _fallback_build(self, processor):
        """兜底：直接从所有平台 + 层级关系构建超网"""
        print("  兜底构建：从所有平台节点构建超网...")
        hierarchy = processor.extract_platform_hierarchy()
        all_platforms = processor.get_all_platforms()

        for plat in all_platforms:
            node_type = self._classify_node(plat)
            layer = node_type if node_type in ('sensor', 'command', 'weapon', 'ew') else 'sensor'
            if plat not in self.hyper_network:
                self.hyper_network.add_node(plat, layer=layer)

        for subordinate, commander in hierarchy.items():
            for n, lyr in [(subordinate, 'command'), (commander, 'command')]:
                if n not in self.hyper_network:
                    self.hyper_network.add_node(n, layer=lyr)
            self.hyper_network.add_edge(commander, subordinate,
                                        weight=1.0, type='intra')

        print(f"  兜底构建完成: {self.hyper_network.number_of_nodes()} 节点")

    # ─────────────────────────────────────────────────────────────────
    # 跨层连接
    # ─────────────────────────────────────────────────────────────────

    def _build_cross_layer_connections(self):
        """建立四层之间的跨层连接"""
        print("建立跨层连接...")
        self._connect_sensor_to_command()
        self._connect_command_to_weapon()
        self._connect_ew_to_sensor()
        self._connect_same_entity_cross_layer()
        print(f"建立 {len(self.cross_layer_edges)} 个跨层连接")

    def _connect_sensor_to_command(self):
        """传感器层 → 指挥层（同系统节点）"""
        for s_node in self.layers['sensor'].nodes():
            for c_node in self.layers['command'].nodes():
                if self._belong_to_same_system(s_node, c_node):
                    self.cross_layer_edges.append({
                        'source_node':  s_node, 'source_layer': 'sensor',
                        'target_node':  c_node, 'target_layer': 'command',
                        'relation':     'reports_to', 'weight': 0.8,
                    })

    def _connect_command_to_weapon(self):
        """指挥层 → 武器层（同系统节点）"""
        for c_node in self.layers['command'].nodes():
            for w_node in self.layers['weapon'].nodes():
                if self._belong_to_same_system(c_node, w_node):
                    self.cross_layer_edges.append({
                        'source_node':  c_node, 'source_layer': 'command',
                        'target_node':  w_node, 'target_layer': 'weapon',
                        'relation':     'controls', 'weight': 0.9,
                    })

    def _connect_ew_to_sensor(self):
        """电子战层 → 传感器层（对抗关系）"""
        for e_node in self.layers['ew'].nodes():
            for s_node in self.layers['sensor'].nodes():
                if self._is_adversarial(e_node, s_node):
                    self.cross_layer_edges.append({
                        'source_node':  e_node, 'source_layer': 'ew',
                        'target_node':  s_node, 'target_layer': 'sensor',
                        'relation':     'degrades', 'weight': 0.7,
                    })

    def _connect_same_entity_cross_layer(self):
        """同一平台出现在多层时，建立自我跨层连接"""
        all_nodes: set = set()
        for layer in self.layers.values():
            all_nodes.update(layer.nodes())

        for node in all_nodes:
            node_layers = [ln for ln, lnet in self.layers.items()
                           if node in lnet.nodes()]
            for i in range(len(node_layers)):
                for j in range(i + 1, len(node_layers)):
                    self.cross_layer_edges.append({
                        'source_node':  node, 'source_layer': node_layers[i],
                        'target_node':  node, 'target_layer': node_layers[j],
                        'relation':     'same_entity', 'weight': 1.0,
                    })

    # ─────────────────────────────────────────────────────────────────
    # 辅助方法
    # ─────────────────────────────────────────────────────────────────

    def _belong_to_same_system(self, node1: str, node2: str) -> bool:
        """判断两个节点是否属于同一作战系统（数字前缀相同）"""
        n1, n2 = str(node1).lower(), str(node2).lower()
        # 相同数字前缀（如 100_xxx 和 100_yyy）
        p1 = n1.split('_')[0]
        p2 = n2.split('_')[0]
        if p1.isdigit() and p1 == p2:
            return True
        # 关键词匹配
        for kw in ('iads', 'sam', 'ship', 'fleet'):
            if kw in n1 and kw in n2:
                return True
        return False

    def _is_adversarial(self, node1: str, node2: str) -> bool:
        t1 = self._classify_node(node1)
        t2 = self._classify_node(node2)
        adversarial = {'ew'}
        friendly    = {'sensor', 'command', 'weapon'}
        return (t1 in adversarial and t2 in friendly) or \
               (t1 in friendly    and t2 in adversarial)

    def _classify_node(self, node: str) -> str:
        """
        节点层分类（优先级从高到低）：weapon > ew > command > sensor > unknown

        支持中英文平台名称关键词匹配。
        导弹/鱼雷/弹药/发射架 → weapon；
        干扰机/SOJ/电子战（非雷达） → ew；
        营级指挥/舰艇/无人机/UCAV/IADS指挥 → command；
        雷达/传感器/声呐/侦察/目标/TTR/ACQ → sensor。

        特殊规则：
          - sam_ttr / acq_radar / ew_radar / radar_company → sensor（探测设备）
          - sam_battalion / sam_cmdr / iads_cmdr → command（指挥单元）
          - sam_launcher / _sam_N（弹药后缀） → weapon（发射/弹药）
          - target → sensor（被探测目标，归入探测层）
          - soj / _soj → ew（压制干扰机）
        """
        n  = str(node)       # 保留原始大小写（中文匹配不受影响）
        nl = n.lower()       # 英文关键词用小写匹配

        import re

        # ══════════════════════════════════════════════════════════════════════
        # 第一优先级：精确子串规则（防止泛关键词误伤）
        # ══════════════════════════════════════════════════════════════════════

        # ── sensor：探测/侦察类（优先于 weapon/command）──────────────────────
        # 侦察无人机、侦察UAV、侦察机 → sensor
        sensor_priority_cn = ['侦察无人机', '侦察UAV', '侦察机', '侦察舰', '侦察艇']
        if any(kw in n for kw in sensor_priority_cn):
            return 'sensor'
        # 英文精确探测组件
        if any(kw in nl for kw in ['_ttr', 'acq_radar', 'ew_radar', 'radar_company',
                                    '_acq', 'acq_']):
            return 'sensor'

        # ── command：营级指挥单元（优先于 weapon）────────────────────────────
        if any(kw in nl for kw in ['_battalion', '_cmdr', 'iads_cmdr', 'sam_cmdr']):
            return 'command'

        # ── sensor：target 节点（被探测目标）────────────────────────────────
        if nl.endswith('_target') or nl == 'target':
            return 'sensor'

        # ══════════════════════════════════════════════════════════════════════
        # 第二优先级：weapon 层
        # 导弹/鱼雷/弹药/发射架/攻击型无人平台
        # ══════════════════════════════════════════════════════════════════════
        weapon_cn = [
            '导弹', '鱼雷', '火箭弹', '炸弹', '射弹',
            # 攻击型无人平台
            '无人作战艇', '自杀型无人艇', '自杀无人艇',
            '察打型', '察打Ⅰ', '察打Ⅱ', '察打一', '察打二',  # 察打型UUV（精确匹配，排除纯侦察）
            '攻击型无人',
        ]
        weapon_en = ['missile', 'torpedo', 'rocket', 'bomb',
                     'launcher', 'weapon', 'munition', 'suicide']
        if any(kw in n for kw in weapon_cn):
            return 'weapon'
        if any(kw in nl for kw in weapon_en):
            return 'weapon'
        # _sam_N 后缀（弹药实例，如 3330_large_sam_launcher_sam_1）
        if re.search(r'_sam_\d+$', nl):
            return 'weapon'

        # ══════════════════════════════════════════════════════════════════════
        # 第三优先级：ew 层（干扰/压制，非雷达）
        # ══════════════════════════════════════════════════════════════════════
        ew_cn = ['干扰机', '干扰舰', '压制机', '电子战', '干扰无人机']
        ew_en = ['jammer', 'jamming', 'ecm', 'ew_', '_soj', 'soj_']
        if any(kw in n for kw in ew_cn):
            return 'ew'
        if any(kw in nl for kw in ew_en):
            return 'ew'
        if nl.endswith('soj') or nl == 'soj':
            return 'ew'
        # ew 单独出现且不含 radar（避免 ew_radar 误判）
        if 'ew' in nl and 'radar' not in nl and 'new' not in nl:
            return 'ew'

        # ══════════════════════════════════════════════════════════════════════
        # 第四优先级：command 层
        # 舰艇/潜艇/母艇/无人机（非侦察/非攻击）/UCAV/IADS/指挥
        # ══════════════════════════════════════════════════════════════════════
        command_cn = [
            # 有人水面舰艇
            '驱逐舰', '护卫舰', '巡洋舰', '航母', '航空母舰',
            '两栖攻击舰', '登陆舰', '综合登陆舰', '补给舰', '指挥舰',
            # 潜艇
            '潜艇', '核潜艇', '潜水器',
            # 无人平台（通用，非攻击/侦察）
            '无人机', '无人艇', '无人船', '无人潜航器', '母艇',
            # 其他
            '指挥', '飞机', '直升机', '运输机', '预警机',
            'UUV', 'UAV',
            # 通用舰艇后缀
            '舰', '艇', '船',
        ]
        command_en = ['ship', 'vessel', 'submarine', 'boat', 'frigate',
                      'destroyer', 'cruiser', 'carrier', 'corvette',
                      'aircraft', 'plane', 'heli', 'uav', 'ucav',
                      'command', 'c2', 'c4i', 'iads', 'cmdr']
        if any(kw in n for kw in command_cn):
            return 'command'
        if any(kw in nl for kw in command_en):
            return 'command'

        # ══════════════════════════════════════════════════════════════════════
        # 第五优先级：sensor 层（雷达/传感器/声呐/SAM探测组件）
        # ══════════════════════════════════════════════════════════════════════
        sensor_cn = ['雷达', '传感器', '声呐', '探测器', '预警雷达', '火控雷达']
        sensor_en = ['radar', 'sensor', 'sonar', 'acq', 'esm',
                     'lidar', 'irst', 'optic', 'sam']
        if any(kw in n for kw in sensor_cn):
            return 'sensor'
        if any(kw in nl for kw in sensor_en):
            return 'sensor'

        return 'unknown'

    # ─────────────────────────────────────────────────────────────────
    # 指标计算
    # ─────────────────────────────────────────────────────────────────

    def _calculate_hyper_metrics(self) -> Dict[str, float]:
        total_possible = self._calculate_possible_cross_edges()
        return {
            'cross_layer_density': (
                len(self.cross_layer_edges) / total_possible
                if total_possible > 0 else 0.0
            ),
            'layer_coupling_strength':    self._calculate_coupling_strength(),
            'cross_layer_connectivity':   self._calculate_cross_layer_connectivity(),
        }

    def _calculate_possible_cross_edges(self) -> int:
        names = list(self.layers.keys())
        total = 0
        for i in range(len(names)):
            for j in range(len(names)):
                if i != j:
                    total += (len(self.layers[names[i]].nodes()) *
                              len(self.layers[names[j]].nodes()))
        return total

    def _calculate_coupling_strength(self) -> float:
        if not self.cross_layer_edges:
            return 0.0
        return (sum(e['weight'] for e in self.cross_layer_edges)
                / len(self.cross_layer_edges))

    def _calculate_cross_layer_connectivity(self) -> float:
        cross_nodes: set = set()
        for edge in self.cross_layer_edges:
            cross_nodes.add((edge['source_node'], edge['source_layer']))
            cross_nodes.add((edge['target_node'], edge['target_layer']))
        total = sum(len(l.nodes()) for l in self.layers.values())
        return len(cross_nodes) / total if total > 0 else 0.0
