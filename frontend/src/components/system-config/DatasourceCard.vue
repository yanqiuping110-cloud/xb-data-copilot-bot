<template>
  <div class="sys-card">
    <span v-if="item.isDefault" class="sys-card__badge">当前问数库</span>
    <div class="sys-card__row">
      <div class="sys-logo" :style="{ background: color }">{{ initial }}</div>
      <div class="sys-card__body">
        <h3 class="sys-card__name" :title="item.name">{{ item.name }}</h3>
        <p class="sys-card__meta">
          <strong>类型：</strong>{{ typeName }}
        </p>
        <p class="sys-card__meta">
          <strong>连接：</strong>{{ item.host }}:{{ item.port }} / {{ item.databaseName }}
        </p>
        <p class="sys-card__meta">
          <strong>最近校验：</strong>
          <template v-if="item.lastTestAt">
            {{ item.lastTestOk ? '成功' : '失败' }} · {{ item.lastTestAt }}
          </template>
          <template v-else>未测试</template>
        </p>
        <p v-if="item.serverVersion" class="sys-card__meta">
          <strong>版本：</strong>{{ item.serverVersion }}
        </p>
      </div>
    </div>
    <div class="sys-card__actions">
      <el-button link type="primary" :loading="testing" @click="$emit('test', item)">校验</el-button>
      <el-button v-if="!item.isDefault" link type="primary" @click="$emit('set-default', item)">
        设为默认
      </el-button>
      <el-button link type="primary" @click="$emit('edit', item)">编辑</el-button>
      <el-button link type="danger" @click="$emit('delete', item)">删除</el-button>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { dsTypeColor, dsTypeLabel } from '../../constants/datasourceTypes.fallback'
import { providerInitial } from '../../constants/llmProviders.fallback'

const props = defineProps({
  item: { type: Object, required: true },
  types: { type: Array, default: () => [] },
  testing: { type: Boolean, default: false },
})

defineEmits(['test', 'set-default', 'edit', 'delete'])

const typeName = computed(() => dsTypeLabel(props.item.dbType, props.types))
const color = computed(() => dsTypeColor(props.item.dbType, props.types))
const initial = computed(() => providerInitial(typeName.value))
</script>
