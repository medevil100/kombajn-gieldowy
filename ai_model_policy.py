"""Single production contract for paid OpenAI calls made by KI."""

MODEL = 'gpt-6-luna'
REASONING_EFFORT = 'none'
FULL_MAX_TOKENS = 6600
MAX_AUTOMATIC_CALLS_DAY = 48

# Standard short-context prices per one million tokens, checked 2026-11-25.
# These constants are estimates for local reservations, not an invoice.
INPUT_USD_PER_MILLION = 0.10
OUTPUT_USD_PER_MILLION = 0.50


def chat_parameters():
    """Parameters shared by Chat Completions requests using Structured Outputs."""
    return {'model': MODEL, 'reasoning_effort': REASONING_EFFORT}
