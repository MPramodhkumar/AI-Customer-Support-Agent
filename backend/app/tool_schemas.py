_order_id = {"order_id": {"type": "integer", "description": "The order number, e.g. 1001"}}

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "get_order_status",
            "description": "Get the current status, item and expected delivery date of the customer's order.",
            "parameters": {"type": "object", "properties": _order_id, "required": ["order_id"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "cancel_order",
            "description": "Cancel the customer's order and start a refund. Only call after the customer explicitly confirmed.",
            "parameters": {"type": "object", "properties": _order_id, "required": ["order_id"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_refund_status",
            "description": "Check the refund status for an order.",
            "parameters": {"type": "object", "properties": _order_id, "required": ["order_id"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_support_ticket",
            "description": "Create a ticket for a human agent when the issue can't be solved with other tools, "
                           "the customer asks for a human, or the customer is upset.",
            "parameters": {
                "type": "object",
                "properties": {
                    "subject": {"type": "string", "description": "Short summary of the issue"},
                    "description": {"type": "string", "description": "Full details, including order numbers"},
                    "priority": {"type": "string", "enum": ["low", "medium", "high"]},
                },
                "required": ["subject", "description"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_knowledge_base",
            "description": "Search company FAQs and policies: returns, shipping, cancellation, refunds.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string", "description": "What the customer wants to know"}},
                "required": ["query"],
            },
        },
    },
]