import os
import asyncio
import json
import argparse

from autoagents.agents.search import ActionRunner
from autoagents.agents.wiki_agent import WikiActionRunner
from dataset import BAMBOOGLE, DEFAULT_Q, Q_HOTPOTQA, FT, HF
from langchain.chat_models import ChatOpenAI
from autoagents.models.custom import CustomLLM
from pprint import pprint


OPENAI_MODEL_NAMES = {"gpt-3.5-turbo", "gpt-4"}
AWAIT_TIMEOUT: int = 120


async def work(user_input, model: str, temperature: int, use_wikiagent: bool, persist_logs: bool):
    outputq = asyncio.Queue()
    if model not in OPENAI_MODEL_NAMES:
        llm = CustomLLM(
            model_name=model,
            temperature=temperature,
            request_timeout=AWAIT_TIMEOUT
        )
    else:
        llm = ChatOpenAI(
            openai_api_key=os.getenv("OPENAI_API_KEY"),
            openai_organization=os.getenv("OPENAI_API_ORG"),
            temperature=temperature,
            model_name=model,
            request_timeout=AWAIT_TIMEOUT
        )
    runner = ActionRunner(outputq, llm=llm, persist_logs=persist_logs) if not use_wikiagent \
        else WikiActionRunner(outputq, llm=llm, persist_logs=persist_logs)
    task = asyncio.create_task(runner.run(user_input, outputq))

    while True:
        try:
            output = await asyncio.wait_for(outputq.get(), AWAIT_TIMEOUT)
            print(output)
        except asyncio.TimeoutError:
            break
        if isinstance(output, RuntimeWarning):
            print(f"Question: {user_input}")
            print(output)
            continue
        elif isinstance(output, Exception):
            print(f"Question: {user_input}")
            print(output)
            return
        try:
            parsed = json.loads(output)
            print(json.dumps(parsed, indent=2))
            print("-----------------------------------------------------------")
            if parsed["action"] == "Tool_Finish":
                break
        except:
            print(f"Question: {user_input}")
            print(output)
            print("-----------------------------------------------------------")
    return await task




async def main(questions, args):
    sem = asyncio.Semaphore(10)
    
    async def safe_work(user_input, model: str, temperature: int, use_wikiagent: bool, persist_logs: bool):
        async with sem:
            return await work(user_input, model, temperature, use_wikiagent, persist_logs)
    
    use_wikiagent = False if args.agent == "ddg" else True
    persist_logs = True if args.persist_logs else False
    await asyncio.gather(*[safe_work(q, args.model, args.temperature, use_wikiagent, persist_logs) for q in questions])


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=str, default="gpt-3.5-turbo")
    parser.add_argument("--temperature", type=int, default=0)
    parser.add_argument("--agent",
        default="ddg",
        const="ddg",
        nargs="?",
        choices=("ddg", "wiki"),
        help='which action agent we want to interact with(default: ddg)'
    )
    parser.add_argument("--persist-logs", action="store_true")
    parser.add_argument("--dataset",
        default="default",
        const="default",
        nargs="?",
        choices=("default", "hotpotqa", "ft", "hf", "bamboogle"),
        help='which dataset we want to interact with(default: default)'
    )
    args = parser.parse_args()
    print(args)
    use_wikiagent = False if args.agent == "ddg" else True
    questions = []
    if args.dataset == "ft":
        questions = [q for _, q in FT]
    elif args.dataset == "hf":
        questions = [q for _, q in HF]
    elif args.dataset == "hotpot":
        questions = [q for _, q in Q_HOTPOTQA]
    elif args.dataset == "bamboogle":
        questions = BAMBOOGLE["questions"]
    else:
        questions = [q for _, q in DEFAULT_Q]
    asyncio.run(main(questions, args))
