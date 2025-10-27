from agents import Agent  # type: ignore

from config.prompts import DEFAULT_AGENT_INSTRUCTIONS
from config.settings import settings


chat_agent = Agent(
    name="AI Learner",
    instructions=DEFAULT_AGENT_INSTRUCTIONS,
    model=settings.models.chat,
)
