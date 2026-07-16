<template>
  <div class="dataset-page">
    <header class="page-header">
      <div>
        <span class="vp-kicker">Dataset Registry</span>
        <h2>数据集版本管理</h2>
        <p>登记数据集元数据和类别映射，冻结后形成不可变版本，并记录训练与模型谱系。</p>
      </div>
      <div class="header-actions">
        <el-button :icon="UploadFilled" @click="openModelImportDialog">导入可用模型</el-button>
        <el-button @click="openBaselineDialog">导入基线 dataset</el-button>
        <el-button type="primary" :icon="Plus" @click="openCreateDialog">新建数据集草稿</el-button>
      </div>
    </header>

    <section class="summary-grid">
      <article class="summary-card current-card">
        <span>当前版本</span>
        <strong>{{ currentDataset?.version || '未设置' }}</strong>
        <small>{{ currentDataset?.name || '冻结版本后可设为当前版本' }}</small>
      </article>
      <article class="summary-card">
        <span>版本总数</span>
        <strong>{{ total }}</strong>
        <small>当前筛选结果 {{ rows.length }} 条</small>
      </article>
      <article class="summary-card">
        <span>草稿</span>
        <strong>{{ statusCount.draft }}</strong>
        <small>仍可编辑和补充类别映射</small>
      </article>
      <article class="summary-card">
        <span>已冻结</span>
        <strong>{{ statusCount.ready }}</strong>
        <small>内容不可修改，可设为当前版本</small>
      </article>
    </section>

    <section class="panel">
      <div class="toolbar">
        <div class="filters">
          <el-input-number
            v-model="filters.scene_id"
            :min="1"
            controls-position="right"
            placeholder="场景 ID"
          />
          <el-select v-model="filters.status" clearable placeholder="全部状态">
            <el-option label="草稿" value="draft" />
            <el-option label="已冻结" value="ready" />
            <el-option label="已归档" value="archived" />
          </el-select>
          <el-button type="primary" plain @click="fetchDatasets">查询</el-button>
          <el-button @click="resetFilters">重置</el-button>
        </div>
        <div class="toolbar-actions">
          <el-tooltip content="仅当后端运行在真实数据所在集群时开启">
            <el-checkbox v-model="checkFilesystem">校验集群目录</el-checkbox>
          </el-tooltip>
          <el-button :icon="Refresh" :loading="loading" @click="fetchDatasets">刷新</el-button>
        </div>
      </div>

      <el-table v-loading="loading" :data="rows" stripe class="dataset-table" empty-text="暂无数据集版本">
        <el-table-column label="版本" min-width="180">
          <template #default="{ row }">
            <div class="version-cell">
              <div class="version-title">
                <strong>{{ row.version }}</strong>
                <el-tag v-if="row.extra_metadata?.catalog_only" type="primary" size="small" effect="plain" round>
                  模型目录
                </el-tag>
                <el-tag v-if="row.is_current" class="current-version-tag" type="success" size="small" effect="plain" round>
                  当前版本
                </el-tag>
              </div>
              <span class="version-name">{{ row.name }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="scene_id" label="场景" width="130">
          <template #default="{ row }">
            <span>{{ row.scene_name || `#${row.scene_id}` }}</span>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="statusType(row.status)" size="small">{{ statusText(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="图片" width="170">
          <template #default="{ row }">
            <div v-if="row.extra_metadata?.catalog_only" class="split-cell">
              <strong>无需训练集</strong>
              <span>从 best.pt 读取类别</span>
            </div>
            <div v-else class="split-cell">
              <strong>{{ row.total_image_count }}</strong>
              <span>T {{ row.train_image_count }} · V {{ row.val_image_count }} · E {{ row.test_image_count }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="class_count" label="类别" width="82" align="center" />
        <el-table-column label="内容指纹" min-width="160">
          <template #default="{ row }">
            <code :title="row.content_hash || ''">{{ shortHash(row.content_hash) }}</code>
          </template>
        </el-table-column>
        <el-table-column label="更新时间" width="170">
          <template #default="{ row }">{{ formatTime(row.updated_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="500" fixed="right">
          <template #default="{ row }">
            <div class="row-actions">
              <el-button class="row-action-button" size="small" :icon="View" @click="openDetail(row)">详情</el-button>
              <el-button v-if="row.status === 'draft'" class="row-action-button" size="small" :icon="Edit" @click="openEditDialog(row)">编辑</el-button>
              <el-button v-if="row.status === 'draft'" class="row-action-button is-primary-action" size="small" :icon="Plus" @click="openAddProductDialog(row)">添加样本</el-button>
              <el-button v-if="row.status === 'draft'" class="row-action-button is-danger-action" size="small" :icon="Delete" @click="openDeleteProductDialog(row)">删除商品</el-button>
              <el-button v-if="row.status === 'draft'" class="row-action-button" size="small" :icon="CircleCheck" @click="validateRow(row)">校验</el-button>
              <el-button v-if="row.status === 'draft'" class="row-action-button is-primary-action" size="small" :icon="Lock" @click="freezeRow(row)">冻结</el-button>
              <el-button v-if="row.status === 'ready' && !row.is_current" class="row-action-button is-success-action" size="small" :icon="Promotion" @click="setCurrent(row)">设为当前</el-button>
              <el-button v-if="row.status === 'ready' && !row.is_current" class="row-action-button" size="small" @click="archiveRow(row)">归档</el-button>
              <el-button v-if="['ready', 'archived'].includes(row.status)" class="row-action-button is-primary-action" size="small" @click="openDeriveDialog(row)">派生版本</el-button>
              <el-button v-if="row.status === 'draft'" class="row-action-button is-danger-action" size="small" :icon="Delete" @click="deleteRow(row)">删除草稿</el-button>
            </div>
          </template>
        </el-table-column>
      </el-table>
    </section>

    <el-dialog
      v-model="dialogVisible"
      :title="editingId ? '编辑数据集草稿' : '新建数据集草稿'"
      class="dataset-editor-dialog"
      width="960px"
      top="4vh"
      :close-on-click-modal="false"
      destroy-on-close
    >
      <el-form ref="formRef" :model="form" :rules="rules" label-width="108px">
        <div class="form-grid">
          <el-form-item label="场景 ID" prop="scene_id">
            <el-input-number v-model="form.scene_id" :min="1" :disabled="Boolean(editingId)" controls-position="right" />
          </el-form-item>
          <el-form-item label="父版本 ID" prop="parent_id">
            <el-input-number v-model="form.parent_id" :min="1" clearable controls-position="right" />
          </el-form-item>
          <el-form-item label="版本号" prop="version">
            <el-input v-model="form.version" placeholder="例如 v2026.07.01" />
          </el-form-item>
          <el-form-item label="显示名称" prop="name">
            <el-input v-model="form.name" placeholder="例如 便利店商品集 2026-07" />
          </el-form-item>
        </div>

        <el-form-item label="版本根目录" prop="storage_path">
          <el-input v-model="form.storage_path" placeholder="/cluster/datasets/vision_pay/v000001 或 s3://..." />
        </el-form-item>
        <el-form-item label="data.yaml" prop="data_yaml_path">
          <el-input v-model="form.data_yaml_path" placeholder="data.yaml 或完整路径" />
        </el-form-item>
        <el-form-item label="manifest">
          <el-input v-model="form.manifest_path" placeholder="manifest.json，可稍后补充" />
        </el-form-item>
        <el-form-item label="内容指纹">
          <el-input v-model="form.content_hash" placeholder="sha256:...，冻结前必填" />
        </el-form-item>

        <el-divider content-position="left">数据规模</el-divider>
        <div class="count-grid">
          <el-form-item label="类别数"><el-input-number v-model="form.class_count" :min="0" /></el-form-item>
          <el-form-item label="训练图片"><el-input-number v-model="form.train_image_count" :min="0" /></el-form-item>
          <el-form-item label="验证图片"><el-input-number v-model="form.val_image_count" :min="0" /></el-form-item>
          <el-form-item label="测试图片"><el-input-number v-model="form.test_image_count" :min="0" /></el-form-item>
          <el-form-item label="训练标注"><el-input-number v-model="form.train_annotation_count" :min="0" /></el-form-item>
          <el-form-item label="验证标注"><el-input-number v-model="form.val_annotation_count" :min="0" /></el-form-item>
          <el-form-item label="测试标注"><el-input-number v-model="form.test_annotation_count" :min="0" /></el-form-item>
        </div>

        <el-form-item label="类别映射 JSON" class="mapping-field">
          <el-input
            v-model="classMappingText"
            type="textarea"
            :rows="9"
            spellcheck="false"
            placeholder='[{"class_index":0,"product_key":"sku-001","category_id":1,"class_name":"product_1","display_name":"商品一"}]'
          />
          <p class="form-tip">class_index 必须从 0 连续排列；product_key 在版本间保持稳定。集群注册脚本后续可直接调用同一 API 批量填写。</p>
        </el-form-item>
        <el-form-item label="版本说明">
          <el-input v-model="form.description" type="textarea" :rows="3" />
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="submitForm">保存草稿</el-button>
      </template>
    </el-dialog>

    <el-drawer v-model="detailVisible" title="数据集版本详情" size="720px">
      <template v-if="detail">
        <div class="detail-heading">
          <div>
            <span>{{ detail.scene_name || `场景 #${detail.scene_id}` }}</span>
            <h3>{{ detail.version }} · {{ detail.name }}</h3>
          </div>
          <el-tag :type="statusType(detail.status)">{{ statusText(detail.status) }}</el-tag>
        </div>
        <el-descriptions :column="2" border>
          <el-descriptions-item label="当前版本">{{ detail.is_current ? '是' : '否' }}</el-descriptions-item>
          <el-descriptions-item label="父版本">{{ detail.parent_version || '-' }}</el-descriptions-item>
          <el-descriptions-item label="类别数">{{ detail.class_count }}</el-descriptions-item>
          <el-descriptions-item label="图片总数">{{ detail.total_image_count }}</el-descriptions-item>
          <el-descriptions-item label="标注总数">{{ detail.total_annotation_count }}</el-descriptions-item>
          <el-descriptions-item label="创建人">{{ detail.creator_name || `#${detail.created_by}` }}</el-descriptions-item>
          <el-descriptions-item label="版本目录" :span="2">{{ detail.storage_path }}</el-descriptions-item>
          <el-descriptions-item label="data.yaml" :span="2">{{ detail.data_yaml_path }}</el-descriptions-item>
          <el-descriptions-item label="内容指纹" :span="2">{{ detail.content_hash || '-' }}</el-descriptions-item>
          <el-descriptions-item label="说明" :span="2">{{ detail.description || '-' }}</el-descriptions-item>
        </el-descriptions>

        <div v-if="detail.validation_report" class="validation-box" :class="{ invalid: !detail.validation_report.valid }">
          <strong>{{ detail.validation_report.valid ? '最近一次校验通过' : '最近一次校验未通过' }}</strong>
          <span>{{ detail.validation_report.checked_filesystem ? '已检查集群目录' : '仅逻辑校验' }}</span>
          <ul v-if="detail.validation_report.errors?.length">
            <li v-for="item in detail.validation_report.errors" :key="item">{{ item }}</li>
          </ul>
        </div>

        <div class="mapping-header">
          <h4>类别映射快照</h4>
          <span>{{ detail.classes.length }} 条</span>
        </div>
        <el-table :data="detail.classes" border height="420" empty-text="尚未登记类别映射">
          <el-table-column prop="class_index" label="class_id" width="88" />
          <el-table-column prop="product_id" label="product_id" width="100" />
          <el-table-column prop="product_key" label="商品键" min-width="130" show-overflow-tooltip />
          <el-table-column prop="category_id" label="原类别 ID" width="100" />
          <el-table-column prop="class_name" label="类别名" min-width="150" show-overflow-tooltip />
          <el-table-column prop="display_name" label="显示名" min-width="130" show-overflow-tooltip />
        </el-table>
      </template>
    </el-drawer>

    <el-dialog
      v-model="modelImportVisible"
      title="导入可用模型"
      width="680px"
      :close-on-click-modal="false"
      destroy-on-close
    >
      <el-alert
        title="适用于已有 best.pt、无需在本系统重新训练的场景"
        description="系统会读取模型内置的类别名称，自动建立模型目录版本、稳定商品映射和价目表入口。请只导入来源可信的 YOLO 目标检测模型。"
        type="info"
        :closable="false"
        show-icon
      />
      <el-form :model="modelImportForm" label-width="118px" class="model-import-form">
        <el-form-item label="场景 ID" required>
          <el-input-number v-model="modelImportForm.scene_id" :min="1" controls-position="right" />
        </el-form-item>
        <el-form-item label="版本号" required>
          <el-input v-model.trim="modelImportForm.version" placeholder="例如 checkout-model-v1" />
        </el-form-item>
        <el-form-item label="显示名称" required>
          <el-input v-model.trim="modelImportForm.name" placeholder="例如 收银检测模型 v1" />
        </el-form-item>
        <el-form-item label="模型来源" required>
          <el-radio-group v-model="modelImportForm.source_mode" @change="handleModelSourceModeChange">
            <el-radio-button value="upload">上传 best.pt</el-radio-button>
            <el-radio-button value="path">服务器文件路径</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-form-item v-if="modelImportForm.source_mode === 'upload'" label="best.pt" required>
          <el-upload
            ref="modelImportUploadRef"
            class="model-import-upload"
            drag
            action="#"
            accept=".pt"
            :auto-upload="false"
            :limit="1"
            :on-change="handleModelFileChange"
            :on-remove="handleModelFileRemove"
            :on-exceed="handleModelFileExceed"
          >
            <el-icon class="el-icon--upload"><UploadFilled /></el-icon>
            <div class="el-upload__text">拖放 best.pt 到这里，或<em>点击选择</em></div>
          </el-upload>
        </el-form-item>
        <el-form-item v-else label="文件路径" required>
          <el-input
            v-model.trim="modelImportForm.source_path"
            placeholder="例如 D:\\models\\best.pt 或 /opt/models/best.pt"
          />
          <p class="form-tip">路径必须能被后端所在机器访问；浏览器所在电脑与后端是同一台机器时可直接填写本机绝对路径。</p>
        </el-form-item>
        <el-form-item label="导入后启用">
          <div class="model-import-switches">
            <el-checkbox v-model="modelImportForm.set_current">设为当前数据集版本</el-checkbox>
            <el-checkbox v-model="modelImportForm.set_default">设为当前检测模型</el-checkbox>
          </div>
        </el-form-item>
        <el-form-item label="说明">
          <el-input v-model="modelImportForm.description" type="textarea" :rows="3" placeholder="可填写模型来源、适用范围等信息" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="modelImportVisible = false">取消</el-button>
        <el-button type="primary" :loading="modelImportSubmitting" @click="submitModelImport">开始导入</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="baselineVisible" title="导入基线 dataset" width="640px" :close-on-click-modal="false">
      <el-form :model="baselineForm" label-width="120px">
        <el-form-item label="场景 ID"><el-input-number v-model="baselineForm.scene_id" :min="1" /></el-form-item>
        <el-form-item label="源目录"><el-input v-model="baselineForm.source_path" placeholder="datasets/vision_pay 或集群绝对路径" /></el-form-item>
        <el-form-item label="版本号"><el-input v-model="baselineForm.version" placeholder="baseline-v1" /></el-form-item>
        <el-form-item label="显示名称"><el-input v-model="baselineForm.name" /></el-form-item>
        <el-form-item label="复制为托管版本"><el-switch v-model="baselineForm.copy_files" /></el-form-item>
        <el-form-item label="设为当前"><el-switch v-model="baselineForm.set_current" /></el-form-item>
        <el-alert title="导入会扫描 data.yaml、图片和 YOLO 标注，创建稳定 product_id/product_key 及 manifest 索引。" type="info" :closable="false" />
      </el-form>
      <template #footer>
        <el-button @click="baselineVisible = false">取消</el-button>
        <el-button type="primary" :loading="workspaceSubmitting" @click="submitBaseline">开始导入</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="deriveVisible" title="新建派生版本" width="560px">
      <el-form :model="deriveForm" label-width="100px">
        <el-form-item label="父版本"><el-input :model-value="deriveParent?.version || ''" disabled /></el-form-item>
        <el-form-item label="版本号"><el-input v-model="deriveForm.version" /></el-form-item>
        <el-form-item label="名称"><el-input v-model="deriveForm.name" /></el-form-item>
        <el-form-item label="说明"><el-input v-model="deriveForm.description" type="textarea" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="deriveVisible = false">取消</el-button>
        <el-button type="primary" :loading="workspaceSubmitting" @click="submitDerive">创建派生版本</el-button>
      </template>
    </el-dialog>

    <el-dialog
      v-model="addProductVisible"
      :title="`添加样本 · ${productDataset?.version || ''}`"
      class="annotation-review-dialog"
      width="1180px"
      top="3vh"
      destroy-on-close
      :close-on-click-modal="false"
      @closed="handleAddProductClosed"
    >
      <el-form ref="productFormRef" :model="productForm" :rules="productRules" label-width="108px" class="product-setup-form">
        <el-form-item label="样本类型" prop="mode" required>
          <el-radio-group v-model="productForm.mode" :disabled="Boolean(annotationStage)" @change="resetSampleFiles">
            <el-radio-button value="train_new">新建商品训练图</el-radio-button>
            <el-radio-button value="train_existing">已有商品训练图</el-radio-button>
            <el-radio-button value="scene">val/test 结账场景</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <div v-if="productForm.mode === 'train_new'" class="product-setup-grid">
          <el-form-item label="商品名称" prop="name" required><el-input v-model="productForm.name" :disabled="Boolean(annotationStage)" /></el-form-item>
          <el-form-item label="类别名称" prop="class_name" required><el-input v-model="productForm.class_name" :disabled="Boolean(annotationStage)" placeholder="模型类别英文名" /></el-form-item>
          <el-form-item label="价格" prop="unit_price" required><el-input-number v-model="productForm.unit_price" :disabled="Boolean(annotationStage)" :min="0" :precision="2" /></el-form-item>
          <el-form-item label="商品条码"><el-input v-model="productForm.barcode" :disabled="Boolean(annotationStage)" clearable /></el-form-item>
        </div>
        <el-form-item v-else-if="productForm.mode === 'train_existing'" label="已有商品" prop="existing_product_id" required>
          <el-select v-model="productForm.existing_product_id" filterable :disabled="Boolean(annotationStage)" placeholder="搜索并选择 train 中已有商品" style="width: 100%">
            <el-option
              v-for="item in availableProducts"
              :key="item.product_id"
              :label="`${item.display_name || item.class_name} · class_id ${item.class_index} · product_id ${item.product_id}`"
              :value="item.product_id"
            />
          </el-select>
        </el-form-item>
        <div class="split-folder-grid">
          <div
            v-for="split in sampleSplitOptions"
            :key="split.value"
            class="split-folder-card"
            :class="{ invalid: sampleFolderError }"
          >
            <div class="split-folder-heading">
              <strong><span v-if="split.required" class="required-star">*</span>{{ split.label }}</strong>
              <span>{{ split.required ? '必填' : '可选' }}</span>
            </div>
            <label class="folder-select-button" :class="{ disabled: Boolean(annotationStage) }">
              <input
                class="folder-input"
                type="file"
                accept="image/*"
                :aria-label="`选择${split.label}`"
                webkitdirectory
                directory
                multiple
                :disabled="Boolean(annotationStage)"
                @change="setProductSplitFolder(split.value, $event)"
              />
              <span>{{ annotationStage ? '审核期间不能更换' : `选择${split.label}` }}</span>
            </label>
            <div class="split-folder-summary">
              <strong>{{ productFolderInfo[split.value].folderName || '未选择' }}</strong>
              <span>
                {{ productFiles[split.value].length }} 张 · {{ formatBytes(productFolderInfo[split.value].totalBytes) }}
                <template v-if="productFolderInfo[split.value].ignoredCount"> · 已忽略 {{ productFolderInfo[split.value].ignoredCount }} 个非图片文件</template>
              </span>
            </div>
            <div v-if="sampleFolderError" class="folder-error">{{ sampleFolderError }}</div>
          </div>
        </div>
        <el-alert
          v-if="!annotationStage"
          :title="productForm.mode === 'scene' ? '上传多商品结账场景' : '上传单一商品的多角度训练图'"
          :description="productForm.mode === 'scene'
            ? '只能选择 val 和/或 test 文件夹。请为每个商品手动画框，并从当前 train 商品目录中选择对应商品；不允许出现未知商品。'
            : '只能选择 train 文件夹。每张图应只有当前这一种商品，可包含该商品的不同拍摄角度；所有检测框必须由用户手工绘制。'"
          type="info"
          :closable="false"
          show-icon
        />
      </el-form>

      <section v-if="annotationStage" class="annotation-review">
        <header class="review-heading">
          <div>
            <h3>人工绘制检测框</h3>
            <p>系统不再自动生成框。请逐张绘制普通矩形框，并确认标注。</p>
          </div>
          <div class="review-summary">
            <el-tag>{{ annotationSummary.total }} 张图片</el-tag>
            <el-tag type="success">{{ annotationSummary.boxes }} 个框</el-tag>
            <el-tag v-if="annotationSummary.pending" type="warning">待审核 {{ annotationSummary.pending }}</el-tag>
            <el-tag v-if="annotationSummary.missing" type="danger">缺少框 {{ annotationSummary.missing }}</el-tag>
          </div>
        </header>

        <div class="review-workspace">
          <aside class="annotation-thumbnails">
            <button
              v-for="(item, index) in annotationImages"
              :key="item.image_id"
              type="button"
              class="annotation-thumbnail"
              :class="{ active: index === activeAnnotationIndex, pending: !item.reviewed, missing: !item.boxes.length }"
              @click="activeAnnotationIndex = index"
            >
              <img :src="item.previewUrl" :alt="item.filename" />
              <span class="thumbnail-copy">
                <strong>{{ item.filename }}</strong>
                <small>{{ splitText(item.split) }} · {{ item.boxes.length }} 个框</small>
              </span>
              <el-tag size="small" :type="item.reviewed ? 'success' : item.boxes.length ? 'warning' : 'danger'">
                {{ item.reviewed ? '已确认' : item.boxes.length ? '待确认' : '需绘制' }}
              </el-tag>
            </button>
          </aside>

          <main v-if="activeAnnotationImage" class="annotation-editor-panel">
            <div class="active-image-heading">
              <div>
                <strong>{{ activeAnnotationImage.filename }}</strong>
                <span>{{ activeAnnotationImage.width }} × {{ activeAnnotationImage.height }} · {{ splitText(activeAnnotationImage.split) }}</span>
              </div>
              <el-tag :type="activeAnnotationImage.reviewed ? 'success' : 'warning'">{{ activeAnnotationImage.reviewed ? '已完成人工标注' : '待人工标注' }}</el-tag>
            </div>
            <DatasetBoxEditor
              :model-value="activeAnnotationImage.boxes"
              :image-url="activeAnnotationImage.previewUrl"
              :image-width="activeAnnotationImage.width"
              :image-height="activeAnnotationImage.height"
              :product-options="availableProducts"
              @update:model-value="updateActiveBoxes"
              @change="markActiveAnnotationReviewed"
            />
            <div v-if="productForm.mode === 'scene' && activeAnnotationImage.boxes.length" class="box-product-assignments">
              <div v-for="(box, boxIndex) in activeAnnotationImage.boxes" :key="boxIndex" class="box-product-row">
                <span>检测框 {{ boxIndex + 1 }}</span>
                <el-select v-model="box.product_id" filterable placeholder="选择该框中的商品" @change="markBoxProductChanged">
                  <el-option
                    v-for="item in availableProducts"
                    :key="item.product_id"
                    :label="`${item.display_name || item.class_name} · class_id ${item.class_index}`"
                    :value="item.product_id"
                  />
                </el-select>
              </div>
            </div>
            <div class="active-review-actions">
              <span v-if="!activeAnnotationImage.boxes.length">请在图片上拖动鼠标绘制至少一个检测框。</span>
              <span v-else-if="productForm.mode === 'scene' && activeImageUnassignedBoxes">还有 {{ activeImageUnassignedBoxes }} 个框没有选择商品。</span>
              <span v-else>确认所有框都准确覆盖商品后，点击确认当前图片。</span>
              <el-button
                type="success"
                :disabled="!canConfirmActiveImage || activeAnnotationImage.reviewed"
                @click="confirmActiveAnnotation"
              >
                {{ activeAnnotationImage.reviewed ? '当前图片已确认' : '确认当前检测框' }}
              </el-button>
            </div>
          </main>
        </div>
      </section>
      <template #footer>
        <el-button @click="addProductVisible = false">取消</el-button>
        <el-button v-if="annotationStage" :disabled="workspaceSubmitting" @click="restartAnnotationStage">重新选择图片</el-button>
        <el-button
          v-if="!annotationStage"
          type="primary"
          :loading="workspaceSubmitting"
          @click="generateProductAnnotations"
        >
          下一步
        </el-button>
        <el-button
          v-else
          type="primary"
          :loading="workspaceSubmitting"
          :disabled="annotationSummary.pending > 0 || annotationSummary.missing > 0 || unassignedBoxCount > 0"
          @click="submitAddProduct"
        >
          确认标注并添加样本
        </el-button>
      </template>
    </el-dialog>

    <el-dialog
      v-model="deleteProductVisible"
      :title="`删除商品 · ${deleteProductDataset?.version || ''}`"
      width="820px"
    >
      <el-alert
        title="删除商品会移除其全部标注并自动重排后续 class_id；多商品场景仍有其他有效框时会保留图片。"
        type="warning"
        :closable="false"
        show-icon
      />
      <el-input
        v-model="productSearch"
        class="product-search"
        :prefix-icon="Search"
        clearable
        placeholder="搜索 product_id、product_key、class_id、类别名或商品名称"
      />
      <div class="search-result-count">找到 {{ filteredDeleteProducts.length }} 个商品</div>
      <el-table :data="filteredDeleteProducts" border max-height="430" empty-text="没有匹配的商品">
        <el-table-column prop="class_index" label="class_id" width="88" />
        <el-table-column prop="product_id" label="product_id" width="100" />
        <el-table-column prop="product_key" label="product_key" min-width="180" show-overflow-tooltip />
        <el-table-column prop="class_name" label="类别名" min-width="140" show-overflow-tooltip />
        <el-table-column prop="display_name" label="商品名称" min-width="140" show-overflow-tooltip />
        <el-table-column label="操作" width="86" fixed="right">
          <template #default="{ row }">
            <el-button
              text
              type="danger"
              size="small"
              :loading="deletingProductId === row.product_id"
              @click="deleteProductMapping(deleteProductDataset, row)"
            >
              删除
            </el-button>
          </template>
        </el-table-column>
      </el-table>
      <template #footer>
        <el-button @click="deleteProductVisible = false">关闭</el-button>
      </template>
    </el-dialog>

    <el-dialog
      v-model="operationProgressVisible"
      :title="operationTask.title || '数据集操作进度'"
      width="540px"
      class="operation-progress-dialog"
      :close-on-click-modal="false"
      :close-on-press-escape="operationFinished"
      :show-close="operationFinished"
    >
      <div class="operation-progress-content">
        <div class="operation-progress-heading">
          <strong>{{ operationStatusText }}</strong>
          <span>{{ operationTask.progress }}%</span>
        </div>
        <el-progress
          :percentage="operationTask.progress"
          :status="operationProgressStatus"
          :stroke-width="14"
          :show-text="false"
          striped
          striped-flow
        />
        <p>{{ operationTask.message || '正在准备处理…' }}</p>
        <code v-if="operationTask.task_id">task_id: {{ operationTask.task_id }}</code>
        <el-alert
          v-if="operationTask.status === 'failed'"
          class="operation-error"
          title="操作未完成，请根据上方信息检查后重试"
          type="error"
          :closable="false"
          show-icon
        />
      </div>
      <template v-if="operationFinished" #footer>
        <el-button type="primary" @click="operationProgressVisible = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { CircleCheck, Delete, Edit, Lock, Plus, Promotion, Refresh, Search, UploadFilled, View } from '@element-plus/icons-vue'
import DatasetBoxEditor from '@/components/dataset/DatasetBoxEditor.vue'
import {
  annotationReviewSummary,
  attachFilesToStagedImages,
  buildDatasetProductCommitPayload,
} from '@/utils/datasetAnnotationReview'
import { collectProductFolderFiles } from '@/utils/datasetProductFiles'
import {
  archiveDatasetVersionApi,
  commitDatasetProductTaskApi,
  createDatasetVersionApi,
  deleteDatasetProductTaskApi,
  deleteDatasetVersionTaskApi,
  deriveDatasetVersionTaskApi,
  discardDatasetProductStageApi,
  freezeDatasetVersionApi,
  getDatasetOperationStatusApi,
  getDatasetVersionApi,
  getDatasetVersionsApi,
  importAvailableModelApi,
  importBaselineDatasetApi,
  setCurrentDatasetVersionApi,
  stageDatasetProductImagesApi,
  updateDatasetVersionApi,
  validateDatasetVersionApi,
} from '@/api/datasets'

const loading = ref(false)
const submitting = ref(false)
const rows = ref([])
const total = ref(0)
const checkFilesystem = ref(false)
const dialogVisible = ref(false)
const detailVisible = ref(false)
const editingId = ref(null)
const detail = ref(null)
const modelImportVisible = ref(false)
const modelImportSubmitting = ref(false)
const modelImportFile = ref(null)
const modelImportUploadRef = ref(null)
const baselineVisible = ref(false)
const deriveVisible = ref(false)
const addProductVisible = ref(false)
const deleteProductVisible = ref(false)
const workspaceSubmitting = ref(false)
const operationProgressVisible = ref(false)
const operationRunToken = ref(0)
const operationTask = ref({
  task_id: '',
  title: '',
  operation: '',
  status: 'pending',
  progress: 0,
  message: '',
  result: null,
})
const deriveParent = ref(null)
const productDataset = ref(null)
const deleteProductDataset = ref(null)
const productSearch = ref('')
const deletingProductId = ref(null)
const productFiles = ref({ train: [], val: [], test: [] })
const annotationStage = ref(null)
const annotationImages = ref([])
const activeAnnotationIndex = ref(0)
const emptyProductFolderInfo = () => ({
  folderName: '',
  ignoredCount: 0,
  totalBytes: 0,
})
const emptyProductFolderInfos = () => ({
  train: emptyProductFolderInfo(),
  val: emptyProductFolderInfo(),
  test: emptyProductFolderInfo(),
})
const productFolderInfo = ref(emptyProductFolderInfos())
const productFormRef = ref(null)
const baselineForm = ref({
  scene_id: 1,
  source_path: 'datasets/vision_pay',
  version: 'baseline-v1',
  name: 'VisionPay 基线数据集',
  description: '',
  copy_files: true,
  set_current: true,
})
const emptyModelImportForm = () => ({
  scene_id: 1,
  version: '',
  name: '',
  description: '',
  source_mode: 'upload',
  source_path: '',
  set_current: true,
  set_default: true,
})
const modelImportForm = ref(emptyModelImportForm())
const deriveForm = ref({ version: '', name: '', description: '' })
const emptyProductForm = () => ({
  mode: 'train_new',
  existing_product_id: null,
  name: '',
  class_name: '',
  unit_price: null,
  barcode: '',
})
const productForm = ref(emptyProductForm())
const formRef = ref(null)
const filters = ref({ scene_id: null, status: '' })

const emptyForm = () => ({
  scene_id: 1,
  parent_id: null,
  version: '',
  name: '',
  description: '',
  storage_path: '',
  data_yaml_path: 'data.yaml',
  manifest_path: 'manifest.json',
  content_hash: '',
  class_count: 0,
  train_image_count: 0,
  val_image_count: 0,
  test_image_count: 0,
  train_annotation_count: 0,
  val_annotation_count: 0,
  test_annotation_count: 0,
})

const form = ref(emptyForm())
const classMappingText = ref('[]')
const rules = {
  scene_id: [{ required: true, message: '请输入场景 ID', trigger: 'blur' }],
  version: [{ required: true, message: '请输入版本号', trigger: 'blur' }],
  name: [{ required: true, message: '请输入显示名称', trigger: 'blur' }],
  storage_path: [{ required: true, message: '请输入版本根目录', trigger: 'blur' }],
  data_yaml_path: [{ required: true, message: '请输入 data.yaml 路径', trigger: 'blur' }],
}
const productRules = computed(() => ({
  mode: [{ required: true, message: '请选择样本类型', trigger: 'change' }],
  name: productForm.value.mode === 'train_new' ? [{ required: true, whitespace: true, message: '请输入商品名称', trigger: ['blur', 'change'] }] : [],
  class_name: productForm.value.mode === 'train_new' ? [{ required: true, whitespace: true, message: '请输入类别名称', trigger: ['blur', 'change'] }] : [],
  unit_price: productForm.value.mode === 'train_new' ? [{ required: true, type: 'number', message: '请输入价格', trigger: ['blur', 'change'] }] : [],
  existing_product_id: productForm.value.mode === 'train_existing' ? [{ required: true, message: '请选择已有商品', trigger: 'change' }] : [],
}))

const currentDataset = computed(() => rows.value.find((item) => item.is_current))
const operationFinished = computed(() => ['completed', 'failed'].includes(operationTask.value.status))
const operationProgressStatus = computed(() => {
  if (operationTask.value.status === 'completed') return 'success'
  if (operationTask.value.status === 'failed') return 'exception'
  return undefined
})
const operationStatusText = computed(() => ({
  pending: '等待处理',
  running: '正在处理',
  completed: '操作完成',
  failed: '操作失败',
}[operationTask.value.status] || '正在处理'))
const annotationSummary = computed(() => annotationReviewSummary(annotationImages.value))
const activeAnnotationImage = computed(() => annotationImages.value[activeAnnotationIndex.value] || null)
const availableProducts = computed(() => productDataset.value?.classes || [])
const sampleSplitOptions = computed(() => (
  productForm.value.mode === 'scene'
    ? [
        { value: 'val', label: '验证集场景文件夹', required: false },
        { value: 'test', label: '测试集场景文件夹', required: false },
      ]
    : [{ value: 'train', label: '训练集图片文件夹', required: true }]
))
const sampleFolderError = computed(() => {
  if (productForm.value.mode === 'scene') {
    return productFiles.value.val.length + productFiles.value.test.length > 0 ? '' : 'val 和 test 至少选择一个非空文件夹'
  }
  return productFiles.value.train.length ? '' : '训练集文件夹至少需要一张图片'
})
const unassignedBoxCount = computed(() => (
  productForm.value.mode === 'scene'
    ? annotationImages.value.reduce((count, image) => count + image.boxes.filter((box) => !box.product_id).length, 0)
    : 0
))
const activeImageUnassignedBoxes = computed(() => (
  productForm.value.mode === 'scene'
    ? activeAnnotationImage.value?.boxes.filter((box) => !box.product_id).length || 0
    : 0
))
const canConfirmActiveImage = computed(() => Boolean(
  activeAnnotationImage.value?.boxes.length && activeImageUnassignedBoxes.value === 0
))
const filteredDeleteProducts = computed(() => {
  const products = deleteProductDataset.value?.classes || []
  const query = productSearch.value.trim().toLowerCase()
  if (!query) return products
  return products.filter((item) => [
    item.product_id,
    item.product_key,
    item.class_index,
    item.category_id,
    item.class_name,
    item.display_name,
  ].some((value) => String(value ?? '').toLowerCase().includes(query)))
})
const statusCount = computed(() => ({
  draft: rows.value.filter((item) => item.status === 'draft').length,
  ready: rows.value.filter((item) => item.status === 'ready').length,
}))

function statusText(status) {
  return { draft: '草稿', ready: '已冻结', archived: '已归档' }[status] || status
}

function statusType(status) {
  return { draft: 'warning', ready: 'success', archived: 'info' }[status] || 'info'
}

function formatTime(value) {
  return value ? new Date(value).toLocaleString() : '-'
}

function shortHash(value) {
  if (!value) return '未填写'
  return value.length > 20 ? `${value.slice(0, 12)}…${value.slice(-7)}` : value
}

function formatBytes(value) {
  const bytes = Number(value || 0)
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(1)} KB`
  if (bytes < 1024 ** 3) return `${(bytes / 1024 ** 2).toFixed(1)} MB`
  return `${(bytes / 1024 ** 3).toFixed(2)} GB`
}

function splitText(split) {
  return { train: '训练集', val: '验证集', test: '测试集' }[split] || split
}

async function fetchDatasets() {
  loading.value = true
  try {
    const params = {}
    if (filters.value.scene_id) params.scene_id = filters.value.scene_id
    if (filters.value.status) params.status = filters.value.status
    const response = await getDatasetVersionsApi(params)
    rows.value = response.items || []
    total.value = response.total || 0
  } catch {
    rows.value = []
    total.value = 0
  } finally {
    loading.value = false
  }
}

function resetFilters() {
  filters.value = { scene_id: null, status: '' }
  fetchDatasets()
}

function openCreateDialog() {
  editingId.value = null
  form.value = emptyForm()
  classMappingText.value = '[]'
  dialogVisible.value = true
}

function openBaselineDialog() {
  baselineVisible.value = true
}

function openModelImportDialog() {
  modelImportForm.value = emptyModelImportForm()
  modelImportFile.value = null
  modelImportVisible.value = true
}

function handleModelSourceModeChange() {
  modelImportFile.value = null
  modelImportForm.value.source_path = ''
  modelImportUploadRef.value?.clearFiles()
}

function handleModelFileChange(uploadFile) {
  modelImportFile.value = uploadFile.raw || null
}

function handleModelFileRemove() {
  modelImportFile.value = null
}

function handleModelFileExceed(files) {
  modelImportUploadRef.value?.clearFiles()
  const file = files[0]
  if (!file) return
  modelImportUploadRef.value?.handleStart(file)
}

async function submitModelImport() {
  const payload = modelImportForm.value
  if (!payload.scene_id || !payload.version || !payload.name) {
    ElMessage.warning('请填写场景 ID、版本号和显示名称')
    return
  }
  if (payload.source_mode === 'upload' && !modelImportFile.value) {
    ElMessage.warning('请选择要导入的 best.pt')
    return
  }
  if (payload.source_mode === 'path' && !payload.source_path) {
    ElMessage.warning('请输入后端可访问的模型文件路径')
    return
  }
  const formData = new FormData()
  formData.append('scene_id', String(payload.scene_id))
  formData.append('version', payload.version)
  formData.append('name', payload.name)
  formData.append('description', payload.description || '')
  formData.append('set_current', String(payload.set_current))
  formData.append('set_default', String(payload.set_default))
  if (payload.source_mode === 'upload') formData.append('file', modelImportFile.value)
  else formData.append('source_path', payload.source_path)

  modelImportSubmitting.value = true
  try {
    const result = await importAvailableModelApi(formData)
    modelImportVisible.value = false
    ElMessage.success(`模型已导入，共建立 ${result.dataset?.class_count || 0} 个商品类别`)
    await fetchDatasets()
  } finally {
    modelImportSubmitting.value = false
  }
}

async function submitBaseline() {
  if (!baselineForm.value.source_path || !baselineForm.value.version || !baselineForm.value.name) {
    ElMessage.warning('请填写源目录、版本号和名称')
    return
  }
  workspaceSubmitting.value = true
  try {
    await importBaselineDatasetApi({
      ...baselineForm.value,
      description: baselineForm.value.description || null,
    })
    baselineVisible.value = false
    ElMessage.success('基线数据集已导入并建立稳定商品索引')
    await fetchDatasets()
  } finally {
    workspaceSubmitting.value = false
  }
}

const waitForOperationPoll = () => new Promise((resolve) => window.setTimeout(resolve, 500))

async function runDatasetOperation(title, startTask) {
  const runToken = operationRunToken.value + 1
  operationRunToken.value = runToken
  workspaceSubmitting.value = true
  operationTask.value = {
    task_id: '',
    title,
    operation: '',
    status: 'pending',
    progress: 0,
    message: '正在创建后台任务…',
    result: null,
  }
  operationProgressVisible.value = true
  let taskCreated = false
  try {
    let task = await startTask()
    taskCreated = true
    operationTask.value = { title, ...task, progress: Number(task.progress || 0) }
    while (!['completed', 'failed'].includes(task.status)) {
      await waitForOperationPoll()
      if (operationRunToken.value !== runToken) return null
      task = await getDatasetOperationStatusApi(task.task_id)
      operationTask.value = { title, ...task, progress: Number(task.progress || 0) }
    }
    if (task.status === 'failed') {
      ElMessage.error(task.message || '数据集操作失败')
      return null
    }
    await new Promise((resolve) => window.setTimeout(resolve, 450))
    operationProgressVisible.value = false
    return task.result
  } catch (error) {
    if (!taskCreated) {
      operationProgressVisible.value = false
      throw error
    }
    operationTask.value = {
      ...operationTask.value,
      status: 'failed',
      message: error.response?.data?.detail || '无法获取后台任务进度，请检查服务器状态',
    }
    ElMessage.error(operationTask.value.message)
    return null
  } finally {
    if (operationRunToken.value === runToken) workspaceSubmitting.value = false
  }
}

function openDeriveDialog(row) {
  deriveParent.value = row
  deriveForm.value = {
    version: `${row.version}-next`,
    name: `${row.name} 派生版本`,
    description: '',
  }
  deriveVisible.value = true
}

async function submitDerive() {
  if (!deriveParent.value || !deriveForm.value.version || !deriveForm.value.name) return
  const result = await runDatasetOperation('创建派生版本', () => (
    deriveDatasetVersionTaskApi(deriveParent.value.id, {
      ...deriveForm.value,
      description: deriveForm.value.description || null,
    })
  ))
  if (!result?.dataset) return
  deriveVisible.value = false
  ElMessage.success('派生版本已创建，可开始增删商品')
  await fetchDatasets()
  await openDetail(result.dataset)
}

async function openAddProductDialog(dataset) {
  workspaceSubmitting.value = true
  try {
    productDataset.value = await getDatasetVersionApi(dataset.id)
  } finally {
    workspaceSubmitting.value = false
  }
  productForm.value = emptyProductForm()
  productFiles.value = { train: [], val: [], test: [] }
  clearLocalAnnotationStage()
  productFolderInfo.value = emptyProductFolderInfos()
  addProductVisible.value = true
}

async function resetSampleFiles() {
  if (annotationStage.value) await discardCurrentAnnotationStage()
  productFiles.value = { train: [], val: [], test: [] }
  productFolderInfo.value = emptyProductFolderInfos()
}

function setProductSplitFolder(split, event) {
  const selection = collectProductFolderFiles(event.target.files)
  productFiles.value = { ...productFiles.value, [split]: selection.files }
  productFolderInfo.value = { ...productFolderInfo.value, [split]: {
    folderName: selection.folderName,
    ignoredCount: selection.ignoredCount,
    totalBytes: selection.totalBytes,
  } }
  event.target.value = ''
  if (!selection.totalImages) ElMessage.warning('所选文件夹中没有支持的图片')
}

function clearLocalAnnotationStage() {
  for (const item of annotationImages.value) {
    if (item.previewUrl) URL.revokeObjectURL(item.previewUrl)
  }
  annotationStage.value = null
  annotationImages.value = []
  activeAnnotationIndex.value = 0
}

async function discardCurrentAnnotationStage() {
  const stage = annotationStage.value
  const dataset = productDataset.value
  clearLocalAnnotationStage()
  if (!stage || !dataset) return
  try {
    await discardDatasetProductStageApi(dataset.id, stage.staging_token)
  } catch {
    // 暂存目录还会由后端 TTL 清理，关闭弹窗不应被清理失败阻塞。
  }
}

async function handleAddProductClosed() {
  await discardCurrentAnnotationStage()
  productFiles.value = { train: [], val: [], test: [] }
  productFolderInfo.value = emptyProductFolderInfos()
}

async function restartAnnotationStage() {
  await discardCurrentAnnotationStage()
  productFiles.value = { train: [], val: [], test: [] }
  productFolderInfo.value = emptyProductFolderInfos()
}

async function generateProductAnnotations() {
  const formValid = await productFormRef.value?.validate().catch(() => false)
  if (!productDataset.value || !formValid || sampleFolderError.value) {
    ElMessage.warning('请先完成所有必填项')
    return
  }
  const formData = new FormData()
  formData.append('mode', productForm.value.mode)
  for (const split of ['train', 'val', 'test']) {
    for (const file of productFiles.value[split]) formData.append(`${split}_files`, file)
  }
  workspaceSubmitting.value = true
  let staged = null
  try {
    staged = await stageDatasetProductImagesApi(productDataset.value.id, formData)
    annotationImages.value = attachFilesToStagedImages(staged, productFiles.value)
    annotationStage.value = staged
    activeAnnotationIndex.value = Math.max(0, annotationImages.value.findIndex((item) => !item.reviewed))
    ElMessage.info(`已载入 ${staged.total_images} 张图片，请逐张手工绘制检测框`)
  } catch (error) {
    if (staged?.staging_token) {
      await discardDatasetProductStageApi(productDataset.value.id, staged.staging_token).catch(() => {})
    }
    throw error
  } finally {
    workspaceSubmitting.value = false
  }
}

function updateActiveBoxes(boxes) {
  if (!activeAnnotationImage.value) return
  activeAnnotationImage.value.boxes = boxes
}

function markActiveAnnotationReviewed() {
  if (!activeAnnotationImage.value) return
  activeAnnotationImage.value.edited = true
  activeAnnotationImage.value.reviewed = false
}

function markBoxProductChanged() {
  if (!activeAnnotationImage.value) return
  activeAnnotationImage.value.reviewed = false
}

function confirmActiveAnnotation() {
  if (!canConfirmActiveImage.value) return
  activeAnnotationImage.value.reviewed = true
  const nextPending = annotationImages.value.findIndex((item, index) => index > activeAnnotationIndex.value && !item.reviewed)
  if (nextPending >= 0) activeAnnotationIndex.value = nextPending
}

async function openDeleteProductDialog(dataset) {
  workspaceSubmitting.value = true
  try {
    deleteProductDataset.value = await getDatasetVersionApi(dataset.id)
    productSearch.value = ''
    deleteProductVisible.value = true
  } finally {
    workspaceSubmitting.value = false
  }
}

async function submitAddProduct() {
  if (!productDataset.value || !annotationStage.value) return
  if (annotationSummary.value.pending || annotationSummary.value.missing || unassignedBoxCount.value) {
    ElMessage.warning('请先完成所有图片的检测框和商品标注')
    return
  }
  const payload = buildDatasetProductCommitPayload(
    annotationStage.value,
    productForm.value,
    annotationImages.value,
  )
  const result = await runDatasetOperation('添加人工标注样本并更新数据集', () => (
    commitDatasetProductTaskApi(productDataset.value.id, payload)
  ))
  if (!result?.dataset) return
  clearLocalAnnotationStage()
  addProductVisible.value = false
  detail.value = result.dataset
  ElMessage.success(
    result.product_id
      ? `训练样本已添加，稳定 product_id=${result.product_id}`
      : 'val/test 多商品场景样本已添加',
  )
  await fetchDatasets()
}

async function deleteProductMapping(dataset, mapping) {
  await ElMessageBox.confirm(
    `将从派生版本删除 product_id=${mapping.product_id} 的全部标注，并重排后续 class_id。单商品图片会删除；多商品场景仍有其他框时会保留。是否继续？`,
    '删除商品样本',
    { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' },
  )
  deletingProductId.value = mapping.product_id
  try {
    const result = await runDatasetOperation(`删除商品 ${mapping.display_name || mapping.class_name}`, () => (
      deleteDatasetProductTaskApi(dataset.id, mapping.product_id, true)
    ))
    if (!result?.dataset) return
    deleteProductDataset.value = result.dataset
    if (detail.value?.id === result.dataset.id) detail.value = result.dataset
    ElMessage.success(`已删除 ${result.annotations_deleted} 个标注、${result.images_deleted} 张空样本图片并重建索引`)
    await fetchDatasets()
  } finally {
    deletingProductId.value = null
  }
}

async function openEditDialog(row) {
  const data = await getDatasetVersionApi(row.id)
  editingId.value = row.id
  form.value = {
    scene_id: data.scene_id,
    parent_id: data.parent_id,
    version: data.version,
    name: data.name,
    description: data.description || '',
    storage_path: data.storage_path,
    data_yaml_path: data.data_yaml_path,
    manifest_path: data.manifest_path || '',
    content_hash: data.content_hash || '',
    class_count: data.class_count,
    train_image_count: data.train_image_count,
    val_image_count: data.val_image_count,
    test_image_count: data.test_image_count,
    train_annotation_count: data.train_annotation_count,
    val_annotation_count: data.val_annotation_count,
    test_annotation_count: data.test_annotation_count,
  }
  classMappingText.value = JSON.stringify(
    data.classes.map(({ id, ...item }) => item),
    null,
    2,
  )
  dialogVisible.value = true
}

function parseClassMappings() {
  let parsed
  try {
    parsed = JSON.parse(classMappingText.value || '[]')
  } catch {
    ElMessage.error('类别映射不是有效 JSON')
    return null
  }
  if (!Array.isArray(parsed)) {
    ElMessage.error('类别映射必须是 JSON 数组')
    return null
  }
  return parsed
}

async function submitForm() {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return
  const classes = parseClassMappings()
  if (classes === null) return

  submitting.value = true
  try {
    const payload = {
      ...form.value,
      parent_id: form.value.parent_id || null,
      manifest_path: form.value.manifest_path || null,
      content_hash: form.value.content_hash || null,
      description: form.value.description || null,
      classes,
    }
    if (editingId.value) {
      delete payload.scene_id
      await updateDatasetVersionApi(editingId.value, payload)
      ElMessage.success('数据集草稿已更新')
    } else {
      await createDatasetVersionApi(payload)
      ElMessage.success('数据集草稿已创建')
    }
    dialogVisible.value = false
    await fetchDatasets()
  } finally {
    submitting.value = false
  }
}

async function openDetail(row) {
  detail.value = await getDatasetVersionApi(row.id)
  detailVisible.value = true
}

async function validateRow(row) {
  const report = await validateDatasetVersionApi(row.id, checkFilesystem.value)
  if (report.valid) {
    ElMessage.success(checkFilesystem.value ? '逻辑和目录校验均通过' : '数据集逻辑校验通过')
  } else {
    await ElMessageBox.alert(report.errors.join('\n'), '数据集校验未通过', { type: 'warning' })
  }
  await fetchDatasets()
}

async function freezeRow(row) {
  await ElMessageBox.confirm(
    `冻结 ${row.version} 后将不能再修改目录、统计和类别映射。是否继续？`,
    '冻结数据集版本',
    { type: 'warning', confirmButtonText: '冻结', cancelButtonText: '取消' },
  )
  await freezeDatasetVersionApi(row.id, checkFilesystem.value)
  ElMessage.success('数据集版本已冻结')
  await fetchDatasets()
}

async function setCurrent(row) {
  await ElMessageBox.confirm(
    `确定将 ${row.version} 设为场景当前数据集吗？这一步暂时不会触发训练。`,
    '切换当前数据集',
    { type: 'warning' },
  )
  await setCurrentDatasetVersionApi(row.id)
  ElMessage.success('当前数据集已切换')
  await fetchDatasets()
}

async function archiveRow(row) {
  await ElMessageBox.confirm(`确定归档 ${row.version} 吗？`, '归档数据集', { type: 'warning' })
  await archiveDatasetVersionApi(row.id)
  ElMessage.success('数据集已归档')
  await fetchDatasets()
}

async function deleteRow(row) {
  await ElMessageBox.confirm(`确定删除草稿 ${row.version} 吗？`, '删除草稿', { type: 'warning' })
  const result = await runDatasetOperation(`删除草稿 ${row.version}`, () => (
    deleteDatasetVersionTaskApi(row.id)
  ))
  if (!result) return
  ElMessage.success('草稿已删除')
  await fetchDatasets()
}

onBeforeUnmount(() => {
  operationRunToken.value += 1
  const operationRunning = ['pending', 'running'].includes(operationTask.value.status)
  if (!(operationRunning && operationTask.value.operation === 'add_product')) {
    void discardCurrentAnnotationStage()
  }
})
onMounted(fetchDatasets)
</script>

<style lang="scss" scoped>
.dataset-page { display: flex; flex-direction: column; gap: 18px; padding: 20px; }
.page-header { display: flex; align-items: flex-start; justify-content: space-between; gap: 24px; padding: 24px 26px; border: 1px solid $border-color; border-radius: $border-radius-lg; background: linear-gradient(135deg, $surface-color 55%, $primary-soft); box-shadow: $shadow-sm; }
.page-header h2 { margin: 5px 0 8px; font-size: 25px; color: $text-primary; }
.page-header p { max-width: 720px; margin: 0; color: $text-secondary; font-size: 13px; line-height: 1.7; }
.header-actions { display: flex; align-items: center; gap: 8px; }
.summary-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 14px; }
.summary-card { min-width: 0; padding: 18px 20px; border: 1px solid $border-color; border-radius: $border-radius-md; background: $surface-color; box-shadow: $shadow-sm; }
.summary-card span, .summary-card small { display: block; color: $text-secondary; }
.summary-card strong { display: block; overflow: hidden; margin: 8px 0 6px; color: $text-primary; font-size: 25px; text-overflow: ellipsis; white-space: nowrap; }
.summary-card small { font-size: 11px; }
.current-card { border-color: $primary-color; background: linear-gradient(145deg, $surface-color, $primary-soft); }
.panel { overflow: hidden; border: 1px solid $border-color; border-radius: $border-radius-lg; background: $surface-color; box-shadow: $shadow-sm; }
.toolbar { display: flex; align-items: center; justify-content: space-between; gap: 18px; padding: 15px 18px; border-bottom: 1px solid $border-color; }
.filters, .toolbar-actions { display: flex; align-items: center; gap: 8px; }
.filters .el-input-number { width: 130px; }.filters .el-select { width: 135px; }
.dataset-table { width: 100%; }
.model-import-form { margin-top: 18px; }
.model-import-upload { width: 100%; }
.model-import-upload :deep(.el-upload), .model-import-upload :deep(.el-upload-dragger) { width: 100%; }
.model-import-switches { display: flex; flex-wrap: wrap; gap: 8px 22px; }
.version-title { display: flex; align-items: flex-start; gap: 8px; min-width: 0; }.version-title strong { min-width: 0; line-height: 1.35; overflow-wrap: anywhere; }.current-version-tag { flex: 0 0 auto; margin-top: 1px; border-radius: 999px; font-weight: 600; }.version-name { display: block; margin-top: 5px; color: $text-secondary; font-size: 12px; line-height: 1.45; }
.split-cell strong, .split-cell span { display: block; }.split-cell span { margin-top: 3px; color: $text-secondary; font-size: 11px; }
code { color: $text-secondary; font-size: 11px; }
.row-actions { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 8px; width: 100%; }
.row-action-button { width: 100%; height: 32px; min-height: 32px; margin: 0 !important; padding: 0 9px; border: 1px solid $border-strong; border-radius: 8px; color: $text-regular; background: $surface-color; box-shadow: none !important; font-weight: 500; transition: border-color 0.18s ease, color 0.18s ease, background-color 0.18s ease; }
.row-action-button:hover, .row-action-button:focus-visible { border-color: $text-secondary; color: $text-primary; background: $surface-muted; }
.row-action-button.is-primary-action { border-color: $primary-color; color: $primary-color; background: $primary-soft; }
.row-action-button.is-primary-action:hover, .row-action-button.is-primary-action:focus-visible { border-color: $primary-hover; color: $primary-hover; background: $primary-soft; }
.row-action-button.is-success-action { border-color: $success-color; color: $success-color; background: color-mix(in srgb, $success-color 12%, transparent); }
.row-action-button.is-success-action:hover, .row-action-button.is-success-action:focus-visible { border-color: $success-color; color: $success-color; background: color-mix(in srgb, $success-color 20%, transparent); }
.row-action-button.is-danger-action { border-color: $danger-color; color: $danger-color; background: color-mix(in srgb, $danger-color 10%, transparent); }
.row-action-button.is-danger-action:hover, .row-action-button.is-danger-action:focus-visible { border-color: $danger-color; color: $danger-color; background: color-mix(in srgb, $danger-color 18%, transparent); }
.form-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); column-gap: 18px; }.form-grid .el-input-number { width: 100%; }
.count-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); column-gap: 16px; }.count-grid :deep(.el-form-item) { min-width: 0; margin-bottom: 14px; }.count-grid .el-input-number { width: 100%; min-width: 0; }
:global(.dataset-editor-dialog) { display: flex; flex-direction: column; box-sizing: border-box; max-width: calc(100vw - 32px); max-height: calc(100% - 8vh); margin: 4vh auto 0 !important; overflow: hidden; }
:global(.dataset-editor-dialog .el-dialog__header), :global(.dataset-editor-dialog .el-dialog__footer) { flex: 0 0 auto; }
:global(.dataset-editor-dialog .el-dialog__body) { flex: 1 1 auto; min-height: 0; overflow-x: hidden; overflow-y: auto; overscroll-behavior: contain; }
.mapping-field :deep(textarea) { font-family: Consolas, monospace; font-size: 12px; }.form-tip { margin: 7px 0 0; color: $text-secondary; font-size: 11px; line-height: 1.6; }
.folder-select-button { display: inline-flex; align-items: center; justify-content: center; padding: 8px 15px; border: 1px solid $primary-color; border-radius: 8px; color: $primary-color; background: $primary-soft; cursor: pointer; transition: 0.2s ease; }.folder-select-button:hover { border-color: $primary-hover; color: $primary-hover; background: $primary-soft; }.folder-select-button.disabled { border-color: $border-color; color: $text-placeholder; background: $surface-muted; cursor: not-allowed; }.folder-input { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0, 0, 0, 0); clip-path: inset(50%); white-space: nowrap; }
:global(.annotation-review-dialog) { display: flex; flex-direction: column; max-width: calc(100vw - 28px); max-height: 94vh; overflow: hidden; }
:global(.annotation-review-dialog .el-dialog__header), :global(.annotation-review-dialog .el-dialog__footer) { flex: 0 0 auto; }
:global(.annotation-review-dialog .el-dialog__body) { flex: 1 1 auto; min-height: 0; overflow-y: auto; }
.product-setup-form { padding-right: 4px; }.product-setup-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 0 14px; }.product-setup-grid :deep(.el-input-number) { width: 100%; }
.split-folder-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; margin: 2px 0 16px; }.split-folder-card { min-width: 0; padding: 13px; border: 1px solid $border-color; border-radius: 10px; background: $surface-color; transition: border-color .2s ease, box-shadow .2s ease; }.split-folder-card.invalid { border-color: $danger-color; box-shadow: 0 0 0 2px color-mix(in srgb, $danger-color 12%, transparent); }.split-folder-heading { display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-bottom: 10px; }.split-folder-heading strong { color: $text-primary; font-size: 13px; }.split-folder-heading > span { color: $text-secondary; font-size: 11px; }.required-star { margin-right: 3px; color: $danger-color; }.split-folder-summary { margin-top: 10px; padding: 9px 10px; border-radius: 7px; background: $surface-muted; }.split-folder-summary strong, .split-folder-summary span { display: block; overflow-wrap: anywhere; }.split-folder-summary strong { color: $text-primary; font-size: 12px; }.split-folder-summary span { margin-top: 3px; color: $text-secondary; font-size: 11px; }.folder-error { margin-top: 7px; color: $danger-color; font-size: 12px; line-height: 1.3; }
.annotation-review { margin-top: 18px; padding-top: 18px; border-top: 1px solid $border-color; }.review-heading { display: flex; align-items: flex-start; justify-content: space-between; gap: 18px; margin-bottom: 12px; }.review-heading h3 { margin: 0; color: $text-primary; font-size: 18px; }.review-heading p { margin: 5px 0 0; color: $text-secondary; font-size: 12px; }.review-summary { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 6px; }
.review-workspace { display: grid; grid-template-columns: 270px minmax(0, 1fr); min-height: 460px; overflow: hidden; border: 1px solid $border-color; border-radius: 12px; background: $surface-muted; }.annotation-thumbnails { max-height: min(60vh, 620px); overflow-y: auto; padding: 9px; border-right: 1px solid $border-color; background: $surface-color; }.annotation-thumbnail { display: grid; grid-template-columns: 56px minmax(0, 1fr) auto; align-items: center; gap: 9px; width: 100%; margin: 0 0 7px; padding: 7px; border: 1px solid $border-color; border-radius: 9px; color: inherit; background: $surface-color; text-align: left; cursor: pointer; }.annotation-thumbnail:hover { border-color: $primary-color; background: $primary-soft; }.annotation-thumbnail.active { border-color: $primary-color; box-shadow: 0 0 0 2px $primary-soft; }.annotation-thumbnail.pending { border-left: 3px solid $warning-color; }.annotation-thumbnail.missing { border-left-color: $danger-color; }.annotation-thumbnail img { width: 56px; height: 48px; object-fit: cover; border-radius: 6px; background: $surface-muted; }.thumbnail-copy { min-width: 0; }.thumbnail-copy strong, .thumbnail-copy small { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }.thumbnail-copy strong { color: $text-primary; font-size: 12px; }.thumbnail-copy small { margin-top: 4px; color: $text-secondary; font-size: 10px; }.annotation-editor-panel { min-width: 0; padding: 14px; }.active-image-heading { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; margin-bottom: 10px; }.active-image-heading strong, .active-image-heading span { display: block; }.active-image-heading strong { color: $text-primary; }.active-image-heading span { margin-top: 4px; color: $text-secondary; font-size: 11px; }.active-review-actions { display: flex; align-items: center; justify-content: space-between; gap: 14px; margin-top: 10px; }.active-review-actions span { color: $text-secondary; font-size: 12px; }
.box-product-assignments { display: grid; gap: 8px; margin-top: 12px; padding: 10px; border: 1px solid $border-color; border-radius: 9px; background: $surface-color; }.box-product-row { display: grid; grid-template-columns: 90px minmax(0, 1fr); align-items: center; gap: 10px; }.box-product-row > span { color: $text-secondary; font-size: 12px; }
.product-search { margin: 16px 0 8px; }.search-result-count { margin-bottom: 8px; color: $text-secondary; font-size: 12px; }
.operation-progress-content { padding: 6px 2px 4px; }.operation-progress-heading { display: flex; align-items: center; justify-content: space-between; gap: 16px; margin-bottom: 12px; }.operation-progress-heading strong { color: $text-primary; font-size: 15px; }.operation-progress-heading span { color: $primary-color; font-size: 20px; font-weight: 700; font-variant-numeric: tabular-nums; }.operation-progress-content p { min-height: 22px; margin: 14px 0 7px; color: $text-secondary; line-height: 1.6; }.operation-progress-content code { display: block; overflow: hidden; color: $text-placeholder; text-overflow: ellipsis; white-space: nowrap; }.operation-error { margin-top: 16px; }
.detail-heading { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 18px; }.detail-heading span { color: $text-secondary; font-size: 12px; }.detail-heading h3 { margin: 5px 0 0; font-size: 21px; }
.validation-box { margin: 18px 0; padding: 13px 15px; border: 1px solid $success-color; border-radius: 9px; color: $success-color; background: color-mix(in srgb, $success-color 12%, transparent); }.validation-box.invalid { border-color: $danger-color; color: $danger-color; background: color-mix(in srgb, $danger-color 10%, transparent); }.validation-box strong, .validation-box span { display: block; }.validation-box span { margin-top: 3px; font-size: 11px; }.validation-box ul { margin: 8px 0 0; padding-left: 18px; }
.mapping-header { display: flex; align-items: center; justify-content: space-between; margin: 20px 0 10px; }.mapping-header h4 { margin: 0; }.mapping-header span { color: $text-secondary; font-size: 12px; }
@media (max-width: 1100px) { .summary-grid { grid-template-columns: repeat(2, 1fr); }.toolbar { align-items: flex-start; flex-direction: column; }.count-grid { grid-template-columns: repeat(2, 1fr); }.product-setup-grid { grid-template-columns: repeat(2, 1fr); }.split-folder-grid { grid-template-columns: 1fr; }.review-workspace { grid-template-columns: 220px minmax(0, 1fr); } }
@media (max-width: 700px) { .dataset-page { padding: 12px; }.page-header { flex-direction: column; }.summary-grid, .form-grid, .count-grid, .product-setup-grid { grid-template-columns: 1fr; }.filters { align-items: stretch; flex-direction: column; width: 100%; }.filters .el-input-number, .filters .el-select { width: 100%; }.review-heading, .active-review-actions { align-items: stretch; flex-direction: column; }.review-summary { justify-content: flex-start; }.review-workspace { display: block; }.annotation-thumbnails { display: flex; max-height: none; overflow-x: auto; border-right: 0; border-bottom: 1px solid $border-color; }.annotation-thumbnail { flex: 0 0 250px; }.annotation-editor-panel { padding: 10px; } }
</style>
