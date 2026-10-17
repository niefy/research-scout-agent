from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from app.collectors.base import ChannelAdapter, RawItem

_MOCK_ITEMS = [
    {
        "external_id": "mock-001",
        "title": "贵州茅台三季度营收同比增长12%，直营渠道占比继续提升",
        "content": (
            "贵州茅台发布三季报，前三季度实现营业收入1231亿元，同比增长12.1%；"
            "归母净利润608亿元，同比增长13.4%。公司直营渠道收入占比提升至46%，"
            "i茅台平台贡献稳步增长。机构认为，飞天茅台批价保持稳定，"
            "全年目标完成概率较高，维持买入评级。"
        ),
        "author": "张分析",
        "source": "示例证券研究所",
        "url": "https://example.com/reports/moutai-q3",
        "hours_ago": 2,
        "engagement": {"views": 3200, "comments": 18},
    },
    {
        "external_id": "mock-002",
        "title": "半导体设备国产化加速，头部厂商订单能见度提升",
        "content": (
            "多家半导体设备公司披露订单数据，刻蚀、薄膜沉积等环节国产替代率持续提升。"
            "业内预计2027年国内晶圆厂扩产仍将维持高位，设备厂商在手订单饱满。"
            "风险在于下游资本开支不及预期以及海外限制升级。"
        ),
        "author": "李产业",
        "source": "产业观察",
        "url": "https://example.com/reports/semi-equipment",
        "hours_ago": 5,
        "engagement": {"views": 2100, "comments": 9},
    },
    {
        "external_id": "mock-003",
        "title": "央行开展6000亿元MLF操作，市场流动性保持合理充裕",
        "content": (
            "中国人民银行今日开展6000亿元中期借贷便利操作，中标利率维持不变。"
            "分析人士指出，本次操作对冲到期量后实现净投放，体现呵护流动性的态度。"
            "短端资金面预计保持平稳，债市情绪偏暖。"
        ),
        "author": "王宏观",
        "source": "宏观研究笔记",
        "url": "https://example.com/reports/pboc-mlf",
        "hours_ago": 8,
        "engagement": {"views": 1800, "comments": 12},
    },
    {
        "external_id": "mock-004",
        "title": "新能源汽车10月前三周零售同比增长8%，价格战压力边际缓解",
        "content": (
            "乘联会数据显示，10月前三周新能源乘用车零售同比增长8%，环比改善。"
            "多家车企收紧终端优惠，行业价格战出现边际缓和迹象。"
            "但碳酸锂价格波动和明年购置税政策变化仍需跟踪。"
        ),
        "author": "赵汽车",
        "source": "汽车产业研究",
        "url": "https://example.com/reports/ev-oct",
        "hours_ago": 12,
        "engagement": {"views": 2600, "comments": 21},
    },
    {
        "external_id": "mock-005",
        "title": "某消费龙头渠道调研：动销环比改善，库存降至健康水平",
        "content": (
            "渠道调研显示，公司核心单品在华东、华南市场动销环比改善，"
            "经销商库存降至约1.5个月，处于近三年较低水平。"
            "公司计划四季度加大费用投放，预计利润率保持稳定。"
        ),
        "author": "陈消费",
        "source": "消费研究随笔",
        "url": "https://example.com/reports/consumer-channel",
        "hours_ago": 20,
        "engagement": {"views": 900, "comments": 3},
    },
    {
        "external_id": "mock-006",
        "title": "海外AI资本开支超预期，算力产业链景气度延续",
        "content": (
            "北美云厂商上调2027年资本开支指引，AI服务器和光模块需求强劲。"
            "国内算力产业链公司订单饱满，但需关注估值处于高位以及技术路线变化的风险。"
        ),
        "author": "周科技",
        "source": "科技前线",
        "url": "https://example.com/reports/ai-capex",
        "hours_ago": 30,
        "engagement": {"views": 4100, "comments": 26},
    },
]


class MockAdapter(ChannelAdapter):
    key = "mock"
    display_name = "示例数据源"
    default_config = {}

    async def fetch(
        self,
        client: httpx.AsyncClient,
        config: dict[str, Any],
        limit: int,
    ) -> list[RawItem]:
        now = datetime.now(UTC)
        return [
            RawItem(
                external_id=entry["external_id"],
                url=entry["url"],
                title=entry["title"],
                content=entry["content"],
                published_at=now - timedelta(hours=entry["hours_ago"]),
                author_name=entry["author"],
                author_external_id=f"mock-author-{entry['author']}",
                source_name=entry["source"],
                engagement=entry["engagement"],
                meta={"channel": "mock"},
            )
            for entry in _MOCK_ITEMS[:limit]
        ]


__all__ = ["MockAdapter"]
