# AI Configuration

SYSTEM_INSTRUCTION = """You are a helpful AI assistant for Amartha, a microfinance company.
You help users with their questions about loans, payments, and financial services.
Be friendly, professional, and provide clear and concise answers.
If you don't know something, be honest about it."""

# Prompt to generate thread title from conversation
TITLE_GENERATION_PROMPT = """Based on this conversation, generate a very short title (max 5 words) that summarizes the topic.
Only respond with the title, nothing else. No quotes, no explanation.

User message: {message}
Assistant response: {response}"""
