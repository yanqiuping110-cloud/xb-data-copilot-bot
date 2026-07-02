"""
注册首表元数据 + 人工字段定义（开发/bootstrap 用）。

用法（在 backend/ 目录）:
  $env:APP_ENV = "development"
  $env:SEED_PRIMARY_TABLE = "your_fact_table"
  python scripts/seed_semantic_meta.py

字段取值（project_id 等）请在管理后台「字段取值」维护，不在脚本中写死。
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.business import get_business_engine
from app.meta.repository import MetaRepository, dump_alias_json
from app.meta.service import ColumnInput, MetaService, TableRegisterInput
from config.settings import get_settings

_TABLE = (os.getenv("SEED_PRIMARY_TABLE") or "").strip()

_TABLE_INPUT = TableRegisterInput(
    table_name=_TABLE,
    table_role="fact",
    biz_domain="活动打卡",
    description_manual="活动打卡/运动统计事实表（列定义须与业务库一致，不存在则跳过）。",
    grain="按业务库实际粒度维护",
    sch_id_column="sch_id",
    status=1,
    columns=[
        ColumnInput(
            column_name="people_id",
            description_manual="参与人 ID，统计参与人数时对 people_id 去重计数。",
            column_role="dimension",
            aliases=["参与人", "学生", "用户"],
        ),
        ColumnInput(
            column_name="user_id",
            description_manual="用户 ID，统计参与人数/打卡人数时对 user_id 去重计数。",
            column_role="dimension",
            aliases=["参与人", "用户", "打卡人数"],
        ),
        ColumnInput(
            column_name="sch_id",
            description_manual="学校 ID，学校账户问数必须按本校 sch_id 过滤。",
            column_role="filter",
            aliases=["学校", "本校"],
        ),
        ColumnInput(
            column_name="project_id",
            description_manual="项目/维度 ID；问句含项目名时须结合字段取值映射或 JOIN 维度表过滤。",
            column_role="filter",
            aliases=["项目", "运动项目"],
        ),
        ColumnInput(
            column_name="create_time",
            description_manual="记录创建时间，可用于时间范围筛选。",
            column_role="time",
            aliases=["创建时间", "打卡时间"],
        ),
        ColumnInput(
            column_name="record_date",
            description_manual="业务日期（yyyy-MM-dd），活动时间/打卡时间判定优先使用。",
            column_role="time",
            aliases=["打卡时间", "活动日期", "日期"],
        ),
        ColumnInput(
            column_name="activity_id",
            description_manual="活动 ID，关联具体亲子活动批次。",
            column_role="dimension",
            aliases=["活动"],
        ),
        ColumnInput(
            column_name="id",
            description_manual="主键，每条打卡记录唯一标识。",
            column_role="pk",
            aliases=[],
        ),
    ],
)

_METRIC_UPDATES = [
    {
        "metric_code": "qzs_month_participants",
        "formula_text": "COUNT(DISTINCT people_id)",
        "filter_hint": "当月 create_time；学校账户加 sch_id",
        "time_column": "create_time",
        "agg_type": "count_distinct",
        "unit": "人",
        "admin_only": None,
    },
    {
        "metric_code": "qzs_weekly_trend",
        "formula_text": "COUNT(DISTINCT people_id) GROUP BY DATE(create_time)",
        "filter_hint": "最近 7 天 create_time",
        "time_column": "create_time",
        "agg_type": "count_distinct",
        "unit": "人",
        "admin_only": None,
    },
    {
        "metric_code": "qzs_platform_yesterday",
        "formula_text": "COUNT(*)",
        "filter_hint": "昨日 DATE(create_time)；仅超管/运营",
        "time_column": "create_time",
        "agg_type": "count",
        "unit": "次",
        "admin_only": 1,
    },
]


async def _seed_table(svc: MetaService, repo: MetaRepository) -> int:
    """注册或刷新首表，并写入人工字段定义。返回 table_id。"""
    existing = await repo.find_table_by_name(_TABLE)
    if existing is None:
        row = await svc.register_table(_TABLE_INPUT)
        table_id = row.id
        print(f"已注册表 {_TABLE}，id={table_id}")
    else:
        table_id = existing.id
        await svc.refresh_table_from_business(table_id)
        await repo.update_table_manual_fields(
            table_id,
            table_role=_TABLE_INPUT.table_role,
            biz_domain=_TABLE_INPUT.biz_domain,
            description_manual=_TABLE_INPUT.description_manual,
            grain=_TABLE_INPUT.grain,
            sch_id_column=_TABLE_INPUT.sch_id_column,
            status=_TABLE_INPUT.status,
        )
        print(f"已刷新表 {_TABLE}，id={table_id}")

    col_map = await repo.get_column_map(table_id)
    for col_inp in _TABLE_INPUT.columns or []:
        col = col_map.get(col_inp.column_name)
        if col is None:
            print(f"  跳过字段（业务库不存在）: {col_inp.column_name}")
            continue
        await repo.update_column_manual(
            col.id,
            description_manual=col_inp.description_manual,
            column_role=col_inp.column_role,
            alias_json=dump_alias_json(col_inp.aliases),
        )
    print(f"已更新人工字段定义 {len(_TABLE_INPUT.columns or [])} 项")
    return table_id


async def _seed_metric_extensions(session: AsyncSession) -> None:
    """补充 V004 指标扩展字段。"""
    from sqlalchemy import text

    for m in _METRIC_UPDATES:
        await session.execute(
            text(
                """
                UPDATE copilot_metric_definition SET
                    formula_text = :formula_text,
                    filter_hint = :filter_hint,
                    time_column = :time_column,
                    agg_type = :agg_type,
                    unit = :unit,
                    admin_only = COALESCE(:admin_only, admin_only)
                WHERE metric_code = :metric_code AND deleted = 0
                """
            ),
            m,
        )
    print(f"已更新指标扩展字段 {len(_METRIC_UPDATES)} 条")


async def main() -> None:
    if not _TABLE:
        print("请设置环境变量 SEED_PRIMARY_TABLE")
        sys.exit(1)

    settings = get_settings()
    copilot_engine = create_async_engine(settings.copilot_database_url, echo=False)
    copilot_factory = async_sessionmaker(copilot_engine, expire_on_commit=False)

    business_engine = get_business_engine()
    business_factory = async_sessionmaker(business_engine, expire_on_commit=False)

    async with copilot_factory() as copilot, business_factory() as business:
        svc = MetaService(copilot, business, settings)
        repo = MetaRepository(copilot)
        table_id = await _seed_table(svc, repo)
        await _seed_metric_extensions(copilot)
        await copilot.commit()
        col_count = len(await repo.list_columns(table_id))
        print(f"完成：{_TABLE} 共 {col_count} 个字段元数据")


if __name__ == "__main__":
    if not os.getenv("APP_ENV"):
        os.environ.setdefault("APP_ENV", "development")
    asyncio.run(main())
