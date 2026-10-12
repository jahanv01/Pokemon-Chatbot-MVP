import respx  # mocks httpx calls
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage  # message types

from app.graph import build_graph, run_config, start_session  # code under test
from tests.fakes import FakeChatModel, mock_pokemon, tool_call  # test doubles


@respx.mock
async def test_context_carries_to_second_turn():
    mock_pokemon("pikachu", 25, ["electric"], 35)  # fake PokeAPI data
    mock_pokemon("charizard", 6, ["fire", "flying"], 78)
    model = FakeChatModel(script=[
        tool_call("get_pokemon", {"name": "pikachu"}), AIMessage("Pikachu is an Electric mouse."),  # turn 1
        tool_call("get_pokemon", {"name": "charizard"}), AIMessage("Charizard is Fire/Flying, Pikachu is Electric."),  # turn 2
    ])
    graph = build_graph(model)  # graph with the scripted model
    config = run_config("session-1")  # one thread for both turns
    await graph.ainvoke({"messages": [HumanMessage("What's a Pikachu?")]}, config)  # turn 1
    result = await graph.ainvoke({"messages": [HumanMessage("How's that different from a Charizard?")]}, config)  # turn 2
    turn2_prompt = model.prompts[2]  # first model call of turn 2
    tool_texts = [m.content for m in turn2_prompt if isinstance(m, ToolMessage)]  # tool results it can see
    assert any('"name":"pikachu"' in t for t in tool_texts)  # turn 1's Pikachu data is in the prompt
    assert any(m.content == "What's a Pikachu?" for m in turn2_prompt)  # and turn 1's question
    assert "Charizard" in result["messages"][-1].content  # final comparison answer


async def test_new_session_starts_with_exact_greeting_and_next_turn_works():
    model = FakeChatModel(script=[AIMessage("Hi! Ask me about any Pokémon.")])  # one scripted reply
    graph = build_graph(model)  # graph with the scripted model
    await start_session(graph, "s")  # seed the greeting
    history = (await graph.aget_state(run_config("s"))).values["messages"]  # stored history
    assert history[0].content == "Hey there, what’s up?"  # exact text incl. curly apostrophe
    await graph.ainvoke({"messages": [HumanMessage("hello")]}, run_config("s"))  # next turn must not error
    assert not isinstance(model.prompts[0][1], AIMessage)  # greeting hidden from the model (index 0 is the system prompt)


@respx.mock
async def test_tool_failure_is_explained_not_crashed():
    respx.get("https://pokeapi.co/api/v2/pokemon/pikachu").respond(503)  # PokeAPI is down
    model = FakeChatModel(script=[
        tool_call("get_pokemon", {"name": "pikachu"}),  # model asks for data
        AIMessage("Sorry, I can't reach the Pokémon database right now."),  # model explains the failure
    ])
    graph = build_graph(model)  # graph with the scripted model
    result = await graph.ainvoke({"messages": [HumanMessage("Tell me about Pikachu")]}, run_config("err"))  # must not raise
    error_msgs = [m for m in model.prompts[1] if isinstance(m, ToolMessage)]  # what the model saw after the tool ran
    assert error_msgs and error_msgs[0].status == "error" and "PokeAPI" in error_msgs[0].content  # error became a message
    assert "can't reach" in result["messages"][-1].content  # user gets an explanation


async def test_falls_back_to_backup_model_when_main_fails():
    main_model = FakeChatModel(script=[])  # empty script makes it raise, like a quota error
    backup = FakeChatModel(script=[AIMessage("from the backup model")])  # works fine
    graph = build_graph(main_model, fallbacks=[backup])  # main first, backup second
    result = await graph.ainvoke({"messages": [HumanMessage("hi")]}, run_config("fb"))  # must not raise
    assert result["messages"][-1].content == "from the backup model"  # backup answered
