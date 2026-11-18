"""Structured output via a single tool. Some models reject a forced tool_choice, so we ask with
tool_choice auto, instruct the model to call the tool, and retry once if it answers in text."""


def call_tool(client, *, tool, messages, **kw):
    name = tool["name"]
    msgs = list(messages)
    for _ in range(2):
        msg = client.messages.create(tools=[tool], tool_choice={"type": "auto"}, messages=msgs, **kw)
        for b in msg.content:
            if b.type == "tool_use" and b.name == name:
                return b.input
        msgs = msgs + [{"role": "assistant", "content": msg.content},
                       {"role": "user", "content": f"Respond only by calling the {name} tool with the complete data."}]
    raise RuntimeError(f"Model did not return the {name} tool")
