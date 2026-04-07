# AFSIM 超网分析系统

基于 AFSIM 仿真数据的多层超网可视化平台。上传 CSV 后自动完成超网构建、Shapley 重心分析、级联失效模拟、3D 动画帧渲染，结果实时展示在 Web 界面。

---

## 目录结构

```
HZ/
├── start.sh              # 一键启动脚本（推荐）
├── qky项目文件/           # Python 分析后端
│   ├── server.py         # HTTP 服务入口（端口 5001）
│   ├── data_processor.py
│   ├── hyper/            # 超网构建 / 分析 / 可视化
│   └── ...
└── hyper-viz/            # Vue3 前端
    ├── src/App.vue       # 主界面
    ├── vite.config.js    # 开发服务器配置（端口 5173）
    └── public/           # 分析产物输出目录（自动写入）
        ├── frames/       # 帧序列 PNG
        ├── hyper_network_animation.mp4
        ├── complex_network.png
        └── *.md          # 分析报告
```

---

## 环境要求

| 依赖 | 版本要求 |
|------|----------|
| Python | 3.8+ |
| Node.js | 18+ |
| ffmpeg | 任意版本（可选，用于合成 MP4） |

Python 依赖包：`networkx` `pandas` `numpy` `matplotlib` `Pillow`

---

## 启动方式

### 方式一：一键启动（推荐）

```bash
cd /Users/qky/Desktop/HZ
bash start.sh
```

脚本会自动完成以下操作：
1. 检查 Python / Node.js 环境
2. 自动安装缺失的前端依赖（`npm install`）
3. 检查并安装缺失的 Python 依赖
4. 后台启动 Python 分析后端（端口 5001）
5. 后台启动 Vue 前端开发服务器（端口 5173）
6. 打印本机和局域网访问地址

启动成功后终端会显示：

```
✅ 服务已启动！

  本机访问:   http://localhost:5173
  局域网访问: http://192.168.x.x:5173  ← 手机/平板用这个
  后端接口:   http://192.168.x.x:5001

按 Ctrl+C 停止所有服务
```

---

### 方式二：手动分两个终端启动

**终端 1 — 启动 Python 后端：**

```bash
cd /Users/qky/Desktop/HZ/qky项目文件
python3 server.py
# 或指定端口：python3 server.py --port 5001 --host 0.0.0.0
```

**终端 2 — 启动 Vue 前端：**

```bash
cd /Users/qky/Desktop/HZ/hyper-viz

# 首次运行需先安装依赖
npm install

# 启动开发服务器
npm run dev
```

两个服务都启动后，浏览器访问 `http://localhost:5173`。

---

## 使用流程

```
1. 打开浏览器访问 http://localhost:5173

2. 点击顶部 [⊕ 导入 CSV] 按钮
   → 选择 AFSIM 仿真输出的 CSV 文件

3. 等待分析完成（进度覆盖层显示实时进度，约 2~5 分钟）
   分析阶段依次为：
   加载数据 → 构建超网 → Shapley 分析 → 生成帧序列 → 合成 MP4 → 生成网络图 → 生成报告

4. 分析完成后，四个 Tab 自动刷新展示结果：
   ⬡ 超网动画   — 3D 旋转 MP4 视频播放
   🎞 帧浏览器  — 逐帧浏览时间窗口快照
   📄 分析报告  — Markdown 报告渲染（综合报告 + 级联失效报告）
   🕸 复杂网络  — 综合复杂网络图（支持滚轮缩放 + 拖拽平移）

5. 需要重新分析时，点击顶部 [↺ 重新导入] 按钮选择新 CSV
```

---

## 后端 API

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/upload` | 上传 CSV，触发异步分析 |
| GET  | `/api/status` | 查询当前分析状态与进度 |
| GET  | `/api/results` | 获取最新分析结果元数据 |
| POST | `/api/cancel` | 取消当前分析 |

前端通过 Vite proxy 将 `/api/*` 转发到 `http://127.0.0.1:5001`。

---

## 常见问题

**Q: 浏览器显示"ERR_CONNECTION_REFUSED"**
A: Vue 前端服务器未启动。执行 `cd hyper-viz && npm run dev`。

**Q: 上传 CSV 后提示"无法连接到分析服务"**
A: Python 后端未启动。执行 `cd qky项目文件 && python3 server.py`。

**Q: 分析完成但视频无法播放**
A: 系统未安装 ffmpeg，MP4 合成被跳过。安装方式：`brew install ffmpeg`，然后重新导入 CSV。

**Q: 手机/平板无法访问**
A: 确保手机与电脑连接同一 WiFi，使用局域网 IP 访问（`start.sh` 启动时会打印该地址）。也可手动查询：`ipconfig getifaddr en0`。
