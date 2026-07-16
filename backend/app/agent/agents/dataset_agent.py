"""Dataset management specialist."""

from app.agent.prompts import DATASET_PROMPT
from app.agent.scoped_agent import ScopedToolAgent
from app.agent.tools import build_dataset_tools, build_knowledge_tools


class DatasetAgent(ScopedToolAgent):
    def __init__(self, *, user_id: int, session_uuid: str) -> None:
        super().__init__(
            name="dataset",
            system_prompt=DATASET_PROMPT,
            tools=build_dataset_tools(user_id, session_uuid)
            + build_knowledge_tools(user_id, session_uuid),
        )
