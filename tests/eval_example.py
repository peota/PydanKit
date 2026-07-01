"""Example: evaluating the agent with Pydantic Evals.

This is a *pattern to copy*, not part of the pytest suite (pytest only collects
``test_*.py``). It shows the guide's #1 principle in action: establish a baseline
you can measure, then swap in cheaper/faster models and check quality holds.

Run it with::

    python -m tests.eval_example

It uses TestModel so it runs offline and deterministically. To evaluate real
quality, drop the ``agent.override(...)`` line so it calls your configured model,
and replace the case(s) and evaluator(s) with ones that reflect your use case.
"""

import asyncio
import sys
from dataclasses import dataclass

from pydantic_ai.models.test import TestModel
from pydantic_evals import Case, Dataset
from pydantic_evals.evaluators import Evaluator, EvaluatorContext

from src.agent import get_agent
from src.dependencies import AgentDeps


@dataclass
class OutputNotEmpty(Evaluator):
    """A trivial evaluator: the agent must return non-empty text.

    Replace with real checks: exact match, contains-keyword, an LLM judge, etc.
    """

    def evaluate(self, ctx: EvaluatorContext) -> bool:
        return bool(ctx.output and str(ctx.output).strip())


async def run_agent_task(inputs: str) -> str:
    """The 'task under evaluation': one agent run for a given input."""
    agent = get_agent()
    # Remove this override to evaluate your real model instead of TestModel.
    with agent.override(model=TestModel()):
        result = await agent.run(inputs, deps=AgentDeps(memory_enabled=False))
    return result.output


dataset = Dataset(
    name="pydankit-example",
    cases=[
        Case(name="greeting", inputs="Say hello to the user."),
        Case(name="question", inputs="What can you help me with?"),
    ],
    evaluators=[OutputNotEmpty()],
)


def main() -> None:
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        # The report renderer emits unicode (e.g. checkmarks); avoid cp1252 errors.
        sys.stdout.reconfigure(encoding="utf-8")
    report = dataset.evaluate_sync(run_agent_task)
    report.print(include_input=True, include_output=True)


if __name__ == "__main__":
    main()
