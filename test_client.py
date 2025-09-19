import asyncio
from fastmcp import Client

async def main():
    # URL твоего сервера
    url = "http://127.0.0.1:8000/mcp"
    async with Client(url) as c:
        res = await c.call_tool("greet", {"name": "Мир"})
        print(res)

if __name__ == "__main__":
    asyncio.run(main())
