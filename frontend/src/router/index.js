/**
 * 前端路由：登录页公开，其余需 accessToken。
 */
import { createRouter, createWebHistory } from 'vue-router'
import { defaultHomePath } from '../utils/roleHome'

const routes = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('../views/Login.vue'),
    meta: { public: true },
  },
  {
    path: '/',
    redirect: () => defaultHomePath(localStorage.getItem('userRole')),
  },
  {
    path: '/ask',
    name: 'Ask',
    component: () => import('../views/Ask.vue'),
  },
  {
    path: '/insight',
    redirect: '/ask',
  },
  {
    path: '/admin/users',
    name: 'AdminUsers',
    component: () => import('../views/AdminUsers.vue'),
    meta: { requiresAdmin: true },
  },
  {
    path: '/admin/code/repos',
    name: 'AdminCodeRepos',
    component: () => import('../views/AdminCodeRepos.vue'),
    meta: { requiresAdmin: true },
  },
  {
    path: '/admin/meta/tables',
    name: 'AdminMetaTables',
    component: () => import('../views/AdminMetaTables.vue'),
    meta: { requiresMetaManager: true },
  },
  {
    path: '/admin/meta/tables/new',
    name: 'AdminMetaTableNew',
    component: () => import('../views/AdminMetaTableNew.vue'),
    meta: { requiresMetaManager: true },
  },
  {
    path: '/admin/meta/tables/:id/columns',
    name: 'AdminMetaColumns',
    component: () => import('../views/AdminMetaColumns.vue'),
    meta: { requiresMetaManager: true },
  },
  {
    path: '/admin/meta/relations',
    name: 'AdminMetaRelations',
    component: () => import('../views/AdminMetaRelations.vue'),
    meta: { requiresMetaManager: true },
  },
  {
    path: '/admin/meta/field-values',
    name: 'AdminMetaFieldValues',
    component: () => import('../views/AdminMetaFieldValues.vue'),
    meta: { requiresMetaManager: true },
  },
  {
    path: '/admin/meta/metrics',
    name: 'AdminMetaMetrics',
    component: () => import('../views/AdminMetaMetrics.vue'),
    meta: { requiresMetaManager: true },
  },
  {
    path: '/admin/meta/sql-examples',
    name: 'AdminMetaSqlExamples',
    component: () => import('../views/AdminMetaSqlExamples.vue'),
    meta: { requiresMetaManager: true },
  },
  {
    path: '/admin/meta/scope',
    name: 'AdminMetaScope',
    component: () => import('../views/AdminMetaScope.vue'),
    meta: { requiresAdmin: true },
  },
  {
    path: '/admin/meta/badcases',
    name: 'AdminBadcases',
    component: () => import('../views/AdminBadcases.vue'),
    meta: { requiresMetaManager: true },
  },
  {
    path: '/admin/meta/ops',
    name: 'AdminOps',
    component: () => import('../views/AdminOps.vue'),
    meta: { requiresMetaManager: true },
  },
  {
    path: '/admin/system/llm',
    name: 'AdminSystemLlm',
    component: () => import('../views/AdminSystemLlm.vue'),
    meta: { requiresAdmin: true },
  },
  {
    path: '/admin/system/datasources',
    name: 'AdminSystemDatasources',
    component: () => import('../views/AdminSystemDatasources.vue'),
    meta: { requiresAdmin: true },
  },
  {
    path: '/embed/ask',
    name: 'EmbedAsk',
    component: () => import('../views/EmbedAsk.vue'),
    meta: { public: true, embed: true },
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach((to) => {
  const token = localStorage.getItem('accessToken')
  if (to.meta.embed && to.query.token) {
    localStorage.setItem('accessToken', String(to.query.token))
    return true
  }
  if (!to.meta.public && !token) {
    return { name: 'Login' }
  }
  if (to.name === 'Login' && token) {
    return defaultHomePath(localStorage.getItem('userRole'))
  }
  if (to.meta.requiresAdmin && localStorage.getItem('userRole') !== 'ADMIN') {
    return { name: 'Ask' }
  }
  if (to.meta.requiresMetaManager) {
    const role = localStorage.getItem('userRole')
    if (role !== 'ADMIN') {
      return { name: 'Ask' }
    }
  }
})

export default router
