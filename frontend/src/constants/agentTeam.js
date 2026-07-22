import { DataAnalysis, Files, MagicStick, PriceTag, View } from '@element-plus/icons-vue'

export const AGENT_TEAM = Object.freeze([
  { name: 'detection', label: 'Detection', description: '图片与视频商品检测', icon: View },
  { name: 'dataset', label: 'Dataset', description: '版本、样品与标注流程', icon: Files },
  { name: 'training', label: 'Training', description: '训练任务与模型发布', icon: DataAnalysis },
  { name: 'catalog', label: 'Catalog', description: '商品目录与价目表', icon: PriceTag },
  { name: 'knowledge', label: 'Knowledge', description: '知识库与故障案例', icon: MagicStick },
])
