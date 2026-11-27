_order_id = {"order_id": {"type": "integer", "description": "The order number, e.g. 1001"}}

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "list_my_orders",
            "description": "List all of the signed-in customer's orders when they ask to see, list, or review their orders or order history. Takes no arguments.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
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
            "description": "Request cancellation of ONE order (and a refund). If the customer names several orders, call this once per order. "
                           "The system asks the customer to confirm and carries out the cancellation itself.",
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
            "description": "Create a ticket for a human agent. Use it right away for: a request for a human or manager, complaints, "
                           "duplicate or wrong charges, damaged/missing/wrong items or replacement requests, hacked accounts, "
                           "escalation requests, or anything the other tools cannot solve.",
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
