<template>
  <div class="app">
    <!-- ── 顶部标题栏 ── -->
    <header class="header">
      <div class="header-left">
        <span class="logo">⬡</span>
        <div class="title-block">
          <h1>超网分析系统</h1>
        </div>
      </div>
      <div class="header-center">
        <!-- 隐藏的文件选择 input（目录模式） -->
        <input ref="fileInputDir" type="file" webkitdirectory multiple
               @change="onCsvImport" style="display:none"
               :disabled="analysisStatus === 'running'" />
        <!-- 隐藏的文件选择 input（多文件模式，Safari 兜底） -->
        <input ref="fileInputMulti" type="file" multiple accept=".csv"
               @change="onCsvImport" style="display:none"
               :disabled="analysisStatus === 'running'" />

        <!-- 数据导入按钮 -->
        <button
          class="import-btn"
          :class="{ loaded: analysisStatus === 'done', running: analysisStatus === 'running' }"
          :disabled="analysisStatus === 'running'"
          @click="triggerFileInput"
        >
          <span class="import-icon">
            {{ analysisStatus === 'running' ? '⟳' : analysisStatus === 'done' ? '✓' : '⊕' }}
          </span>
          <span>{{ importBtnLabel }}</span>
        </button>
        <!-- 取消按钮 -->
        <button v-if="analysisStatus === 'running'" class="cancel-btn" @click="cancelAnalysis">
          ✕ 取消
        </button>
        <!-- 重新导入按钮（done 状态下显示） -->
        <button v-if="analysisStatus === 'done'" class="reimport-btn" @click="triggerFileInput">
          ↺ 重新导入
        </button>
        <!-- 统计标签 -->
        <div v-if="analysisStatus === 'done'" class="csv-stats">
          <span class="cs-tag">{{ serverResults.nodes }} 节点</span>
          <span class="cs-tag">{{ serverResults.edges }} 边</span>
          <span class="cs-tag">{{ serverResults.total_frames }} 帧</span>
        </div>
      </div>
      <div class="header-right">
        <div class="stat-badge">
          <span class="stat-label">节点数</span>
          <span class="stat-value">{{ analysisStatus === 'done' ? serverResults.nodes : '—' }}</span>
        </div>
        <div class="stat-badge">
          <span class="stat-label">边数</span>
          <span class="stat-value">{{ analysisStatus === 'done' ? serverResults.edges : '—' }}</span>
        </div>
        <div class="stat-badge cog">
          <span class="stat-label">重心</span>
          <span class="stat-value">{{ analysisStatus === 'done' ? (serverResults.cog_node || '—') : '—' }}</span>
        </div>
      </div>
    </header>

    <!-- ── 分析进度覆盖层 ── -->
    <transition name="fade">
      <div v-if="analysisStatus === 'running' || analysisStatus === 'error'" class="analysis-overlay">
        <div class="analysis-card">
          <div class="ac-header">
            <span class="ac-icon" :class="{ spin: analysisStatus === 'running' }">
              {{ analysisStatus === 'error' ? '❌' : '⬡' }}
            </span>
            <div>
              <div class="ac-title">
                {{ analysisStatus === 'error' ? '分析失败' : '超网分析中' }}
              </div>
              <div class="ac-stage">{{ analysisStage }}</div>
            </div>
          </div>

          <!-- 进度条 -->
          <div v-if="analysisStatus === 'running'" class="ac-progress-wrap">
            <div class="ac-progress-bar">
              <div class="ac-progress-fill" :style="{ width: analysisProgress + '%' }"></div>
            </div>
            <span class="ac-pct">{{ analysisProgress }}%</span>
          </div>

          <!-- 错误信息 -->
          <div v-if="analysisStatus === 'error'" class="ac-error">{{ analysisError }}</div>

          <!-- 日志 -->
          <div class="ac-log" ref="logEl">
            <div v-for="(line, i) in analysisLog" :key="i" class="ac-log-line">{{ line }}</div>
          </div>

          <div class="ac-actions">
            <button v-if="analysisStatus === 'running'" class="ac-btn cancel" @click="cancelAnalysis">
              ✕ 取消分析
            </button>
            <button v-if="analysisStatus === 'error'" class="ac-btn retry" @click="resetState">
              ↺ 重新上传
            </button>
          </div>
        </div>
      </div>
    </transition>

    <!-- ── 主体 ── -->
    <div class="body">
      <!-- 左侧导航 -->
      <nav class="sidenav">
        <button
          v-for="tab in tabs" :key="tab.id"
          class="nav-btn"
          :class="{ active: activeTab === tab.id }"
          @click="activeTab = tab.id"
        >
          <span class="nav-icon">{{ tab.icon }}</span>
          <span class="nav-label">{{ tab.label }}</span>
          <span class="nav-sub">{{ tab.sub }}</span>
        </button>
      </nav>

      <!-- 右侧内容区 -->
      <main class="content">

        <!-- ══ 空状态引导页（无数据时全屏显示，覆盖所有 Tab）══ -->
        <transition name="fade">
          <div v-if="analysisStatus === 'idle' && activeTab !== 5" class="welcome-overlay">
            <div class="welcome-card">
              <!-- 动态网络图标 -->
              <div class="wc-icon">
                <div class="wc-ring wc-ring1"></div>
                <div class="wc-ring wc-ring2"></div>
                <div class="wc-ring wc-ring3"></div>
                <span class="wc-star">⬡</span>
              </div>
              <h2 class="wc-title">超网分析系统</h2>
              <p class="wc-desc">导入仿真数据目录，自动构建多层超网并完成<br>Shapley 重心分析 · 级联失效模拟 · 3D 动态复盘</p>

              <!-- 四层说明 -->
              <div class="wc-layers">
                <div class="wc-layer" v-for="l in welcomeLayers" :key="l.name">
                  <span class="wc-dot" :style="{ background: l.color }"></span>
                  <span class="wc-lname">{{ l.name }}</span>
                  <span class="wc-ldesc">{{ l.desc }}</span>
                </div>
              </div>

              <!-- 导入按钮 -->
              <button class="wc-import-btn" @click="triggerFileInput">
                <span>⊕</span>
                <span>选择数据目录开始分析</span>
              </button>
              <p class="wc-hint">支持目录导入仿真 CSV 文件</p>
            </div>
          </div>
        </transition>

        <!-- ══ Tab 1: 超网整体视频 ══ -->
        <section v-show="activeTab === 1" class="tab-panel">
          <div class="panel-header">
<h2>⬡ 3D超网动态演化复盘</h2>
          <p>3D 旋转多层作战网络 · 360° · {{ totalFrames }} 帧{{ timeRangeLabel }}</p>
          </div>
          <div class="video-wrap">
            <!-- 封面 -->
            <div v-if="!videoPlaying" class="video-cover">
              <div class="cover-bg"></div>
              <div class="scan-line"></div>
              <div class="corner corner-tl"></div><div class="corner corner-tr"></div>
              <div class="corner corner-bl"></div><div class="corner corner-br"></div>
              <div class="cover-topbar">
                <span>系统: {{ analysisStatus === 'done' ? '在线' : '待机' }}</span>
                <span class="tb-sep">|</span>
                <span>节点: {{ analysisStatus === 'done' ? serverResults.nodes : '—' }}</span>
                <span class="tb-sep">|</span>
                <span>层数: 4</span>
                <span class="tb-sep">|</span>
                <span class="blink">● {{ analysisStatus === 'done' ? '录制' : '等待' }}</span>
              </div>
              <div class="cover-content">
                <div class="network-icon">
                  <div class="ring ring1"></div>
                  <div class="ring ring2"></div>
                  <div class="ring ring3"></div>
                  <span class="center-star">★</span>
                </div>
                <h3>3D超网动态演化复盘</h3>
                <p>360° 旋转 · {{ totalFrames }} 帧{{ timeRangeLabel }}</p>
                <button
                  class="play-btn"
                  :class="{ disabled: analysisStatus === 'running' }"
                  @click="videoReady ? startVideo() : (analysisStatus !== 'running' && triggerFileInput())"
                >
                  <span>{{ videoReady ? '▶' : (analysisStatus === 'running' ? '⟳' : '⊕') }}</span>
                  <span>{{ videoReady ? '播放动画' : (analysisStatus === 'running' ? '分析中...' : '导入 CSV 开始分析') }}</span>
                </button>
              </div>
              <div class="cover-bottombar">
                <div v-for="l in layers" :key="l.name" class="cb-layer">
                  <span class="cb-dot" :style="{ background: l.color }"></span>
                  <span>{{ l.name }}</span>
                  <span class="cb-count">{{ l.nodes }}n</span>
                </div>
              </div>
            </div>
            <!-- 播放器 -->
            <video
              ref="videoEl"
              class="video-player"
              :class="{ visible: videoPlaying }"
              :src="videoSrc"
              @ended="videoPaused = true"
              @timeupdate="onTimeUpdate"
              @loadedmetadata="videoDuration = $event.target.duration"
              preload="metadata"
            ></video>
            <!-- 控制栏 -->
            <div v-if="videoPlaying" class="video-controls">
              <div class="progress-bar" @click="seekVideo">
                <div class="progress-fill" :style="{ width: videoPct + '%' }"></div>
                <div class="progress-thumb" :style="{ left: videoPct + '%' }"></div>
              </div>
              <div class="ctrl-row">
                <div class="ctrl-left">
                  <button class="ctrl-btn" @click="toggleVideo">{{ videoPaused ? '▶' : '⏸' }}</button>
                  <button class="ctrl-btn" @click="restartVideo">⟳</button>
                  <span class="time-txt">{{ fmtTime(videoTime) }} / {{ fmtTime(videoDuration) }}</span>
                </div>
                <div class="ctrl-right">
                  <button class="ctrl-btn" @click="videoMuted = !videoMuted; videoEl.muted = videoMuted">
                    {{ videoMuted ? '🔇' : '🔊' }}
                  </button>
                  <button class="ctrl-btn" @click="videoFullscreen = !videoFullscreen">⛶</button>
                </div>
              </div>
            </div>
          </div>
        </section>

        <!-- ══ Tab 2: 时间帧浏览 ══ -->
        <section v-show="activeTab === 2 && analysisStatus !== 'idle'" class="tab-panel">
          <div class="panel-header">
            <h2>🎞 时间帧浏览器</h2>
            <p>逐帧浏览时间窗口快照 · 共 {{ totalFrames }} 帧可用</p>
          </div>
          <div class="frame-browser">
            <!-- 控制区 -->
            <div class="frame-controls">
              <div class="frame-ctrl-row">
                <label class="ctrl-label">帧</label>
                <input
                  type="range" class="frame-slider"
                  :min="0" :max="totalFrames - 1" :value="currentFrame"
                  @input="currentFrame = +$event.target.value"
                />
                <span class="frame-num">{{ currentFrame + 1 }} / {{ totalFrames }}</span>
              </div>
              <div class="frame-ctrl-row">
                <label class="ctrl-label">时间</label>
                <span class="frame-time">t = {{ frameTimeStart(currentFrame) }}s ~ {{ frameTimeEnd(currentFrame) }}s</span>
                <div class="frame-nav">
                  <button class="fn-btn" @click="currentFrame = Math.max(0, currentFrame - 1)">◀</button>
                  <button class="fn-btn" :class="{ active: frameAutoPlay }" @click="toggleFramePlay">
                    {{ frameAutoPlay ? '⏸' : '▶' }}
                  </button>
                  <button class="fn-btn" @click="currentFrame = Math.min(totalFrames - 1, currentFrame + 1)">▶</button>
                </div>
              </div>
              <!-- 缩略图轨道 -->
              <div class="thumb-track">
                <div
                  v-for="i in Math.min(totalFrames, 20)" :key="i"
                  class="thumb-item"
                  :class="{ active: currentFrame === (i - 1) * Math.ceil(totalFrames / 20) }"
                  @click="currentFrame = (i - 1) * Math.ceil(totalFrames / 20)"
                >
                  <span class="thumb-label">{{ frameTimeStart((i-1) * Math.ceil(totalFrames/20)) }}s</span>
                </div>
              </div>
            </div>
            <!-- 帧图像 -->
            <div class="frame-viewer">
              <img
                :src="frameSrc(currentFrame)"
                :key="frameKey"
                :alt="`Frame ${currentFrame}`"
                class="frame-img"
                @error="frameImgError = true"
                @load="frameImgError = false"
              />
              <div v-if="frameImgError" class="frame-error">
                <span>⚠ 帧图像未找到</span>
                <p>{{ analysisStatus === 'idle' ? '请先导入 CSV 文件以生成帧序列' : '请等待分析流程完成' }}</p>
              </div>
              <div class="frame-overlay">
                <span>Frame {{ currentFrame + 1 }}/{{ totalFrames }}</span>
                <span>t = {{ frameTimeStart(currentFrame) }}s ~ {{ frameTimeEnd(currentFrame) }}s</span>
                <span>azim = {{ Math.round(35 + currentFrame * (360 / totalFrames)) % 360 }}°</span>
              </div>
            </div>
          </div>
        </section>

        <!-- ══ Tab 3: 报告渲染 ══ -->
        <section v-show="activeTab === 3 && analysisStatus !== 'idle'" class="tab-panel">
          <div class="panel-header">
            <h2>📄 分析报告</h2>
            <p>分析流程生成的 Markdown 报告渲染展示</p>
          </div>
          <div class="report-layout">
            <!-- 报告选择侧栏 -->
            <div class="report-sidebar">
              <div class="rs-title">可用报告</div>
              <button
                v-for="r in reports" :key="r.id"
                class="report-item"
                :class="{ active: activeReport === r.id }"
                @click="loadReport(r)"
              >
                <span class="ri-icon">{{ r.icon }}</span>
                <div class="ri-info">
                  <span class="ri-name">{{ r.name }}</span>
                  <span class="ri-desc">{{ r.desc }}</span>
                </div>
              </button>
              <!-- 自定义 MD 文件 -->
              <label class="report-item upload-item">
                <input type="file" accept=".md,.markdown" @change="onMdUpload" style="display:none" />
                <span class="ri-icon">⊕</span>
                <div class="ri-info">
                  <span class="ri-name">加载自定义报告</span>
                  <span class="ri-desc">上传本地 Markdown 文件</span>
                </div>
              </label>
            </div>
            <!-- 报告内容 -->
            <div class="report-content">
              <div v-if="!reportHtml" class="report-empty">
                <span>📋</span>
                <p>{{ analysisStatus === 'idle' ? '请先导入 CSV 文件以生成报告' : '请从左侧选择一份报告' }}</p>
              </div>
              <div v-else class="md-body" v-html="reportHtml"></div>
            </div>
          </div>
        </section>

        <!-- ══ Tab 4: 综合复杂网络 ══ -->
        <section v-show="activeTab === 4 && analysisStatus !== 'idle'" class="tab-panel">
          <div class="panel-header">
            <h2>🕸 综合复杂网络图</h2>
            <p>基于传感器 / 通信 / 指挥关系构建的多层作战网络</p>
          </div>
          <div class="network-view">
            <!-- 工具栏 -->
            <div class="net-toolbar">
              <div class="net-stats">
                <span class="ns-item"><span class="ns-dot" style="background:#1565c0"></span>雷达/传感器</span>
                <span class="ns-item"><span class="ns-dot" style="background:#d84315"></span>电子战/干扰机</span>
                <span class="ns-item"><span class="ns-dot" style="background:#2e7d32"></span>指挥/无人机</span>
                <span class="ns-item"><span class="ns-dot" style="background:#c62828"></span>防空/武器</span>
                <span class="ns-item"><span class="ns-dot" style="background:#546e7a"></span>其他</span>
              </div>
              <div class="net-actions">
                <button class="na-btn" @click="netZoomIn">＋</button>
                <span class="zoom-val">{{ Math.round(netZoom * 100) }}%</span>
                <button class="na-btn" @click="netZoomOut">－</button>
                <button class="na-btn" @click="netReset">⊡ 重置</button>
                <span class="na-hint">滚轮缩放 · 拖拽平移</span>
              </div>
            </div>
            <!-- 图像容器 -->
            <div
              class="net-img-wrap"
              ref="netWrap"
              @wheel.prevent="onNetWheel"
              @mousedown="onNetMouseDown"
              @mousemove="onNetMouseMove"
              @mouseup="onNetMouseUp"
              @mouseleave="onNetMouseUp"
              :style="{ cursor: netDragging ? 'grabbing' : 'grab' }"
            >
              <img
                :src="complexNetSrc"
                :key="complexNetKey"
                alt="Integrated Complex Network"
                class="net-img"
                :style="{ transform: `translate(${netPanX}px, ${netPanY}px) scale(${netZoom})`, transformOrigin: 'center' }"
                @error="netImgError = true"
                @load="netImgError = false"
                draggable="false"
              />
              <div v-if="netImgError" class="net-error">
                <span>⚠ 网络图像未找到</span>
                <p>{{ analysisStatus === 'idle' ? '请先导入 CSV 文件以生成网络图' : '生成中，请稍候...' }}</p>
              </div>
            </div>
            <!-- 网络指标 -->
            <div class="net-metrics">
              <div v-for="m in netMetrics" :key="m.label" class="nm-item">
                <span class="nm-label">{{ m.label }}</span>
                <span class="nm-value">{{ m.value }}</span>
              </div>
            </div>
          </div>
        </section>

        <!-- ══ Tab 5: 参数配置 ══ -->
        <section v-show="activeTab === 5" class="tab-panel">
          <div class="panel-header">
            <h2>⚙ 参数配置</h2>
            <p>调整分析算法参数 · 修改后下次导入 CSV 时生效</p>
          </div>
          <div class="cfg-layout">

            <!-- 左列 -->
            <div class="cfg-col">

              <!-- Shapley 分析 -->
              <div class="cfg-card">
                <div class="cfg-card-title">🧮 Shapley 分析</div>
                <div class="cfg-row">
                  <label class="cfg-label">
                    蒙特卡洛采样次数
                    <span class="cfg-hint">越大越精确，越慢（建议 50~500）</span>
                  </label>
                  <div class="cfg-input-wrap">
                    <input type="number" class="cfg-input" v-model.number="cfg.shapley_samples" min="10" max="2000" step="10" />
                  </div>
                </div>
                <div class="cfg-row">
                  <label class="cfg-label">
                    级联失效 Monte Carlo 轮数
                    <span class="cfg-hint">越多结果越稳定（建议 10~100）</span>
                  </label>
                  <div class="cfg-input-wrap">
                    <input type="number" class="cfg-input" v-model.number="cfg.cascade_rounds" min="1" max="200" step="5" />
                  </div>
                </div>
                <div class="cfg-row">
                  <label class="cfg-label">
                    级联失效崩溃阈值 (%)
                    <span class="cfg-hint">效率下降超过此值视为网络崩溃</span>
                  </label>
                  <div class="cfg-input-wrap">
                    <input type="number" class="cfg-input" v-model.number="cfg.collapse_threshold_pct" min="10" max="90" step="5" />
                    <span class="cfg-unit">%</span>
                  </div>
                </div>
              </div>

              <!-- 重心融合权重 -->
              <div class="cfg-card">
                <div class="cfg-card-title">⚖ 重心融合权重</div>
                <div class="cfg-note">度中心性权重 + Shapley 权重 = 1.0</div>
                <div class="cfg-row">
                  <label class="cfg-label">
                    度中心性权重
                    <span class="cfg-hint">局部连接强度的贡献比例</span>
                  </label>
                  <div class="cfg-input-wrap">
                    <input type="range" class="cfg-slider" v-model.number="cfg.degree_weight"
                      min="0" max="1" step="0.05"
                      @input="cfg.shapley_weight = +(1 - cfg.degree_weight).toFixed(2)" />
                    <span class="cfg-val">{{ cfg.degree_weight.toFixed(2) }}</span>
                  </div>
                </div>
                <div class="cfg-row">
                  <label class="cfg-label">
                    Shapley 值权重
                    <span class="cfg-hint">全局协同贡献的比例（自动联动）</span>
                  </label>
                  <div class="cfg-input-wrap">
                    <input type="range" class="cfg-slider" v-model.number="cfg.shapley_weight"
                      min="0" max="1" step="0.05"
                      @input="cfg.degree_weight = +(1 - cfg.shapley_weight).toFixed(2)" />
                    <span class="cfg-val">{{ cfg.shapley_weight.toFixed(2) }}</span>
                  </div>
                </div>
                <div class="cfg-weight-bar">
                  <div class="cwb-fill deg" :style="{ width: (cfg.degree_weight * 100) + '%' }">
                    <span v-if="cfg.degree_weight > 0.12">度 {{ (cfg.degree_weight*100).toFixed(0) }}%</span>
                  </div>
                  <div class="cwb-fill shap" :style="{ width: (cfg.shapley_weight * 100) + '%' }">
                    <span v-if="cfg.shapley_weight > 0.12">Shapley {{ (cfg.shapley_weight*100).toFixed(0) }}%</span>
                  </div>
                </div>
              </div>

              <!-- 桥梁加分融合 -->
              <div class="cfg-card">
                <div class="cfg-card-title">🌉 跨层桥梁加分融合</div>
                <div class="cfg-note">基础 Shapley 比例 + 桥梁加分比例 = 1.0</div>
                <div class="cfg-row">
                  <label class="cfg-label">
                    基础 Shapley 保留比例
                    <span class="cfg-hint">原始 Shapley 值的保留程度</span>
                  </label>
                  <div class="cfg-input-wrap">
                    <input type="range" class="cfg-slider" v-model.number="cfg.shapley_base_weight"
                      min="0" max="1" step="0.05"
                      @input="cfg.bridge_bonus_weight = +(1 - cfg.shapley_base_weight).toFixed(2)" />
                    <span class="cfg-val">{{ cfg.shapley_base_weight.toFixed(2) }}</span>
                  </div>
                </div>
                <div class="cfg-row">
                  <label class="cfg-label">
                    跨层桥梁加分比例
                    <span class="cfg-hint">奖励跨层枢纽节点的力度（自动联动）</span>
                  </label>
                  <div class="cfg-input-wrap">
                    <input type="range" class="cfg-slider" v-model.number="cfg.bridge_bonus_weight"
                      min="0" max="1" step="0.05"
                      @input="cfg.shapley_base_weight = +(1 - cfg.bridge_bonus_weight).toFixed(2)" />
                    <span class="cfg-val">{{ cfg.bridge_bonus_weight.toFixed(2) }}</span>
                  </div>
                </div>
              </div>

            </div>

            <!-- 右列 -->
            <div class="cfg-col">

              <!-- 逐帧动态融合 -->
              <div class="cfg-card">
                <div class="cfg-card-title">🎞 逐帧动态融合权重</div>
                <div class="cfg-note">全局 Shapley 权重 + 当前帧度数权重 = 1.0</div>
                <div class="cfg-row">
                  <label class="cfg-label">
                    全局 Shapley 权重
                    <span class="cfg-hint">保留全局战略价值的比例</span>
                  </label>
                  <div class="cfg-input-wrap">
                    <input type="range" class="cfg-slider" v-model.number="cfg.frame_global_weight"
                      min="0" max="1" step="0.05"
                      @input="cfg.frame_degree_weight = +(1 - cfg.frame_global_weight).toFixed(2)" />
                    <span class="cfg-val">{{ cfg.frame_global_weight.toFixed(2) }}</span>
                  </div>
                </div>
                <div class="cfg-row">
                  <label class="cfg-label">
                    当前帧度数权重
                    <span class="cfg-hint">反映实时活跃度变化的比例（自动联动）</span>
                  </label>
                  <div class="cfg-input-wrap">
                    <input type="range" class="cfg-slider" v-model.number="cfg.frame_degree_weight"
                      min="0" max="1" step="0.05"
                      @input="cfg.frame_global_weight = +(1 - cfg.frame_degree_weight).toFixed(2)" />
                    <span class="cfg-val">{{ cfg.frame_degree_weight.toFixed(2) }}</span>
                  </div>
                </div>
              </div>

              <!-- 视频帧生成 -->
              <div class="cfg-card">
                <div class="cfg-card-title">🎬 视频帧生成</div>
                <div class="cfg-row">
                  <label class="cfg-label">
                    生成帧总数
                    <span class="cfg-hint">帧数越多动画越细腻，耗时越长</span>
                  </label>
                  <div class="cfg-input-wrap">
                    <input type="number" class="cfg-input" v-model.number="cfg.n_frames" min="10" max="300" step="10" />
                    <span class="cfg-unit">帧</span>
                  </div>
                </div>
                <div class="cfg-row">
                  <label class="cfg-label">
                    视频帧率 (fps)
                    <span class="cfg-hint">越高播放越快（1=慢速，5=正常）</span>
                  </label>
                  <div class="cfg-input-wrap">
                    <input type="number" class="cfg-input" v-model.number="cfg.video_fps" min="1" max="30" step="1" />
                    <span class="cfg-unit">fps</span>
                  </div>
                </div>
                <div class="cfg-row">
                  <label class="cfg-label">
                    视频质量 CRF
                    <span class="cfg-hint">0=无损体积大，51=最差体积小，18=高质量</span>
                  </label>
                  <div class="cfg-input-wrap">
                    <input type="range" class="cfg-slider" v-model.number="cfg.video_crf" min="0" max="51" step="1" />
                    <span class="cfg-val">{{ cfg.video_crf }}</span>
                  </div>
                </div>
                <div class="cfg-row">
                  <label class="cfg-label">
                    3D 旋转起始方位角
                    <span class="cfg-hint">初始视角方向（0~360°）</span>
                  </label>
                  <div class="cfg-input-wrap">
                    <input type="number" class="cfg-input" v-model.number="cfg.azim_start" min="0" max="360" step="5" />
                    <span class="cfg-unit">°</span>
                  </div>
                </div>
                <div class="cfg-row">
                  <label class="cfg-label">
                    时间窗口大小
                    <span class="cfg-hint">0 = 自动计算；手动指定单位为秒</span>
                  </label>
                  <div class="cfg-input-wrap">
                    <input type="number" class="cfg-input" v-model.number="cfg.time_window_override" min="0" step="10" />
                    <span class="cfg-unit">s</span>
                  </div>
                </div>
              </div>

              <!-- 复杂网络图 -->
              <div class="cfg-card">
                <div class="cfg-card-title">🕸 复杂网络图</div>
                <div class="cfg-row">
                  <label class="cfg-label">
                    介数中心性采样节点数
                    <span class="cfg-hint">越大越精确，大图建议 50~200</span>
                  </label>
                  <div class="cfg-input-wrap">
                    <input type="number" class="cfg-input" v-model.number="cfg.cn_betweenness_k" min="10" max="500" step="10" />
                    <span class="cfg-unit">个</span>
                  </div>
                </div>
              </div>

              <!-- 关键节点展示模式 -->
              <div class="cfg-card">
                <div class="cfg-card-title">🎯 关键节点展示模式</div>
                <div class="cfg-note">控制报告和排名中展示多少个关键节点（节点多时尤其有用）</div>

                <!-- 模式选择 -->
                <div class="cfg-row">
                  <label class="cfg-label">
                    展示模式
                    <span class="cfg-hint">选择按固定数量、百分比还是全部展示</span>
                  </label>
                  <div class="cfg-mode-btns">
                    <button class="cfg-mode-btn" :class="{ active: cfg.top_n_mode === 'abs' }" @click="cfg.top_n_mode = 'abs'">固定数量</button>
                    <button class="cfg-mode-btn" :class="{ active: cfg.top_n_mode === 'pct' }" @click="cfg.top_n_mode = 'pct'">百分比</button>
                    <button class="cfg-mode-btn" :class="{ active: cfg.top_n_mode === 'all' }" @click="cfg.top_n_mode = 'all'">全部</button>
                  </div>
                </div>

                <!-- 固定数量 -->
                <div v-if="cfg.top_n_mode === 'abs'" class="cfg-row">
                  <label class="cfg-label">
                    展示前 N 个节点
                    <span class="cfg-hint">中心性排名、Shapley 排名均取前 N 个</span>
                  </label>
                  <div class="cfg-input-wrap">
                    <input type="number" class="cfg-input" v-model.number="cfg.top_n_abs" min="1" max="500" step="1" />
                    <span class="cfg-unit">个</span>
                  </div>
                </div>

                <!-- 百分比 -->
                <div v-if="cfg.top_n_mode === 'pct'" class="cfg-row">
                  <label class="cfg-label">
                    展示前 X% 节点
                    <span class="cfg-hint">按总节点数的百分比动态计算，节点越多展示越多</span>
                  </label>
                  <div class="cfg-input-wrap">
                    <input type="range" class="cfg-slider" v-model.number="cfg.top_n_pct" min="1" max="100" step="1" />
                    <span class="cfg-val">{{ cfg.top_n_pct }}%</span>
                  </div>
                </div>

                <!-- 预览提示 -->
                <div class="cfg-topn-preview">
                  <span class="ctp-icon">ℹ</span>
                  <span v-if="cfg.top_n_mode === 'abs'">
                    将展示中心性最高的 <b>{{ cfg.top_n_abs }}</b> 个节点
                  </span>
                  <span v-else-if="cfg.top_n_mode === 'pct'">
                    将展示总节点数的 <b>{{ cfg.top_n_pct }}%</b>（如 100 节点 → 展示 {{ Math.max(1, Math.round(100 * cfg.top_n_pct / 100)) }} 个）
                  </span>
                  <span v-else>
                    展示全部节点的排名（节点数很多时报告会较长）
                  </span>
                </div>
              </div>

            </div>
          </div>

          <!-- 底部操作栏 -->
          <div class="cfg-actions">
            <div class="cfg-status-msg" :class="cfgSaveStatus">{{ cfgSaveMsg }}</div>
            <button class="cfg-btn reset" @click="resetConfig">↺ 恢复默认</button>
            <button class="cfg-btn save" @click="saveConfig" :disabled="cfgSaving">
              {{ cfgSaving ? '保存中...' : '✓ 保存配置' }}
            </button>
          </div>
        </section>

      </main>
    </div>

    <!-- ── 底部状态栏 ── -->
    <footer class="footer">
      <span>超网分析系统</span>
      <span class="fsep">|</span>
      <span>{{ tabs.find(t => t.id === activeTab)?.label }}</span>
      <span class="fsep">|</span>
      <span :class="['fstatus', { active: analysisStatus === 'done' }]">
        {{ footerStatus }}
      </span>
      <span v-if="analysisStatus === 'running'" class="fsep">|</span>
      <span v-if="analysisStatus === 'running'" class="fstatus running-txt">
        {{ analysisProgress }}% · {{ analysisStage }}
      </span>
    </footer>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, nextTick, watch } from 'vue'
import { marked } from 'marked'

const API_BASE = '/api'

// ── 导航 tabs ─────────────────────────────────────────────────────────────────
const activeTab = ref(1)
const tabs = [
  { id: 1, icon: '⬡', label: '超网复盘',   sub: '3D 动态演化' },
  { id: 2, icon: '🎞', label: '帧浏览器',   sub: '时间窗口快照' },
  { id: 3, icon: '📄', label: '分析报告',   sub: 'Markdown 报告' },
  { id: 4, icon: '🕸', label: '复杂网络',   sub: '综合关系图' },
  { id: 5, icon: '⚙', label: '参数配置',   sub: '调整分析参数' },
]

// ── 层信息 ────────────────────────────────────────────────────────────────────
const layers = [
  { name: '传感器层', nodes: 37, color: '#1565c0' },
  { name: '电子战层', nodes: 12, color: '#d84315' },
  { name: '指挥层',   nodes: 15, color: '#2e7d32' },
  { name: '武器层',   nodes: 7,  color: '#c62828' },
]

// ── 欢迎页四层说明 ────────────────────────────────────────────────────────────
const welcomeLayers = [
  { name: 'SENSOR 层',  color: '#1565c0', desc: '雷达 / 传感器 / 探测关系' },
  { name: 'EW 层',      color: '#d84315', desc: '电子战 / 干扰 / 压制关系' },
  { name: 'COMMAND 层', color: '#2e7d32', desc: '指挥控制 / C2 通信链路' },
  { name: 'WEAPON 层',  color: '#c62828', desc: '武器打击 / 导弹 / 火力关系' },
]

// ── 分析状态 ──────────────────────────────────────────────────────────────────
const analysisStatus   = ref('idle')   // idle | running | done | error
const analysisProgress = ref(0)
const analysisStage    = ref('')
const analysisError    = ref('')
const analysisLog      = ref([])
const serverResults    = ref({
  total_frames: 0, nodes: 0, edges: 0,
  cog_node: '', cog_score: 0,
  has_video: false, has_reports: false, has_complex_network: false,
  t_min: 0, t_max: 0,
})

// 缓存破坏 key（分析完成后递增，强制刷新图片/视频）
const refreshKey = ref(0)

// ── 文件选择 input refs ──────────────────────────────────────────────────────
const fileInputDir   = ref(null)   // 目录模式（webkitdirectory）
const fileInputMulti = ref(null)   // 多文件模式（Safari 兜底）

function triggerFileInput() {
  if (analysisStatus.value === 'running') return
  // 检测浏览器是否真正支持 webkitdirectory（Safari 老版本不支持）
  const dirInput = fileInputDir.value
  const supportsDir = dirInput && ('webkitdirectory' in dirInput)
  if (supportsDir) {
    dirInput.value = ''
    dirInput.click()
  } else if (fileInputMulti.value) {
    // 兜底：多文件选择模式（用户手动选多个 CSV）
    fileInputMulti.value.value = ''
    fileInputMulti.value.click()
  }
}

let pollTimer = null
const logEl = ref(null)

// ── 轮询后端状态 ──────────────────────────────────────────────────────────────
async function pollStatus() {
  try {
    const res = await fetch(`${API_BASE}/status`)
    if (!res.ok) return
    const data = await res.json()

    analysisStatus.value   = data.status
    analysisProgress.value = data.progress
    analysisStage.value    = data.stage
    analysisError.value    = data.error || ''
    analysisLog.value      = data.log || []

    if (data.results) {
      serverResults.value = data.results
    }

    // 自动滚动日志到底部
    await nextTick()
    if (logEl.value) logEl.value.scrollTop = logEl.value.scrollHeight

    if (data.status === 'done') {
      // 分析完成：刷新所有产物
      refreshKey.value++
      stopPolling()
      // 自动加载报告
      await loadReport(reports.value[0])
      // 重置视频播放器
      videoPlaying.value = false
      videoPaused.value  = false
      // 重置 input，确保下次可以重新选择文件
      if (fileInputDir.value)   fileInputDir.value.value   = ''
      if (fileInputMulti.value) fileInputMulti.value.value = ''
    } else if (data.status === 'error') {
      stopPolling()
    }
  } catch (e) {
    // 后端未启动时静默忽略
  }
}

function startPolling() {
  stopPolling()
  pollTimer = setInterval(pollStatus, 1500)
}

function stopPolling() {
  if (pollTimer) { clearInterval(pollTimer); pollTimer = null }
}

// ── 目录导入 → 收集 CSV → 上传到后端 ────────────────────────────────────────
async function onCsvImport(e) {
  // webkitdirectory 模式下 files 是目录内所有文件
  const allFiles = Array.from(e.target.files || [])
  e.target.value = ''  // 立即重置，确保下次选同一目录也能触发 change

  // 只保留 .csv 文件（大小写不敏感）
  const csvFiles = allFiles.filter(f => f.name.toLowerCase().endsWith('.csv'))
  if (csvFiles.length === 0) {
    alert('所选目录中未找到 CSV 文件，请选择包含仿真数据的目录')
    return
  }

  // 取目录名（用第一个文件的 webkitRelativePath 解析）
  const dirName = csvFiles[0].webkitRelativePath
    ? csvFiles[0].webkitRelativePath.split('/')[0]
    : 'sim_data'

  // 构造 multipart：每个 CSV 作为独立字段上传，字段名统一为 'files'
  const formData = new FormData()
  for (const f of csvFiles) {
    // 只传文件名（去掉目录前缀），后端按文件名识别表类型
    formData.append('files', f, f.name)
  }
  formData.append('dir_name', dirName)

  try {
    const res = await fetch(`${API_BASE}/upload`, {
      method: 'POST',
      body: formData,
    })
    const data = await res.json()
    if (data.ok) {
      analysisStatus.value   = 'running'
      analysisProgress.value = 0
      analysisStage.value    = '准备中'
      analysisLog.value      = []
      startPolling()
    } else {
      alert(`上传失败：${data.error}`)
    }
  } catch (err) {
    alert(`无法连接到分析服务（请先启动 server.py）\n\n${err.message}`)
  }
}

async function cancelAnalysis() {
  try {
    await fetch(`${API_BASE}/cancel`, { method: 'POST' })
    stopPolling()
    analysisStatus.value = 'idle'
    analysisStage.value  = ''
  } catch {}
}

function resetState() {
  stopPolling()
  analysisStatus.value   = 'idle'
  analysisProgress.value = 0
  analysisStage.value    = ''
  analysisError.value    = ''
  analysisLog.value      = []
}

// ── 计算属性 ──────────────────────────────────────────────────────────────────
const importBtnLabel = computed(() => {
  if (analysisStatus.value === 'running') return `分析中 ${analysisProgress.value}%`
  if (analysisStatus.value === 'done')    return serverResults.value.cog_node ? `重心: ${serverResults.value.cog_node}` : '分析完成'
  return '选择数据目录'
})

const videoReady = computed(() =>
  analysisStatus.value === 'done' && serverResults.value.has_video
)

const videoSrc = computed(() =>
  `/hyper_network_animation.mp4?v=${refreshKey.value}`
)

const complexNetSrc = computed(() =>
  `/complex_network.png?v=${refreshKey.value}`
)

const complexNetKey = computed(() => refreshKey.value)

const footerStatus = computed(() => {
  if (analysisStatus.value === 'running') return '⟳ 分析中'
  if (analysisStatus.value === 'done')    return '✓ 分析完成'
  if (analysisStatus.value === 'error')   return '❌ 分析出错'
  return '⏹ 就绪'
})

// ── Tab1: 视频播放器 ──────────────────────────────────────────────────────────
const videoEl         = ref(null)
const videoPlaying    = ref(false)
const videoPaused     = ref(false)
const videoMuted      = ref(false)
const videoFullscreen = ref(false)
const videoTime       = ref(0)
const videoDuration   = ref(0)
const videoPct        = computed(() =>
  videoDuration.value > 0 ? (videoTime.value / videoDuration.value) * 100 : 0
)

function startVideo() {
  videoPlaying.value = true
  videoPaused.value  = false
  nextTick(() => videoEl.value?.play())
}
function toggleVideo() {
  if (!videoEl.value) return
  if (videoPaused.value) { videoEl.value.play(); videoPaused.value = false }
  else                   { videoEl.value.pause(); videoPaused.value = true }
}
function restartVideo() {
  if (!videoEl.value) return
  videoEl.value.currentTime = 0
  videoEl.value.play()
  videoPaused.value = false
}
function onTimeUpdate(e) { videoTime.value = e.target.currentTime }
function seekVideo(e) {
  if (!videoEl.value) return
  const r = e.currentTarget.getBoundingClientRect()
  videoEl.value.currentTime = ((e.clientX - r.left) / r.width) * videoDuration.value
}
function fmtTime(s) {
  const m = Math.floor(s / 60)
  return `${m}:${Math.floor(s % 60).toString().padStart(2, '0')}`
}

// ── Tab2: 帧浏览器 ────────────────────────────────────────────────────────────
const totalFrames   = computed(() =>
  analysisStatus.value === 'done' && serverResults.value.total_frames > 0
    ? serverResults.value.total_frames
    : 60
)
const currentFrame  = ref(0)
const frameImgError = ref(false)
const frameAutoPlay = ref(false)
const frameKey      = computed(() => `${currentFrame.value}-${refreshKey.value}`)
let   frameTimer    = null

// 时间范围从后端结果中读取，无数据时为 0
const timeTotal = computed(() =>
  analysisStatus.value === 'done' && serverResults.value.t_max > 0
    ? serverResults.value.t_max
    : 0
)
const timeRangeLabel = computed(() =>
  timeTotal.value > 0 ? ` · t = 0 ~ ${Math.round(timeTotal.value)}s` : ''
)
function frameTimeStart(i) {
  const total = timeTotal.value || totalFrames.value
  return Math.round(i * (total / totalFrames.value))
}
function frameTimeEnd(i) {
  const total = timeTotal.value || totalFrames.value
  return Math.round((i + 1) * (total / totalFrames.value))
}

function frameSrc(i) {
  return `/frames/frame_${String(i).padStart(4, '0')}.png?v=${refreshKey.value}`
}

function toggleFramePlay() {
  frameAutoPlay.value = !frameAutoPlay.value
  if (frameAutoPlay.value) {
    frameTimer = setInterval(() => {
      currentFrame.value = (currentFrame.value + 1) % totalFrames.value
    }, 800)
  } else {
    clearInterval(frameTimer)
  }
}

// ── Tab3: 报告渲染 ────────────────────────────────────────────────────────────
const activeReport = ref(null)
const reportHtml   = ref('')

const reports = ref([
  { id: 'full',    icon: '📊', name: '综合分析报告',   desc: 'Shapley + 级联失效', file: '/full_analysis_report.md' },
  { id: 'cascade', icon: '⚡', name: '级联失效报告',   desc: '蒙特卡洛模拟',       file: '/cascade_failure_report.md' },
  { id: 'cn',      icon: '🕸️', name: '复杂网络报告',   desc: '中心性 + 拓扑特征',  file: '/complex_network_report.md' },
])

async function loadReport(r) {
  activeReport.value = r.id
  try {
    const res  = await fetch(`${r.file}?v=${refreshKey.value}`)
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    const text = await res.text()
    reportHtml.value = marked.parse(text)
  } catch (e) {
    reportHtml.value = `<p style="color:#c62828">⚠ 报告加载失败：${e.message}</p>`
  }
}

function onMdUpload(e) {
  const file = e.target.files[0]
  if (!file) return
  activeReport.value = 'custom'
  const reader = new FileReader()
  reader.onload = (ev) => {
    reportHtml.value = marked.parse(ev.target.result)
  }
  reader.readAsText(file)
}

// ── Tab4: 复杂网络 ────────────────────────────────────────────────────────────
const netZoom     = ref(1)
const netPanX     = ref(0)
const netPanY     = ref(0)
const netDragging = ref(false)
const netImgError = ref(false)
let   _netDragStart = { x: 0, y: 0, px: 0, py: 0 }

function netZoomIn()  { netZoom.value = Math.min(8, +(netZoom.value + 0.2).toFixed(2)) }
function netZoomOut() { netZoom.value = Math.max(0.2, +(netZoom.value - 0.2).toFixed(2)) }
function netReset()   { netZoom.value = 1; netPanX.value = 0; netPanY.value = 0 }

function onNetWheel(e) {
  const delta = e.deltaY > 0 ? -0.15 : 0.15
  netZoom.value = Math.min(8, Math.max(0.2, +(netZoom.value + delta).toFixed(2)))
}
function onNetMouseDown(e) {
  if (e.button !== 0) return
  netDragging.value = true
  _netDragStart = { x: e.clientX, y: e.clientY, px: netPanX.value, py: netPanY.value }
}
function onNetMouseMove(e) {
  if (!netDragging.value) return
  netPanX.value = _netDragStart.px + (e.clientX - _netDragStart.x)
  netPanY.value = _netDragStart.py + (e.clientY - _netDragStart.y)
}
function onNetMouseUp() { netDragging.value = false }
const netMetrics  = computed(() => {
  if (analysisStatus.value === 'done') {
    return [
      { label: '节点数',   value: String(serverResults.value.nodes) },
      { label: '边数',     value: String(serverResults.value.edges) },
      { label: '重心节点', value: serverResults.value.cog_node || '—' },
      { label: '重心分数', value: serverResults.value.cog_score?.toFixed(4) || '—' },
      { label: '帧数',     value: String(serverResults.value.total_frames) },
      { label: '网络层',   value: '传感器 + 电子战 + 指挥 + 武器' },
    ]
  }
  return [
    { label: '节点数',   value: '—' },
    { label: '边数',     value: '—' },
    { label: '重心节点', value: '—' },
    { label: '重心分数', value: '—' },
    { label: '帧数',     value: '—' },
    { label: '网络层',   value: '传感器 + 电子战 + 指挥 + 武器' },
  ]
})

// ── Tab5: 参数配置 ────────────────────────────────────────────────────────────
const CFG_DEFAULTS = {
  shapley_samples:        150,
  cascade_rounds:         20,
  degree_weight:          0.4,
  shapley_weight:         0.6,
  shapley_base_weight:    0.7,
  bridge_bonus_weight:    0.3,
  frame_global_weight:    0.5,
  frame_degree_weight:    0.5,
  n_frames:               60,
  video_fps:              2,
  video_crf:              18,
  azim_start:             35,
  time_window_override:   0,
  cn_betweenness_k:       100,
  cn_top_n:               10,       // 兼容旧版，由后端根据 top_n_mode 计算
  top_n_mode:             'abs',    // 'abs' | 'pct' | 'all'
  top_n_abs:              10,       // 固定数量模式：展示前 N 个
  top_n_pct:              10,       // 百分比模式：展示前 X%
  collapse_threshold_pct: 50.0,
}

const cfg        = ref({ ...CFG_DEFAULTS })
const cfgSaving  = ref(false)
const cfgSaveMsg = ref('')
const cfgSaveStatus = ref('')  // 'ok' | 'err' | ''

async function loadConfig() {
  try {
    const res = await fetch(`${API_BASE}/config`)
    if (!res.ok) return
    const data = await res.json()
    Object.assign(cfg.value, data)
  } catch {}
}

async function saveConfig() {
  cfgSaving.value = true
  cfgSaveMsg.value = ''
  try {
    const res = await fetch(`${API_BASE}/config`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(cfg.value),
    })
    const data = await res.json()
    if (data.ok) {
      cfgSaveMsg.value = '✓ 配置已保存，下次分析时生效'
      cfgSaveStatus.value = 'ok'
    } else {
      cfgSaveMsg.value = `✕ 保存失败：${data.error}`
      cfgSaveStatus.value = 'err'
    }
  } catch (e) {
    cfgSaveMsg.value = `✕ 无法连接后端：${e.message}`
    cfgSaveStatus.value = 'err'
  } finally {
    cfgSaving.value = false
    setTimeout(() => { cfgSaveMsg.value = ''; cfgSaveStatus.value = '' }, 4000)
  }
}

function resetConfig() {
  Object.assign(cfg.value, CFG_DEFAULTS)
  cfgSaveMsg.value = '已恢复默认值，点击「保存配置」使其生效'
  cfgSaveStatus.value = ''
  setTimeout(() => { cfgSaveMsg.value = '' }, 3000)
}

// ── 生命周期 ──────────────────────────────────────────────────────────────────
onMounted(async () => {
  // 启动时查询一次后端状态（可能上次分析已完成）
  await pollStatus()
  // 加载后端当前配置
  await loadConfig()
  // 如果后端正在运行，继续轮询
  if (analysisStatus.value === 'running') {
    startPolling()
  }
})

onUnmounted(() => {
  clearInterval(frameTimer)
  stopPolling()
})
</script>

<style scoped>
/* ── Reset & Base ── */
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
.app {
  height: 100dvh; display: flex; flex-direction: column;
  background: #0d1117; color: #e6edf3;
  font-family: 'SF Mono', 'Fira Code', 'Consolas', monospace;
  overflow: hidden;
}

/* ── Header ── */
.header {
  display: flex; align-items: center; gap: 12px;
  padding: 8px 16px;
  background: linear-gradient(90deg, #0d1117, #161b22);
  border-bottom: 1px solid #21262d;
  flex-shrink: 0; flex-wrap: nowrap; overflow: hidden;
}
.header-left  { display: flex; align-items: center; gap: 10px; flex-shrink: 0; }
.header-center{ display: flex; align-items: center; gap: 10px; flex: 1; justify-content: center; min-width: 0; }
.header-right { display: flex; gap: 8px; flex-shrink: 0; }
.logo { font-size: 22px; color: #f9a825; flex-shrink: 0; }
.title-block h1 { font-size: 14px; font-weight: 700; color: #e6edf3; letter-spacing: 0.04em; white-space: nowrap; }

/* CSV 导入按钮 */
.import-btn {
  display: flex; align-items: center; gap: 7px;
  padding: 6px 14px; border-radius: 20px; cursor: pointer;
  background: #161b22; border: 1px solid #30363d;
  font-size: 11px; color: #8b949e; transition: all 0.2s;
  font-family: inherit;
  /* button reset */
  outline: none; user-select: none;
}
.import-btn:disabled { opacity: 0.6; cursor: not-allowed; }
.import-btn:hover { border-color: #1565c0; color: #e6edf3; }
.import-btn.loaded  { border-color: #2ea043; color: #2ea043; }
.import-btn.running { border-color: #f9a825; color: #f9a825; animation: pulse-border 1.5s ease-in-out infinite; }
@keyframes pulse-border { 0%,100%{box-shadow:0 0 0 0 rgba(249,168,37,0.4)} 50%{box-shadow:0 0 0 4px rgba(249,168,37,0)} }
.import-icon { font-size: 14px; }
.cancel-btn {
  padding: 5px 12px; border-radius: 20px; cursor: pointer;
  background: rgba(198,40,40,0.15); border: 1px solid #c62828;
  font-size: 11px; color: #ef5350; transition: all 0.2s; font-family: inherit;
}
.cancel-btn:hover { background: rgba(198,40,40,0.3); }
.reimport-btn {
  padding: 5px 12px; border-radius: 20px; cursor: pointer;
  background: rgba(21,101,192,0.15); border: 1px solid #1565c0;
  font-size: 11px; color: #79c0ff; transition: all 0.2s; font-family: inherit;
  white-space: nowrap;
}
.reimport-btn:hover { background: rgba(21,101,192,0.3); }
.csv-stats { display: flex; gap: 6px; }
.cs-tag {
  padding: 2px 8px; border-radius: 10px;
  background: #21262d; font-size: 10px; color: #8b949e;
}

/* stat badges */
.stat-badge {
  display: flex; flex-direction: column; align-items: center;
  padding: 4px 10px; background: #161b22;
  border: 1px solid #30363d; border-radius: 7px; min-width: 48px;
}
.stat-badge.cog { border-color: #f9a825; background: #1a1500; }
.stat-label { font-size: 8px; color: #8b949e; letter-spacing: 0.1em; text-transform: uppercase; }
.stat-value { font-size: 13px; font-weight: 700; color: #e6edf3; margin-top: 1px; }
.stat-badge.cog .stat-value { color: #f9a825; }

/* ── 分析进度覆盖层 ── */
.analysis-overlay {
  position: fixed; inset: 0; z-index: 100;
  background: rgba(13,17,23,0.88);
  display: flex; align-items: center; justify-content: center;
  backdrop-filter: blur(4px);
}
.analysis-card {
  width: 520px; max-width: 90vw;
  background: #161b22; border: 1px solid #30363d; border-radius: 14px;
  padding: 24px; display: flex; flex-direction: column; gap: 16px;
  box-shadow: 0 20px 60px rgba(0,0,0,0.6);
}
.ac-header { display: flex; align-items: center; gap: 14px; }
.ac-icon { font-size: 32px; color: #f9a825; }
.ac-icon.spin { animation: spin 1.5s linear infinite; display: inline-block; }
@keyframes spin { from{transform:rotate(0deg)} to{transform:rotate(360deg)} }
.ac-title { font-size: 15px; font-weight: 700; color: #e6edf3; }
.ac-stage { font-size: 11px; color: #8b949e; margin-top: 3px; }
.ac-progress-wrap { display: flex; align-items: center; gap: 10px; }
.ac-progress-bar {
  flex: 1; height: 6px; background: #21262d; border-radius: 3px; overflow: hidden;
}
.ac-progress-fill {
  height: 100%; background: linear-gradient(90deg, #1565c0, #42a5f5);
  border-radius: 3px; transition: width 0.4s ease;
}
.ac-pct { font-size: 12px; color: #f9a825; font-weight: 700; width: 36px; text-align: right; }
.ac-error { font-size: 12px; color: #ef5350; background: rgba(198,40,40,0.1); padding: 8px 12px; border-radius: 6px; border: 1px solid rgba(198,40,40,0.3); }
.ac-log {
  height: 160px; overflow-y: auto; background: #0d1117;
  border: 1px solid #21262d; border-radius: 6px;
  padding: 8px 10px; font-size: 10px; color: #8b949e;
  font-family: 'SF Mono', monospace;
}
.ac-log-line { line-height: 1.6; white-space: pre-wrap; word-break: break-all; }
.ac-actions { display: flex; justify-content: flex-end; gap: 8px; }
.ac-btn {
  padding: 7px 18px; border-radius: 8px; cursor: pointer;
  font-size: 12px; font-weight: 700; font-family: inherit; transition: all 0.2s;
}
.ac-btn.cancel { background: rgba(198,40,40,0.15); border: 1px solid #c62828; color: #ef5350; }
.ac-btn.cancel:hover { background: rgba(198,40,40,0.3); }
.ac-btn.retry  { background: #1565c0; border: 1px solid #1976d2; color: #fff; }
.ac-btn.retry:hover { background: #1976d2; }

/* fade transition */
.fade-enter-active, .fade-leave-active { transition: opacity 0.3s; }
.fade-enter-from, .fade-leave-to { opacity: 0; }

/* ── Body ── */
.body { flex: 1; display: flex; min-height: 0; }

/* ── Sidenav ── */
.sidenav {
  width: 130px; flex-shrink: 0;
  background: #0d1117; border-right: 1px solid #21262d;
  display: flex; flex-direction: column;
  padding: 12px 8px; gap: 6px;
}
.nav-btn {
  display: flex; flex-direction: column; align-items: center;
  padding: 12px 6px; border-radius: 10px; cursor: pointer;
  background: none; border: 1px solid transparent;
  color: #8b949e; transition: all 0.2s; font-family: inherit;
  text-align: center;
}
.nav-btn:hover { background: #161b22; border-color: #30363d; color: #e6edf3; }
.nav-btn.active {
  background: #161b22; border-color: #1565c0;
  color: #e6edf3;
  box-shadow: 0 0 12px rgba(21,101,192,0.25);
}
.nav-icon  { font-size: 22px; margin-bottom: 4px; }
.nav-label { font-size: 10px; font-weight: 700; letter-spacing: 0.04em; }
.nav-sub   { font-size: 8.5px; color: #546e7a; margin-top: 2px; line-height: 1.3; }
.nav-btn.active .nav-sub { color: #8b949e; }

/* ── Content ── */
.content { flex: 1; min-width: 0; overflow: hidden; position: relative; }
.tab-panel { height: 100%; display: flex; flex-direction: column; padding: 16px 20px; gap: 12px; overflow: hidden; }

.panel-header h2 { font-size: 15px; font-weight: 700; color: #e6edf3; }
.panel-header p  { font-size: 11px; color: #8b949e; margin-top: 3px; }

/* ══ Tab1: Video ══ */
.video-wrap {
  flex: 1; position: relative; min-height: 0;
  background: #0d1117; border: 1px solid #21262d; border-radius: 10px; overflow: hidden;
}
.video-cover {
  position: absolute; inset: 0;
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  z-index: 10;
}
.cover-bg {
  position: absolute; inset: 0;
  background:
    radial-gradient(ellipse at 50% 50%, #0d2a4a 0%, #0d1117 65%),
    repeating-linear-gradient(0deg, transparent, transparent 39px, rgba(255,255,255,0.02) 40px),
    repeating-linear-gradient(90deg, transparent, transparent 39px, rgba(255,255,255,0.02) 40px);
}
.scan-line {
  position: absolute; left: 0; right: 0; height: 2px;
  background: linear-gradient(90deg, transparent, rgba(21,101,192,0.6), transparent);
  animation: scan 3s linear infinite; z-index: 2;
}
@keyframes scan { 0%{top:0%;opacity:0} 5%{opacity:1} 95%{opacity:1} 100%{top:100%;opacity:0} }
.corner { position: absolute; width: 18px; height: 18px; z-index: 3; }
.corner::before,.corner::after { content:''; position:absolute; background:#1565c0; }
.corner::before { width:100%; height:2px; top:0; left:0; }
.corner::after  { width:2px; height:100%; top:0; left:0; }
.corner-tl{top:10px;left:10px} .corner-tr{top:10px;right:10px;transform:scaleX(-1)}
.corner-bl{bottom:10px;left:10px;transform:scaleY(-1)} .corner-br{bottom:10px;right:10px;transform:scale(-1)}
.cover-topbar {
  position: absolute; top: 14px; left: 50%; transform: translateX(-50%);
  display: flex; align-items: center; gap: 8px;
  font-size: 10px; color: #8b949e; letter-spacing: 0.08em; z-index: 3;
}
.tb-sep { color: #21262d; }
.blink { color: #c62828; animation: blink 1.2s step-end infinite; }
@keyframes blink { 0%,100%{opacity:1} 50%{opacity:0} }
.cover-content {
  position: relative; z-index: 1;
  display: flex; flex-direction: column; align-items: center; gap: 16px; text-align: center;
}
.cover-content h3 { font-size: 20px; font-weight: 700; color: #e6edf3; }
.cover-content p  { font-size: 12px; color: #8b949e; }
.cover-bottombar {
  position: absolute; bottom: 14px; left: 50%; transform: translateX(-50%);
  display: flex; gap: 18px; z-index: 3;
}
.cb-layer { display: flex; align-items: center; gap: 4px; font-size: 10px; color: #546e7a; }
.cb-dot   { width: 7px; height: 7px; border-radius: 2px; }
.cb-count { color: #30363d; }
/* 旋转环 */
.network-icon { position: relative; width: 140px; height: 140px; display: flex; align-items: center; justify-content: center; }
.ring { position: absolute; border-radius: 50%; border: 2px solid transparent; animation: spin linear infinite; }
.ring1 { width:140px;height:140px; border-top-color:#1565c0; border-right-color:rgba(21,101,192,0.2); animation-duration:5s; }
.ring2 { width:100px;height:100px; border-right-color:#d84315; border-left-color:rgba(216,67,21,0.2); animation-duration:3.5s; animation-direction:reverse; }
.ring3 { width:64px;height:64px; border-bottom-color:#f9a825; border-top-color:rgba(249,168,37,0.2); animation-duration:2.5s; }
.center-star { font-size:26px; color:#f9a825; z-index:1; text-shadow:0 0 18px rgba(249,168,37,0.8); }
/* 播放按钮 */
.play-btn {
  display: flex; align-items: center; gap: 8px;
  padding: 12px 28px; background: linear-gradient(135deg,#1565c0,#0d47a1);
  border: 1px solid #1976d2; border-radius: 50px;
  color: #fff; font-size: 14px; font-weight: 700; cursor: pointer;
  transition: all 0.2s; font-family: inherit;
}
.play-btn:hover:not(.disabled) { transform: scale(1.04); box-shadow: 0 0 20px rgba(21,101,192,0.5); }
.play-btn.disabled { opacity: 0.5; cursor: not-allowed; background: #21262d; border-color: #30363d; }
/* 视频 */
.video-player { width:100%; height:100%; position:absolute; inset:0; object-fit:contain; display:none; background:#0d1117; }
.video-player.visible { display:block; }
.video-controls {
  position: absolute; bottom: 0; left: 0; right: 0;
  background: linear-gradient(transparent, rgba(0,0,0,0.85));
  padding: 18px 14px 10px;
}
.progress-bar { position:relative; height:4px; background:rgba(255,255,255,0.2); border-radius:2px; cursor:pointer; margin-bottom:8px; }
.progress-fill { height:100%; background:#1565c0; border-radius:2px; transition:width 0.1s linear; }
.progress-thumb { position:absolute; top:50%; transform:translate(-50%,-50%); width:11px; height:11px; background:#fff; border-radius:50%; transition:left 0.1s linear; }
.ctrl-row { display:flex; align-items:center; justify-content:space-between; }
.ctrl-left,.ctrl-right { display:flex; align-items:center; gap:6px; }
.ctrl-btn { background:none; border:none; color:#e6edf3; font-size:15px; cursor:pointer; padding:3px 7px; border-radius:4px; transition:background 0.15s; font-family:inherit; }
.ctrl-btn:hover { background:rgba(255,255,255,0.1); }
.time-txt { font-size:11px; color:#8b949e; }

/* ══ Tab2: Frame Browser ══ */
.frame-browser { flex: 1; display: flex; flex-direction: column; gap: 10px; min-height: 0; }
.frame-controls {
  background: #161b22; border: 1px solid #21262d; border-radius: 8px;
  padding: 12px 16px; display: flex; flex-direction: column; gap: 8px; flex-shrink: 0;
}
.frame-ctrl-row { display: flex; align-items: center; gap: 10px; }
.ctrl-label { font-size: 10px; color: #8b949e; width: 36px; flex-shrink: 0; text-transform: uppercase; letter-spacing: 0.08em; }
.frame-slider { flex: 1; accent-color: #1565c0; cursor: pointer; }
.frame-num  { font-size: 11px; color: #e6edf3; width: 60px; text-align: right; flex-shrink: 0; }
.frame-time { font-size: 11px; color: #f9a825; flex: 1; }
.frame-nav  { display: flex; gap: 4px; }
.fn-btn {
  padding: 4px 10px; background: #21262d; border: 1px solid #30363d;
  border-radius: 5px; color: #e6edf3; cursor: pointer; font-size: 12px;
  transition: all 0.15s; font-family: inherit;
}
.fn-btn:hover { background: #30363d; }
.fn-btn.active { background: #1565c0; border-color: #1976d2; }
/* 缩略图轨道 */
.thumb-track { display: flex; gap: 3px; overflow-x: auto; padding-bottom: 2px; }
.thumb-item {
  flex-shrink: 0; width: 44px; height: 24px;
  background: #21262d; border: 1px solid #30363d; border-radius: 4px;
  display: flex; align-items: center; justify-content: center;
  cursor: pointer; transition: all 0.15s;
}
.thumb-item:hover { border-color: #1565c0; }
.thumb-item.active { background: #1565c0; border-color: #1976d2; }
.thumb-label { font-size: 8px; color: #8b949e; }
.thumb-item.active .thumb-label { color: #fff; }
/* 帧图像 */
.frame-viewer { flex: 1; position: relative; min-height: 0; background: #0d1117; border: 1px solid #21262d; border-radius: 8px; overflow: hidden; }
.frame-img { width: 100%; height: 100%; object-fit: contain; display: block; }
.frame-error { position: absolute; inset: 0; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 8px; color: #8b949e; font-size: 13px; }
.frame-overlay {
  position: absolute; bottom: 10px; right: 12px;
  display: flex; gap: 12px;
  font-size: 10px; color: #8b949e; background: rgba(0,0,0,0.6);
  padding: 4px 10px; border-radius: 4px;
}

/* ══ Tab3: Reports ══ */
.report-layout { flex: 1; display: flex; gap: 12px; min-height: 0; }
.report-sidebar {
  width: 200px; flex-shrink: 0;
  background: #161b22; border: 1px solid #21262d; border-radius: 8px;
  padding: 10px; display: flex; flex-direction: column; gap: 6px; overflow-y: auto;
}
.rs-title { font-size: 9px; color: #546e7a; text-transform: uppercase; letter-spacing: 0.1em; padding: 4px 6px; }
.report-item {
  display: flex; align-items: center; gap: 8px;
  padding: 8px 10px; border-radius: 7px; cursor: pointer;
  background: none; border: 1px solid transparent;
  color: #8b949e; transition: all 0.15s; text-align: left; font-family: inherit; width: 100%;
}
.report-item:hover { background: #21262d; border-color: #30363d; color: #e6edf3; }
.report-item.active { background: #21262d; border-color: #1565c0; color: #e6edf3; }
.upload-item { border-style: dashed; border-color: #30363d; }
.ri-icon { font-size: 18px; flex-shrink: 0; }
.ri-info { display: flex; flex-direction: column; gap: 2px; }
.ri-name { font-size: 11px; font-weight: 700; }
.ri-desc { font-size: 9px; color: #546e7a; }
.report-content {
  flex: 1; min-width: 0;
  background: #161b22; border: 1px solid #21262d; border-radius: 8px;
  overflow-y: auto; padding: 20px 24px;
}
.report-empty { height: 100%; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 10px; color: #546e7a; font-size: 13px; }
.report-empty span { font-size: 32px; }

/* Markdown 样式 */
.md-body { color: #e6edf3; line-height: 1.7; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; }
.md-body :deep(h1) { font-size: 20px; font-weight: 700; color: #e6edf3; border-bottom: 1px solid #21262d; padding-bottom: 8px; margin: 0 0 16px; }
.md-body :deep(h2) { font-size: 16px; font-weight: 700; color: #79c0ff; margin: 20px 0 10px; }
.md-body :deep(h3) { font-size: 14px; font-weight: 700; color: #d2a8ff; margin: 16px 0 8px; }
.md-body :deep(p)  { margin: 0 0 10px; font-size: 13px; color: #c9d1d9; }
.md-body :deep(blockquote) { border-left: 3px solid #1565c0; padding: 6px 12px; background: #161b22; margin: 10px 0; border-radius: 0 4px 4px 0; }
.md-body :deep(blockquote p) { color: #8b949e; margin: 0; }
.md-body :deep(code) { background: #21262d; padding: 1px 5px; border-radius: 3px; font-size: 12px; color: #f9a825; font-family: 'SF Mono', monospace; }
.md-body :deep(pre)  { background: #161b22; border: 1px solid #21262d; border-radius: 6px; padding: 12px; overflow-x: auto; margin: 10px 0; }
.md-body :deep(pre code) { background: none; padding: 0; color: #e6edf3; }
.md-body :deep(table) { width: 100%; border-collapse: collapse; margin: 12px 0; font-size: 12px; }
.md-body :deep(th) { background: #21262d; color: #e6edf3; padding: 7px 10px; text-align: left; border: 1px solid #30363d; }
.md-body :deep(td) { padding: 6px 10px; border: 1px solid #21262d; color: #c9d1d9; }
.md-body :deep(tr:nth-child(even) td) { background: rgba(255,255,255,0.02); }
.md-body :deep(strong) { color: #e6edf3; font-weight: 700; }
.md-body :deep(hr) { border: none; border-top: 1px solid #21262d; margin: 16px 0; }
.md-body :deep(ul), .md-body :deep(ol) { padding-left: 20px; margin: 8px 0; }
.md-body :deep(li) { font-size: 13px; color: #c9d1d9; margin: 3px 0; }

/* ══ Tab4: Complex Network ══ */
.network-view { flex: 1; display: flex; flex-direction: column; gap: 10px; min-height: 0; }
.net-toolbar {
  display: flex; align-items: center; justify-content: space-between;
  background: #161b22; border: 1px solid #21262d; border-radius: 8px;
  padding: 8px 14px; flex-shrink: 0;
}
.net-stats { display: flex; gap: 14px; }
.ns-item { display: flex; align-items: center; gap: 5px; font-size: 10px; color: #8b949e; }
.ns-dot  { width: 8px; height: 8px; border-radius: 50%; }
.net-actions { display: flex; align-items: center; gap: 6px; }
.na-btn {
  padding: 4px 10px; background: #21262d; border: 1px solid #30363d;
  border-radius: 5px; color: #e6edf3; cursor: pointer; font-size: 12px;
  transition: all 0.15s; font-family: inherit;
}
.na-btn:hover { background: #30363d; }
.zoom-val { font-size: 11px; color: #8b949e; width: 38px; text-align: center; }
.net-img-wrap {
  flex: 1; min-height: 0;
  background: #0d1117; border: 1px solid #21262d; border-radius: 8px;
  overflow: hidden; display: flex; align-items: center; justify-content: center;
  position: relative; user-select: none;
}
.net-img { max-width: 100%; max-height: 100%; object-fit: contain; will-change: transform; transition: none; }
.na-hint { font-size: 10px; color: #546e7a; margin-left: 4px; white-space: nowrap; }
.net-error { display: flex; flex-direction: column; align-items: center; gap: 8px; color: #8b949e; font-size: 13px; }
.net-error code { background: #21262d; padding: 2px 6px; border-radius: 3px; color: #f9a825; font-size: 11px; }
.net-metrics {
  display: flex; gap: 8px; flex-wrap: wrap; flex-shrink: 0;
  background: #161b22; border: 1px solid #21262d; border-radius: 8px;
  padding: 8px 14px;
}
.nm-item { display: flex; flex-direction: column; gap: 2px; min-width: 100px; }
.nm-label { font-size: 9px; color: #546e7a; text-transform: uppercase; letter-spacing: 0.08em; }
.nm-value { font-size: 13px; font-weight: 700; color: #e6edf3; }

/* ══ Tab5: Config ══ */
.cfg-layout {
  flex: 1; display: flex; gap: 14px; min-height: 0; overflow-y: auto;
}
.cfg-col {
  flex: 1; display: flex; flex-direction: column; gap: 12px; min-width: 0;
}
.cfg-card {
  background: #161b22; border: 1px solid #21262d; border-radius: 10px;
  padding: 14px 16px; display: flex; flex-direction: column; gap: 10px;
}
.cfg-card-title {
  font-size: 12px; font-weight: 700; color: #79c0ff;
  letter-spacing: 0.04em; padding-bottom: 6px;
  border-bottom: 1px solid #21262d;
}
.cfg-note {
  font-size: 10px; color: #546e7a; margin-top: -4px;
}
.cfg-row {
  display: flex; align-items: center; gap: 12px; min-height: 32px;
}
.cfg-label {
  flex: 1; font-size: 11px; color: #c9d1d9; display: flex; flex-direction: column; gap: 2px;
  cursor: default;
}
.cfg-hint {
  font-size: 9.5px; color: #546e7a; font-weight: 400;
}
.cfg-input-wrap {
  display: flex; align-items: center; gap: 6px; flex-shrink: 0;
}
.cfg-input {
  width: 80px; padding: 4px 8px;
  background: #0d1117; border: 1px solid #30363d; border-radius: 6px;
  color: #e6edf3; font-size: 12px; font-family: inherit;
  text-align: right;
  transition: border-color 0.15s;
}
.cfg-input:focus { outline: none; border-color: #1565c0; }
.cfg-unit {
  font-size: 10px; color: #546e7a; width: 16px;
}
.cfg-slider {
  width: 120px; accent-color: #1565c0; cursor: pointer;
}
.cfg-val {
  font-size: 12px; color: #f9a825; font-weight: 700; width: 36px; text-align: right;
}
/* 权重可视化条 */
.cfg-weight-bar {
  display: flex; height: 20px; border-radius: 4px; overflow: hidden;
  border: 1px solid #21262d; margin-top: 2px;
}
.cwb-fill {
  display: flex; align-items: center; justify-content: center;
  font-size: 9px; font-weight: 700; color: #fff; transition: width 0.2s ease;
  overflow: hidden; white-space: nowrap;
}
.cwb-fill.deg  { background: linear-gradient(90deg, #1565c0, #1976d2); }
.cwb-fill.shap { background: linear-gradient(90deg, #2e7d32, #388e3c); }
/* 底部操作栏 */
.cfg-actions {
  display: flex; align-items: center; gap: 10px; flex-shrink: 0;
  padding: 10px 0 0; border-top: 1px solid #21262d; margin-top: 4px;
}
.cfg-status-msg {
  flex: 1; font-size: 11px; color: #8b949e;
}
.cfg-status-msg.ok  { color: #2ea043; }
.cfg-status-msg.err { color: #ef5350; }
.cfg-btn {
  padding: 7px 18px; border-radius: 8px; cursor: pointer;
  font-size: 12px; font-weight: 700; font-family: inherit; transition: all 0.2s;
  white-space: nowrap;
}
.cfg-btn.reset {
  background: #21262d; border: 1px solid #30363d; color: #8b949e;
}
.cfg-btn.reset:hover { background: #30363d; color: #e6edf3; }
.cfg-btn.save {
  background: linear-gradient(135deg, #1565c0, #0d47a1);
  border: 1px solid #1976d2; color: #fff;
}
.cfg-btn.save:hover:not(:disabled) { background: linear-gradient(135deg, #1976d2, #1565c0); box-shadow: 0 0 12px rgba(21,101,192,0.4); }
.cfg-btn.save:disabled { opacity: 0.5; cursor: not-allowed; }
/* 模式切换按钮组 */
.cfg-mode-btns {
  display: flex; gap: 4px; flex-shrink: 0;
}
.cfg-mode-btn {
  padding: 4px 10px; border-radius: 6px; cursor: pointer;
  font-size: 11px; font-family: inherit; font-weight: 600;
  background: #21262d; border: 1px solid #30363d; color: #8b949e;
  transition: all 0.15s;
}
.cfg-mode-btn:hover { background: #30363d; color: #e6edf3; }
.cfg-mode-btn.active { background: #1565c0; border-color: #1976d2; color: #fff; }
/* 预览提示 */
.cfg-topn-preview {
  display: flex; align-items: flex-start; gap: 6px;
  background: #0d1117; border: 1px solid #21262d; border-radius: 6px;
  padding: 8px 10px; font-size: 11px; color: #8b949e; line-height: 1.5;
}
.ctp-icon { color: #1565c0; flex-shrink: 0; font-size: 13px; }
.cfg-topn-preview b { color: #f9a825; }

/* ── Footer ── */
.footer {
  padding: 8px 20px; background: #161b22; border-top: 1px solid #21262d;
  font-size: 10px; color: #8b949e; display: flex; align-items: center; gap: 8px; flex-shrink: 0;
}
.fsep { color: #30363d; }
.fstatus { color: #8b949e; }
.fstatus.active { color: #2ea043; }
.running-txt { color: #f9a825; }

/* ══ 欢迎引导页 ══ */
.welcome-overlay {
  position: absolute; inset: 0; z-index: 20;
  display: flex; align-items: center; justify-content: center;
  background: #0d1117;
}
.welcome-card {
  display: flex; flex-direction: column; align-items: center;
  gap: 20px; max-width: 520px; width: 90%; text-align: center;
  padding: 48px 40px;
  background: #161b22; border: 1px solid #21262d; border-radius: 20px;
  box-shadow: 0 8px 48px rgba(0,0,0,0.5);
}
/* 动态图标 */
.wc-icon {
  position: relative; width: 80px; height: 80px;
  display: flex; align-items: center; justify-content: center;
}
.wc-ring {
  position: absolute; border-radius: 50%;
  border: 1.5px solid transparent; animation: wc-spin linear infinite;
}
.wc-ring1 { width: 80px; height: 80px; border-top-color: #1565c0; animation-duration: 3s; }
.wc-ring2 { width: 58px; height: 58px; border-top-color: #d84315; animation-duration: 2.2s; animation-direction: reverse; }
.wc-ring3 { width: 38px; height: 38px; border-top-color: #2e7d32; animation-duration: 1.6s; }
@keyframes wc-spin { to { transform: rotate(360deg); } }
.wc-star { font-size: 22px; color: #f9a825; z-index: 1; }
/* 文字 */
.wc-title { font-size: 22px; font-weight: 700; color: #e6edf3; margin: 0; letter-spacing: 0.04em; }
.wc-desc  { font-size: 13px; color: #8b949e; line-height: 1.7; margin: 0; }
/* 四层说明 */
.wc-layers {
  display: grid; grid-template-columns: 1fr 1fr; gap: 10px; width: 100%;
}
.wc-layer {
  display: flex; align-items: center; gap: 8px;
  background: #0d1117; border: 1px solid #21262d; border-radius: 8px;
  padding: 10px 12px; text-align: left;
}
.wc-dot   { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.wc-lname { font-size: 11px; font-weight: 700; color: #e6edf3; white-space: nowrap; }
.wc-ldesc { font-size: 10px; color: #8b949e; margin-left: 2px; }
/* 导入按钮 */
.wc-import-btn {
  display: flex; align-items: center; gap: 10px;
  padding: 14px 32px; border-radius: 50px; cursor: pointer;
  background: linear-gradient(135deg, #1565c0, #0d47a1);
  border: 1px solid #1976d2; color: #fff;
  font-size: 15px; font-weight: 700; font-family: inherit;
  transition: all 0.2s; outline: none;
}
.wc-import-btn:hover { transform: scale(1.04); box-shadow: 0 0 24px rgba(21,101,192,0.5); }
.wc-hint { font-size: 11px; color: #484f58; margin: 0; }
</style>
