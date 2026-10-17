from __future__ import annotations

import argparse
import asyncio
import json
import logging

from app.db.session import async_session_factory, close_db, init_db
from app.services.analysis import analyze_pending
from app.services.ingest import crawl_channels
from app.services.seed import seed_base, seed_demo

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
logger = logging.getLogger("research-scout")


def _parse_channels(value: str | None) -> list[str] | None:
    if not value:
        return None
    return [item.strip() for item in value.split(",") if item.strip()]


async def command_init_db() -> None:
    await init_db()
    logger.info("database tables created")


async def command_seed(demo: bool = False) -> None:
    await init_db()
    async with async_session_factory() as session:
        summary = await seed_demo(session) if demo else await seed_base(session)
    logger.info("seed complete: %s", json.dumps(summary, ensure_ascii=False, default=str))


async def command_crawl(channels: str | None, limit: int, analyze: bool) -> None:
    async with async_session_factory() as session:
        results = await crawl_channels(
            session, channel_codes=_parse_channels(channels), limit=limit
        )
        logger.info("crawl results: %s", json.dumps(results, ensure_ascii=False))
        if analyze:
            stats = await analyze_pending(session, limit=max(limit * len(results), 50))
            logger.info("analysis: %s", stats)


async def command_analyze(limit: int, force: bool) -> None:
    async with async_session_factory() as session:
        stats = await analyze_pending(session, limit=limit, force=force)
        logger.info("analysis: %s", stats)


async def main_async(args: argparse.Namespace) -> None:
    if args.command == "init-db":
        await command_init_db()
    elif args.command == "seed":
        await command_seed(demo=False)
    elif args.command == "seed-demo":
        await command_seed(demo=True)
    elif args.command == "crawl":
        await command_crawl(args.channels, args.limit, args.analyze)
    elif args.command == "analyze":
        await command_analyze(args.limit, args.force)
    else:
        raise SystemExit(f"unknown command: {args.command}")
    await close_db()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="research-scout", description="Research Scout CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init-db", help="create database tables")
    sub.add_parser("seed", help="seed channels, industries, securities and admin")
    sub.add_parser("seed-demo", help="seed base data plus mock posts and demo user")

    crawl = sub.add_parser("crawl", help="fetch reports from channels")
    crawl.add_argument("--channels", help="comma separated channel codes")
    crawl.add_argument("--limit", type=int, default=30)
    crawl.add_argument("--analyze", action="store_true", help="analyze fetched reports")

    analyze = sub.add_parser("analyze", help="run the analysis pipeline on pending reports")
    analyze.add_argument("--limit", type=int, default=50)
    analyze.add_argument("--force", action="store_true", help="re-analyze reports already done")

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
