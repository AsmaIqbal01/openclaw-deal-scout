def format_embed(deal: dict) -> dict:
    """Build a Discord webhook embed payload from a deal state store entry.

    Applies pre-send truncation so the HTTP POST never triggers a 400 from Discord.
    Title is capped at 256 chars (Discord's hard limit). Subject > 256 → first 253 + '...'.
    """
    subject = deal.get("subject") or ""
    title = subject if len(subject) <= 256 else subject[:253] + "..."

    summary = deal.get("deal_summary") or ""
    description = summary if summary else "(no summary)"

    sender_name = deal.get("sender_name")
    sender_email = deal.get("sender_email") or ""
    from_value = f"{sender_name} <{sender_email}>" if sender_name else sender_email

    category = deal.get("deal_category") or ""
    score = deal.get("confidence_score") or 0.0
    confidence = f"{round(score * 100)}%"

    return {
        "embeds": [
            {
                "title": title,
                "description": description,
                "fields": [
                    {"name": "From", "value": from_value, "inline": True},
                    {"name": "Category", "value": category, "inline": True},
                    {"name": "Confidence", "value": confidence, "inline": True},
                ],
            }
        ]
    }
