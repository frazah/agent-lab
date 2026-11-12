import anthropic
from dotenv import load_dotenv
import os

load_dotenv()

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

response = client.messages.create(
    model="claude-haiku-5-5",
    max_tokens=50,
    output_config={"effort": "low"},
    messages=[{"role": "user", "content": "ciao"}],
)

print(response.model_dump_json(indent=2))

print("\n--- campi principali ---")
print("type:       ", response.type)
print("role:       ", response.role)
print("model:      ", response.model)
print("stop_reason:", response.stop_reason)
print("usage:      ", response.usage.input_tokens, "in /", response.usage.output_tokens, "out")

print("\n--- content (lista di blocchi) ---")
for i, block in enumerate(response.content):
    print(f"[{i}] type={block.type!r}")
    if block.type == "text":
        print("    text:", block.text)
