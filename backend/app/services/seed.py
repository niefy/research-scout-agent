from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import hash_password
from app.models.author import AuthorIdentity
from app.models.channel import Channel
from app.models.personalization import AuthorFollow, WatchlistItem
from app.models.security import Industry, Security
from app.models.user import User
from app.services.analysis import analyze_pending
from app.services.ingest import crawl_channels

logger = logging.getLogger(__name__)

CHANNELS = [
    {
        "code": "sina",
        "name": "新浪财经",
        "adapter_key": "sina",
        "enabled": True,
        "config": {"lids": [2516, 2517], "num_per_lid": 30, "fetch_detail": True},
    },
    {
        "code": "wallstreetcn",
        "name": "华尔街见闻",
        "adapter_key": "wallstreetcn",
        "enabled": True,
        "config": {"channel": "global", "fetch_detail": True},
    },
    {
        "code": "mock",
        "name": "示例数据源",
        "adapter_key": "mock",
        "enabled": True,
        "config": {},
    },
]

INDUSTRIES = [
    ("IND_BAIJIU", "白酒", 1),
    ("IND_CONSUMER", "消费", 1),
    ("IND_SEMI", "半导体", 1),
    ("IND_NEWENERGY", "新能源", 1),
    ("IND_AUTO", "汽车", 1),
    ("IND_BANK", "银行", 1),
    ("IND_BROKER", "券商", 1),
    ("IND_PHARMA", "医药", 1),
    ("IND_COLOR", "有色金属", 1),
    ("IND_AI", "AI算力", 1),
    ("IND_TELECOM", "通信", 1),
    ("IND_UTILITY", "公用事业", 1),
    ("IND_REALESTATE", "房地产", 1),
    ("IND_CHEM", "化工", 1),
]

SECURITIES = [
    ("600519.SH", "600519", "贵州茅台", "SH", "IND_BAIJIU", ["茅台"]),
    ("000858.SZ", "000858", "五粮液", "SZ", "IND_BAIJIU", []),
    ("000333.SZ", "000333", "美的集团", "SZ", "IND_CONSUMER", ["美的"]),
    ("600887.SH", "600887", "伊利股份", "SH", "IND_CONSUMER", ["伊利"]),
    ("601888.SH", "601888", "中国中免", "SH", "IND_CONSUMER", ["中免"]),
    ("300750.SZ", "300750", "宁德时代", "SZ", "IND_NEWENERGY", ["宁王"]),
    ("601012.SH", "601012", "隆基绿能", "SH", "IND_NEWENERGY", ["隆基"]),
    ("002594.SZ", "002594", "比亚迪", "SZ", "IND_AUTO", []),
    ("601633.SH", "601633", "长城汽车", "SH", "IND_AUTO", []),
    ("688981.SH", "688981", "中芯国际", "SH", "IND_SEMI", ["中芯"]),
    ("002371.SZ", "002371", "北方华创", "SZ", "IND_SEMI", []),
    ("603501.SH", "603501", "韦尔股份", "SH", "IND_SEMI", ["韦尔"]),
    ("002415.SZ", "002415", "海康威视", "SZ", "IND_AI", ["海康"]),
    ("688111.SH", "688111", "金山办公", "SH", "IND_AI", ["WPS"]),
    ("000063.SZ", "000063", "中兴通讯", "SZ", "IND_TELECOM", ["中兴"]),
    ("600941.SH", "600941", "中国移动", "SH", "IND_TELECOM", []),
    ("600036.SH", "600036", "招商银行", "SH", "IND_BANK", ["招行"]),
    ("601166.SH", "601166", "兴业银行", "SH", "IND_BANK", []),
    ("000001.SZ", "000001", "平安银行", "SZ", "IND_BANK", []),
    ("600030.SH", "600030", "中信证券", "SH", "IND_BROKER", []),
    ("300059.SZ", "300059", "东方财富", "SZ", "IND_BROKER", ["东财"]),
    ("600276.SH", "600276", "恒瑞医药", "SH", "IND_PHARMA", ["恒瑞"]),
    ("300760.SZ", "300760", "迈瑞医疗", "SZ", "IND_PHARMA", ["迈瑞"]),
    ("601899.SH", "601899", "紫金矿业", "SH", "IND_COLOR", ["紫金"]),
    ("600111.SH", "600111", "北方稀土", "SH", "IND_COLOR", ["稀土"]),
    ("601088.SH", "601088", "中国神华", "SH", "IND_UTILITY", ["神华"]),
    ("600900.SH", "600900", "长江电力", "SH", "IND_UTILITY", ["长电"]),
    ("601668.SH", "601668", "中国建筑", "SH", "IND_REALESTATE", []),
    ("600048.SH", "600048", "保利发展", "SH", "IND_REALESTATE", ["保利"]),
    ("000002.SZ", "000002", "万科A", "SZ", "IND_REALESTATE", ["万科"]),
    ("600309.SH", "600309", "万华化学", "SH", "IND_CHEM", ["万华"]),
]

DEMO_EMAIL = "demo@example.com"
DEMO_PASSWORD = "demo12345"


async def seed_channels(session: AsyncSession) -> int:
    created = 0
    for data in CHANNELS:
        existing = await session.scalar(select(Channel).where(Channel.code == data["code"]))
        if existing is None:
            session.add(Channel(**data))
            created += 1
    await session.commit()
    return created


async def seed_industries(session: AsyncSession) -> int:
    created = 0
    for code, name, level in INDUSTRIES:
        existing = await session.scalar(select(Industry).where(Industry.code == code))
        if existing is None:
            session.add(Industry(code=code, name=name, level=level))
            created += 1
    await session.commit()
    return created


async def seed_securities(session: AsyncSession) -> int:
    created = 0
    for code, symbol, name, exchange, industry_code, aliases in SECURITIES:
        existing = await session.scalar(select(Security).where(Security.code == code))
        if existing is None:
            session.add(
                Security(
                    code=code,
                    symbol=symbol,
                    name=name,
                    exchange=exchange,
                    industry_code=industry_code,
                    aliases=aliases,
                )
            )
            created += 1
    await session.commit()
    return created


async def seed_admin(session: AsyncSession) -> User | None:
    if not settings.admin_email or not settings.admin_password:
        return None
    email = settings.admin_email.strip().lower()
    existing = await session.scalar(select(User).where(User.email == email))
    if existing is not None:
        if existing.role != "admin":
            existing.role = "admin"
            await session.commit()
        return existing
    admin = User(
        email=email,
        password_hash=hash_password(settings.admin_password),
        nickname="管理员",
        role="admin",
        status="active",
        scoring_config={},
    )
    session.add(admin)
    await session.commit()
    await session.refresh(admin)
    return admin


async def seed_base(session: AsyncSession) -> dict:
    channels = await seed_channels(session)
    industries = await seed_industries(session)
    securities = await seed_securities(session)
    admin = await seed_admin(session)
    return {
        "channels_created": channels,
        "industries_created": industries,
        "securities_created": securities,
        "admin": admin.email if admin else None,
    }


async def seed_demo(session: AsyncSession) -> dict:
    base = await seed_base(session)

    mock_channel = await session.scalar(select(Channel).where(Channel.code == "mock"))
    if mock_channel is None:
        raise RuntimeError("mock channel missing")
    await crawl_channels(session, channel_codes=["mock"], limit=20)
    analysis = await analyze_pending(session, limit=50)

    demo = await session.scalar(select(User).where(User.email == DEMO_EMAIL))
    if demo is None:
        demo = User(
            email=DEMO_EMAIL,
            password_hash=hash_password(DEMO_PASSWORD),
            nickname="演示用户",
            role="user",
            status="active",
            scoring_config={},
        )
        session.add(demo)
        await session.commit()
        await session.refresh(demo)

    author_ids = (
        await session.scalars(
            select(AuthorIdentity.author_id).where(
                AuthorIdentity.channel_id == mock_channel.id
            )
        )
    ).all()
    for author_id in set(author_ids):
        follow = await session.scalar(
            select(AuthorFollow).where(
                AuthorFollow.user_id == demo.id,
                AuthorFollow.author_id == author_id,
            )
        )
        if follow is None:
            session.add(AuthorFollow(user_id=demo.id, author_id=author_id, weight=1.0))
    await session.commit()

    for code in ("600519.SH", "300750.SZ", "688981.SH"):
        security = await session.scalar(select(Security).where(Security.code == code))
        if security is None:
            continue
        item = await session.scalar(
            select(WatchlistItem).where(
                WatchlistItem.user_id == demo.id,
                WatchlistItem.security_id == security.id,
            )
        )
        if item is None:
            session.add(WatchlistItem(user_id=demo.id, security_id=security.id))
    await session.commit()

    mock_author_count = len(set(author_ids))
    logger.info(
        "demo seeded: %s authors followed, analysis=%s, login=%s / %s",
        mock_author_count,
        analysis,
        DEMO_EMAIL,
        DEMO_PASSWORD,
    )
    return {
        **base,
        "demo_email": DEMO_EMAIL,
        "demo_password": DEMO_PASSWORD,
        "mock_authors_followed": mock_author_count,
        "analysis": analysis,
    }
