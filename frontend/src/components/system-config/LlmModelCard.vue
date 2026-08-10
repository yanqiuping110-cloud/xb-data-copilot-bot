<template>
  <div class="sys-card">
    <span v-if="model.isDefault" class="sys-card__badge">默认模型</span>
    <div class="sys-card__row">
      <div class="sys-logo" :style="{ background: color }">{{ initial }}</div>
      <div class="sys-card__body">
        <h3 class="sys-card__name" :title="model.name">{{ model.name }}</h3>
        <p class="sys-card__meta">
          <strong>模型类型：</strong>{{ roleLabel }}
        </p>
        <p class="sys-card__meta">
          <strong>基础模型：</strong>{{ model.modelName }}
        </p>
        <p class="sys-card__meta">
          <strong>供应商：</strong>{{ providerName }}
        </p>
      </div>
    </div>
    <div class="sys-card__actions">
      <el-button link type="primary" :loading="testing" @click="$emit('test', model)">测试</el-button>
      <el-button v-if="!model.isDefault" link type="primary" @click="$emit('set-default', model)">
        设为默认
      </el-button>
      <el-button link type="primary" @click="$emit('edit', model)">编辑</el-button>
      <el-button link type="danger" @click="$emit('delete', model)">删除</el-button>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { providerColor, providerInitial, providerLabel } from '../../constants/llmProviders.fallback'

const props = defineProps({
  model: { type: Object, required: true },
  providers: { type: Array, default: () => [] },
  testing: { type: Boolean, default: false },
})

defineEmits(['test', 'set-default', 'edit', 'delete'])

const providerName = computed(() => providerLabel(props.model.provider, props.providers))
const color = computed(() => providerColor(props.model.provider, props.providers))
const initial = computed(() => providerInitial(providerName.value))
const roleLabel = computed(() =>
  props.model.role === 'embedding' ? '向量模型' : '大语言模型',
)
</script>
