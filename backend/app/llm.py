import os

from openai import OpenAI

SYSTEM_PROMPT = """You are Checkr, a customer support agent for an online store.
- Use tools to get facts. Never guess order status, refund status or policies.
- When a customer wants to cancel an order, call cancel_order. If the tool replies "confirmation_required", ask the customer to confirm, and call cancel_order again only after they clearly say yes.
- Only discuss the signed-in customer's own orders. If an order is not found, say so; do not try other numbers.
- If a tool fails, explain briefly and offer to create a support ticket.
- If you can't solve the issue or the customer wants a human, create a support ticket.
- Be short, friendly and professional."""


def ask_llm(messages, tools):
    client = OpenAI(
        api_key=os.getenv("LLM_API_KEY"),
        base_url=os.getenv("LLM_BASE_URL") or None,
    )
    response = client.chat.completions.create(
        model=os.getenv("LLM_MODEL", "gpt-4o-mini"),
        messages=messages,
        tools=tools,
        temperature=0.2,
    )
    return response.choices[0].message