# Writes the reasoning text that goes into the audit log.
# If an Anthropic API key is set, Claude writes the text.
# If not (or if anything goes wrong), a simple template sentence is used instead,
# so the project still runs without an API key.

import os


def template_text(agent, action, details):
    return (agent + " did '" + action + "' because " + details + ".")


def explain(agent, action, details):
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if api_key is None:
        return template_text(agent, action, details)

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        prompt = ("You are writing one line for a maintenance audit log. In one or two plain sentences, "
                  "explain why the " + agent + " did this action: " + action +
                  ". Facts: " + details + ". Do not add any facts that are not given.")
        reply = client.messages.create(
            model="claude-haiku-5-5",
            max_tokens=120,
            messages=[{"role": "user", "content": prompt}],
        )
        return reply.content[0].text
    except Exception as error:
        print("Claude could not write the text, using the template. Error:", error)
        return template_text(agent, action, details)
