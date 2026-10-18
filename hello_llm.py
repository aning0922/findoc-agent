"""
hello_llm.py — 你的第一个 LLM 调用(Week 1 热身)
跑通它 = 你的第一条 commit。看到流式输出,你就从"读计划"正式进入"写代码"。

跑起来(环境已在第 0 周配好,约 5 分钟):
  1) 在 findoc-rag 目录:  uv sync            # 装依赖(openai/python-dotenv 已在 pyproject,别用 pip)
  2) cp .env.example .env,填 DEEPSEEK_API_KEY
     LLM_MODEL 默认使用 deepseek-v4-flash,也可以改成控制台中的其他可用模型
  3) 运行:                uv run python hello_llm.py   # 别手动 activate,交给 uv run
"""

import os
import asyncio
from dotenv import load_dotenv          # 读 .env 里的密钥(永远别把 key 写进代码)
from openai import OpenAI, AsyncOpenAI   # DeepSeek 兼容 OpenAI 的 SDK,直接用

load_dotenv()  # 把 .env 的变量加载进环境变量

MODEL = os.environ.get("LLM_MODEL", "deepseek-v4-flash")  # 从环境变量读取模型名

# DeepSeek 复用 OpenAI 的 SDK,只是换 base_url。类似 C# 里 new HttpClient + 配 BaseAddress。
client = OpenAI(
    api_key=os.environ["DEEPSEEK_API_KEY"],
    base_url="https://api.deepseek.com",
)


def simple_call():
    """最简单的一次问答(非流式)。"""
    resp = client.chat.completions.create(
        model=MODEL,
        messages=[                       # messages = 对话历史,一个 list[dict](Lua 里的 table 数组)
            {"role": "system", "content": "你是一个简洁的助手。"},
            {"role": "user", "content": "用一句话解释什么是 RAG。"},
        ],
        temperature=0.3,                 # 越低越稳定,越高越发散
    )
    print("【回答】", resp.choices[0].message.content)
    # 每次调用都耗额度,养成看 token 的习惯(成本意识 = 工程岗加分项)
    u = resp.usage
    print(f"【token】prompt={u.prompt_tokens} completion={u.completion_tokens} total={u.total_tokens}")


def streaming_call():
    """流式输出:一个字一个字往外蹦(ChatGPT 打字效果)。这就是后面 Gateway 要做的 SSE。"""
    stream = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": "用三点说明有工程经验的人转 AI 应用的优势。"}],
        stream=True,                     # 关键:开启流式
    )
    print("【流式】", end="", flush=True)
    for chunk in stream:                 # 像 C# 的 IEnumerable / Lua 的 for,每次拿一小段
        delta = chunk.choices[0].delta.content or ""
        print(delta, end="", flush=True)
    print()


async def async_calls():
    """异步并发:同时问两个问题。你用过 async/await——这里心智一样,await 就是'不阻塞地等'。"""
    aclient = AsyncOpenAI(api_key=os.environ["DEEPSEEK_API_KEY"], base_url="https://api.deepseek.com")

    async def ask(q: str) -> str:
        resp = await aclient.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": q}],
        )
        return resp.choices[0].message.content

    # asyncio.gather 同时跑多个,等同 C# 的 Task.WhenAll
    answers = await asyncio.gather(
        ask("DeepSeek 和 Qwen 各是什么?一句话。"),
        ask("向量数据库是干什么的?一句话。"),
    )
    for i, a in enumerate(answers, 1):
        print(f"【并发{i}】{a}")


if __name__ == "__main__":
    simple_call()
    print("-" * 40)
    streaming_call()
    print("-" * 40)
    asyncio.run(async_calls())   # asyncio.run 启动事件循环(原理第 6-7 周再深究,现在会用就行)
