# 超网分析系统

基于仿真数据的多层超网可视化平台。导入仿真 CSV 目录后自动完成超网构建、Shapley 重心分析、级联失效模拟、3D 动画帧渲染，结果实时展示在 Web 界面。

---

## 目录结构

```
HZ/
├── start.sh                   # 一键启动脚本（推荐）
├── server.py                  # Python 分析后端（端口 5001）
├── data_processor.py
├── hyper/                     # 超网构建 / 分析 / 可视化模块
│   ├── hyper_network_builder.py
│   ├── hyper_network_analyzer.py
│   └── hyper_network_visualizer.py
└── hyper-viz/                 # Vue3 前端
    ├── src/App.vue            # 主界面
    ├── vite.config.js         # 开发服务器配置（端口 5173）
    └── public/                # 分析产物输出目录（运行时自动写入）
```

---

## 环境要求

| 依赖 | 版本要求 |
|------|----------|
| Python | 3.8+ |
| Node.js | 18+ |
| ffmpeg | 任意版本（可选，用于合成 MP4） |

Python 依赖包：

```bash
pip3 install networkx pandas numpy matplotlib Pillow
```

---

## 安装与启动

### 方式一：一键启动（推荐）

```bash
cd HZ
bash start.sh
```

脚本会自动：
1. 检查 Python / Node.js 环境
2. 安装缺失的前端依赖（`npm install`）
3. 检查并安装缺失的 Python 依赖
4. 后台启动 Python 分析后端（端口 5001）
5. 后台启动 Vue 前端开发服务器（端口 5173）
6. 打印本机和局域网访问地址

启动成功后终端会显示：

```
✅ 服务已启动！

  本机访问:   http://localhost:5173
  局域网访问: http://192.168.x.x:5173
  后端接口:   http://192.168.x.x:5001

按 Ctrl+C 停止所有服务
```

---

### 方式二：手动启动（两个终端）

**终端 1 — 启动 Python 后端：**

```bash
cd HZ
python3 server.py
```

**终端 2 — 启动 Vue 前端：**

```bash
cd HZ/hyper-viz

# 首次运行先安装依赖
npm install

# 启动开发服务器
npm run dev
```

两个服务都启动后，浏览器访问 `http://localhost:5173`。

---

## 使用流程

1. 浏览器打开 `http://localhost:5173`，看到欢迎引导页
2. 点击 **选择数据目录开始分析**，选择包含仿真 CSV 文件的目录
3. 等待分析完成（进度覆盖层显示实时进度，约 2～5 分钟）
4. 分析完成后，各 Tab 自动展示结果：
   - **⬡ 超网复盘** — 3D 旋转动画播放
   - **🎞 帧浏览器** — 逐帧浏览时间窗口快照
   - **📄 分析报告** — Markdown 报告渲染
   - **🕸 复杂网络** — 综合复杂网络图（支持缩放 + 拖拽）
   - **⚙ 参数配置** — 调整分析参数，下次导入时生效
5. 需要重新分析时，点击顶部 **↺ 重新导入** 按钮

---

## 常见问题

**Q: 浏览器显示"ERR_CONNECTION_REFUSED"**  
A: Vue 前端未启动。执行 `cd hyper-viz && npm run dev`。

**Q: 导入后提示"无法连接到分析服务"**  
A: Python 后端未启动。执行 `python3 server.py`。

**Q: 分析完成但视频无法播放**  
A: 系统未安装 ffmpeg，MP4 合成被跳过。安装：`brew install ffmpeg`，然后重新导入。

**Q: 手机/平板无法访问**  
A: 确保与电脑在同一 WiFi，使用局域网 IP 访问（`start.sh` 启动时会打印该地址）。手动查询 IP：`ipconfig getifaddr en0`。
