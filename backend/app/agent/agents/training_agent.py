"""Remote/local training monitoring specialist."""

from app.agent.prompts import TRAINING_PROMPT
from app.agent.scoped_agent import ScopedToolAgent
from app.agent.tools import build_knowledge_tools, build_training_tools


class TrainingAgent(ScopedToolAgent):
    def __init__(self, *, user_id: int, session_uuid: str) -> None:
        super().__init__(
            name="training",
            system_prompt=TRAINING_PROMPT,
            tools=build_training_tools(user_id, session_uuid)
            + build_knowledge_tools(user_id, session_uuid),
        )
