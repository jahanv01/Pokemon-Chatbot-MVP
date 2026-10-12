from langchain.chat_models import init_chat_model  # provider-agnostic model factory
from langchain_core.messages import AIMessage, SystemMessage  # greeting + system prompt message types
from langgraph.checkpoint.memory import InMemorySaver  # per-thread conversation memory
from langgraph.graph import START, MessagesState, StateGraph  # graph building blocks
from langgraph.prebuilt import ToolNode, tools_condition  # tool execution + routing

from app.config import settings  # model name and recursion limit
from app.tools import TOOLS  # the four Pokémon tools

SYSTEM_PROMPT = """You are a friendly Pokémon expert chatting with a user.
- ALWAYS use the tools for facts (types, stats, evolutions, moves, abilities). Never answer facts from memory.
- State only what appears in tool results. Do not add outside trivia (anime, lore) and do not guess evolution methods; use the "how" details in evolution_paths.
- When comparing Pokémon you MUST call get_pokemon for EACH one being compared, including one discussed earlier, so the user sees both cards. Example: after discussing Pikachu, "How's that different from Charizard?" needs get_pokemon for pikachu AND charizard.
- For weaknesses or resistances of a Pokémon, call get_type_matchups once with ALL of its types (the tool does the math).
- Report type multipliers exactly as the tool gives them (4x, 2x, 0.5x, 0.25x, immune). Don't re-derive them or invent reasons.
- Keep answers short: a few sentences or bullets. A card already shows the stats, so don't list every stat unless asked. Give more detail only when the user asks.
- Resolve references like "it", "that" or "the first one" using the conversation. If it could mean either of two Pokémon just discussed, assume the most recent one, say so in a few words (e.g. "Assuming you mean Charizard…") and offer the other.
- Evolution methods can differ between games. Present the methods the tool gives, say they can vary by game, and if the user names a specific game, say you can't confirm game-specific details.
- You cannot look up which moves a Pokémon learns, where to catch Pokémon, or game-specific data. Say so plainly instead of guessing.
- Explain in plain language for beginners.
- If the question is not about Pokémon, politely say so in one sentence and steer back to Pokémon.
- If the user sounds distressed or in danger (for example "I'm in trouble"), respond briefly and kindly, say you can only help with Pokémon, encourage them to contact local emergency services or someone they trust, and offer to chat about Pokémon when they are ready.
- If a tool returns NOT_FOUND, say so and ask the user which Pokémon (or move/ability/type) they meant.
- If a tool result has a "note" about an auto-corrected name, briefly say you assumed the corrected name (e.g. "I assume you meant Pikachu") and answer normally; don't call the name fake.
- You have already greeted the user, so never greet them again."""  # behaviour rules

GREETING = "Hey there, what’s up?"  # exact text from the brief (curly apostrophe)


def run_config(session_id: str) -> dict:
    return {"configurable": {"thread_id": session_id}, "recursion_limit": settings.recursion_limit}  # thread = memory key, limit stops loops


def build_graph(model=None, fallbacks=None):
    if model is None:  # real run: build models from settings
        model = init_chat_model(settings.llm_model)  # main model
        fallbacks = [init_chat_model(name) for name in settings.fallback_models]  # backups
    llm = model.bind_tools(TOOLS)  # model that can request tool calls
    if fallbacks:  # switch to a backup if the main model errors (quota, outage...)
        llm = llm.with_fallbacks([f.bind_tools(TOOLS) for f in fallbacks])

    async def agent(state: MessagesState) -> dict:
        history = list(state["messages"])  # copy so we can trim it
        while history and isinstance(history[0], AIMessage):  # some providers reject a leading assistant message
            history.pop(0)  # drop the greeting from the model's view
        reply = await llm.ainvoke([SystemMessage(SYSTEM_PROMPT), *history])  # prompt = system + full history
        return {"messages": [reply]}  # append the reply to the history

    builder = StateGraph(MessagesState)  # state is just the message list
    builder.add_node("agent", agent)  # LLM decides: answer or call tools
    builder.add_node("tools", ToolNode(TOOLS, handle_tool_errors=True))  # run tools, turn exceptions into messages
    builder.add_edge(START, "agent")  # always begin with the agent
    builder.add_conditional_edges("agent", tools_condition)  # tool calls -> "tools", otherwise END
    builder.add_edge("tools", "agent")  # feed tool results back to the agent
    return builder.compile(checkpointer=InMemorySaver())  # checkpointer gives conversation memory


async def start_session(graph, session_id: str) -> None:
    await graph.aupdate_state(run_config(session_id), {"messages": [AIMessage(GREETING)]}, as_node="agent")  # seed history with the greeting
