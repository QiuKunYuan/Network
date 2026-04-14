# data_processor.py
# -*- coding: utf-8 -*-
"""
SimDataProcessor — 多 CSV 仿真数据处理器
==========================================
输入：一个目录，目录下包含若干 CSV 文件，文件名对应消息类型：
    BaseEntity.csv          ← YD_BaseEntity          平台信息（主节点表）
    Communication.csv       ← JSAF_Communication     通信事件
    DetectEvent.csv         ← JSAF_DetectEvent        探测事件
    WeaponFire.csv          ← JSAF_WeaponFire         武器开火
    MunitionDetonation.csv  ← JSAF_MunitionDetonation 武器爆炸/命中
    EquipDamage.csv         ← JSAF_EquipDamage        平台毁伤
    JamingEvent.csv         ← JSAF_JamingEvent        电子干扰
    ExtTrackMessage.csv     ← JSAF_ExtTrackMessage    融合态势
    PlatWeaponSurplus.csv   ← JSAF_PlatWeaponSurplus  武器余量
    PlatSensorState.csv     ← JSAF_PlatSensorState    传感器状态
    AircraftLaunchEvent.csv ← JSAF_AircraftLaunchEvent 起飞事件
    AircraftLandEvent.csv   ← 降落事件（字段同起飞）
    DetectNums.csv          ← DetectNums              传感器处理数量
    BattleFieldTime.csv     ← JSAF_BattleFieldTime    作战时间
    AttackOrder.csv         ← JSAF_AttackOrder        打击指令

设计原则：
  - 每个 CSV 都是可选的，缺失时静默跳过，不影响其他数据
  - 所有公开方法与旧 AFSIMDataProcessor 接口保持兼容
  - 时间字段统一为 `time`（秒，float），来源优先 BattleFieldTime，
    其次各表的 dwTime/time 字段
"""

import os
import glob
import pandas as pd
import numpy as np
from typing import Dict, List, Tuple, Any, Optional


# ── 每个 CSV 文件的"时间列"候选名（按优先级） ──────────────────────────────
_TIME_CANDIDATES = ['time', 'dwTime', 'dfTime', 'dwDate']

# ── 每个 CSV 文件名（不含扩展名）→ 对应结构体的关键字段 ──────────────────────
# 格式：{ csv_stem: { 逻辑名: [候选列名, ...] } }
_CSV_SCHEMA: Dict[str, Dict[str, List[str]]] = {
    'BaseEntity': {
        'time':      ['dwTime', 'time'],
        'name':      ['platName'],
        'alliance':  ['alliance'],
        'entity_type': ['entityType', 'cSimType'],
        'lon':       ['longtitude', 'longitude', 'lon'],
        'lat':       ['latitude', 'lat'],
        'alt':       ['altitude', 'alt'],
        'speed':     ['speed'],
        'life':      ['wLife'],
    },
    'Communication': {
        'time':      ['time', 'dwTime'],
        'sender':    ['platName_S', 'sendName'],
        'sender_id': ['glideNum_S', 'senderId_glideNum', 'senderId'],
        'receiver':  ['platName_R', 'receiveName'],
        'recv_id':   ['glideNum_R', 'receiverId_glideNum', 'receiverId'],
        'content':   ['content'],
    },
    'DetectEvent': {
        'time':      ['time', 'dwTime'],
        'sensor_name':  ['cSensorname'],
        'sensor_owner': ['Processor', 'platNameEntity'],   # 探测主体（平台名或 glideNum）
        'sensor_owner_id': ['glideNumEntity'],             # 探测主体 glideNum（备用）
        'target_name':  ['cTargetname', 'platNameTarget'], # 目标名或 glideNum
        'target_id':    ['glideNumTarget'],                # 目标 glideNum（备用）
        'sensor_type':  ['cSensorType', 'iSensorType'],
        'lon':       ['dfLon'],
        'lat':       ['dfLat'],
        'classification': ['classification'],
        'event_type':    ['cEventType'],
    },
    'WeaponFire': {
        'time':      ['dwTime', 'time'],
        'shooter':   ['platNameEntity', 'strEntityID_glideNum', 'strEntityID'],
        'shooter_id': ['glideNumEntity'],
        'weapon_id': ['glideNumWeapon', 'strWeaponID_glideNum', 'strWeaponID'],
        'target':    ['platNameTarget', 'strTargetID_glideNum', 'strTargetID'],
        'target_id': ['glideNumTarget'],
        'weapon_name': ['platNameWeapon', 'weaponName'],
        'device_type': ['wDeviceType'],
        'fire_status': ['wFireStatus'],
    },
    'MunitionDetonation': {
        'time':      ['dwTime', 'time'],
        'shooter':   ['platNameEntity', 'strEntityID_glideNum', 'strEntityID'],
        'shooter_id': ['glideNumEntity'],
        'weapon_id': ['glideNumWeapon', 'strWeaponID_glideNum', 'strWeaponID'],
        'target':    ['platNameTarget', 'strTargetID_glideNum', 'strTargetID'],
        'target_id': ['glideNumTarget'],
        'hit_result': ['wHitResult'],
        'lon':       ['dfLon'],
        'lat':       ['dfLat'],
    },
    'EquipDamage': {
        'time':      ['dwTime', 'time'],
        'platform':  ['platNameEntity', 'dwPlatID_glideNum', 'dwPlatID'],
        'platform_id': ['glideNumEntity'],
        'weapon':    ['dwWeaponID_glideNum', 'dwWeaponID'],
        'ship_life': ['cShipLife'],
        'part':      ['cPart'],
    },
    'JamingEvent': {
        'time':      ['time', 'dwTime'],
        'attacker':  ['attackName'],
        'target':    ['targetName'],
        'system':    ['systemName'],
        'jam_type':  ['iJamType'],
        'jam_flag':  ['iFlag'],
    },
    'ExtTrackMessage': {
        'time':      ['time', 'dwTime'],
        'platform':  ['platId_glideNum', 'platId'],
        'num':       ['num'],
    },
    'PlatWeaponSurplus': {
        'time':      ['time', 'dwTime'],
        'platform':  ['platId_glideNum', 'platId'],
        'weapon_count': ['weaponCount'],
    },
    'PlatSensorState': {
        'time':      ['time', 'dwTime'],
        'platform':  ['platId_glideNum', 'platId'],
        'sensor_type': ['type'],
        'sensor_count': ['sensorCount'],
    },
    'AircraftLaunchEvent': {
        'time':      ['time', 'dwTime'],
        'carrier':   ['aircraftPlatName', 'platNameEntity'],
        'carrier_id': ['glideNumEntity'],
        'aircraft':  ['aircraftName', 'platNameWeapon'],
        'aircraft_id': ['glideNumWeapon'],
    },
    'AircraftLandEvent': {
        'time':      ['time', 'dwTime'],
        'carrier':   ['aircraftBackPlatName', 'aircraftPlatName', 'platNameEntity'],
        'carrier_id': ['glideNumEntity'],
        'aircraft':  ['aircraftName', 'platNameWeapon'],
        'aircraft_id': ['glideNumWeapon'],
    },
    'DetectNums': {
        'time':      ['time', 'dwTime'],
        'platform':  ['strEntity_glideNum', 'strEntity'],
        'sensor_name': ['cSensorname'],
        'target_num':  ['targetnum'],
    },
    'BattleFieldTime': {
        'time':      ['time'],
    },
    'AttackOrder': {
        'time':      ['dwTime', 'time'],
        'shooter':   ['platNameEntity', 'strEntityID_glideNum', 'strEntityID'],
        'shooter_id': ['glideNumEntity'],
        'target':    ['platNameTarget', 'strTargetID_glideNum', 'strTargetID'],
        'target_id': ['glideNumTarget'],
        'device_type': ['wDeviceType'],
    },
}

# ── 实体 ID 字段的展开列名（结构体嵌套展开后的常见格式） ─────────────────────
# 仿真导出 CSV 时，YD_EntityIdentifierStruct 通常展开为：
#   platName_nodeId / platName_appNum / platName_glideNum
# 或直接用 glideNum 作为唯一标识
_ID_SUFFIXES = ['_glideNum', '_nodeId', '_appNum', '']


def _detect_encoding(path: str) -> str:
    """自动检测文件编码"""
    for enc in ['utf-8', 'gb18030', 'gbk', 'gb2312', 'latin1']:
        try:
            with open(path, 'r', encoding=enc) as f:
                f.read(4096)
            return enc
        except (UnicodeDecodeError, Exception):
            continue
    return 'utf-8'


def _load_csv(path: str) -> Optional[pd.DataFrame]:
    """安全加载单个 CSV，失败返回 None"""
    enc = _detect_encoding(path)
    for e in [enc, 'utf-8', 'gb18030', 'gbk', 'latin1']:
        try:
            df = pd.read_csv(path, encoding=e, low_memory=False)
            df.columns = [c.strip() for c in df.columns]
            return df
        except Exception:
            continue
    print(f"  ⚠️  无法读取 {os.path.basename(path)}，跳过")
    return None


def _find_col(df: pd.DataFrame, candidates: List[str]) -> Optional[str]:
    """从候选列名列表中找到第一个存在的列"""
    for c in candidates:
        if c in df.columns:
            return c
    return None


def _normalize_time(df: pd.DataFrame, time_col: str) -> pd.DataFrame:
    """将时间列转为 float，丢弃无效行"""
    df = df.copy()
    df[time_col] = pd.to_numeric(df[time_col], errors='coerce')
    before = len(df)
    df = df.dropna(subset=[time_col])
    dropped = before - len(df)
    if dropped > 0:
        print(f"    时间列转换丢弃 {dropped} 行")
    return df


class SimDataProcessor:
    """
    多 CSV 仿真数据处理器。

    用法：
        processor = SimDataProcessor('/path/to/csv_dir')
        # 之后接口与旧 AFSIMDataProcessor 完全兼容
    """

    def __init__(self, csv_dir: str):
        self.csv_dir = csv_dir
        # 已加载的 DataFrame，key = CSV stem（如 'BaseEntity'）
        self.tables: Dict[str, pd.DataFrame] = {}
        # 每张表的列名映射缓存，key = stem → {逻辑名: 实际列名 or None}
        self._cols: Dict[str, Dict[str, Optional[str]]] = {}

        self._load_all()
        self._build_col_cache()
        self._print_summary()

        # ── 兼容旧接口：暴露一个"主 df"供 server.py 直接访问 ──────────
        # 以 BaseEntity 为主表；若不存在则合并所有表的时间列构造最小 df
        self.df = self._build_compat_df()
        self._col = self._build_compat_col()

        # ── glideNum → platName 映射表（用于 ID 反查平台名）──────────
        self._id_to_name: Dict[int, str] = self._build_id_map()

    # ─────────────────────────────────────────────────────────────────
    # 加载
    # ─────────────────────────────────────────────────────────────────

    def _load_all(self):
        """扫描目录，加载所有已知 CSV"""
        if not os.path.isdir(self.csv_dir):
            # 兼容旧版：如果传入的是单个文件路径，当作目录的父目录
            if os.path.isfile(self.csv_dir):
                self.csv_dir = os.path.dirname(self.csv_dir)
            else:
                raise FileNotFoundError(f"目录不存在: {self.csv_dir}")

        found = []
        for stem in _CSV_SCHEMA:
            path = os.path.join(self.csv_dir, f'{stem}.csv')
            if os.path.exists(path):
                df = _load_csv(path)
                if df is not None and not df.empty:
                    self.tables[stem] = df
                    found.append(f'{stem}({len(df)}行)')
            else:
                # 大小写不敏感兜底
                matches = glob.glob(os.path.join(self.csv_dir, f'{stem}.csv'),
                                    recursive=False)
                if not matches:
                    matches = [p for p in glob.glob(os.path.join(self.csv_dir, '*.csv'))
                               if os.path.splitext(os.path.basename(p))[0].lower() == stem.lower()]
                if matches:
                    df = _load_csv(matches[0])
                    if df is not None and not df.empty:
                        self.tables[stem] = df
                        found.append(f'{stem}({len(df)}行)')

        print(f"[SimDataProcessor] 加载 {len(self.tables)}/{len(_CSV_SCHEMA)} 个 CSV：")
        for item in found:
            print(f"  ✓ {item}")
        missing = [s for s in _CSV_SCHEMA if s not in self.tables]
        if missing:
            print(f"  ○ 缺失（跳过）: {', '.join(missing)}")

    def _build_col_cache(self):
        """为每张表建立逻辑名→实际列名的缓存"""
        for stem, schema in _CSV_SCHEMA.items():
            if stem not in self.tables:
                self._cols[stem] = {k: None for k in schema}
                continue
            df = self.tables[stem]
            self._cols[stem] = {
                k: _find_col(df, candidates)
                for k, candidates in schema.items()
            }

    def _build_id_map(self) -> Dict[int, str]:
        """
        从 BaseEntity 构建 glideNum → platName 映射。
        glideNum 是每个平台实体的唯一数字 ID，各关系表用它引用平台。
        """
        id_map: Dict[int, str] = {}
        df_be = self.tables.get('BaseEntity')
        if df_be is None:
            return id_map
        name_col  = self._cols['BaseEntity'].get('name')   # platName
        gnum_col  = _find_col(df_be, ['glideNum'])
        if not name_col or not gnum_col:
            return id_map
        for _, row in df_be.drop_duplicates(subset=[gnum_col]).iterrows():
            gnum = row.get(gnum_col)
            name = row.get(name_col)
            if pd.notna(gnum) and pd.notna(name) and str(name).strip():
                try:
                    id_map[int(gnum)] = str(name).strip()
                except (ValueError, TypeError):
                    pass
        print(f"  glideNum→platName 映射: {len(id_map)} 条")
        return id_map

    def _resolve_name(self, name_val, id_val=None) -> str:
        """
        优先用 name_val（平台名字符串），若为空则用 id_val（glideNum）查映射表。
        返回空串表示无效。
        """
        # 先尝试直接名称
        if name_val is not None:
            try:
                if not pd.isna(name_val):
                    s = str(name_val).strip()
                    if s:
                        return s
            except (TypeError, ValueError):
                s = str(name_val).strip()
                if s:
                    return s
        # 再尝试 ID 反查
        if id_val is not None:
            try:
                if not pd.isna(id_val):
                    gnum = int(id_val)
                    if gnum in self._id_to_name:
                        return self._id_to_name[gnum]
            except (TypeError, ValueError):
                pass
        return ''

    def _print_summary(self):
        """打印各表时间范围"""
        for stem, df in self.tables.items():
            t_col = self._cols[stem].get('time')
            if t_col and t_col in df.columns:
                df2 = _normalize_time(df, t_col)
                if not df2.empty:
                    print(f"  {stem}: 时间 {df2[t_col].min():.1f}~{df2[t_col].max():.1f}s")

    # ─────────────────────────────────────────────────────────────────
    # 兼容旧接口：构造 self.df / self._col
    # ─────────────────────────────────────────────────────────────────

    def _build_compat_df(self) -> pd.DataFrame:
        """
        构造兼容旧接口的主 DataFrame。
        以 BaseEntity 为主；若无则返回空 DataFrame。
        """
        if 'BaseEntity' in self.tables:
            return self.tables['BaseEntity'].copy()
        # 兜底：返回空 df，避免 server.py 崩溃
        return pd.DataFrame(columns=['time', 'platName', 'alliance'])

    def _build_compat_col(self) -> Dict[str, Optional[str]]:
        """构造兼容旧接口的 _col 字典"""
        be = self._cols.get('BaseEntity', {})
        return {
            'time':       be.get('time'),
            'platform':   be.get('name'),       # platName
            'interactor': None,
            'component':  None,
            'track_id':   None,
            'col8':       None,
            'type':       None,
        }

    # ─────────────────────────────────────────────────────────────────
    # 公开接口（与旧 AFSIMDataProcessor 兼容）
    # ─────────────────────────────────────────────────────────────────

    def get_data_info(self) -> Dict[str, Any]:
        """返回数据概况，供 server.py 展示"""
        total_rows = sum(len(df) for df in self.tables.values())
        platforms = self._get_all_platform_names()

        # 统计各表行数作为"消息类型分布"
        msg_types = {stem: len(df) for stem, df in self.tables.items()}

        return {
            'total_rows':     total_rows,
            'total_columns':  sum(len(df.columns) for df in self.tables.values()),
            'column_names':   list(self.tables.keys()),   # 用表名代替列名
            'message_types':  msg_types,
            'platforms_count': len(platforms),
            'tables_loaded':  list(self.tables.keys()),
        }

    def get_all_platforms(self) -> List[str]:
        """获取所有平台名称（去重）"""
        return self._get_all_platform_names()

    def get_time_range(self) -> Tuple[float, float]:
        """返回全局时间范围 (t_min, t_max)"""
        t_min, t_max = float('inf'), float('-inf')
        for stem, df in self.tables.items():
            t_col = self._cols[stem].get('time')
            if not t_col or t_col not in df.columns:
                continue
            df2 = _normalize_time(df, t_col)
            if df2.empty:
                continue
            t_min = min(t_min, float(df2[t_col].min()))
            t_max = max(t_max, float(df2[t_col].max()))
        if t_min == float('inf'):
            return 0.0, 0.0
        return t_min, t_max

    def get_time_windows(self, window_size: float = 120.0,
                         step: float = 60.0) -> List[Tuple[float, float, 'SimDataProcessor']]:
        """
        按时间窗口切分，返回 (t_start, t_end, sub_processor) 列表。
        sub_processor 是一个轻量快照对象，接口与 self 相同。
        """
        t_min, t_max = self.get_time_range()
        if t_min >= t_max:
            return []

        windows = []
        for start in np.arange(t_min, t_max, step):
            end = start + window_size
            sub = self._slice(start, end)
            if sub is not None:
                windows.append((start, end, sub))

        print(f"共生成 {len(windows)} 个时间窗口（窗口={window_size}s，步长={step}s）")
        return windows

    # ─────────────────────────────────────────────────────────────────
    # 关系提取（供 hyper_network_builder 调用）
    # ─────────────────────────────────────────────────────────────────

    def extract_communication_links(self) -> List[Tuple[str, str, float]]:
        """
        通信边：Communication.csv → sender → receiver
        名称字段为空时用 glideNum 反查 platName
        """
        links = []
        df = self.tables.get('Communication')
        if df is None:
            return links
        c = self._cols['Communication']
        s_col  = c.get('sender')
        s_id   = c.get('sender_id')
        r_col  = c.get('receiver')
        r_id   = c.get('recv_id')
        for _, row in df.iterrows():
            s = self._resolve_name(
                row.get(s_col) if s_col else None,
                row.get(s_id)  if s_id  else None)
            r = self._resolve_name(
                row.get(r_col) if r_col else None,
                row.get(r_id)  if r_id  else None)
            if s and r and s != r:
                links.append((s, r, 1.0))
        print(f"  通信链路: {len(links)} 条")
        return links

    def extract_sensor_detections(self) -> List[Tuple[str, str, float]]:
        """
        探测边：DetectEvent.csv → 探测主体 → 目标
        名称字段为空时用 glideNum 反查 platName
        """
        detections = []
        df = self.tables.get('DetectEvent')
        if df is None:
            return detections
        c = self._cols['DetectEvent']
        owner_col = c.get('sensor_owner')
        owner_id  = c.get('sensor_owner_id')
        tgt_col   = c.get('target_name')
        tgt_id    = c.get('target_id')
        for _, row in df.iterrows():
            src = self._resolve_name(
                row.get(owner_col) if owner_col else None,
                row.get(owner_id)  if owner_id  else None)
            tgt = self._resolve_name(
                row.get(tgt_col) if tgt_col else None,
                row.get(tgt_id)  if tgt_id  else None)
            if src and tgt and src != tgt:
                detections.append((src, tgt, 1.0))
        print(f"  探测关系: {len(detections)} 条")
        return detections

    def extract_weapon_engagements(self) -> List[Tuple[str, str, float]]:
        """
        武器打击边：WeaponFire.csv → 发射平台 → 目标
        命中结果来自 MunitionDetonation.csv（wHitResult=1 表示命中，权重加成）
        """
        engagements = []

        # 主来源：WeaponFire
        df_fire = self.tables.get('WeaponFire')
        if df_fire is not None:
            c = self._cols['WeaponFire']
            for _, row in df_fire.iterrows():
                src = self._resolve_name(
                    row.get(c['shooter'])    if c.get('shooter')    else None,
                    row.get(c['shooter_id']) if c.get('shooter_id') else None)
                tgt = self._resolve_name(
                    row.get(c['target'])    if c.get('target')    else None,
                    row.get(c['target_id']) if c.get('target_id') else None)
                if src and tgt and src != tgt:
                    engagements.append((src, tgt, 1.0))

        # 补充来源：MunitionDetonation（命中的才加边，权重 1.5）
        df_det = self.tables.get('MunitionDetonation')
        if df_det is not None:
            c = self._cols['MunitionDetonation']
            hit_col = c.get('hit_result')
            for _, row in df_det.iterrows():
                src = self._resolve_name(
                    row.get(c['shooter'])    if c.get('shooter')    else None,
                    row.get(c['shooter_id']) if c.get('shooter_id') else None)
                tgt = self._resolve_name(
                    row.get(c['target'])    if c.get('target')    else None,
                    row.get(c['target_id']) if c.get('target_id') else None)
                hit = int(row.get(hit_col, 0)) if hit_col else 0
                if src and tgt and src != tgt:
                    w = 1.5 if hit == 1 else 0.8
                    engagements.append((src, tgt, w))

        # 补充来源：AttackOrder（打击指令）
        df_atk = self.tables.get('AttackOrder')
        if df_atk is not None:
            c = self._cols['AttackOrder']
            for _, row in df_atk.iterrows():
                src = self._resolve_name(
                    row.get(c['shooter'])    if c.get('shooter')    else None,
                    row.get(c['shooter_id']) if c.get('shooter_id') else None)
                tgt = self._resolve_name(
                    row.get(c['target'])    if c.get('target')    else None,
                    row.get(c['target_id']) if c.get('target_id') else None)
                if src and tgt and src != tgt:
                    engagements.append((src, tgt, 0.9))

        print(f"  武器打击关系: {len(engagements)} 条")
        return engagements

    def extract_jamming_relations(self) -> List[Tuple[str, str, float]]:
        """
        电子战边：JamingEvent.csv → attackName → targetName
        """
        jammings = []
        df = self.tables.get('JamingEvent')
        if df is None:
            return jammings
        c = self._cols['JamingEvent']
        atk_col = c.get('attacker')
        tgt_col = c.get('target')
        for _, row in df.iterrows():
            src = self._resolve_name(
                row.get(atk_col) if atk_col else None, None)
            tgt = self._resolve_name(
                row.get(tgt_col) if tgt_col else None, None)
            if src and tgt and src != tgt:
                jammings.append((src, tgt, 0.9))
        print(f"  干扰关系: {len(jammings)} 条")
        return jammings

    def extract_platform_hierarchy(self) -> Dict[str, str]:
        """
        指挥层级：从 Communication.csv 推断（发送方→接收方 中的指挥关系）
        以及从 AircraftLaunchEvent.csv 推断（载机→飞机）
        返回 {下级: 上级}
        """
        hierarchy = {}

        # 从起飞事件推断：载机 → 飞机（载机是上级）
        df_launch = self.tables.get('AircraftLaunchEvent')
        if df_launch is not None:
            c = self._cols['AircraftLaunchEvent']
            for _, row in df_launch.iterrows():
                carrier = self._resolve_name(
                    row.get(c['carrier'])    if c.get('carrier')    else None,
                    row.get(c['carrier_id']) if c.get('carrier_id') else None)
                aircraft = self._resolve_name(
                    row.get(c['aircraft'])    if c.get('aircraft')    else None,
                    row.get(c['aircraft_id']) if c.get('aircraft_id') else None)
                if carrier and aircraft and carrier != aircraft:
                    hierarchy[aircraft] = carrier   # 飞机的上级是载机

        print(f"  层级关系: {len(hierarchy)} 条")
        return hierarchy

    def extract_fusion_tracks(self) -> List[Tuple[str, int]]:
        """
        融合态势：ExtTrackMessage.csv → (平台名, 融合数量)
        """
        tracks = []
        df = self.tables.get('ExtTrackMessage')
        if df is None:
            return tracks
        c = self._cols['ExtTrackMessage']
        plat_col = c.get('platform')
        num_col  = c.get('num')
        if not plat_col:
            return tracks
        for _, row in df.iterrows():
            plat = _safe_str(row.get(plat_col))
            num  = int(row.get(num_col, 1)) if num_col else 1
            if plat:
                tracks.append((plat, num))
        return tracks

    def get_damage_info(self) -> Dict[str, float]:
        """
        毁伤信息：EquipDamage.csv → {平台名: 生命值}
        生命值越低说明毁伤越重
        """
        damage = {}
        df = self.tables.get('EquipDamage')
        if df is None:
            return damage
        c = self._cols['EquipDamage']
        plat_col = c.get('platform')
        life_col = c.get('ship_life')
        if not plat_col:
            return damage
        for _, row in df.iterrows():
            plat = _safe_str(row.get(plat_col))
            life = float(row.get(life_col, 100)) if life_col else 100.0
            if plat:
                # 取最低生命值（最严重毁伤）
                damage[plat] = min(damage.get(plat, 100.0), life)
        return damage

    # ─────────────────────────────────────────────────────────────────
    # 内部工具
    # ─────────────────────────────────────────────────────────────────

    def _get_all_platform_names(self) -> List[str]:
        """从 BaseEntity 获取所有平台名，兜底从其他表收集"""
        names = set()

        # 优先 BaseEntity.platName
        df_be = self.tables.get('BaseEntity')
        if df_be is not None:
            name_col = self._cols['BaseEntity'].get('name')
            if name_col:
                names.update(
                    str(v) for v in df_be[name_col].dropna().unique()
                    if str(v).strip()
                )

        # 兜底：从通信/探测/打击表收集
        for stem, src_tgt in [
            ('Communication',      ('sender', 'receiver')),
            ('DetectEvent',        ('sensor_owner', 'target_name')),
            ('WeaponFire',         ('shooter', 'target')),
            ('JamingEvent',        ('attacker', 'target')),
            ('AttackOrder',        ('shooter', 'target')),
        ]:
            df = self.tables.get(stem)
            if df is None:
                continue
            c = self._cols[stem]
            for role in src_tgt:
                col = c.get(role)
                if col and col in df.columns:
                    names.update(
                        str(v) for v in df[col].dropna().unique()
                        if str(v).strip()
                    )

        result = sorted(names)
        print(f"  平台总数: {len(result)}")
        return result

    def _slice(self, t_start: float, t_end: float) -> Optional['SimDataProcessor']:
        """
        返回一个时间切片的轻量 SimDataProcessor 快照。
        只切分有时间列的表，其余表保持原样（静态数据）。
        """
        snap = _SnapProcessor(self, t_start, t_end)
        # 如果切片后所有动态表都为空，返回 None
        dynamic_stems = ['Communication', 'DetectEvent', 'WeaponFire',
                         'MunitionDetonation', 'JamingEvent', 'AttackOrder',
                         'ExtTrackMessage']
        has_data = any(
            stem in snap.tables and not snap.tables[stem].empty
            for stem in dynamic_stems
        )
        # BaseEntity 是静态的，只要有节点就算有数据
        if not has_data and 'BaseEntity' in snap.tables:
            has_data = not snap.tables['BaseEntity'].empty
        return snap if has_data else None


class _SnapProcessor(SimDataProcessor):
    """
    时间切片快照，继承 SimDataProcessor 但不重新加载文件。
    由 SimDataProcessor._slice() 创建，外部不直接使用。
    """

    def __init__(self, parent: SimDataProcessor, t_start: float, t_end: float):
        # 不调用 super().__init__()，直接复用父对象的数据
        self.csv_dir     = parent.csv_dir
        self._cols       = parent._cols          # 列名缓存共享
        self._id_to_name = parent._id_to_name    # ID→名称映射共享
        self.tables      = {}

        # 静态表（无时间列）直接复用
        static_stems = {'BaseEntity', 'BattleFieldTime', 'ScenarioLoadStatus'}

        for stem, df in parent.tables.items():
            if stem in static_stems:
                self.tables[stem] = df
                continue
            t_col = parent._cols[stem].get('time')
            if not t_col or t_col not in df.columns:
                self.tables[stem] = df   # 无时间列，全量保留
                continue
            df2 = _normalize_time(df, t_col)
            mask = (df2[t_col] >= t_start) & (df2[t_col] < t_end)
            self.tables[stem] = df2[mask].reset_index(drop=True)

        # 兼容旧接口
        self.df   = self.tables.get('BaseEntity', pd.DataFrame())
        self._col = parent._col


# ─────────────────────────────────────────────────────────────────────
# 工具函数
# ─────────────────────────────────────────────────────────────────────

def _safe_str(val) -> str:
    """安全转字符串，NaN/None 返回空串。不再过滤数字（ID 反查由 _resolve_name 处理）"""
    if val is None:
        return ''
    try:
        if pd.isna(val):
            return ''
    except (TypeError, ValueError):
        pass
    return str(val).strip()


# ── 向后兼容：保留旧类名别名 ──────────────────────────────────────────
AFSIMDataProcessor = SimDataProcessor
