"""Product catalog and price specialist."""

from app.agent.prompts import CATALOG_PROMPT
from app.agent.scoped_agent import ScopedToolAgent
from app.agent.tools import build_catalog_tools, build_interaction_tools, build_knowledge_tools


class CatalogAgent(ScopedToolAgent):
    def __init__(self, *, user_id: int, session_uuid: str) -> None:
        super().__init__(
            name="catalog",
            system_prompt=CATALOG_PROMPT,
            tools=build_catalog_tools(user_id, session_uuid)
            + build_interaction_tools("catalog")
            + build_knowledge_tools(user_id, session_uuid),
        )
