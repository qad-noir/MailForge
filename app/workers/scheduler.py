import asyncio

import typer

from app.db.session import SessionFactory
from app.services.scheduler_service import SchedulerService

app = typer.Typer()


async def run_once() -> int:
    async with SessionFactory() as session:
        return await SchedulerService(session).process_due()


async def run_scheduler(loop: bool, interval: float) -> None:
    while True:
        await run_once()
        if not loop:
            return
        await asyncio.sleep(interval)


@app.command()
def main(
    loop: bool = typer.Option(False, "--loop"),
    interval: float = typer.Option(30, "--interval", min=1),
) -> None:
    asyncio.run(run_scheduler(loop, interval))


if __name__ == "__main__":
    app()

