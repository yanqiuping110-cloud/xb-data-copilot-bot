-- V009：Git 业务代码知识图谱（§11.8.1 · 第 10 周）
-- 执行：在 copilot 库手工运行（见 docs/DATABASE_CHANGE_POLICY.md）

-- ---------- Git 仓库配置（超管维护）----------
CREATE TABLE IF NOT EXISTS copilot_git_repo (
    id BIGINT AUTO_INCREMENT PRIMARY KEY COMMENT '主键',
    name VARCHAR(128) NOT NULL COMMENT '展示名，如体育报表后端',
    repo_url VARCHAR(512) NOT NULL COMMENT 'Git 远程地址',
    branch VARCHAR(128) NOT NULL DEFAULT 'main' COMMENT '同步分支',
    auth_secret_ref VARCHAR(128) NULL COMMENT '凭证环境变量名，不入库明文',
    include_paths_json TEXT NULL COMMENT '包含路径 glob JSON 数组',
    exclude_paths_json TEXT NULL COMMENT '排除路径 glob JSON 数组',
    local_path VARCHAR(512) NULL COMMENT 'sync 后本地工作目录',
    last_sync_at DATETIME NULL COMMENT '最近同步时间',
    sync_status VARCHAR(32) NOT NULL DEFAULT 'pending' COMMENT 'pending/syncing/ok/fail',
    sync_message TEXT NULL COMMENT '最近同步消息',
    content_hash VARCHAR(64) NULL COMMENT '内容摘要 hash',
    status TINYINT NOT NULL DEFAULT 1 COMMENT '1 启用 0 停用',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    deleted TINYINT NOT NULL DEFAULT 0 COMMENT '逻辑删除',
    KEY idx_status_deleted (status, deleted)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Git 业务仓库配置';

-- ---------- 代码符号（图节点）----------
CREATE TABLE IF NOT EXISTS copilot_code_symbol (
    id BIGINT AUTO_INCREMENT PRIMARY KEY COMMENT '主键',
    repo_id BIGINT NOT NULL COMMENT 'copilot_git_repo.id',
    symbol_kind VARCHAR(32) NOT NULL COMMENT 'class/method/mapper_statement/route',
    qualified_name VARCHAR(512) NOT NULL COMMENT '全限定名',
    file_path VARCHAR(512) NOT NULL COMMENT '相对仓库根路径',
    start_line INT NOT NULL DEFAULT 0 COMMENT '起始行',
    end_line INT NOT NULL DEFAULT 0 COMMENT '结束行',
    signature TEXT NULL COMMENT '方法签名',
    doc_comment TEXT NULL COMMENT '文档注释',
    http_method VARCHAR(16) NULL COMMENT 'Controller HTTP 方法',
    http_path VARCHAR(256) NULL COMMENT 'Controller 路由路径',
    status TINYINT NOT NULL DEFAULT 1 COMMENT '1 有效',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    deleted TINYINT NOT NULL DEFAULT 0 COMMENT '逻辑删除',
    UNIQUE KEY uk_repo_qualified (repo_id, qualified_name(191)),
    KEY idx_repo_kind (repo_id, symbol_kind, deleted)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='代码知识图谱节点';

-- ---------- 代码符号边（图边）----------
CREATE TABLE IF NOT EXISTS copilot_code_edge (
    id BIGINT AUTO_INCREMENT PRIMARY KEY COMMENT '主键',
    repo_id BIGINT NOT NULL COMMENT '仓库 id',
    from_symbol_id BIGINT NOT NULL COMMENT '源符号 id',
    to_symbol_id BIGINT NULL COMMENT '目标符号 id（references_table 可为空）',
    edge_type VARCHAR(32) NOT NULL COMMENT 'calls/uses_mapper/references_table/imports',
    target_name VARCHAR(256) NULL COMMENT '边目标名（表名/mapper id 等）',
    status TINYINT NOT NULL DEFAULT 1 COMMENT '1 有效',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    deleted TINYINT NOT NULL DEFAULT 0 COMMENT '逻辑删除',
    KEY idx_from_symbol (from_symbol_id, deleted),
    KEY idx_repo_type (repo_id, edge_type, deleted)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='代码知识图谱边';

-- ---------- 问数召回单元：报表/接口级 artifact ----------
CREATE TABLE IF NOT EXISTS copilot_code_artifact (
    id BIGINT AUTO_INCREMENT PRIMARY KEY COMMENT '主键',
    repo_id BIGINT NOT NULL COMMENT '仓库 id',
    symbol_id BIGINT NULL COMMENT '关联主符号 id',
    artifact_type VARCHAR(32) NOT NULL COMMENT 'controller_method/mybatis_select/service_rule',
    title VARCHAR(256) NOT NULL COMMENT '标题',
    summary_text TEXT NULL COMMENT '业务口径摘要（可 LLM  enrichment）',
    tables_json TEXT NULL COMMENT '涉及业务表 JSON 数组',
    join_hints_json TEXT NULL COMMENT 'JOIN 线索 JSON',
    filter_hints_json TEXT NULL COMMENT '过滤线索 JSON',
    dimensions_json TEXT NULL COMMENT '维度/动态列提示 JSON',
    metrics_json TEXT NULL COMMENT '指标提示 JSON',
    raw_snippet MEDIUMTEXT NULL COMMENT '原文片段',
    search_text TEXT NULL COMMENT '入 ES 的拼接文本',
    status TINYINT NOT NULL DEFAULT 1 COMMENT '1 启用',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    deleted TINYINT NOT NULL DEFAULT 0 COMMENT '逻辑删除',
    KEY idx_repo_type (repo_id, artifact_type, deleted),
    FULLTEXT KEY ft_search_text (search_text)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='代码知识 artifact';

-- ---------- 代码 artifact ↔ meta 表桥梁 ----------
CREATE TABLE IF NOT EXISTS copilot_code_table_link (
    id BIGINT AUTO_INCREMENT PRIMARY KEY COMMENT '主键',
    artifact_id BIGINT NOT NULL COMMENT 'copilot_code_artifact.id',
    table_name VARCHAR(128) NOT NULL COMMENT 'copilot_table_meta.table_name',
    link_type VARCHAR(32) NOT NULL DEFAULT 'primary_fact' COMMENT 'primary_fact/join_dim/filter',
    confidence DECIMAL(4,3) NOT NULL DEFAULT 1.000 COMMENT '置信度 0~1',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    deleted TINYINT NOT NULL DEFAULT 0 COMMENT '逻辑删除',
    KEY idx_artifact (artifact_id, deleted),
    KEY idx_table_name (table_name, deleted)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='代码 artifact 与 meta 表关联';
