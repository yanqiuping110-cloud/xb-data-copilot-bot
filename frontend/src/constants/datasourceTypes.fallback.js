/**
 * 数据源类型离线兜底（仅 API 不可用时）。主数据源为 GET /datasource-types。
 * temporary — 与 backend/app/system/catalogs/datasource_types.yaml 保持同步。
 */
export const DATASOURCE_TYPES_FALLBACK = [
  { code: 'mysql', name: 'MySQL', group: 'oltp', status: 'ga', selectable: true, color: '#00758F', defaultPort: 3306, versionHint: '5.6+', dialect: 'mysql', formSchema: [] },
  { code: 'postgresql', name: 'PostgreSQL', group: 'oltp', status: 'ga', selectable: true, color: '#336791', defaultPort: 5432, versionHint: '12+', dialect: 'postgres', formSchema: [] },
  { code: 'sqlserver', name: 'SQL Server', group: 'oltp', status: 'ga', selectable: true, color: '#CC2927', defaultPort: 1433, versionHint: '2016+', dialect: 'tsql', formSchema: [] },
  { code: 'oracle', name: 'Oracle', group: 'oltp', status: 'ga', selectable: true, color: '#F80000', defaultPort: 1521, versionHint: '12c+', dialect: 'oracle', formSchema: [] },
  { code: 'clickhouse', name: 'ClickHouse', group: 'olap', status: 'ga', selectable: true, color: '#FFCC01', defaultPort: 8123, versionHint: '22+', dialect: 'clickhouse', formSchema: [] },
  { code: 'doris', name: 'Apache Doris', group: 'olap', status: 'ga', selectable: true, color: '#444444', defaultPort: 9030, versionHint: '1.2+', dialect: 'mysql', formSchema: [] },
  { code: 'starrocks', name: 'StarRocks', group: 'olap', status: 'ga', selectable: true, color: '#0B5FFF', defaultPort: 9030, versionHint: '2.5+', dialect: 'mysql', formSchema: [] },
  { code: 'excel', name: '本地 Excel/CSV', group: 'file', status: 'ga', selectable: true, color: '#217346', defaultPort: 0, versionHint: 'xlsx/csv', dialect: 'sqlite', formSchema: [] },
]

export function dsTypeLabel(code, types = DATASOURCE_TYPES_FALLBACK) {
  return types.find((t) => t.code === code)?.name || code || '未知'
}

export function dsTypeColor(code, types = DATASOURCE_TYPES_FALLBACK) {
  return types.find((t) => t.code === code)?.color || '#0CA678'
}
