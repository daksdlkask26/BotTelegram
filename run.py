import asyncio
import main

async def _runner():
    # gọi main.main() của bạn (hàm sync)
    main.main()

if __name__ == "__main__":
    asyncio.run(_runner())
