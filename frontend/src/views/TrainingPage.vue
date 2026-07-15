<template>
  <div class="training-page">
    <div class="page-header">
      <div>
        <span class="vp-kicker">Model Operations</span>
        <h2>模型训练与监控</h2>
        <p>启动 YOLOv11 训练任务，实时观察 loss、mAP 与运行状态。</p>
      </div>
      <div class="page-actions">
        <el-button :icon="Upload" @click="openImportDialog">
          导入离线结果
        </el-button>
        <el-button type="primary" :icon="Plus" @click="openCreateTrainingDialog">
          新建训练任务
        </el-button>
      </div>
    </div>

    <section class="panel detection-model-panel">
      <div class="panel-header">
        <div>
          <span>检测使用版本</span>
          <small>图片、视频和实时检测统一使用场景当前选中的 best.pt</small>
        </div>
        <el-button text :icon="Refresh" :loading="loadingModelVersions" @click="fetchModelVersions">
          刷新版本
        </el-button>
      </div>

      <div class="model-version-selector">
        <el-select
          v-model="selectedModelVersionId"
          filterable
          placeholder="选择要用于检测的模型版本"
          :loading="loadingModelVersions"
        >
          <el-option
            v-for="item in modelVersionList"
            :key="item.id"
            :label="modelVersionOptionLabel(item)"
            :value="item.id"
            :disabled="!item.file_exists"
          />
        </el-select>
        <el-button
          type="primary"
          :loading="switchingModelVersionId === selectedModelVersionId"
          :disabled="!selectedModelVersion || selectedModelVersion.is_default || !selectedModelVersion.file_exists"
          @click="switchDetectionModel"
        >
          {{ selectedModelVersion?.is_default ? '当前检测版本' : '切换检测版本' }}
        </el-button>
      </div>

      <div v-if="selectedModelVersion" class="model-version-detail">
        <div class="model-version-main">
          <div>
            <span>模型版本</span>
            <strong>{{ selectedModelVersion.version }}</strong>
          </div>
          <el-tag :type="selectedModelVersion.is_default ? 'success' : 'info'" effect="plain">
            {{ selectedModelVersion.is_default ? '检测使用中' : '可切换' }}
          </el-tag>
        </div>
        <div class="model-version-grid">
          <div><span>所属场景</span><strong>{{ selectedModelVersion.scene_name || `#${selectedModelVersion.scene_id}` }}</strong></div>
          <div><span>数据集版本</span><strong>{{ selectedModelVersion.dataset_version || 'Legacy 未登记' }}</strong></div>
          <div><span>训练任务</span><strong>{{ selectedModelVersion.training_task_uuid || '内置正式模型' }}</strong></div>
          <div><span>模型大小</span><strong>{{ formatFileSize(selectedModelVersion.file_size) }}</strong></div>
          <div><span>训练参数</span><strong>{{ modelParameterSummary(selectedModelVersion) }}</strong></div>
          <div><span>训练结果</span><strong>{{ modelResultSummary(selectedModelVersion) }}</strong></div>
        </div>
        <div class="model-path-row">
          <span>best.pt</span>
          <code>{{ selectedModelVersion.model_path }}</code>
          <el-tag size="small" :type="selectedModelVersion.file_exists ? 'success' : 'danger'">
            {{ selectedModelVersion.file_exists ? '文件可用' : '文件缺失' }}
          </el-tag>
        </div>
        <p v-if="selectedModelVersion.description" class="model-description">{{ selectedModelVersion.description }}</p>
      </div>
      <el-empty v-else-if="!loadingModelVersions" description="暂无可用的检测模型" />
    </section>

    <section class="panel dataset-version-panel">
      <div class="panel-header">
        <div>
          <span>可训练数据集版本</span>
          <small>仅展示已冻结版本；训练状态由关联任务实时汇总</small>
        </div>
        <el-button text :icon="Refresh" :loading="loadingDatasets" @click="fetchTrainingDatasets">
          刷新数据集
        </el-button>
      </div>
      <el-table
        v-loading="loadingDatasets"
        :data="trainableDatasets"
        stripe
        empty-text="暂无已冻结的数据集版本，请先到数据集版本页面登记并冻结"
      >
        <el-table-column label="数据集版本" min-width="190">
          <template #default="{ row }">
            <div class="dataset-version-cell">
              <strong>{{ row.version }}</strong>
              <el-tag v-if="row.is_current" size="small" type="success">当前</el-tag>
              <span>{{ row.name }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="场景" min-width="140">
          <template #default="{ row }">{{ row.scene_name || `#${row.scene_id}` }}</template>
        </el-table-column>
        <el-table-column label="规模" width="170">
          <template #default="{ row }">
            {{ row.total_image_count }} 张 / {{ row.class_count }} 类
          </template>
        </el-table-column>
        <el-table-column label="训练状态" width="120">
          <template #default="{ row }">
            <el-tag :type="datasetTrainingStatusType(row.training_status)" size="small">
              {{ datasetTrainingStatusText(row.training_status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="训练记录" width="130">
          <template #default="{ row }">
            {{ row.completed_training_count }}/{{ row.training_task_count }} 成功
          </template>
        </el-table-column>
        <el-table-column label="内容指纹" min-width="150">
          <template #default="{ row }"><code>{{ shortHash(row.content_hash) }}</code></template>
        </el-table-column>
        <el-table-column label="操作" width="120" fixed="right">
          <template #default="{ row }">
            <el-button size="small" type="primary" text @click="trainDataset(row)">训练此版本</el-button>
          </template>
        </el-table-column>
      </el-table>
    </section>

    <section class="panel">
      <div class="panel-header">
        <span>训练任务列表</span>
        <el-button text :icon="Refresh" :loading="loadingTasks" @click="fetchTasks">
          刷新
        </el-button>
      </div>

      <el-table
        v-loading="loadingTasks"
        :data="taskList"
        stripe
        class="task-table"
        empty-text="暂无训练任务"
      >
        <el-table-column prop="task_uuid" label="任务 ID" min-width="110" />
        <el-table-column prop="model_name" label="模型" min-width="110" />
        <el-table-column label="数据集版本" min-width="150">
          <template #default="{ row }">
            <span v-if="row.dataset_version">{{ row.dataset_version }}</span>
            <el-tag v-else size="small" type="info">Legacy</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="device" label="设备" width="170" />
        <el-table-column label="进度" min-width="180">
          <template #default="{ row }">
            <el-progress
              :percentage="row.progress || 0"
              :status="progressStatus(row.status)"
              :stroke-width="14"
            />
          </template>
        </el-table-column>
        <el-table-column label="Epoch" width="110">
          <template #default="{ row }">
            {{ row.current_epoch || 0 }}/{{ row.epochs || 0 }}
          </template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="statusType(row.status)" size="small">
              {{ statusText(row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="创建时间" min-width="170">
          <template #default="{ row }">
            {{ formatTime(row.created_at) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="420" fixed="right">
          <template #default="{ row }">
            <el-button size="small" type="primary" text @click="selectTask(row)">
              监控
            </el-button>
            <el-button
              v-if="row.status === 'running'"
              size="small"
              type="danger"
              text
              @click="stopTask(row.id)"
            >
              停止
            </el-button>
            <el-button size="small" text @click="openLogDrawer(row)">
              Log
            </el-button>
            <el-button
              v-if="row.status === 'completed'"
              size="small"
              text
              @click="openEvalDrawer(row)"
            >
              评估
            </el-button>
            <el-button
              v-if="row.status === 'completed'"
              size="small"
              text
              @click="openExportDialog(row)"
            >
              导出
            </el-button>
            <el-button
              v-if="row.status === 'completed'"
              size="small"
              text
              @click="downloadWeights(row)"
            >
              权重
            </el-button>
            <el-button
              v-if="row.status === 'completed'"
              size="small"
              text
              @click="openPredictDialog(row)"
            >
              测试
            </el-button>
            <el-button
              v-if="row.status === 'completed'"
              size="small"
              text
              @click="downloadResults(row.task_uuid)"
            >
              结果
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </section>

    <section v-if="selectedTask" class="panel monitor-panel">
      <div class="panel-header monitor-header">
        <div>
          <span>训练监控 - 任务 {{ selectedTask.task_uuid }}</span>
          <el-tag :type="statusType(selectedTask.status)" size="small">
            {{ statusText(selectedTask.status) }}
          </el-tag>
        </div>
        <div class="monitor-meta">
          <span>模型 {{ selectedTask.model_name }}</span>
          <span>数据集 {{ selectedTask.dataset_version || 'Legacy 未登记' }}</span>
          <span>设备 {{ selectedTask.device }}</span>
          <span>Epoch {{ selectedTask.current_epoch || 0 }}/{{ selectedTask.epochs || 0 }}</span>
        </div>
      </div>

      <div class="live-progress-panel">
        <div class="live-progress-header">
          <span>{{ liveProgressTitle }}</span>
          <span>{{ liveProgressPercent.toFixed(1) }}%</span>
        </div>
        <el-progress
          class="monitor-progress"
          :percentage="liveProgressPercent"
          :status="progressStatus(selectedTask.status)"
          :stroke-width="16"
        />
        <div class="live-progress-meta">
          <span>Epoch {{ liveProgress?.epoch ?? (selectedTask.current_epoch || 0) }}/{{ selectedTask.epochs || 0 }}</span>
          <span v-if="liveProgress?.total_batches">Batch {{ liveProgress.batch || 0 }}/{{ liveProgress.total_batches }}</span>
          <span>Elapsed {{ liveProgress?.elapsed_text || '-' }}</span>
          <span>ETA {{ liveProgress?.eta_text || '-' }}</span>
          <span>{{ liveProgress?.rate_text || '--it/s' }}</span>
        </div>
        <pre v-if="liveProgress?.tqdm_line" class="tqdm-line">{{ liveProgress.tqdm_line }}</pre>
      </div>

      <div class="metric-grid">
        <div v-for="item in metricCards" :key="item.label" class="metric-card">
          <span>{{ item.label }}</span>
          <strong>{{ item.value }}</strong>
        </div>
      </div>

      <div class="chart-grid">
        <div ref="lossChartRef" class="chart"></div>
        <div ref="metricChartRef" class="chart"></div>
      </div>
    </section>

    <el-empty v-else class="empty-monitor" description="选择一个训练任务查看监控曲线" />

    <el-dialog
      v-model="showCreateDialog"
      title="新建训练任务"
      width="620px"
      :close-on-click-modal="false"
    >
      <el-form :model="trainForm" label-width="120px">
        <el-form-item label="数据集版本" required>
          <el-select
            v-model="trainForm.dataset_version_id"
            filterable
            placeholder="选择已冻结的数据集版本"
            style="width: 100%"
            @change="syncTrainDatasetScene"
          >
            <el-option
              v-for="dataset in trainableDatasets"
              :key="dataset.id"
              :label="`${dataset.version} · ${dataset.name} · ${datasetTrainingStatusText(dataset.training_status)}`"
              :value="dataset.id"
            />
          </el-select>
        </el-form-item>

        <el-form-item label="检测场景">
          <el-input-number v-model="trainForm.scene_id" :min="1" :disabled="Boolean(trainForm.dataset_version_id)" />
        </el-form-item>

        <el-form-item label="基础模型">
          <el-select v-model="trainForm.model_name">
            <el-option label="YOLOv11n (Nano)" value="yolov11n" />
            <el-option label="YOLOv11s (Small)" value="yolov11s" />
            <el-option label="YOLOv11m (Medium)" value="yolov11m" />
            <el-option label="YOLOv11l (Large)" value="yolov11l" />
            <el-option label="YOLOv11x (XLarge)" value="yolov11x" />
          </el-select>
        </el-form-item>

        <el-form-item label="训练轮数">
          <el-slider v-model="trainForm.epochs" :min="1" :max="300" :step="1" show-input />
        </el-form-item>

        <el-form-item label="批次大小">
          <el-input-number v-model="trainForm.batch_size" :min="1" :max="512" />
        </el-form-item>

        <el-form-item label="图像尺寸">
          <el-select v-model="trainForm.img_size">
            <el-option label="416" :value="416" />
            <el-option label="512" :value="512" />
            <el-option label="640" :value="640" />
            <el-option label="768" :value="768" />
          </el-select>
        </el-form-item>

        <el-form-item label="训练设备">
          <div class="device-field">
            <el-select
              v-model="trainForm.device"
              filterable
              allow-create
              default-first-option
              placeholder="选择或输入设备，如 0,1,2,3,4,5,6,7"
            >
              <el-option
                v-for="option in deviceOptions"
                :key="option.value"
                :label="option.label"
                :value="option.value"
              />
            </el-select>
            <p class="form-tip">多卡训练使用 Ultralytics DDP；batch_size 是总 batch，会分摊到每张 GPU。</p>
          </div>
        </el-form-item>

        <el-form-item label="优化器">
          <el-select v-model="trainForm.optimizer">
            <el-option label="SGD" value="SGD" />
            <el-option label="Adam" value="Adam" />
            <el-option label="AdamW" value="AdamW" />
          </el-select>
        </el-form-item>

        <el-form-item label="初始学习率">
          <el-input-number
            v-model="trainForm.lr0"
            :min="0.0001"
            :max="0.1"
            :step="0.001"
            :precision="4"
          />
        </el-form-item>

        <el-form-item label="场景增强">
          <el-switch v-model="trainForm.checkout_augment" />
        </el-form-item>

        <el-form-item label="数据集目录">
          <el-input :model-value="selectedTrainDataset?.storage_path || ''" disabled />
          <p class="form-tip">目录和 data.yaml 由所选数据集版本决定，启动时后端会再次检查。</p>
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="showCreateDialog = false">取消</el-button>
        <el-button type="primary" :loading="creating" @click="createTask">
          启动训练
        </el-button>
      </template>
    </el-dialog>

    <el-dialog
      v-model="showImportDialog"
      title="导入离线训练结果"
      width="720px"
      :close-on-click-modal="false"
    >
      <el-form :model="importForm" label-width="130px">
        <el-form-item label="数据集版本" required>
          <el-select
            v-model="importForm.dataset_version_id"
            filterable
            placeholder="选择离线训练实际使用的数据集版本"
            style="width: 100%"
            @change="syncImportDatasetScene"
          >
            <el-option
              v-for="dataset in importableDatasets"
              :key="dataset.id"
              :label="`${dataset.version} · ${dataset.name}`"
              :value="dataset.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="检测场景">
          <el-input-number v-model="importForm.scene_id" :min="1" :disabled="Boolean(importForm.dataset_version_id)" />
        </el-form-item>
        <el-form-item label="训练输出目录">
          <el-input
            v-model="importForm.run_dir"
            placeholder="/home/xshi/projects/VisionPay-Agent/backend/runs/train/task_xxx"
          />
        </el-form-item>
        <el-form-item label="任务 ID">
          <el-input v-model="importForm.task_uuid" placeholder="可选；默认从 task_xxx 推断" />
        </el-form-item>
        <el-form-item label="基础模型">
          <el-select v-model="importForm.model_name" clearable placeholder="默认读取 args.yaml">
            <el-option label="YOLOv11 Nano" value="yolov11n" />
            <el-option label="YOLOv11 Small" value="yolov11s" />
            <el-option label="YOLOv11 Medium" value="yolov11m" />
            <el-option label="YOLOv11 Large" value="yolov11l" />
            <el-option label="YOLOv11 X" value="yolov11x" />
          </el-select>
        </el-form-item>
        <el-form-item label="数据集目录">
          <el-input
            :model-value="selectedImportDataset?.storage_path || ''"
            disabled
            placeholder="由所选数据集版本决定"
          />
        </el-form-item>
        <el-form-item label="data.yaml">
          <el-input :model-value="selectedImportDataset?.data_yaml_path || ''" disabled />
        </el-form-item>
        <el-form-item label="训练日志">
          <el-input v-model="importForm.log_path" placeholder="可选；默认 run_dir/train.log" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showImportDialog = false">取消</el-button>
        <el-button type="primary" :loading="importing" @click="submitImportRun">
          导入结果
        </el-button>
      </template>
    </el-dialog>

    <el-drawer
      v-model="showLogDrawer"
      size="70%"
      :title="logDrawerTitle"
      direction="rtl"
      @closed="stopLogPolling"
    >
      <div class="log-toolbar">
        <div class="log-meta">
          <span>Task {{ logTask?.task_uuid || '-' }}</span>
          <span v-if="logPath">{{ logPath }}</span>
        </div>
        <div class="log-actions">
          <el-switch v-model="autoRefreshLog" active-text="Auto refresh" />
          <el-button size="small" :loading="loadingLog" @click="refreshLog">
            Refresh
          </el-button>
        </div>
      </div>

      <el-empty v-if="!logExists && !loadingLog" description="Log file has not been generated" />
      <pre v-else ref="logContentRef" class="log-content">{{ logText }}</pre>
    </el-drawer>

    <el-drawer
      v-model="showEvalDrawer"
      size="70%"
      title="模型评估报告"
      direction="rtl"
    >
      <div class="eval-toolbar">
        <div class="log-meta">
          <span>Task {{ evalTask?.task_uuid || '-' }}</span>
          <span v-if="evalReport?.report_path">{{ evalReport.report_path }}</span>
        </div>
        <div class="eval-actions">
          <el-select v-model="evalForm.split" size="small">
            <el-option label="val" value="val" />
            <el-option label="test" value="test" />
            <el-option label="train" value="train" />
          </el-select>
          <el-input-number
            v-model="evalForm.conf"
            size="small"
            :min="0"
            :max="1"
            :step="0.05"
            :precision="3"
          />
          <el-input-number
            v-model="evalForm.iou"
            size="small"
            :min="0"
            :max="1"
            :step="0.05"
            :precision="2"
          />
          <el-button size="small" type="primary" :loading="evaluating" @click="runEvaluation">
            运行评估
          </el-button>
        </div>
      </div>

      <el-skeleton v-if="evaluating && !evalReport" :rows="6" animated />
      <template v-else-if="evalReport">
        <div class="metric-grid">
          <div v-for="item in evalMetricCards" :key="item.label" class="metric-card">
            <span>{{ item.label }}</span>
            <strong>{{ item.value }}</strong>
          </div>
        </div>

        <div class="eval-columns">
          <section class="eval-section">
            <h3>弱势类别 Top 10</h3>
            <el-table :data="weakClassRows" size="small" height="280" empty-text="暂无每类 AP">
              <el-table-column prop="class_name" label="类别" min-width="160" />
              <el-table-column label="AP" width="100">
                <template #default="{ row }">{{ formatPercent(row.ap) }}</template>
              </el-table-column>
            </el-table>
          </section>

          <section class="eval-section">
            <h3>评估产物</h3>
            <ul v-if="artifactRows.length" class="artifact-list">
              <li v-for="item in artifactRows" :key="item.name">
                <strong>{{ item.name }}</strong>
                <span>{{ item.path }}</span>
              </li>
            </ul>
            <el-empty v-else description="暂无混淆矩阵或曲线图" />
          </section>
        </div>
      </template>
      <el-empty v-else description="点击运行评估生成报告" />
    </el-drawer>

    <el-dialog
      v-model="showExportDialog"
      title="导出模型版本"
      width="520px"
      :close-on-click-modal="false"
    >
      <el-form :model="exportForm" label-width="100px">
        <el-form-item label="任务">
          <el-input :model-value="exportTask?.task_uuid || '-'" disabled />
        </el-form-item>
        <el-form-item label="版本号">
          <el-input v-model="exportForm.version" placeholder="v1.0.0" />
        </el-form-item>
        <el-form-item label="版本说明">
          <el-input v-model="exportForm.description" type="textarea" :rows="3" />
        </el-form-item>
        <el-form-item label="默认模型">
          <el-switch v-model="exportForm.set_default" />
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="showExportDialog = false">取消</el-button>
        <el-button type="primary" :loading="exporting" @click="submitExport">
          导出
        </el-button>
      </template>
    </el-dialog>

    <el-dialog
      v-model="showPredictDialog"
      title="测试图验证"
      width="860px"
      :close-on-click-modal="false"
      @closed="clearPredictState"
    >
      <div class="predict-layout">
        <section class="predict-panel">
          <div class="predict-controls">
            <input class="file-input" type="file" accept="image/*" @change="onPredictFileChange" />
            <el-form label-width="80px" class="predict-form">
              <el-form-item label="置信度">
                <el-input-number
                  v-model="predictForm.conf"
                  :min="0"
                  :max="1"
                  :step="0.05"
                  :precision="2"
                />
              </el-form-item>
              <el-form-item label="IoU">
                <el-input-number
                  v-model="predictForm.iou"
                  :min="0"
                  :max="1"
                  :step="0.05"
                  :precision="2"
                />
              </el-form-item>
              <el-form-item label="设备">
                <el-input v-model="predictForm.device" />
              </el-form-item>
            </el-form>
            <el-button
              type="primary"
              :loading="predicting"
              :disabled="!predictFile"
              @click="runPredict"
            >
              开始检测
            </el-button>
          </div>
          <img v-if="predictPreview" class="preview-image" :src="predictPreview" alt="preview" />
        </section>

        <section class="predict-panel">
          <template v-if="predictResult">
            <div class="predict-summary">
              <span>目标数：{{ predictResult.total_objects }}</span>
              <span>耗时：{{ formatMs(predictResult.inference_time) }}</span>
            </div>
            <img
              v-if="predictResult.annotated_image"
              class="result-image"
              :src="predictResult.annotated_image"
              alt="prediction"
            />
            <el-table :data="predictResult.detections || []" size="small" height="220">
              <el-table-column prop="class_name" label="类别" min-width="130" />
              <el-table-column label="置信度" width="100">
                <template #default="{ row }">{{ formatPercent(row.confidence) }}</template>
              </el-table-column>
              <el-table-column label="BBox" min-width="180">
                <template #default="{ row }">{{ formatBox(row.bbox) }}</template>
              </el-table-column>
            </el-table>
          </template>
          <el-empty v-else description="上传图片后运行检测" />
        </section>
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Refresh, Upload } from '@element-plus/icons-vue'
import * as echarts from 'echarts/core'
import { GridComponent, LegendComponent, TitleComponent, TooltipComponent } from 'echarts/components'
import { LineChart } from 'echarts/charts'
import { CanvasRenderer } from 'echarts/renderers'
import {
  downloadTrainingModelApi,
  downloadTrainingResultsApi,
  exportTrainingModelApi,
  getDetectionModelVersionsApi,
  getTrainingLogApi,
  getTrainingMetricsApi,
  getTrainingStatusApi,
  getTrainingTasksApi,
  importTrainingRunApi,
  predictTrainingImageApi,
  setDefaultDetectionModelApi,
  startTrainingApi,
  stopTrainingApi,
  validateTrainingTaskApi,
} from '@/api/training'
import { getDatasetVersionsApi } from '@/api/datasets'

echarts.use([TitleComponent, TooltipComponent, LegendComponent, GridComponent, LineChart, CanvasRenderer])

const taskList = ref([])
const loadingTasks = ref(false)
const modelVersionList = ref([])
const loadingModelVersions = ref(false)
const selectedModelVersionId = ref(null)
const switchingModelVersionId = ref(null)
const datasetList = ref([])
const loadingDatasets = ref(false)
const selectedTask = ref(null)
const latestMetric = ref(null)
const liveProgress = ref(null)
const showCreateDialog = ref(false)
const creating = ref(false)
const showImportDialog = ref(false)
const importing = ref(false)
const importForm = ref({
  scene_id: 1,
  dataset_version_id: null,
  run_dir: '/home/xshi/projects/VisionPay-Agent/backend/runs/train/task_sbatch_mixed_yolov11x',
  task_uuid: '',
  model_name: '',
  log_path: '',
})

const showLogDrawer = ref(false)
const logTask = ref(null)
const logLines = ref([])
const logPath = ref('')
const logExists = ref(false)
const loadingLog = ref(false)
const autoRefreshLog = ref(true)
const logContentRef = ref(null)

const showEvalDrawer = ref(false)
const evalTask = ref(null)
const evalReport = ref(null)
const evaluating = ref(false)
const evalForm = ref({
  split: 'val',
  conf: 0.001,
  iou: 0.6,
  device: '0',
})

const showExportDialog = ref(false)
const exportTask = ref(null)
const exportForm = ref({
  version: '',
  description: '',
  set_default: true,
})
const exporting = ref(false)

const showPredictDialog = ref(false)
const predictTask = ref(null)
const predictFile = ref(null)
const predictPreview = ref('')
const predictResult = ref(null)
const predicting = ref(false)
const predictForm = ref({
  conf: 0.25,
  iou: 0.45,
  device: 'cpu',
})
const lossChartRef = ref(null)
const metricChartRef = ref(null)
let lossChart = null
let metricChart = null
let pollTimer = null
let logPollTimer = null

const deviceOptions = [
  { label: 'CPU', value: 'cpu' },
  ...Array.from({ length: 8 }, (_, index) => ({
    label: `GPU ${index}`,
    value: String(index),
  })),
  { label: '2 卡 GPU 0-1', value: '0,1' },
  { label: '4 卡 GPU 0-3', value: '0,1,2,3' },
  { label: '8 卡 GPU 0-7', value: '0,1,2,3,4,5,6,7' },
]

const trainForm = ref({
  scene_id: 1,
  dataset_version_id: null,
  model_name: 'yolov11n',
  epochs: 100,
  batch_size: 16,
  img_size: 640,
  device: '0',
  optimizer: 'SGD',
  lr0: 0.01,
  checkout_augment: true,
})

const trainableDatasets = computed(() =>
  datasetList.value.filter((dataset) => dataset.status === 'ready')
)
const importableDatasets = computed(() =>
  datasetList.value.filter((dataset) => ['ready', 'archived'].includes(dataset.status))
)
const selectedTrainDataset = computed(() =>
  datasetList.value.find((dataset) => dataset.id === trainForm.value.dataset_version_id)
)
const selectedImportDataset = computed(() =>
  datasetList.value.find((dataset) => dataset.id === importForm.value.dataset_version_id)
)
const selectedModelVersion = computed(() =>
  modelVersionList.value.find((model) => model.id === selectedModelVersionId.value) || null
)

const metricCards = computed(() => {
  const task = selectedTask.value
  const metric = latestMetric.value
  if (!task) return []
  return [
    { label: 'Epoch', value: `${task.current_epoch || 0}/${task.epochs || 0}` },
    { label: '进度', value: `${task.progress || 0}%` },
    { label: 'Box Loss', value: formatNumber(metric?.box_loss) },
    { label: 'Cls Loss', value: formatNumber(metric?.cls_loss) },
    { label: 'DFL Loss', value: formatNumber(metric?.dfl_loss) },
    { label: 'Precision', value: formatPercent(metric?.precision) },
    { label: 'Recall', value: formatPercent(metric?.recall) },
    { label: 'mAP@50', value: formatPercent(metric?.map50) },
    { label: 'mAP@50-95', value: formatPercent(metric?.map50_95) },
  ]
})

const liveProgressPercent = computed(() => {
  const value = liveProgress.value?.percent ?? selectedTask.value?.progress ?? 0
  return Math.min(100, Math.max(0, Number(value) || 0))
})

const liveProgressTitle = computed(() => {
  const phase = liveProgress.value?.phase || selectedTask.value?.status || 'pending'
  const label = {
    pending: '等待中',
    train: '训练中',
    running: '训练中',
    completed: '训练完成',
    failed: '训练失败',
    cancelled: '已取消',
  }[phase] || phase
  return `${label} ${liveProgress.value?.bar || ''}`.trim()
})

const logText = computed(() => logLines.value.join('\n'))
const logDrawerTitle = computed(() => `Training Log - ${logTask.value?.task_uuid || '-'}`)

const evalMetricCards = computed(() => {
  const report = evalReport.value
  if (!report) return []
  return [
    { label: 'Precision', value: formatPercent(report.precision ?? report.overall?.precision) },
    { label: 'Recall', value: formatPercent(report.recall ?? report.overall?.recall) },
    { label: 'mAP@50', value: formatPercent(report.map50 ?? report.overall?.map50) },
    { label: 'mAP@50-95', value: formatPercent(report.map50_95 ?? report.overall?.map50_95) },
    { label: 'Split', value: report.split || '-' },
    { label: 'Classes', value: Object.keys(report.per_class_ap || {}).length },
  ]
})

const weakClassRows = computed(() => {
  if (Array.isArray(evalReport.value?.weak_classes) && evalReport.value.weak_classes.length) {
    return evalReport.value.weak_classes
  }
  return Object.entries(evalReport.value?.per_class_ap || {})
    .map(([class_name, ap]) => ({ class_name, ap }))
    .filter((item) => item.ap != null)
    .sort((a, b) => Number(a.ap) - Number(b.ap))
    .slice(0, 10)
})

const artifactRows = computed(() =>
  Object.entries(evalReport.value?.artifacts || {}).map(([name, path]) => ({ name, path }))
)

function statusType(status) {
  return {
    pending: 'info',
    running: 'warning',
    completed: 'success',
    failed: 'danger',
    cancelled: 'info',
  }[status] || 'info'
}

function progressStatus(status) {
  if (status === 'completed') return 'success'
  if (status === 'failed') return 'exception'
  return undefined
}

function statusText(status) {
  return {
    pending: '等待中',
    running: '训练中',
    completed: '已完成',
    failed: '失败',
    cancelled: '已取消',
  }[status] || status || '-'
}

function datasetTrainingStatusText(status) {
  return {
    untrained: '未训练',
    queued: '排队中',
    training: '训练中',
    trained: '已训练',
    failed: '训练失败',
  }[status] || status || '-'
}

function datasetTrainingStatusType(status) {
  return {
    untrained: 'info',
    queued: 'warning',
    training: 'warning',
    trained: 'success',
    failed: 'danger',
  }[status] || 'info'
}

function shortHash(value) {
  if (!value) return '-'
  return value.length > 20 ? `${value.slice(0, 12)}…${value.slice(-7)}` : value
}

function formatNumber(value) {
  return value == null ? '-' : Number(value).toFixed(4)
}

function formatPercent(value) {
  return value == null ? '-' : `${(Number(value) * 100).toFixed(1)}%`
}

function formatFileSize(value) {
  const bytes = Number(value || 0)
  if (!bytes) return '-'
  const units = ['B', 'KB', 'MB', 'GB']
  const index = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1)
  return `${(bytes / (1024 ** index)).toFixed(index ? 1 : 0)} ${units[index]}`
}

function modelVersionOptionLabel(model) {
  return `${model.scene_name || `场景 #${model.scene_id}`} · ${model.version} · ${model.dataset_version || '未绑定数据集'}`
}

function modelParameterSummary(model) {
  const params = model.training_parameters
  if (!params) return '历史正式参数未登记'
  return `${params.model_name} · ${params.epochs} epochs · imgsz ${params.img_size} · batch ${params.batch_size} · ${params.optimizer}`
}

function modelResultSummary(model) {
  const result = model.training_result
  if (!result) return '历史正式结果未登记'
  return `mAP50 ${formatPercent(result.map50)} · mAP50-95 ${formatPercent(result.map50_95)} · P ${formatPercent(result.precision)} · R ${formatPercent(result.recall)}`
}

function formatTime(value) {
  if (!value) return '-'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString()
}

function formatMs(value) {
  return value == null ? '-' : `${(Number(value) * 1000).toFixed(1)} ms`
}

function formatBox(value) {
  return Array.isArray(value) ? value.map((item) => Number(item).toFixed(1)).join(', ') : '-'
}

function singleDevice(device) {
  if (!device || device === 'cpu') return device || 'cpu'
  return String(device).split(',')[0]
}

function defaultVersion() {
  const date = new Date()
  const pad = (value) => String(value).padStart(2, '0')
  return `v${date.getFullYear()}${pad(date.getMonth() + 1)}${pad(date.getDate())}_${pad(
    date.getHours()
  )}${pad(date.getMinutes())}${pad(date.getSeconds())}`
}

async function fetchTasks() {
  loadingTasks.value = true
  try {
    const res = await getTrainingTasksApi()
    taskList.value = res.items || []
  } catch {
    taskList.value = []
  } finally {
    loadingTasks.value = false
  }
}

async function fetchModelVersions() {
  loadingModelVersions.value = true
  try {
    const response = await getDetectionModelVersionsApi()
    modelVersionList.value = response.items || []
    const selectedStillExists = modelVersionList.value.some((item) => item.id === selectedModelVersionId.value)
    if (!selectedStillExists) {
      selectedModelVersionId.value = (
        modelVersionList.value.find((item) => item.is_default)?.id
        || modelVersionList.value[0]?.id
        || null
      )
    }
  } catch {
    modelVersionList.value = []
    selectedModelVersionId.value = null
  } finally {
    loadingModelVersions.value = false
  }
}

async function switchDetectionModel() {
  const model = selectedModelVersion.value
  if (!model || model.is_default || !model.file_exists) return
  await ElMessageBox.confirm(
    `确定将 ${model.version} 设为场景“${model.scene_name || model.scene_id}”的检测使用版本吗？`,
    '切换检测模型',
    { type: 'warning', confirmButtonText: '切换', cancelButtonText: '取消' },
  )
  switchingModelVersionId.value = model.id
  try {
    await setDefaultDetectionModelApi(model.id)
    ElMessage.success(`检测模型已切换为 ${model.version}`)
    await fetchModelVersions()
    selectedModelVersionId.value = model.id
  } finally {
    switchingModelVersionId.value = null
  }
}

async function fetchTrainingDatasets() {
  loadingDatasets.value = true
  try {
    const response = await getDatasetVersionsApi({ limit: 500 })
    datasetList.value = response.items || []
  } catch {
    datasetList.value = []
  } finally {
    loadingDatasets.value = false
  }
}

function syncTrainDatasetScene(datasetId) {
  const dataset = datasetList.value.find((item) => item.id === datasetId)
  if (dataset) trainForm.value.scene_id = dataset.scene_id
}

function syncImportDatasetScene(datasetId) {
  const dataset = datasetList.value.find((item) => item.id === datasetId)
  if (dataset) importForm.value.scene_id = dataset.scene_id
}

function openCreateTrainingDialog() {
  if (!trainableDatasets.value.length) {
    ElMessage.warning('请先在数据集版本页面登记并冻结一个数据集版本')
    return
  }
  if (!trainForm.value.dataset_version_id) {
    const preferred = trainableDatasets.value.find((item) => item.is_current) || trainableDatasets.value[0]
    trainForm.value.dataset_version_id = preferred.id
    trainForm.value.scene_id = preferred.scene_id
  }
  showCreateDialog.value = true
}

function openImportDialog() {
  if (!importableDatasets.value.length) {
    ElMessage.warning('请先登记并冻结一个数据集版本')
    return
  }
  if (!importForm.value.dataset_version_id) {
    const preferred = importableDatasets.value.find((item) => item.is_current) || importableDatasets.value[0]
    importForm.value.dataset_version_id = preferred.id
    importForm.value.scene_id = preferred.scene_id
  }
  showImportDialog.value = true
}

function trainDataset(dataset) {
  trainForm.value.dataset_version_id = dataset.id
  trainForm.value.scene_id = dataset.scene_id
  showCreateDialog.value = true
}

async function selectTask(task) {
  selectedTask.value = { ...task }
  latestMetric.value = null
  liveProgress.value = null
  await nextTick()
  initCharts()
  await refreshSelectedTask()
  startPolling()
}

async function refreshSelectedTask() {
  if (!selectedTask.value) return
  const taskId = selectedTask.value.id
  const previousStatus = selectedTask.value.status
  const [statusRes, metricsRes] = await Promise.all([
    getTrainingStatusApi(taskId),
    getTrainingMetricsApi(taskId),
  ])

  selectedTask.value = { ...selectedTask.value, ...(statusRes.task || {}) }
  latestMetric.value = statusRes.latest_metric || null
  liveProgress.value = statusRes.live_progress || null
  updateCharts(metricsRes.metrics || [])
  if (selectedTask.value.status !== previousStatus) {
    await Promise.all([fetchTrainingDatasets(), fetchModelVersions()])
  }
}

function initCharts() {
  if (lossChart) lossChart.dispose()
  if (metricChart) metricChart.dispose()
  if (lossChartRef.value) lossChart = echarts.init(lossChartRef.value)
  if (metricChartRef.value) metricChart = echarts.init(metricChartRef.value)
  updateCharts([])
}

function updateCharts(metrics) {
  const epochs = metrics.map((item) => item.epoch)
  if (lossChart) {
    lossChart.setOption({
      title: { text: '训练损失曲线', left: 'center', textStyle: { fontSize: 14 } },
      tooltip: { trigger: 'axis' },
      legend: { bottom: 0 },
      grid: { left: 56, right: 24, top: 52, bottom: 52 },
      xAxis: { type: 'category', name: 'Epoch', data: epochs },
      yAxis: { type: 'value', name: 'Loss' },
      series: [
        { name: 'Box Loss', type: 'line', smooth: true, data: metrics.map((m) => m.box_loss) },
        { name: 'Cls Loss', type: 'line', smooth: true, data: metrics.map((m) => m.cls_loss) },
        { name: 'DFL Loss', type: 'line', smooth: true, data: metrics.map((m) => m.dfl_loss) },
      ],
    })
  }

  if (metricChart) {
    metricChart.setOption({
      title: { text: '评估指标曲线', left: 'center', textStyle: { fontSize: 14 } },
      tooltip: { trigger: 'axis' },
      legend: { bottom: 0 },
      grid: { left: 56, right: 24, top: 52, bottom: 52 },
      xAxis: { type: 'category', name: 'Epoch', data: epochs },
      yAxis: { type: 'value', name: 'Score', min: 0, max: 1 },
      series: [
        { name: 'mAP@50', type: 'line', smooth: true, data: metrics.map((m) => m.map50) },
        { name: 'mAP@50-95', type: 'line', smooth: true, data: metrics.map((m) => m.map50_95) },
        { name: 'Precision', type: 'line', smooth: true, data: metrics.map((m) => m.precision) },
        { name: 'Recall', type: 'line', smooth: true, data: metrics.map((m) => m.recall) },
      ],
    })
  }
}

function startPolling() {
  stopPolling()
  pollTimer = window.setInterval(async () => {
    try {
      await refreshSelectedTask()
      if (!['pending', 'running'].includes(selectedTask.value?.status)) {
        stopPolling()
        await fetchTasks()
      }
    } catch {
      stopPolling()
    }
  }, 5000)
}

function stopPolling() {
  if (pollTimer) {
    window.clearInterval(pollTimer)
    pollTimer = null
  }
}

async function createTask() {
  if (!trainForm.value.dataset_version_id) {
    ElMessage.warning('请选择数据集版本')
    return
  }
  creating.value = true
  try {
    const payload = { ...trainForm.value }
    const checkoutAugment = payload.checkout_augment
    delete payload.checkout_augment
    if (checkoutAugment) {
      payload.augment_config = {
        degrees: 180,
        translate: 0.2,
        scale: 0.6,
        flipud: 0.5,
        fliplr: 0.5,
        mosaic: 1.0,
        mixup: 0.1,
        close_mosaic: 10,
      }
    }
    const task = await startTrainingApi(payload)
    ElMessage.success(`训练任务已创建：${task.task_uuid}`)
    showCreateDialog.value = false
    await Promise.all([fetchTasks(), fetchTrainingDatasets(), fetchModelVersions()])
    const created = taskList.value.find((item) => item.id === task.id)
    await selectTask(created || task)
  } finally {
    creating.value = false
  }
}


async function submitImportRun() {
  if (!importForm.value.dataset_version_id) {
    ElMessage.warning('请选择离线训练实际使用的数据集版本')
    return
  }
  importing.value = true
  try {
    const payload = { ...importForm.value }
    Object.keys(payload).forEach((key) => {
      if (payload[key] === '' || payload[key] == null) delete payload[key]
    })
    const result = await importTrainingRunApi(payload)
    ElMessage.success(`已导入 ${result.metrics_imported || 0} 个 epoch 指标`)
    showImportDialog.value = false
    await Promise.all([fetchTasks(), fetchTrainingDatasets(), fetchModelVersions()])
    if (result.task) await selectTask(result.task)
  } finally {
    importing.value = false
  }
}

async function stopTask(taskId) {
  await ElMessageBox.confirm('确定要停止当前训练任务吗？', '确认停止', { type: 'warning' })
  await stopTrainingApi(taskId)
  ElMessage.success('训练任务已停止')
  await Promise.all([fetchTasks(), fetchTrainingDatasets()])
  if (selectedTask.value?.id === taskId) {
    await refreshSelectedTask()
  }
}

async function downloadResults(taskUuid) {
  const blob = await downloadTrainingResultsApi(taskUuid)
  const url = window.URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `training_results_${taskUuid}.csv`
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  window.URL.revokeObjectURL(url)
}

async function downloadWeights(task) {
  const blob = await downloadTrainingModelApi(task.id)
  const url = window.URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `${task.model_name}_${task.task_uuid}_best.pt`
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  window.URL.revokeObjectURL(url)
}

async function openEvalDrawer(task) {
  evalTask.value = { ...task }
  evalReport.value = null
  evalForm.value.device = singleDevice(task.device)
  showEvalDrawer.value = true
  await runEvaluation()
}

async function runEvaluation() {
  if (!evalTask.value) return
  evaluating.value = true
  try {
    evalReport.value = await validateTrainingTaskApi(evalTask.value.id, { ...evalForm.value })
    ElMessage.success('评估报告已生成')
  } finally {
    evaluating.value = false
  }
}

function openExportDialog(task) {
  exportTask.value = { ...task }
  exportForm.value = {
    version: defaultVersion(),
    description: '',
    set_default: true,
  }
  showExportDialog.value = true
}

async function submitExport() {
  if (!exportTask.value) return
  exporting.value = true
  try {
    const result = await exportTrainingModelApi(exportTask.value.id, { ...exportForm.value })
    ElMessage.success('模型版本已导出')
    showExportDialog.value = false
    await fetchModelVersions()
    if (result.model_version?.id) selectedModelVersionId.value = result.model_version.id
  } finally {
    exporting.value = false
  }
}

function openPredictDialog(task) {
  predictTask.value = { ...task }
  predictForm.value.device = singleDevice(task.device)
  predictResult.value = null
  showPredictDialog.value = true
}

function onPredictFileChange(event) {
  const file = event.target.files?.[0]
  if (predictPreview.value) {
    window.URL.revokeObjectURL(predictPreview.value)
  }
  predictFile.value = file || null
  predictResult.value = null
  predictPreview.value = file ? window.URL.createObjectURL(file) : ''
}

async function runPredict() {
  if (!predictTask.value || !predictFile.value) return
  const formData = new FormData()
  formData.append('task_id', predictTask.value.id)
  formData.append('conf', predictForm.value.conf)
  formData.append('iou', predictForm.value.iou)
  formData.append('device', predictForm.value.device || 'cpu')
  formData.append('file', predictFile.value)

  predicting.value = true
  try {
    predictResult.value = await predictTrainingImageApi(formData)
    ElMessage.success(`检测完成：${predictResult.value.total_objects} 个目标`)
  } finally {
    predicting.value = false
  }
}

function clearPredictState() {
  if (predictPreview.value) {
    window.URL.revokeObjectURL(predictPreview.value)
  }
  predictFile.value = null
  predictPreview.value = ''
  predictResult.value = null
}

async function openLogDrawer(task) {
  logTask.value = { ...task }
  logLines.value = []
  logPath.value = task.log_path || ''
  logExists.value = false
  showLogDrawer.value = true
  await refreshLog()
  startLogPolling()
}

async function refreshLog() {
  if (!logTask.value) return
  loadingLog.value = true
  try {
    const res = await getTrainingLogApi(logTask.value.id, 500)
    logExists.value = Boolean(res.exists)
    logPath.value = res.path || logTask.value.log_path || ''
    logLines.value = res.lines || []
    await nextTick()
    if (logContentRef.value) {
      logContentRef.value.scrollTop = logContentRef.value.scrollHeight
    }
  } finally {
    loadingLog.value = false
  }
}

function startLogPolling() {
  stopLogPolling()
  logPollTimer = window.setInterval(async () => {
    if (!showLogDrawer.value || !autoRefreshLog.value) return
    try {
      await refreshLog()
    } catch {
      stopLogPolling()
    }
  }, 3000)
}

function stopLogPolling() {
  if (logPollTimer) {
    window.clearInterval(logPollTimer)
    logPollTimer = null
  }
}

function resizeCharts() {
  lossChart?.resize()
  metricChart?.resize()
}

onMounted(() => {
  fetchTasks()
  fetchTrainingDatasets()
  fetchModelVersions()
  window.addEventListener('resize', resizeCharts)
})

onBeforeUnmount(() => {
  stopPolling()
  stopLogPolling()
  clearPredictState()
  window.removeEventListener('resize', resizeCharts)
  lossChart?.dispose()
  metricChart?.dispose()
})
</script>

<style scoped lang="scss">
.training-page {
  display: flex;
  flex-direction: column;
  gap: 18px;
  min-height: 100%;
  padding: 32px;
  color: $text-primary;
  background: $bg-color;
}

.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
  padding: 8px 0 14px;

  h2 {
    margin: 10px 0 0;
    font-family: 'Space Grotesk', 'DM Sans', sans-serif;
    font-size: 40px;
    line-height: 1.08;
    color: $text-primary;
    letter-spacing: 0;
  }

  p {
    max-width: 560px;
    margin: 12px 0 0;
    color: $text-secondary;
    font-size: 16px;
    line-height: 1.6;
  }
}

.page-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}

.panel {
  padding: 20px;
  background: $surface-color;
  border: 1px solid $border-color;
  border-radius: $border-radius-md;
  box-shadow: $shadow-sm;
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 14px;
  font-weight: 600;
  color: $text-primary;

  small {
    display: block;
    margin-top: 5px;
    color: $text-secondary;
    font-size: 12px;
    font-weight: 400;
  }
}

.detection-model-panel {
  background: linear-gradient(135deg, rgba(47, 111, 223, 0.06), $surface-color 42%);
}

.model-version-selector {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 12px;

  .el-select {
    width: 100%;
  }
}

.model-version-detail {
  margin-top: 14px;
  padding: 16px;
  border: 1px solid #d9e5fb;
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.72);
}

.model-version-main {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 14px;
  margin-bottom: 14px;

  span,
  strong {
    display: block;
  }

  span {
    color: $text-secondary;
    font-size: 12px;
  }

  strong {
    margin-top: 4px;
    font-size: 20px;
  }
}

.model-version-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;

  > div {
    min-width: 0;
    padding: 10px 12px;
    border-radius: 9px;
    background: $surface-muted;
  }

  span,
  strong {
    display: block;
  }

  span {
    color: $text-secondary;
    font-size: 11px;
  }

  strong {
    margin-top: 5px;
    overflow-wrap: anywhere;
    font-size: 13px;
    line-height: 1.45;
  }
}

.model-path-row {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: 10px;
  margin-top: 12px;
  color: $text-secondary;
  font-size: 12px;

  code {
    min-width: 0;
    overflow: hidden;
    color: #42526e;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
}

.model-description {
  margin: 10px 0 0;
  color: $text-secondary;
  font-size: 12px;
  line-height: 1.6;
}

.dataset-version-panel {
  :deep(.el-table__header th) {
    background: $surface-muted;
    color: $text-secondary;
    font-weight: 800;
  }

  code {
    color: $text-secondary;
    font: 12px/1.4 Consolas, 'Courier New', monospace;
  }
}

.dataset-version-cell {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;

  strong {
    color: $text-primary;
  }

  span:last-child {
    flex-basis: 100%;
    color: $text-secondary;
    font-size: 12px;
  }
}

.monitor-header {
  align-items: flex-start;

  > div:first-child {
    display: flex;
    align-items: center;
    gap: 8px;
  }
}

.monitor-meta {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 12px;
  font-size: 13px;
  font-weight: 400;
  color: $text-secondary;
}

.device-field {
  width: 100%;

  .el-select {
    width: 100%;
  }
}

.form-tip {
  margin: 6px 0 0;
  font-size: 12px;
  line-height: 1.5;
  color: $text-secondary;
}

.log-toolbar {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 12px;
}

.log-meta {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
  color: $text-secondary;
  font-size: 13px;

  span {
    overflow-wrap: anywhere;
  }
}

.log-actions {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-shrink: 0;
}

.log-content {
  height: calc(100vh - 190px);
  margin: 0;
  padding: 12px;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-word;
  color: #d7e1ef;
  background: $bg-color-dark;
  border-radius: $border-radius-sm;
  font: 12px/1.6 Consolas, 'Courier New', monospace;
}

.eval-toolbar,
.eval-actions,
.predict-summary {
  display: flex;
  align-items: center;
  gap: 12px;
}

.eval-toolbar {
  justify-content: space-between;
  margin-bottom: 16px;
}

.eval-actions {
  flex-wrap: wrap;
  justify-content: flex-end;

  .el-select {
    width: 90px;
  }
}

.eval-columns {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
  margin-top: 16px;
}

.eval-section,
.predict-panel {
  padding: 14px;
  border: 1px solid $border-color;
  border-radius: $border-radius-sm;
  background: $surface-color;

  h3 {
    margin: 0 0 12px;
    font-size: 15px;
    color: $text-primary;
  }
}

.artifact-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin: 0;
  padding: 0;
  list-style: none;

  li {
    display: flex;
    flex-direction: column;
    gap: 4px;
    min-width: 0;
  }

  strong {
    color: $text-primary;
  }

  span {
    color: $text-secondary;
    overflow-wrap: anywhere;
  }
}

.predict-layout {
  display: grid;
  grid-template-columns: 280px minmax(0, 1fr);
  gap: 16px;
}

.predict-controls,
.predict-form {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.file-input {
  width: 100%;
}

.preview-image,
.result-image {
  display: block;
  width: 100%;
  max-height: 360px;
  margin-top: 12px;
  object-fit: contain;
  border: 1px solid $border-color;
  border-radius: $border-radius-sm;
  background: $surface-muted;
}

.predict-summary {
  justify-content: space-between;
  margin-bottom: 12px;
  color: $text-secondary;
}

.task-table {
  width: 100%;
}

.live-progress-panel {
  margin-bottom: 14px;
  padding: 12px;
  border: 1px solid #ebeef5;
  border-radius: $border-radius-sm;
  background: #fafafa;
}

.live-progress-header,
.live-progress-meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.live-progress-header {
  margin-bottom: 10px;
  font-weight: 600;
  color: $text-primary;
}

.live-progress-meta {
  flex-wrap: wrap;
  margin-top: 8px;
  color: $text-secondary;
  font-size: 12px;
}

.monitor-progress {
  margin-bottom: 0;
}

.tqdm-line {
  margin: 10px 0 0;
  padding: 8px;
  overflow-x: auto;
  color: #d7e1ef;
  background: #111827;
  border-radius: $border-radius-sm;
  font: 12px/1.5 Consolas, 'Courier New', monospace;
}

.metric-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(112px, 1fr));
  gap: 12px;
}

.metric-card {
  min-height: 72px;
  padding: 14px;
  border: 1px solid $border-color;
  border-radius: $border-radius-sm;
  background: $surface-muted;

  span {
    display: block;
    color: $text-secondary;
    font-size: 12px;
  }

  strong {
    display: block;
    margin-top: 8px;
    font-size: 20px;
    color: $text-primary;
  }
}

.chart-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
  margin-top: 16px;
}

.chart {
  min-height: 340px;
  border: 1px solid $border-color;
  border-radius: $border-radius-sm;
  background: $surface-color;
}

.empty-monitor {
  padding: 32px 0;
  background: $surface-color;
  border: 1px solid $border-color;
  border-radius: $border-radius-md;
  box-shadow: $shadow-sm;
}

.task-table :deep(.el-table__header th) {
  background: $surface-muted;
  color: $text-secondary;
  font-weight: 800;
}

.task-table :deep(.el-table__row:hover > td.el-table__cell) {
  background: $primary-soft;
}

@media (max-width: 1100px) {
  .metric-grid,
  .chart-grid,
  .eval-columns,
  .predict-layout {
    grid-template-columns: 1fr;
  }

  .model-version-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 760px) {
  .training-page {
    padding: 20px;
  }

  .page-header {
    align-items: flex-start;
    flex-direction: column;

    h2 {
      font-size: 30px;
    }
  }

  .model-version-selector,
  .model-version-grid,
  .model-path-row {
    grid-template-columns: 1fr;
  }
}
</style>
