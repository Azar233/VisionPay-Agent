"""Knowledge, fault-case and explicit-memory specialist."""

from app.agent.prompts import KNOWLEDGE_PROMPT
from app.agent.scoped_agent import ScopedToolAgent
from app.agent.tools import build_knowledge_tools


class KnowledgeAgent(ScopedToolAgent):
    def __init__(self, *, user_id: int, session_uuid: str) -> None:
        super().__init__(
            name="knowledge",
            system_prompt=KNOWLEDGE_PROMPT,
            tools=build_knowledge_tools(user_id, session_uuid),
        )
