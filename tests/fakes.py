import respx  # mocks httpx calls
from langchain_core.language_models import BaseChatModel  # base class to subclass
from langchain_core.messages import AIMessage  # scripted reply type
from langchain_core.outputs import ChatGeneration, ChatResult  # model output wrappers
from pydantic import Field  # mutable default for the prompt log

API = "https://pokeapi.co/api/v2/"  # base url used in mocks


class FakeChatModel(BaseChatModel):
    script: list[AIMessage]  # replies returned in order
    prompts: list = Field(default_factory=list)  # every prompt the model received

    @property
    def _llm_type(self) -> str:
        return "fake"  # required identifier

    def bind_tools(self, tools, **kwargs):
        return self  # tool calls are scripted, so binding is a no-op

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        self.prompts.append(list(messages))  # record what the model saw
        return ChatResult(generations=[ChatGeneration(message=self.script.pop(0))])  # next scripted reply


def tool_call(name: str, args: dict, call_id: str = "c1") -> AIMessage:
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": call_id}])  # an AI message requesting a tool


def mock_pokemon(name: str, number: int, types: list[str], hp: int) -> None:
    respx.get(API + f"pokemon/{name}").respond(json={  # minimal /pokemon payload
        "name": name, "id": number, "height": 10, "sprites": {"other": {"official-artwork": {"front_default": f"https://img/{name}.png"}}}, "weight": 100, "species": {"name": name},
        "types": [{"type": {"name": t}} for t in types],
        "stats": [{"stat": {"name": "hp"}, "base_stat": hp}],
        "abilities": [{"ability": {"name": "x"}, "is_hidden": False}]})
    respx.get(API + f"pokemon-species/{name}").respond(json={  # minimal /pokemon-species payload
        "genera": [{"language": {"name": "en"}, "genus": f"{name} Pokémon"}],
        "flavor_text_entries": [{"language": {"name": "en"}, "flavor_text": f"About {name}."}],
        "generation": {"name": "generation-i"}, "is_legendary": False, "is_mythical": False,
        "evolution_chain": {"url": API + f"evolution-chain/{number}/"}})
    respx.get(API + f"evolution-chain/{number}").respond(json={"chain": {"species": {"name": name}, "evolves_to": []}})  # no evolutions
